"""Bounded, read-only access to one explicitly approved Unix socket."""
import errno
import http.client
import json
import re
import socket
import stat
import time
from contextlib import closing, contextmanager
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlencode

from .config import DEFAULT_DOCKER_SOCKETS

API_MAX = (1, 47)
API_MIN = (1, 41)
TIMEOUT = 2.0
JSON_LIMIT = 2 * 1024 * 1024
LOG_LIMIT = 128 * 1024
KIRI_VERSION = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}(?:[-+][0-9A-Za-z.-]{1,32})?")
API_VERSION = re.compile(r"(1)\.(\d{1,3})")
IDS = {
    "containers": re.compile(r"[a-f0-9]{64}"),
    "images": re.compile(r"sha256:[a-f0-9]{64}"),
    "networks": re.compile(r"[a-f0-9]{64}"),
    "volumes": re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}"),
}
LISTS = {
    "info": "/info",
    "containers": "/containers/json?all=1",
    "images": "/images/json?all=1",
    "volumes": "/volumes",
    "networks": "/networks",
    "disk": "/system/df",
}


class KiriError(Exception):
    def __init__(self, code, status=502):
        super().__init__(code)
        self.code = code
        self.status = status


class DeadlineSocket(socket.socket):
    def __init__(self, timeout):
        super().__init__(socket.AF_UNIX, socket.SOCK_STREAM)
        self.deadline = time.monotonic() + timeout

    def set_remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.settimeout(remaining)

    def recv_into(self, *args):
        self.set_remaining()
        return super().recv_into(*args)

    def sendall(self, *args):
        self.set_remaining()
        return super().sendall(*args)


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("kiri", timeout=timeout)
        self.path = path

    def connect(self):
        sock = DeadlineSocket(self.timeout)
        try:
            sock.set_remaining()
            sock.connect(str(self.path))
        except BaseException:
            sock.close()
            raise
        self.sock = sock


class UnixTransport:
    def __init__(self, path, timeout=TIMEOUT):
        self.path = Path(path)
        self.timeout = timeout
        self.identity = None

    def check_socket(self):
        if not hasattr(socket, "AF_UNIX") or not self.path.is_absolute():
            raise KiriError("socket_invalid")
        canonical = self.path.resolve(strict=True)
        if canonical != self.path or str(canonical) in DEFAULT_DOCKER_SOCKETS:
            raise KiriError("socket_invalid")
        file = self.path.stat()
        if not stat.S_ISSOCK(file.st_mode):
            raise KiriError("socket_invalid")
        identity = (file.st_dev, file.st_ino)
        if self.identity is not None and identity != self.identity:
            raise KiriError("socket_changed")
        self.identity = identity

    def get(self, path, limit, expected=None):
        if not path.startswith("/") or path.startswith("//"):
            raise KiriError("bad_response")
        try:
            self.check_socket()
            with closing(UnixHTTPConnection(self.path, self.timeout)) as conn:
                conn.request("GET", path, headers={"X-Kiri-Background": "1", "Connection": "close",
                                                   "Accept-Encoding": "identity"})
                with conn.getresponse() as response:
                    server = response.getheader("Server", "")
                    if expected is not None and server != expected:
                        raise KiriError("bad_engine")
                    if response.status in {401, 403}:
                        raise KiriError("permission_denied", 403)
                    if response.status in {404, 405, 501}:
                        raise KiriError("resource_missing" if response.status == 404 else "unsupported",
                                        404 if response.status == 404 else 501)
                    if response.status != 200:
                        raise KiriError("engine_error")
                    if response.getheader("Content-Encoding", "identity") != "identity":
                        raise KiriError("bad_response")
                    if response.length is not None and response.length > limit:
                        raise KiriError("large_response")
                    content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
                    body = response.read(limit + 1)
                    if len(body) > limit:
                        raise KiriError("large_response")
                    if response.length not in (0, None):
                        raise KiriError("disconnected", 503)
            self.check_socket()
            return server, content_type, body
        except TimeoutError:
            raise KiriError("timeout", 504) from None
        except (FileNotFoundError, NotADirectoryError):
            raise KiriError("socket_missing", 503) from None
        except PermissionError:
            raise KiriError("permission_denied", 403) from None
        except (http.client.RemoteDisconnected, http.client.IncompleteRead, ConnectionError):
            raise KiriError("disconnected", 503) from None
        except OSError as e:
            code = "socket_invalid" if e.errno in {errno.ELOOP, errno.ENOTSOCK, errno.EINVAL} else "disconnected"
            raise KiriError(code, 503) from None
        except (http.client.HTTPException, RuntimeError, ValueError):
            raise KiriError("bad_response") from None


