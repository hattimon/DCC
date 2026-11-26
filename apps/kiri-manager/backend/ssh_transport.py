"""Engine HTTP over a verified SSH connection; no user-controlled commands."""
import http.client
import io
import logging
import time
from contextlib import closing, contextmanager
from threading import Timer

import paramiko

from .kiri_client import KiriError

COMMAND = "docker system dial-stdio"
# Paramiko may include remote-controlled authentication/error strings in its logs.
LOGGER = logging.getLogger("dcc.kiri.ssh.private")
LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False
LOGGER.disabled = True

class NoReconnectHTTP(http.client.HTTPConnection):
    def connect(self):
        raise KiriError("disconnected", 503)


class SessionHTTP:
    def __init__(self, conn, channel):
        self.conn, self.channel = conn, channel

    def get(self, path, limit, expected=None):
        return self.request("GET", path, limit, expected)

    def request(self, method, path, limit, expected=None):
        timeout = 3 if method == "GET" else 15
        if self.conn.sock is None:
            raise KiriError("disconnected", 503)
        self.conn.sock.deadline = time.monotonic() + timeout
        try:
            self.conn.request(method, path, body=b"" if method != "GET" else None,
                              headers={"X-Kiri-Background": "1", "Accept-Encoding": "identity",
                                       "Connection": "keep-alive"})
            with self.conn.getresponse() as response:
                return read_response(response, method, limit, expected)
        except KiriError:
            raise
        except TimeoutError:
            raise KiriError("timeout", 504) from None
        except Exception:
            raise KiriError("ssh_connection", 503) from None


def read_response(response, method, limit, expected):
    server = response.getheader("Server", "")
    if expected is not None and server != expected:
        raise KiriError("bad_engine")
    if response.status in {401, 403}:
        raise KiriError("permission_denied", 403)
    if response.status in {404, 405, 501}:
        raise KiriError("resource_missing" if response.status == 404 else "unsupported",
                        404 if response.status == 404 else 501)
    if response.status == 409:
        raise KiriError("engine_conflict", 409)
    if response.status not in ({200} if method == "GET" else {200, 204, 304}):
        raise KiriError("engine_error")
    if response.getheader("Content-Encoding", "identity") != "identity":
        raise KiriError("bad_response")
    if response.length is not None and response.length > limit:
        raise KiriError("large_response")
    kind = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
    body = response.read(limit + 1)
    if len(body) > limit:
        raise KiriError("large_response")
    if response.length not in (0, None):
        raise KiriError("disconnected", 503)
    return server, kind, body


def trusted_keys(host, port, known_hosts):
    name = host if port == 22 else f"[{host}]:{port}"
    keys = paramiko.HostKeys()
    try:
        for line in known_hosts.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            entry = paramiko.hostkeys.HostKeyEntry.from_line(line.strip())
            if entry is None or entry.key is None:
                raise ValueError
            for hostname in entry.hostnames:
                if hostname != name:
                    continue
                existing = keys.lookup(name)
                if existing and entry.key.get_name() in existing and existing[entry.key.get_name()] != entry.key:
                    raise ValueError
                keys.add(name, entry.key.get_name(), entry.key)
        if not keys.lookup(name):
            raise ValueError
    except Exception:
        raise KiriError("ssh_host_key", 400) from None
    return keys


def private_key(value, passphrase):
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(value), password=passphrase or None)
        except Exception:
            continue
    raise KiriError("ssh_credentials", 400)


class ChannelReader(io.RawIOBase):
    def __init__(self, channel, deadline):
        self.channel, self.deadline = channel, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.channel.settimeout(remaining)
        chunk = self.channel.recv(len(buffer))
        buffer[:len(chunk)] = chunk
        return len(chunk)


class ChannelSocket:
    def __init__(self, channel, deadline):
        self.channel, self.deadline = channel, deadline

    def sendall(self, data):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.channel.settimeout(remaining)
        self.channel.sendall(data)

    def makefile(self, mode):
        return io.BufferedReader(ChannelReader(self.channel, self.deadline))

    def close(self):
        self.channel.close()


class SSHTransport:
    def __init__(self, profile):
        self.profile = profile
        self.client = paramiko.SSHClient()
        self.client.set_log_channel(LOGGER.name)

    def __enter__(self):
        p = self.profile
        try:
            keys = trusted_keys(p["ssh_host"], p["ssh_port"], p["ssh_known_hosts"])
            for name, entries in keys.items():
                for kind, key in entries.items():
                    self.client.get_host_keys().add(name, kind, key)
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
            auth = p["credentials"]
            key = private_key(auth["private_key"], auth.get("passphrase")) if auth.get("private_key") else None
            self.client.connect(p["ssh_host"], port=p["ssh_port"], username=p["ssh_username"],
                                password=auth.get("password") or None, pkey=key,
                                allow_agent=False, look_for_keys=False, timeout=4,
                                banner_timeout=4, auth_timeout=4, channel_timeout=4)
            return self
        except KiriError:
            self.client.close()
            raise
        except (paramiko.BadHostKeyException, paramiko.AuthenticationException):
            self.client.close()
            raise KiriError("ssh_auth_failed", 403) from None
        except Exception:
            self.client.close()
            raise KiriError("ssh_connection", 503) from None

    def __exit__(self, *args):
        self.client.close()

    def get(self, path, limit, expected=None):
        return self.request("GET", path, limit, expected)

    @contextmanager
    def mutation_session(self):
        # Same fixed remote process and stream for version, inspect and write.
        # An engine that closes the stream before the write fails closed.
        try:
            with closing(self.client.get_transport().open_session(timeout=4)) as channel:
                channel.settimeout(4)
                watchdog = Timer(4, self.client.close)
                watchdog.daemon = True
                watchdog.start()
                try:
                    channel.exec_command(COMMAND)
                finally:
                    watchdog.cancel()
                with closing(NoReconnectHTTP("docker", timeout=4)) as conn:
                    conn.sock = ChannelSocket(channel, time.monotonic() + 4)
                    yield SessionHTTP(conn, channel)
        except KiriError:
            raise
        except TimeoutError:
            raise KiriError("timeout", 504) from None
        except Exception:
            raise KiriError("ssh_connection", 503) from None

    def request(self, method, path, limit, expected=None):
        # Every read gets its own bounded channel. Mutations use mutation_session.
        if method != "GET":
            raise KiriError("bad_input", 400)
        with self.mutation_session() as session:
            return session.get(path, limit, expected)
