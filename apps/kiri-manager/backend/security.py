"""One local administrator, bounded authentication and revocable sessions."""
import hmac
import re
import secrets
import time
from collections import deque
from contextlib import contextmanager
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path
from threading import Lock

from flask import g, request, session

from .kiri_client import KiriError

UNSAFE_NAME = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\ud800-\udfff]")
SETUP_TTL = 10 * 60


def valid_username(value):
    return (
        isinstance(value, str) and 1 <= len(value) <= 64
        and value == value.strip() and not UNSAFE_NAME.search(value)
    )


def valid_password(value, minimum=14):
    return isinstance(value, str) and minimum <= len(value) <= 128 and not UNSAFE_NAME.search(value)


def default_gateway():
    # Docker and Kiri can relay a host-loopback port from the container's bridge gateway.
    try:
        with Path("/proc/net/route").open(encoding="ascii") as routes:
            next(routes, None)
            for route in routes:
                _, destination, gateway, flags, *_ = route.split()
                if destination == "00000000" and int(flags, 16) & 3 == 3:
                    return IPv4Address(bytes.fromhex(gateway)[::-1])
    except (OSError, ValueError):
        return None
    return None


def local_setup_peer(gateway):
    try:
        peer = ip_address(request.remote_addr or "")
    except ValueError:
        return False
    if isinstance(peer, IPv6Address) and peer.ipv4_mapped:
        peer = peer.ipv4_mapped
    return peer.is_loopback or peer == gateway


def begin_setup():
    session.clear()
    session["setup_until"] = time.time() + SETUP_TTL


def setup_pending():
    return session.get("setup_until", 0) > time.time()


class LoginGate:
    def __init__(self):
        self.guard = Lock()
        self.attempts = deque()
        self.verification = Lock()

    @contextmanager
    def allow(self):
        now = time.monotonic()
        with self.guard:
            while self.attempts and now - self.attempts[0] >= 60:
                self.attempts.popleft()
            if len(self.attempts) >= 8 or not self.verification.acquire(blocking=False):
                raise KiriError("login_limited", 429)
            self.attempts.append(now)
        try:
            yield
        finally:
            self.verification.release()


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def enforce_access(storage, origin):
    sid = session.get("sid")
    g.sid = sid if sid and storage.session_valid(sid) else None
    if request.path not in {"/api/session", "/api/login", "/api/setup"} and not g.sid:
        raise KiriError("unauthorized", 401)
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected_origin = origin or request.host_url.rstrip("/")
    submitted = request.headers.get("X-CSRF-Token", "")
    if (request.headers.get("Origin") != expected_origin or not session.get("csrf")
            or not submitted.isascii() or not hmac.compare_digest(session["csrf"], submitted)):
        raise KiriError("csrf", 403)
    if not request.is_json:
        raise KiriError("bad_input", 400)
