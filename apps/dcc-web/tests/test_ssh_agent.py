"""Real agent signing and verified SSH handshake, using disposable test keys only."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from profile_ssh import configure_client, connection_options


@unittest.skipUnless(os.name != 'nt' and shutil.which('ssh-agent') and shutil.which('ssh-add'), 'Unix OpenSSH agent required')
class AgentHandshakeTests(unittest.TestCase):
    def test_encrypted_key_is_unlocked_in_agent_not_in_web_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = paramiko.RSAKey.generate(2048)
            identity = root/'identity.pem'
            key.write_private_key_file(str(identity), password='test-only-passphrase')
            identity.chmod(0o600)
            askpass = root/'askpass'
            askpass.write_text('#!/bin/sh\nprintf "%s" test-only-passphrase\n')
            askpass.chmod(0o700)
            sock = str(root/'agent.sock')
            env = dict(os.environ, SSH_AUTH_SOCK=sock, SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE='force', DISPLAY=':test')
            agent = subprocess.Popen(['ssh-agent','-D','-a',sock], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(agent.wait, timeout=5)
            self.addCleanup(agent.terminate)
            import time
            for _ in range(100):
                if Path(sock).exists(): break
                time.sleep(.02)
            subprocess.run(['ssh-add',str(identity)], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=10)
            listener = socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen(1); listener.settimeout(15)
            self.addCleanup(listener.close)
            host_key = paramiko.RSAKey.generate(2048)
            known = root/'known_hosts'
            known.write_text(f'[127.0.0.1]:{listener.getsockname()[1]} {host_key.get_name()} {host_key.get_base64()}\n')

            class Server(paramiko.ServerInterface):
                def get_allowed_auths(self, username): return 'publickey'
                def check_auth_publickey(self, username, offered):
                    return paramiko.AUTH_SUCCESSFUL if username == 'fixture' and offered == key else paramiko.AUTH_FAILED

            transports = []
            def serve():
                conn, _ = listener.accept()
                transport = paramiko.Transport(conn); transports.append(transport)
                transport.add_server_key(host_key); transport.start_server(server=Server())
                transport.accept(timeout=3)
            thread = threading.Thread(target=serve,daemon=True); thread.start()
            profile = dict(host='127.0.0.1',port=listener.getsockname()[1],username='fixture',ssh_auth='agent',
                           key_path='C:/not/in/container/key',known_hosts_path=str(known),credentials={})
            client = paramiko.SSHClient()
            try:
                configure_client(client,profile)
                with patch.dict(os.environ,env):
                    client.connect(**connection_options(profile))
                self.assertTrue(client.get_transport().is_authenticated())
            finally:
                client.close()
                for transport in transports: transport.close()
                thread.join(timeout=5)
