"""MCP elevation, preserved tokens and live host/session authorization."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
from mcp_preview import MCPService, TERMINAL_TOOLS, stdio
from mcp_host import SSHCommand, MAX_OUTPUT
from security import CAPABILITIES
from web import create_app
from fixtures import FakeBackend
import profile_facts


class FakePTY:
    def __init__(self, profile, cols, rows):
        self.input, self.queue, self.closed = [], queue.Queue(), False
        self.size = (cols, rows)
    def read(self): return self.queue.get()
    def write(self, raw): self.input.append(raw)
    def resize(self, cols, rows): self.size = (cols, rows)
    def close(self):
        self.closed = True
        self.queue.put(b'')


class FakeCommand:
    def __init__(self, profile): self.closed = False
    def run(self, command, timeout, authorize):
        authorize()
        return {"stdout": "Linux\n", "stderr": "", "exit_code": 0, "timed_out": False, "truncated": False}
    def close(self): self.closed = True


class MCPHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({"TESTING": True, "DATA_DIR": self.temp.name, "MASTER_KEY": Fernet.generate_key()}, backend_factory=FakeBackend)
        self.state = self.app.extensions['dcc_state']
        self.client = self.app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as session: self.csrf = session['csrf']
        self.client.post('/setup', data={'username': 'mcp-admin', 'password': 'Mcp-Test-Password-1348', 'csrf': self.csrf})
        with self.client.session_transaction() as session: self.csrf = session['csrf']
        for ident, kind in [('local', 'local'), ('ssh-one', 'ssh'), ('ssh-two', 'balena')]:
            self.state.save_profile(ident, {'name': ident, 'kind': kind, 'host': '192.0.2.1', 'username': 'qa', 'permissions': sorted(CAPABILITIES)})

    def request(self, path, data, method='POST'):
        return self.client.open('/api/'+path, method=method, json=data, headers={'X-CSRF-Token': self.csrf})

    def payload(self, **changes):
        return dict({'name': 'host grant', 'client': 'OpenAI Codex', 'mode': 'write', 'profiles': ['local', 'ssh-one', 'ssh-two'],
            'tools': ['list_containers', *TERMINAL_TOOLS], 'allow_host_terminal': True, 'terminal_profiles': ['ssh-one', 'ssh-two'],
            'current_password': 'Mcp-Test-Password-1348'}, **changes)

    def grant(self, **changes):
        response = self.request('mcp/grants', self.payload(**changes))
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def service(self, grant, command_factory=FakeCommand):
        value = MCPService(self.state, grant['token'], FakeBackend, FakePTY, command_factory)
        self.addCleanup(value.close)
        return value

    def call(self, service, name, profile='ssh-one', **arguments):
        return json.loads(service.call(name, {'profile': profile, **arguments})['content'][0]['text'])

    def test_edit_keeps_active_token_hash_expiry_and_other_grants(self):
        first = self.grant(tools=['list_containers', 'container_start'], allow_host_terminal=False, terminal_profiles=[])
        other = self.grant()
        before = dict(self.state.rows('SELECT * FROM grants WHERE id=?', (first['id'],))[0])
        other_before = dict(self.state.rows('SELECT * FROM grants WHERE id=?', (other['id'],))[0])
        old_service = self.service(first)
        with self.assertRaises(PermissionError): self.call(old_service, 'host_exec', command='uname')
        response = self.request('mcp/grants/'+first['id'], self.payload(), 'PUT')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json['token_preserved'])
        self.assertNotIn('token', response.json)
        after = self.state.rows('SELECT * FROM grants WHERE id=?', (first['id'],))[0]
        self.assertEqual(after['token'], before['token'])
        for key in ('expires', 'created'): self.assertEqual(json.loads(after['data'])[key], json.loads(before['data'])[key])
        self.assertEqual(dict(self.state.rows('SELECT * FROM grants WHERE id=?', (other['id'],))[0]), other_before)
        self.assertEqual(self.call(old_service, 'host_exec', command='uname')['exit_code'], 0)

    def test_edit_reauth_revoked_paused_and_expired(self):
        grant = self.grant()
        path = 'mcp/grants/'+grant['id']
        self.assertEqual(self.request(path, self.payload(current_password='wrong'), 'PUT').status_code, 403)
        self.state.execute('UPDATE grants SET paused=1 WHERE id=?', (grant['id'],))
        self.assertEqual(self.request(path, self.payload(), 'PUT').status_code, 200)
        self.assertTrue(self.state.rows('SELECT paused FROM grants WHERE id=?', (grant['id'],))[0]['paused'])
        metadata = self.service(grant)
        with self.assertRaises(PermissionError): metadata.grant()
        self.state.execute('UPDATE grants SET paused=0 WHERE id=?', (grant['id'],))
        self.assertEqual(self.request(path, self.payload(renew_expiry=True, unlimited=True), 'PUT').status_code, 200)
        self.assertIsNone(metadata.grant()['expires'])
        self.state.execute('UPDATE grants SET revoked=1 WHERE id=?', (grant['id'],))
        self.assertEqual(self.request(path, self.payload(), 'PUT').status_code, 409)
        with self.assertRaises(PermissionError): metadata.grant()

    def test_terminal_scope_requires_explicit_write_device_and_capability(self):
        for changes in ({'mode': 'read'}, {'allow_host_terminal': False}, {'terminal_profiles': []},
                        {'terminal_profiles': ['local']}, {'terminal_profiles': ['not-granted']},
                        {'terminal_profiles': ['ssh-one', 'ssh-one']}):
            with self.subTest(changes=changes): self.assertEqual(self.request('mcp/grants', self.payload(**changes)).status_code, 400)
        profile = self.state.profile('ssh-one'); profile['permissions'] = ['read']
        self.state.save_profile('ssh-one', profile)
        self.assertEqual(self.request('mcp/grants', self.payload()).status_code, 400)

    def test_command_does_not_use_docker_backend_and_is_bounded(self):
        service = self.service(self.grant(terminal_profiles=['ssh-one']))
        with patch.object(service, 'factory', side_effect=AssertionError('Docker backend must not run')):
            self.assertEqual(self.call(service, 'host_exec', command='uname -s')['stdout'], 'Linux\n')
        for arguments in ({'command': ''}, {'command': 'x'*8193}, {'command': 'a\x00b'}, {'command': 'uname', 'timeout': 301}, {'command': 'uname', 'timeout': True}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError): self.call(service, 'host_exec', **arguments)
        with self.assertRaises(PermissionError): self.call(service, 'host_exec', profile='ssh-two', command='uname')
        with self.assertRaises(PermissionError): self.call(service, 'host_exec', profile='local', command='uname')

    def test_terminal_isolated_by_connection_grant_and_device(self):
        grant = self.grant(); service = self.service(grant)
        opened = self.call(service, 'host_terminal_open')
        terminal = opened['terminal']; session = service.terminals.get(terminal, service.digest, service.connection_id)
        for other in (self.service(grant), self.service(self.grant())):
            with self.assertRaises(KeyError): self.call(other, 'host_terminal_read', terminal=terminal)
        with self.assertRaises(PermissionError): self.call(service, 'host_terminal_read', profile='ssh-two', terminal=terminal)
        self.call(service, 'host_terminal_write', terminal=terminal, data=base64.b64encode(b'htop\r').decode())
        self.assertEqual(session.connection.input, [b'htop\r'])
        self.call(service, 'host_terminal_resize', terminal=terminal, cols=80, rows=24)
        self.assertEqual(session.connection.size, (80, 24))
        session.connection.queue.put(b'x'*80000)
        for _ in range(100):
            if session.buffer: break
            time.sleep(.002)
        output = self.call(service, 'host_terminal_read', terminal=terminal)
        self.assertEqual(len(base64.b64decode(output['data'])), 65536)
        rest = self.call(service, 'host_terminal_read', terminal=terminal, offset=output['offset'])
        self.assertEqual(len(base64.b64decode(rest['data'])), 80000-65536)
        for data in ('!', '', base64.b64encode(b'x'*16385).decode()):
            with self.assertRaises(ValueError): self.call(service, 'host_terminal_write', terminal=terminal, data=data)
        self.call(service, 'host_terminal_close', terminal=terminal)
        self.assertTrue(session.connection.closed)

    def test_idle_terminals_close_when_authority_changes(self):
        for change in ('pause', 'revoke', 'expiry', 'profile', 'edit'):
            with self.subTest(change=change):
                # Restore the profile capability removed in the previous iteration.
                profile = self.state.profile('ssh-one'); profile['permissions'] = sorted(CAPABILITIES)
                self.state.save_profile('ssh-one', profile)
                grant = self.grant(); service = self.service(grant)
                opened = self.call(service, 'host_terminal_open'); terminal = opened['terminal']
                session = service.terminals.get(terminal, service.digest, service.connection_id)
                if change in ('pause', 'revoke'):
                    self.state.execute('UPDATE grants SET '+('paused' if change=='pause' else 'revoked')+'=1 WHERE id=?', (grant['id'],))
                elif change == 'profile':
                    profile['permissions'] = ['read']; self.state.save_profile('ssh-one', profile)
                elif change == 'edit':
                    self.assertEqual(self.request('mcp/grants/'+grant['id'], self.payload(), 'PUT').status_code, 200)
                else:
                    metadata = service.grant(); metadata['expires'] = 1
                    self.state.execute('UPDATE grants SET data=? WHERE id=?', (json.dumps(metadata), grant['id']))
                for _ in range(150):
                    if session.closed: break
                    time.sleep(.01)
                self.assertTrue(session.closed, change)
                with self.assertRaises((PermissionError, KeyError, ValueError)):
                    self.call(service, 'host_terminal_write', terminal=terminal, data='eA==')

    def test_command_rechecks_authority_and_closes_connection(self):
        grant = self.grant(); runner = FakeCommand({})
        def run(command, timeout, authorize):
            self.state.execute('UPDATE grants SET paused=1 WHERE id=?', (grant['id'],))
            authorize()
        runner.run = run
        service = self.service(grant, lambda profile: runner)
        with self.assertRaises(PermissionError): self.call(service, 'host_exec', command='sleep 10')
        self.assertTrue(runner.closed)
        audit = self.state.rows("SELECT * FROM audit WHERE action='host_exec'")[-1]
        self.assertEqual(audit['result'], 403)
        self.assertNotIn('sleep', json.dumps(dict(audit)))

    def test_exports_include_only_per_device_terminal_and_cached_engine_facts(self):
        grant = self.grant(terminal_profiles=['ssh-one'])
        profile_facts.remember(self.state, self.state.profile('ssh-one'), {'OperatingSystem': 'Debian QA', 'Architecture': 'aarch64', 'password': 'do-not-export'})
        instructions = self.client.get('/api/mcp/instructions/'+grant['id']).json['content']
        self.assertIn('Debian QA', instructions)
        self.assertIn('aarch64', instructions)
        self.assertIn('ONLY through', instructions)
        self.assertIn('Do not bypass', instructions)
        self.assertIn('Host terminal access: not granted', instructions)
        self.assertNotIn('do-not-export', instructions)
        # Profile identity changes invalidate old engine facts.
        profile = self.state.profile('ssh-one'); profile['host'] = '192.0.2.2'; self.state.save_profile('ssh-one', profile)
        self.assertNotIn('Debian QA', self.client.get('/api/mcp/instructions/'+grant['id']).json['content'])
        for platform in ('windows', 'linux', 'macos'):
            with self.subTest(platform=platform), patch.dict(os.environ, {'DCC_WEB_CONTAINER_NAME':'qa-web'}), patch('docker.from_env') as docker_client, patch('host_setup.local_container') as local:
                local.return_value.name = 'qa-web'
                response = self.client.get('/api/mcp/bundle/'+grant['id']+'?platform='+platform)
                self.assertEqual(response.status_code, 200, response.json)
                with ZipFile(io.BytesIO(response.data)) as archive:
                    self.assertEqual(set(archive.namelist()), {'AGENTS.md','.codex/config.toml','README.md'})
                    guide = archive.read('README.md').decode()
                    self.assertIn('System klienta: '+platform, guide)
                    self.assertIn('Docker CLI', guide)
                    self.assertIn('DCC_MCP_TOKEN', guide)
                    self.assertNotIn('Finder/Dock', guide) if platform!='macos' else self.assertIn('Finder/Dock', guide)
                    for name in archive.namelist(): self.assertNotIn(grant['token'].encode(), archive.read(name))
        self.assertEqual(self.client.get('/api/mcp/bundle/'+grant['id']+'?platform=unknown').status_code, 400)

    def test_stdio_eof_always_closes_terminal_sessions(self):
        with patch('mcp_preview.MCPService') as factory:
            stdio(self.state, io.StringIO(''), io.StringIO())
        factory.return_value.close.assert_called_once()


class SSHCommandTests(unittest.TestCase):
    def test_strict_host_verification_and_profile_port(self):
        client = MagicMock()
        with patch('paramiko.SSHClient', return_value=client):
            runner = SSHCommand({'kind':'balena','host':'example.invalid','port':22223,'username':'qa','ssh_auth':'password'})
        self.assertEqual(type(client.set_missing_host_key_policy.call_args.args[0]).__name__, 'RejectPolicy')
        self.assertEqual(client.connect.call_args.kwargs['port'], 22223)
        runner.close(); client.close.assert_called_once()

    def test_result_nonzero_exit_stderr_truncation_and_timeout(self):
        runner = SSHCommand.__new__(SSHCommand); channel = runner.channel = MagicMock()
        channel.recv_ready.side_effect = [True, False, False]
        channel.recv.return_value = b'x'*(MAX_OUTPUT+50)
        channel.recv_stderr_ready.side_effect = [True, False, False]
        channel.recv_stderr.return_value = b'failure'
        channel.exit_status_ready.return_value = True
        channel.recv_exit_status.return_value = 7
        result = runner.run('qa-command', 5, lambda:None)
        self.assertEqual(len(result['stdout'])+len(result['stderr']), MAX_OUTPUT)
        self.assertEqual(result['exit_code'], 7); self.assertTrue(result['truncated'])
        with patch('mcp_host.time.monotonic', side_effect=[1, 3]):
            result = runner.run('qa-command', 1, lambda:None)
        self.assertTrue(result['timed_out']); self.assertIsNone(result['exit_code'])


if __name__ == '__main__': unittest.main()
