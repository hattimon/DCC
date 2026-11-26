"""Real OpenSSH and engine test, restricted to disposable GitHub runners."""
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

from backend.kiri_client import Connector, KiriError


def run(*args, **kwargs):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{args[0]} exited with status {result.returncode}')
    return result.stdout.strip()


def verify_engine(kind, socket_path, port, user, password, key, passphrase, directory):
    engine = ('sudo', '-n', 'docker', '--host', 'unix://' + socket_path)
    host_key = directory / ('host-' + kind)
    wrong_key = directory / ('wrong-' + kind)
    for path in (host_key, wrong_key):
        run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(path))
    forced = directory / ('dial-' + kind)
    forced.write_text('#!/bin/sh\n[ "$SSH_ORIGINAL_COMMAND" = "docker system dial-stdio" ] || exit 1\n'
                      f'exec /usr/bin/docker --host unix://{socket_path} system dial-stdio\n')
    forced.chmod(0o755)
    config = directory / ('sshd-' + kind)
    config.write_text(f'Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\n'
                      f'PidFile {directory / (kind + ".pid")}\nAllowUsers {user}\n'
                      'PasswordAuthentication yes\nPubkeyAuthentication yes\nUsePAM no\n'
                      'PermitRootLogin no\nDisableForwarding yes\nPermitTTY no\n'
                      f'ForceCommand {forced}\n')
    run('sudo', '-n', '/usr/sbin/sshd', '-t', '-f', str(config))
    run('sudo', '-n', '/usr/sbin/sshd', '-f', str(config))

    def pin(path):
        return f'[127.0.0.1]:{port} ' + ' '.join(path.with_suffix('.pub').read_text().split()[:2])

    name = 'dcc-ssh-ci-' + secrets.token_hex(6)
    volume = name + '-data'
    base = {'transport': 'ssh', 'ssh_cli': kind, 'ssh_host': '127.0.0.1', 'ssh_port': port,
            'ssh_username': user, 'ssh_known_hosts': pin(host_key)}
    try:
        for credentials in ({'password': password}, {'private_key': key, 'passphrase': passphrase}):
            run(*engine, 'volume', 'create', volume)
            cid = None
            try:
                cid = run(*engine, 'create', '--name', name, '--mount',
                          f'type=volume,src={volume},dst=/fixture', 'alpine:3.22', 'sleep', '300')
                with Connector({}).connect_profile(dict(base, credentials=credentials)) as connection:
                    assert connection.identity['kind'] == kind
                    assert any(item['Id'] == cid for item in connection.read('containers'))
                    for action, status in (('start', 'running'), ('pause', 'paused'), ('unpause', 'running'),
                                           ('restart', 'running'), ('stop', 'exited'), ('remove', None)):
                        connection.container_action(cid, action, name if action == 'remove' else cid)
                        if status:
                            assert run(*engine, 'inspect', '--format', '{{.State.Status}}', cid) == status
                        else:
                            assert cid not in run(*engine, 'ps', '-aq', '--no-trunc').splitlines()
                    assert run(*engine, 'volume', 'inspect', '--format', '{{.Name}}', volume) == volume
                cid = None
                print(f'{kind}: SSH {next(iter(credentials))}, lifecycle and volume retention verified')
            finally:
                if cid and cid in run(*engine, 'ps', '-aq', '--no-trunc').splitlines():
                    run(*engine, 'rm', '-f', cid)
                run(*engine, 'volume', 'rm', volume)
        try:
            with Connector({}).connect_profile(dict(base, ssh_known_hosts=pin(wrong_key), credentials={'password': password})):
                raise AssertionError('wrong SSH host key accepted')
        except KiriError as error:
            assert error.code == 'ssh_auth_failed'
        print(f'{kind}: wrong host key rejected')
    finally:
        pid = (directory / (kind + '.pid')).read_text().strip()
        run('sudo', '-n', 'kill', pid)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('Only run on disposable GitHub-hosted runners')
    user = 'dccssh' + secrets.token_hex(5)
    password, passphrase = secrets.token_hex(24), secrets.token_hex(24)
    sockets = {'docker': '/var/run/docker.sock', 'kiri': '/run/kiri/docker.sock'}
    run('sudo', '-n', 'useradd', '-m', '-s', '/bin/sh', user)
    try:
        run('sudo', '-n', 'chpasswd', input=f'{user}:{password}\n')
        gid = str(os.stat(sockets['docker']).st_gid)
        run('sudo', '-n', 'usermod', '-aG', gid, user)
        run('sudo', '-n', '/usr/bin/kiri', 'host-access', user)
        with tempfile.TemporaryDirectory(prefix='dcc-ssh-ci-', dir='/tmp') as temp:
            directory = Path(temp)
            directory.chmod(0o755)
            client = directory / 'client'
            run('ssh-keygen', '-q', '-t', 'ed25519', '-N', passphrase, '-f', str(client))
            home = Path('/home') / user
            run('sudo', '-n', 'install', '-d', '-m', '700', '-o', user, str(home / '.ssh'))
            run('sudo', '-n', 'install', '-m', '600', '-o', user, str(client.with_suffix('.pub')),
                str(home / '.ssh' / 'authorized_keys'))
            run('sudo', '-n', 'install', '-d', '-m', '755', '/run/sshd')
            for port, (kind, socket_path) in enumerate(sockets.items(), 22222):
                run('sudo', '-n', '-u', user, 'test', '-w', socket_path)
                run('sudo', '-n', 'docker', '--host', 'unix://' + socket_path, 'pull', 'alpine:3.22')
                verify_engine(kind, socket_path, port, user, password, client.read_text(), passphrase, directory)
                time.sleep(0.2)
    finally:
        run('sudo', '-n', 'userdel', '-r', user)


if __name__ == '__main__':
    main()
