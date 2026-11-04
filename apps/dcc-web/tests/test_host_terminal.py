"""PTY session boundaries without opening host shells or remote connections."""
import base64
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import unittest
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from host_terminal import HostTerminals

class FakePTY:
    def __init__(self,profile,cols,rows):
        self.profile=profile
        self.input=[];self.dimensions=(cols,rows);self.queue=queue.Queue();self.stopped=False
    def read(self):return self.queue.get()
    def write(self,value):self.input.append(value)
    def resize(self,cols,rows):self.dimensions=(cols,rows)
    def close(self):
        if not self.stopped:self.stopped=True;self.queue.put(b'')

class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.manager=HostTerminals(FakePTY)
        self.addCleanup(self.cleanup)
    def cleanup(self):
        for session in list(self.manager.sessions.values()):session.close()
    def open(self,owner='user',login='login',profile='local',limit=16):
        return self.manager.open({'id':profile,'kind':'local'},owner,login,120,32,limit=limit)

    def test_close_deleted_profiles_preserves_other_hosts_and_owners(self):
        selected = self.open(profile='deleted')
        other_owner = self.open(owner='another', profile='deleted')
        retained = self.open(profile='retained')
        self.manager.close_profiles({'deleted'})
        self.assertTrue(selected.closed)
        self.assertTrue(other_owner.closed)
        self.assertNotIn(selected.id, self.manager.sessions)
        self.assertIn(retained.id, self.manager.sessions)
        self.assertFalse(retained.closed)

    def test_sixteen_sessions_and_configurable_limit(self):
        sessions=[self.open() for _ in range(16)]
        with self.assertRaisesRegex(ValueError,r'limit \(16\)'):self.open()
        self.manager.close(sessions[0].id,'user','login')
        self.assertIsNotNone(self.open())
        self.assertIsNotNone(self.open(owner='other'))
        with self.assertRaises(ValueError):self.open(limit=2)

    def test_owner_login_and_profile_are_independent(self):
        first=self.open(profile='first');second=self.open(profile='second')
        with self.assertRaises(KeyError):self.manager.get(first.id,'other','login')
        with self.assertRaises(KeyError):self.manager.get(first.id,'user','other-login')
        self.assertEqual(self.manager.get(first.id,'user','login').profile,'first')
        first.connection.write(b'first command\r')
        self.assertEqual(second.connection.input,[])
        self.manager.close(first.id,'user','login')
        self.assertFalse(second.closed)

    def test_completed_shell_does_not_consume_session_limit(self):
        first=self.open(limit=1);first.connection.close()
        for _ in range(100):
            if first.closed:break
            time.sleep(.001)
        self.assertTrue(first.closed)
        self.assertIsNotNone(self.open(limit=1))

    def test_output_is_bounded_and_reports_truncation(self):
        session=self.open();session.connection.queue.put(b'x'*1_000_020)
        for _ in range(100):
            with session.condition:ready=session.offset>0
            if ready:break
            time.sleep(.001)
        output=session.output(0,wait=0)
        self.assertTrue(output['truncated'])
        self.assertEqual(len(base64.b64decode(output['data'])),1_000_000)
        self.assertEqual(output['offset'],1_000_020)
        with self.assertRaises(ValueError):session.output(2_000_000,wait=0)

    def test_containerized_local_docker_profile_never_claims_to_open_the_host_shell(self):
        from host_terminal import PTYConnection
        with patch.dict(os.environ, {'DCC_WEB_CONTAINER_NAME':'dcc-web'}):
            with self.assertRaisesRegex(ValueError, 'Create or select an SSH profile for this same Docker host'):
                PTYConnection({'kind':'local'})

