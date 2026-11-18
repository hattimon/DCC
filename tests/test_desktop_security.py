import hashlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import DockerControlCenter as dcc


class DesktopSecurityTests(unittest.TestCase):
    def test_key_passphrase_is_not_an_ssh_login_password(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / 'key'
            key.touch()
            profile = dcc.RemoteProfile(name='Fixture', mode='ssh', ssh_target='user@fixture.invalid',
                                        ssh_auth_mode='key_password', ssh_key_path=str(key),
                                        ssh_passphrase='fixture-key-passphrase')
            with patch.object(dcc, 'USER_DATA_DIR', Path(folder)), patch.object(dcc.paramiko, 'SSHClient') as client:
                dcc.SshDockerClient(profile)._ensure_client()
            options = client.return_value.connect.call_args.kwargs
            self.assertNotIn('password', options)
            self.assertEqual(options['passphrase'], 'fixture-key-passphrase')

    def test_first_ssh_host_key_is_persisted_and_a_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ssh_known_hosts'
            host = '[fixture.invalid]:22222'
            first = dcc.paramiko.ECDSAKey.generate()
            change = dcc.paramiko.ECDSAKey.generate()
            dcc.RememberSshHostKey(path).missing_host_key(None, host, first)
            self.assertEqual(dcc.paramiko.HostKeys(str(path)).lookup(host)[first.get_name()], first)
            with self.assertRaises(dcc.paramiko.SSHException):
                dcc.RememberSshHostKey(path).missing_host_key(None, host, change)
            self.assertEqual(dcc.paramiko.HostKeys(str(path)).lookup(host)[first.get_name()], first)

    @unittest.skipUnless(os.name == 'posix', 'POSIX file permissions')
    def test_existing_and_new_secret_store_files_are_owner_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'secrets.json'
            path.write_text('{"secrets":{"fixture":"dGVzdA=="}}', encoding='utf-8')
            path.chmod(0o644)
            store = dcc.SecretStore(path)
            self.assertEqual(store.get_secret('fixture'), 'test')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            store.set_secret('new', 'synthetic')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_update_download_never_exposes_a_package_with_an_invalid_digest(self):
        class Response(io.BytesIO):
            def geturl(self):
                return 'https://github.com/test/fixture'

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'DockerControlCenter.deb'
            data = b'synthetic-test-package'
            digest = 'sha256:' + hashlib.sha256(data).hexdigest()
            for response, expected in ((b'modified-package', False), (data, True)):
                with self.subTest(valid=expected), patch.object(dcc, 'urlopen', return_value=Response(response)):
                    worker = dcc.UpdateDownloadWorker('https://github.com/test/fixture', str(path), digest=digest)
                    result = []
                    worker.finished.connect(lambda *args: result.append(args))
                    worker.run()
                    self.assertEqual(result[0][0], expected)
                    self.assertEqual(path.exists(), expected)
                    self.assertFalse(path.with_suffix('.deb.part').exists())
