"""Unit coverage for the isolated local Docker panel socket relay.

The test child is plain Python, never a real Docker run or user container.
"""
import queue
import socket
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import EngineError
import panel_transport


CONTAINER = 'a' * 64
IMAGE = 'sha256:' + 'b' * 64


class InMemorySocket:
    """Two-ended byte stream for restricted Windows QA without TCP listeners."""

    def __init__(self):
        self.incoming = queue.Queue()
        self.pending = bytearray()
        self.remote = None
        self.timeout = None
        self.closed = False

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        if self.closed:
            raise OSError('Closed test socket')
        self.remote.incoming.put(bytes(data))

    def recv(self, size):
        if not self.pending:
            try:
                value = self.incoming.get(timeout=self.timeout)
            except queue.Empty:
                raise socket.timeout('Test socket timed out') from None
            if not value:
                return b''
            self.pending.extend(value)
        value = bytes(self.pending[:size])
        del self.pending[:size]
        return value

    def shutdown(self, _how):
        self.incoming.put(b'')
        self.remote.incoming.put(b'')

    def close(self):
        if not self.closed:
            self.closed = True
            self.shutdown(socket.SHUT_RDWR)


def in_memory_socket_pair():
    channel, peer = InMemorySocket(), InMemorySocket()
    channel.remote, peer.remote = peer, channel
    return channel, peer


class NamespaceRelayTests(unittest.TestCase):
    def test_relay_bytes_and_strict_docker_isolation_flags(self):
        original = subprocess.Popen
        commands = []

        def local_child(command, **options):
            commands.append(command)
            # A stand-in for the Docker helper process; no TCP listener needed.
            script = ('import sys; data=sys.stdin.buffer.read(6); '
                      'sys.stdout.buffer.write(data[::-1]); sys.stdout.buffer.flush()')
            return original([sys.executable,'-u','-c',script],**options)

        with patch('panel_transport._self_image',return_value=IMAGE), \
                patch('panel_transport._published_addresses',return_value=['172.18.0.4']), \
                patch('panel_transport.subprocess.Popen',side_effect=local_child), \
                patch('panel_transport.socket.socketpair',side_effect=in_memory_socket_pair):
            channel, owner = panel_transport.open_local_panel({'kind':'local'},CONTAINER,3000)
            try:
                channel.sendall(b'abcdef')
                self.assertEqual(channel.recv(6),b'fedcba')
                self.assertEqual(commands[0][commands[0].index('--network')+1],
                                 'container:'+CONTAINER)
                self.assertEqual(commands[0][-2:],['3000','172.18.0.4'])
                for flag in ('--rm','-i','--read-only','--cap-drop','--security-opt',
                             '--pull','--pids-limit','--memory','--cpus'):
                    self.assertIn(flag,commands[0])
                self.assertNotIn('--privileged',commands[0])
                self.assertNotIn('-v',commands[0])
                self.assertNotIn('-p',commands[0])
                self.assertIn('--no-healthcheck',commands[0])
                self.assertEqual(commands[0][commands[0].index('--log-driver')+1],'none')
            finally:
                channel.close()
                owner.close()
                owner.close()
            self.assertTrue(owner.closed)
            self.assertIsNotNone(owner.process.poll())

    def test_target_verification_is_fail_closed(self):
        with patch('panel_transport._self_image',return_value=IMAGE) as image:
            for profile, identity, port in (
                ({'kind':'tcp'},CONTAINER,80),
                ({'kind':'local','context':'foreign'},CONTAINER,80),
                ({'kind':'local'},'../different-container',80),
                ({'kind':'local'},'a'*12,80),
                ({'kind':'local'},CONTAINER,0),
                ({'kind':'local'},CONTAINER,65536),
                ({'kind':'local'},CONTAINER,'80'),
            ):
                with self.subTest(profile=profile,identity=identity,port=port):
                    with self.assertRaises(EngineError):
                        panel_transport.open_local_panel(profile,identity,port)
            image.assert_not_called()

    def test_helper_image_must_be_own_verified_container(self):
        panel_transport._self_image.cache_clear()
        try:
            with patch('panel_transport.docker.DockerClient') as docker_client, \
                    patch('panel_transport.local_container') as identify:
                identify.return_value.attrs={'Image':'untrusted:latest'}
                with self.assertRaises(EngineError):panel_transport._self_image()
                identify.return_value.attrs={'Image':IMAGE}
                self.assertEqual(panel_transport._self_image(),IMAGE)
                identify.assert_called_with(docker_client.return_value)
        finally:
            panel_transport._self_image.cache_clear()

    def test_inspects_exact_running_container_and_only_its_published_addresses(self):
        attrs={'Id':CONTAINER,'State':{'Running':True},'HostConfig':{'NetworkMode':'project'},
               'NetworkSettings':{'Ports':{'3000/tcp':[{'HostIp':'127.0.0.1','HostPort':'33100'}]},
                                  'Networks':{'other':{'IPAddress':'172.18.0.3'},
                                              'project':{'IPAddress':'172.20.0.4','GwPriority':1,
                                                         'GlobalIPv6Address':'fd00::4'}}}}
        with patch('panel_transport.docker.DockerClient') as client:
            inspect=client.return_value.containers.get
            inspect.return_value.attrs=attrs
            self.assertEqual(panel_transport._published_addresses(CONTAINER,3000),
                             ['172.20.0.4','fd00::4','172.18.0.3'])
            inspect.assert_called_with(CONTAINER)
            with self.assertRaisesRegex(EngineError,'not published'):
                panel_transport._published_addresses(CONTAINER,8080)
            for mode in ('host','none','container:'+CONTAINER):
                attrs['HostConfig']['NetworkMode']=mode
                with self.assertRaisesRegex(EngineError,'not published'):
                    panel_transport._published_addresses(CONTAINER,3000)

    def test_spawn_failure_frees_connection_slot(self):
        with patch('panel_transport._self_image',return_value=IMAGE), \
                patch('panel_transport._published_addresses',return_value=['172.18.0.4']), \
                patch('panel_transport.subprocess.Popen',side_effect=OSError('blocked')), \
                patch('panel_transport._SLOTS') as slots:
            slots.acquire.return_value=True
            with self.assertRaisesRegex(EngineError,'scoped local'):
                panel_transport.open_local_panel({'kind':'local'},CONTAINER,80)
            slots.release.assert_called_once()

    def test_connection_limit_rejects_without_spawning(self):
        with patch('panel_transport._self_image',return_value=IMAGE), \
                patch('panel_transport._SLOTS') as slots, \
                patch('panel_transport.subprocess.Popen') as spawn:
            slots.acquire.return_value=False
            with self.assertRaisesRegex(EngineError,'limit'):
                panel_transport.open_local_panel({'kind':'local'},CONTAINER,80)
            spawn.assert_not_called()


if __name__=='__main__':unittest.main()
