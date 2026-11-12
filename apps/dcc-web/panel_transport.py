"""Bounded Docker namespace transport for panels on the local Docker engine.

The temporary helper shares only the selected container's network namespace.
It has no Docker socket, mounts, DCC credentials, published ports or listeners.
The DCC Web container never joins an application network.
"""

from functools import lru_cache
import ipaddress
import os
import re
import socket
import subprocess
import threading
from contextlib import closing

import docker
from engine import DockerBackend, EngineError
from host_setup import local_container


_SLOTS = threading.BoundedSemaphore(12)
_ENGINE = 'unix:///var/run/docker.sock'

# Runs in a new, restricted container using the same immutable image as DCC Web.
# The arguments are a published port and the selected container's own addresses.
_RELAY = '''import socket,sys,threading,time
deadline=time.monotonic()+6
for address in sys.argv[2:]:
    try:
        s=socket.create_connection((address,int(sys.argv[1])),max(0.1,deadline-time.monotonic()))
        break
    except OSError:
        if time.monotonic()>=deadline:sys.exit(1)
else:sys.exit(1)
s.settimeout(10)
def upstream():
    try:
        while True:
            data=sys.stdin.buffer.read1(65536)
            if not data:break
            s.sendall(data)
    except OSError:pass
    finally:
        # The Docker CLI detaches stdin when its parent disappears. Closing
        # both directions wakes recv and releases this helper container.
        try:s.shutdown(socket.SHUT_RDWR)
        except OSError:pass
threading.Thread(target=upstream,daemon=True).start()
try:
    expires=time.monotonic()+600
    while time.monotonic()<expires:
        try:data=s.recv(65536)
        except socket.timeout:continue
        if not data:break
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
finally:s.close()
'''


@lru_cache(maxsize=1)
def _self_image():
    """Reuse the same identity check as HTTPS/zrok, including after Updater."""
    try:
        with closing(docker.DockerClient(base_url=_ENGINE, timeout=5)) as client:
            image = local_container(client).attrs.get('Image', '')
    except (docker.errors.DockerException, ValueError, OSError) as error:
        raise EngineError('The local Docker engine is unavailable for panel forwarding') from error
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
        raise EngineError('Cannot verify the DCC Web helper image on the local Docker engine')
    return image


def _published_addresses(container_id, port):
    try:
        with closing(docker.DockerClient(base_url=_ENGINE, timeout=5)) as client:
            attrs = client.containers.get(container_id).attrs
    except (docker.errors.DockerException, OSError) as error:
        raise EngineError('Cannot inspect the local Docker panel target') from error
    mode = attrs.get('HostConfig', {}).get('NetworkMode', '')
    network = attrs.get('NetworkSettings') or {}
    endpoints = network.get('Networks') or {}
    if (attrs.get('Id') != container_id or not attrs.get('State', {}).get('Running')
            or mode in {'host', 'none'} or mode.startswith('container:')
            or not (network.get('Ports') or {}).get(f'{port}/tcp')):
        raise EngineError('The selected Docker panel is not published in its own network namespace')
    addresses = []
    for endpoint in sorted(endpoints.values(), key=lambda value: value.get('GwPriority') or 0, reverse=True):
        for field in ('IPAddress', 'GlobalIPv6Address'):
            try:
                address = ipaddress.ip_address(endpoint.get(field) or '')
            except ValueError:
                continue
            if not (address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local):
                if str(address) not in addresses:
                    addresses.append(str(address))
    if not addresses:
        raise EngineError('The selected Docker panel has no reachable container address')
    return addresses[:8]


class _RelayOwner:
    def __init__(self, process, peer):
        self.process, self.peer = process, peer
        self.lock = threading.Lock()
        self.closed = False

    def start(self):
        threading.Thread(target=self._upload, daemon=True, name='dcc-panel-relay-up').start()
        threading.Thread(target=self._download, daemon=True, name='dcc-panel-relay-down').start()

    def _upload(self):
        try:
            while True:
                data = self.peer.recv(65536)
                if not data:
                    break
                remaining = memoryview(data)
                while remaining:
                    written = os.write(self.process.stdin.fileno(), remaining)
                    if written <= 0:
                        return
                    remaining = remaining[written:]
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.process.stdin.close()
            except OSError:
                pass

    def _download(self):
        try:
            while True:
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    break
                self.peer.sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.peer.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        try:
            try:
                self.peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.peer.close()
            if self.process.poll() is None:
                # Prefer a graceful EOF so docker run --rm can remove the
                # helper. Terminate only if the relay does not exit promptly.
                try:
                    self.process.stdin.close()
                except (OSError, ValueError):
                    pass
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            for stream in (self.process.stdin, self.process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        finally:
            _SLOTS.release()


def open_local_panel(profile, container_id, container_port):
    """Return a normal socket and a cleanup owner, scoped to one running ID."""
    if (profile.get('kind', 'local') != 'local' or profile.get('context') or
            not isinstance(container_id, str) or
            not re.fullmatch(r'[a-f0-9]{64}', container_id) or
            type(container_port) is not int or not 1 <= container_port <= 65535):
        raise EngineError('The selected Docker panel target cannot be verified')
    if not _SLOTS.acquire(blocking=False):
        raise EngineError('Local panel connection limit reached')
    channel = peer = process = None
    try:
        image = _self_image()
        addresses = _published_addresses(container_id, container_port)
        cli, environment, flags = DockerBackend(profile)._local_command()
        for key in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY'):
            environment.pop(key, None)
        command = [*cli, '--host', _ENGINE, 'run', '--rm', '-i', '--pull', 'never',
                   '--network', 'container:' + container_id,
                   '--read-only', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--user', '10001:10001',
                   '--pids-limit', '32', '--memory', '64m', '--cpus', '0.5',
                   '--no-healthcheck', '--log-driver', 'none',
                   '--entrypoint', 'python', image, '-u', '-c', _RELAY, str(container_port), *addresses]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, bufsize=0,
                                   env=environment, creationflags=flags)
        channel, peer = socket.socketpair()
        channel.settimeout(8)
        owner = _RelayOwner(process, peer)
        owner.start()
        return channel, owner
    except (OSError, ValueError, EngineError) as error:
        try:
            if channel:
                channel.close()
            if peer:
                peer.close()
            if process:
                process.kill()
                process.communicate(timeout=2)
        finally:
            _SLOTS.release()
        if isinstance(error, EngineError):
            raise
        raise EngineError('Cannot start a scoped local Docker panel connection') from error