class TerminalTransportTests(unittest.TestCase):
    def setUp(self):
        from cryptography.fernet import Fernet
        from web import create_app
        from fixtures import FakeBackend
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app=create_app({'TESTING':True,'DATA_DIR':self.temp.name,'MASTER_KEY':Fernet.generate_key(),
            'ALLOWED_HOSTS':{'localhost','127.0.0.1','::1','192.168.11.20','dcc.example.invalid'}},
            backend_factory=FakeBackend,terminal_factory=FakePTY)
        self.manager=self.app.extensions['dcc_terminals']
        self.addCleanup(lambda:[s.close() for s in list(self.manager.sessions.values())])
        self.client=self.app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as session:csrf=session['csrf']
        response=self.client.post('/setup',data={'username':'fixture-admin','password':'Fixture-terminal-password-44','csrf':csrf})
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as session:self.csrf=session['csrf']
        self.state=self.app.extensions['dcc_state']
        self.state.save_profile('ssh',{'name':'Fixture SSH','kind':'ssh','host':'192.168.11.20',
            'username':'fixture','permissions':['read','host.exec']})

    def open(self,base='http://localhost',origin=True,remote='172.17.0.1',confirmation=True,extra_headers=None,csrf=True):
        hostname=urlsplit(base).hostname
        cookie=self.client.get_cookie('dcc_web_session')
        if hostname!='localhost':
            self.client.set_cookie('dcc_web_session',cookie.value,domain=hostname)
        data={'profile':'ssh'}
        if confirmation:
            response=self.client.post('/api/confirmations',json={'action':'host.terminal','target':'ssh','profile':'ssh'},
                headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(response.status_code,200,response.json)
            data['confirmation']=response.json['confirmation']
        headers={'X-CSRF-Token':self.csrf} if csrf else {}
        if origin:
            headers['Origin']=base if origin is True else origin
        headers.update(extra_headers or {})
        return self.client.post('/api/host-terminal',base_url=base,json=data,headers=headers,
            environ_overrides={'REMOTE_ADDR':remote})

    def test_loopback_http_works_through_docker_bridge_for_selected_ssh_profile(self):
        for base in ('http://localhost:8789','http://127.0.0.1:8789','http://[::1]:8789'):
            with self.subTest(base=base):
                response=self.open(base)
                self.assertEqual(response.status_code,201,response.json)
                self.assertEqual(response.json['address'],'192.168.11.20:22')
                terminal=self.manager.sessions[response.json['id']]
                self.assertEqual(terminal.profile,'ssh')
                self.assertEqual(terminal.connection.profile['host'],'192.168.11.20')

    def test_balena_terminal_formats_ipv6_address_and_custom_port(self):
        self.state.save_profile('ssh',{'name':'Fixture Balena','kind':'balena','host':'2001:db8::14',
            'port':22222,'username':'fixture','permissions':['read','host.exec']})
        response=self.open()
        self.assertEqual(response.status_code,201,response.json)
        self.assertEqual(response.json['address'],'[2001:db8::14]:22222')

    def test_loopback_requires_matching_origin_and_csrf(self):
        for origin in (False,'http://evil.invalid','http://localhost:9999'):
            with self.subTest(origin=origin):
                self.assertEqual(self.open(origin=origin).status_code,403)
        self.assertEqual(self.open(csrf=False).status_code,403)
        self.assertFalse(self.manager.sessions)

    def test_other_devices_require_https_and_ignore_untrusted_forwarding_headers(self):
        for base in ('http://192.168.11.20:8789','http://dcc.example.invalid'):
            with self.subTest(base=base):
                self.assertEqual(self.open(base,extra_headers={'X-Forwarded-Proto':'https'}).status_code,403)
        self.assertFalse(self.manager.sessions)
        response=self.open('https://dcc.example.invalid')
        self.assertEqual(response.status_code,201,response.json)

    def test_host_permission_and_explicit_confirmation_are_still_required(self):
        self.assertEqual(self.open(confirmation=False).status_code,409)
        self.state.save_profile('ssh',{'name':'Read-only SSH','kind':'ssh','host':'192.168.11.20',
            'username':'fixture','permissions':['read']})
        response=self.open()
        self.assertEqual(response.status_code,403,response.json)
        self.assertIn('host.exec',response.json['error'])
        self.assertFalse(self.manager.sessions)


if __name__=='__main__':unittest.main()