def read_json(content_type, body):
    if content_type != "application/json":
        raise KiriError("bad_response")
    try:
        return json.loads(body, parse_constant=lambda ignored: None)
    except (ValueError, RecursionError):
        raise KiriError("bad_response") from None


def api_tuple(raw):
    match = API_VERSION.fullmatch(raw) if isinstance(raw, str) else None
    if not match:
        raise KiriError("api_version")
    return tuple(map(int, match.groups()))


def identify(server, value):
    if not isinstance(value, dict):
        raise KiriError("bad_engine")
    version = value.get("KiriVersion")
    platform = value.get("Platform")
    components = value.get("Components")
    if (not isinstance(version, str) or not KIRI_VERSION.fullmatch(version)
            or server != f"Kiri/{version} (linux)"
            or not isinstance(platform, dict) or platform.get("Name") != "Kiri"
            or not isinstance(components, list)):
        raise KiriError("bad_engine")
    reported = [c.get("Version") for c in components if isinstance(c, dict) and c.get("Name") == "Kiri"]
    if reported != [version]:
        raise KiriError("bad_engine")
    maximum = api_tuple(value.get("ApiVersion"))
    minimum = api_tuple(value.get("MinAPIVersion"))
    selected = min(maximum, API_MAX)
    if max(minimum, API_MIN) > selected:
        raise KiriError("api_version")
    arch = value.get("Arch")
    system = value.get("Os")
    return {
        "version": version, "api": ".".join(map(str, selected)),
        "api_max": value["ApiVersion"], "api_min": value["MinAPIVersion"],
        "os": system if system == "linux" else None,
        "arch": arch if arch in {"amd64", "arm64", "386", "arm", "riscv64", "ppc64le", "s390x"} else None,
    }


class VerifiedKiri:
    def __init__(self, transport):
        self.transport = transport
        for attempt in range(2):
            try:
                self.server, content_type, payload = transport.get("/version", 16 * 1024)
                self.identity = identify(self.server, read_json(content_type, payload))
                break
            except KiriError as e:
                if e.code in {"resource_missing", "unsupported"}:
                    raise KiriError("bad_engine") from None
                if attempt or e.code not in {"disconnected", "timeout"}:
                    raise

    def _json(self, path):
        _, content_type, body = self.transport.get(
            f"/v{self.identity['api']}{path}", JSON_LIMIT, self.server,
        )
        return read_json(content_type, body)

    def read(self, resource):
        try:
            return self._json(LISTS[resource])
        except KiriError as e:
            if e.code == "resource_missing":
                raise KiriError("unsupported", 501) from None
            raise

    def details(self, resource, key):
        validate_key(resource, key)
        suffix = "/json" if resource in {"containers", "images"} else ""
        return self._json(f"/{resource}/{key}{suffix}")

    def volume_users(self, name):
        validate_key("volumes", name)
        query = urlencode({"all": 1, "filters": json.dumps({"volume": [name]}, separators=(",", ":"))})
        return self._json(f"/containers/json?{query}")

    def container_stats(self, key):
        validate_key("containers", key)
        # Kiri takes two samples for non-streaming stats unless one-shot is set.
        return self._json(f"/containers/{key}/stats?stream=0")

    def container_logs(self, key, tail):
        validate_key("containers", key)
        if type(tail) is not int or not 1 <= tail <= 200:
            raise KiriError("bad_input", 400)
        path = f"/v{self.identity['api']}/containers/{key}/logs?stdout=1&stderr=1&follow=0&timestamps=1&tail={tail}"
        return self.transport.get(path, LOG_LIMIT, self.server)[1:]


def validate_key(resource, key):
    if not IDS[resource].fullmatch(key):
        raise KiriError("bad_id", 400)


class Connector:
    def __init__(self, sockets, transport=UnixTransport):
        self.sockets = dict(sockets)
        self.transport = transport
        self.slots = BoundedSemaphore(3)

    @contextmanager
    def connect(self, alias):
        path = self.sockets.get(alias)
        if path is None:
            raise KiriError("endpoint_disabled", 409)
        if not self.slots.acquire(blocking=False):
            raise KiriError("busy", 503)
        try:
            yield VerifiedKiri(self.transport(path))
        finally:
            self.slots.release()
