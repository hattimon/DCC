"""Shared SSH directories and bulk profile changes use explicit, scoped consent."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
import paramiko
from web import create_app
from profile_ssh import inspect_file, safe_name, configure_client, MAX_FILE
from fixtures import FakeBackend


class ProfileSSHTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = paramiko.RSAKey.generate(1024)  # Disposable fixture, never used on a host.
        output = io.StringIO()
        cls.key.write_private_key(output)
        cls.private = output.getvalue().encode()
        cls.known = ('fixture.invalid '+cls.key.get_name()+' '+cls.key.get_base64()+'\n').encode()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.temp.name, 'MASTER_KEY': Fernet.generate_key()}, backend_factory=FakeBackend)
        self.state = self.app.extensions['dcc_state']
        FakeBackend.commands = []
        self.client = self.app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
        result = self.client.post('/setup', data={'username': 'fixture-admin', 'password': 'Profile-fixture-pass-4477', 'csrf': self.csrf})
        self.assertEqual(result.status_code, 302)
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
        for ident, name in [('a', 'Selected SSH'), ('b', 'Individual SSH')]:
            self.state.save_profile(ident, {'name': name, 'kind': 'ssh', 'host': 'fixture.invalid', 'username': 'fixture', 'key_path': 'C:/Users/fixture/.ssh/id_ed25519', 'permissions': ['read'], 'users': ['some-user']}, {'passphrase': 'dummy-encrypted-secret'})

    def request(self, path, value=None, method='POST', client=None, csrf=None):
        return (client or self.client).open('/api/'+path, method=method, json=value or {}, headers={'X-CSRF-Token': csrf or self.csrf})

    def token(self, action, target):
        result = self.request('confirmations', {'action': action, 'target': target})
        self.assertEqual(result.status_code, 200, result.json)
        return result.json['confirmation']

    def upload(self, files, preview=True, token='', replace=False, csrf=True):
        return self.client.post('/api/profile-ssh/files'+('/preview' if preview else ''), data={'files': [(io.BytesIO(content), name) for name, content in files], 'replace': str(replace).lower(), 'confirmation': token}, headers={'X-CSRF-Token': self.csrf} if csrf else {})

    def test_selected_profiles_migrate_basename_without_changing_others_or_credentials(self):
        original = self.state.profile('b', private=True)
        private_blob = self.state.rows("SELECT private FROM profiles WHERE id='a'")[0]['private']
        payload = {'action': 'profiles.ssh.apply', 'ids': ['a', 'local', 'a']}
        plan = self.request('profiles/bulk/preview', payload).json
        self.assertEqual(len(plan['changes']), 1)
        self.assertEqual(len(plan['skipped']), 1)
        self.assertEqual(plan['changes'][0]['key_path'], 'id_ed25519')
        self.assertEqual(self.request('profiles/bulk', payload).status_code, 409)
        payload['confirmation'] = self.token(payload['action'], plan['target'])
        self.assertEqual(self.request('profiles/bulk', payload).status_code, 200)
        self.assertEqual(self.request('profiles/bulk', payload).status_code, 409)
        self.assertEqual(self.state.profile('b', private=True), original)
        a = self.state.profile('a', private=True)
        self.assertEqual(Path(a['key_path']), Path(self.temp.name)/'ssh'/'id_ed25519')
        self.assertEqual(a['users'], ['some-user'])
        self.assertEqual(a['credentials']['passphrase'], 'dummy-encrypted-secret')
        self.assertEqual(self.state.rows("SELECT private FROM profiles WHERE id='a'")[0]['private'], private_blob)
        self.assertEqual(self.state.profile('a')['key_path'], 'id_ed25519')

    def test_stale_profile_or_changed_selection_requires_new_confirmation(self):
        payload = {'action': 'profiles.ssh.apply', 'ids': ['a']}
        plan = self.request('profiles/bulk/preview', payload).json
        payload['confirmation'] = self.token(payload['action'], plan['target'])
        self.state.save_profile('a', {**self.state.profile('a'), 'name': 'Changed'})
        self.assertEqual(self.request('profiles/bulk', payload).status_code, 409)
        payload['ids'] = ['b']
        self.assertEqual(self.request('profiles/bulk', payload).status_code, 409)

    def test_upload_preview_is_metadata_only_and_requires_exact_files_and_confirmation(self):
        files = [('id_ed25519', self.private), ('known_hosts', self.known)]
        preview = self.upload(files)
        self.assertEqual(preview.status_code, 200, preview.json)
        self.assertNotIn('BEGIN RSA PRIVATE', preview.get_data(as_text=True))
        self.assertFalse((Path(self.temp.name)/'ssh').exists())
        self.assertEqual(self.upload(files, preview=False).status_code, 409)
        token = self.token('profiles.ssh.files', preview.json['target'])
        altered = [('other_key', self.private), ('known_hosts', self.known)]
        self.assertEqual(self.upload(altered, preview=False, token=token).status_code, 409)
        result = self.upload(files, preview=False, token=token)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertFalse((Path(self.temp.name)/'ssh'/'id_ed25519').exists())
        self.assertEqual(self.state.vault.decrypt(self.state.ssh.vault_file('id_ed25519')['private']),self.private)
        self.assertNotIn('BEGIN RSA PRIVATE', self.client.get('/api/profiles/export').get_data(as_text=True))
        self.assertNotIn('BEGIN RSA PRIVATE', json.dumps(self.state.rows('SELECT * FROM audit')))
        if os.name != 'nt':
            self.assertEqual((Path(self.temp.name)/'ssh').stat().st_mode & 0o777, 0o700)
            self.assertEqual((Path(self.temp.name)/'ssh'/'known_hosts').stat().st_mode & 0o777, 0o600)

    def test_overwrite_requires_separate_opt_in_and_changed_existing_file_invalidates_token(self):
        files = [('known_hosts', self.known)]
        plan = self.upload(files).json
        self.upload(files, preview=False, token=self.token('profiles.ssh.files', plan['target']))
        self.assertEqual(self.upload(files).status_code, 400)
        plan = self.upload(files, replace=True).json
        self.assertTrue(plan['files'][0]['replacing'])
        token = self.token('profiles.ssh.files', plan['target'])
        (Path(self.temp.name)/'ssh'/'known_hosts').write_bytes(b'# changed\n'+self.known)
        self.assertEqual(self.upload(files, preview=False, token=token, replace=True).status_code, 409)

    def test_reject_traversal_invalid_content_and_oversize(self):
        for name in ['../key', 'C:\\key', 'sub/key', '.ssh', 'NUL', 'COM1.txt', 'key.', 'key:ads']:
            with self.subTest(name=name):
                self.assertEqual(self.upload([(name, self.private)]).status_code, 400)
        for name, content in [('config', b'ProxyCommand run-anything'), ('known_hosts', b'invalid'), ('id_key', b'x'*(MAX_FILE+1))]:
            self.assertEqual(self.upload([(name, content)]).status_code, 400)
        self.assertEqual(self.upload([('known_hosts', self.known), ('KNOWN_HOSTS', self.known)]).status_code, 400)

    def test_symlink_destinations_and_roots_rejected(self):
        root = Path(self.temp.name)/'ssh'
        root.mkdir()
        outside = Path(self.temp.name)/'external'
        outside.write_bytes(b'preserve')
        try:
            (root/'known_hosts').symlink_to(outside)
        except OSError:
            self.skipTest('OS does not permit creation of test symlinks')
        self.assertEqual(self.upload([('known_hosts', self.known)]).status_code, 400)
        self.assertEqual(outside.read_bytes(), b'preserve')
        (root/'known_hosts').unlink()
        root.rmdir()
        root.symlink_to(Path(self.temp.name), target_is_directory=True)
        self.assertEqual(self.upload([('known_hosts', self.known)]).status_code, 400)

    def test_external_directory_is_read_only_and_only_opted_in_profiles_follow_changes(self):
        root = Path(self.temp.name)/'mounted'
        root.mkdir()
        self.state.save_profile('a', {**self.state.profile('a'), 'key_scope': 'shared', 'key_path': 'id_key'})
        plan = self.request('profile-ssh/directory/preview', {'directory': str(root)}).json
        self.assertEqual([v['id'] for v in plan['profiles']], ['a'])
        result = self.request('profile-ssh/directory', {'directory': str(root), 'confirmation': self.token('profiles.ssh.directory', plan['target'])}, method='PUT')
        self.assertEqual(result.status_code, 200)
        self.assertFalse(self.client.get('/api/profile-ssh').json['uploads_allowed'])
        self.assertEqual(Path(self.state.profile('a', private=True)['key_path']), root/'id_key')
        self.assertEqual(self.state.profile('b')['key_path'], 'C:/Users/fixture/.ssh/id_ed25519')
        self.assertEqual(self.upload([('known_hosts', self.known)]).status_code, 400)
        self.assertEqual(self.request('profile-ssh/directory/preview', {'directory': 'C:/not-in-container'}).status_code, 400)

    def test_bulk_delete_all_preserves_files_and_closes_sessions_without_active_profile(self):
        root = Path(self.temp.name)/'ssh'
        root.mkdir(); (root/'known_hosts').write_bytes(self.known)
        payload = {'action': 'profiles.remove.selected', 'ids': [p['id'] for p in self.state.profiles()]}
        plan = self.request('profiles/bulk/preview', payload).json
        payload['confirmation'] = self.token(payload['action'], plan['target'])
        with patch.object(self.app.extensions['dcc_terminals'], 'close_profiles') as close:
            self.assertEqual(self.request('profiles/bulk', payload).status_code, 200)
            close.assert_called_once_with(set(payload['ids']))
        self.assertEqual(self.state.profiles(), [])
        self.assertTrue((root/'known_hosts').exists())
        # Workspace confirmations do not depend on a deleted active profile.
        self.assertEqual(self.request('confirmations', {'action': 'profiles.ssh.directory', 'target': 'new'}).status_code, 200)
        self.assertEqual(FakeBackend.commands, [])

    def test_admin_csrf_and_session_scoping(self):
        self.assertEqual(self.upload([('known_hosts', self.known)], csrf=False).status_code, 403)
        user = self.state.rows('SELECT id FROM users')[0]['id']
        self.state.execute("UPDATE users SET role='viewer' WHERE id=?", (user,))
        self.assertEqual(self.client.get('/api/profile-ssh').status_code, 403)
        self.assertEqual(self.request('profiles/bulk/preview', {'action': 'profiles.ssh.apply', 'ids': ['a']}).status_code, 403)
        self.assertEqual(self.upload([('known_hosts', self.known)]).status_code, 403)
        self.assertEqual(self.request('confirmations', {'action': 'profiles.ssh.files', 'target': 'a'}).status_code, 403)

    def test_individual_edits_keep_shared_basename_and_legacy_paths_unchanged(self):
        self.state.save_profile('a', {**self.state.profile('a'), 'key_scope': 'shared', 'key_path': 'id_key'})
        self.assertEqual(self.request('profiles/a', {'name': 'Edited'}, method='PUT').status_code, 200)
        self.assertEqual(self.state.profile('a')['key_path'], 'id_key')
        self.assertEqual(self.request('profiles/a', {'key_path': '../escape'}, method='PUT').status_code, 400)
        self.assertEqual(self.request('profiles/a', {'key_scope': 'individual', 'key_path': '/mounted/key'}, method='PUT').status_code, 200)
        self.assertEqual(self.state.profile('a', private=True)['key_path'], '/mounted/key')
        self.assertNotIn('key_scope', self.state.profile('b'))

    def test_known_hosts_loading_reject_policy_and_missing_files(self):
        root = Path(self.temp.name)/'ssh'; root.mkdir()
        p = {'kind': 'ssh', 'key_scope': 'shared', 'key_path': str(root/'key'), 'known_hosts_path': str(root/'known_hosts')}
        client = MagicMock()
        with self.assertRaisesRegex(ValueError, 'known_hosts'):
            configure_client(client, p)
        (root/'known_hosts').write_bytes(self.known)
        with self.assertRaisesRegex(ValueError, 'key is missing'):
            configure_client(client, p)
        (root/'key').write_bytes(self.private)
        configure_client(client, p)
        client.load_system_host_keys.assert_any_call(str(root/'known_hosts'))
        self.assertIsInstance(client.set_missing_host_key_policy.call_args.args[0], paramiko.RejectPolicy)
        real = paramiko.SSHClient()
        configure_client(real, p)
        self.assertIsNotNone(real._system_host_keys.lookup('fixture.invalid'))
        real.close()

    def test_confirmation_cannot_be_used_from_another_login_session(self):
        payload = {'action': 'profiles.ssh.apply', 'ids': ['a']}
        plan = self.request('profiles/bulk/preview', payload).json
        payload['confirmation'] = self.token(payload['action'], plan['target'])
        other = self.app.test_client()
        other.get('/login')
        with other.session_transaction() as session:
            csrf = session['csrf']
        other.post('/login', data={'username': 'fixture-admin', 'password': 'Profile-fixture-pass-4477', 'csrf': csrf})
        with other.session_transaction() as session:
            csrf = session['csrf']
        self.assertEqual(self.request('profiles/bulk', payload, client=other, csrf=csrf).status_code, 409)
        self.assertEqual(self.request('profiles/bulk', payload).status_code, 200)

    def test_private_key_public_key_and_host_fingerprints(self):
        self.assertEqual(inspect_file('id_key', self.private)['kind'], 'private key')
        self.assertEqual(inspect_file('id_key.pub', (self.key.get_name()+' '+self.key.get_base64()).encode())['kind'], 'public key')
        self.assertTrue(inspect_file('known_hosts', self.known)['fingerprints'][0].startswith('SHA256:'))
        output = io.StringIO(); self.key.write_private_key(output, password='fixture-only-passphrase')
        self.assertEqual(inspect_file('id_encrypted', output.getvalue().encode())['kind'], 'private key')

    def test_key_content_overrides_extension_and_encryption_is_reported(self):
        for name in ('sensecap_root', 'host-key.pem', 'host.key', 'wrong.pub'):
            self.assertEqual(inspect_file(name, self.private)['kind'], 'private key')
        public = (self.key.get_name()+' '+self.key.get_base64()).encode()
        self.assertEqual(inspect_file('public_without_extension', public)['kind'], 'public key')
        output = io.StringIO(); self.key.write_private_key(output, password='fixture-passphrase')
        self.assertTrue(inspect_file('locked.pem', output.getvalue().encode())['encrypted'])

    def test_import_windows_profile_can_explicitly_match_uploaded_private_key(self):
        root = Path(self.temp.name)/'ssh'; root.mkdir()
        (root/'id_ed25519').write_bytes(self.private)
        result = self.request('profiles/import', {'profiles': [{'name':'Windows import', 'mode':'ssh', 'ssh_target':'fixture@fixture.invalid', 'ssh_key_path':r'C:\Users\fixture\.ssh\id_ed25519', 'ssh_passphrase':'must-not-import'}], 'shared_keys':True})
        self.assertEqual(result.status_code,200,result.json)
        p = self.state.profile(result.json['added'][0],private=True)
        self.assertEqual(Path(p['key_path']),root/'id_ed25519')
        self.assertEqual(p['key_scope'],'shared')
        self.assertNotIn('passphrase',p['credentials'])
        self.assertEqual(p['credentials']['private_key'].encode(),self.private)
        self.assertEqual(p['permissions'],['read'])

    def test_agent_is_explicit_and_does_not_require_the_imported_windows_key_path(self):
        from profile_ssh import connection_options
        p = self.state.profile('a'); p['ssh_auth']='agent'
        with patch('profile_ssh.agent_status',return_value={'available':True,'keys':1}):
            options = connection_options(p)
        self.assertIsNone(options['key_filename'])
        self.assertIsNone(options['passphrase'])
        self.assertTrue(options['allow_agent'])
        self.assertFalse(options['look_for_keys'])
        with patch('profile_ssh.agent_status',return_value={'available':False,'keys':0}), self.assertRaisesRegex(ValueError,'agent is unavailable'):
            connection_options(p)

    def test_pkcs8_encrypted_key_requires_passphrase_and_is_parsed_in_memory(self):
        from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, BestAvailableEncryption
        from profile_ssh import connection_options
        content=self.key.key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,BestAvailableEncryption(b'fixture-pass'))
        path=Path(self.temp.name)/'key.pem';path.write_bytes(content)
        self.assertTrue(inspect_file(path.name,content)['encrypted'])
        p=dict(self.state.profile('a'),key_path=str(path),ssh_auth='key')
        with self.assertRaisesRegex(ValueError,'valid passphrase'):
            connection_options(p)
        options=connection_options(dict(p,credentials={'passphrase':'fixture-pass'}))
        self.assertIsNotNone(options['pkey'])
        self.assertIsNone(options['key_filename'])

if __name__ == '__main__':
    unittest.main()
