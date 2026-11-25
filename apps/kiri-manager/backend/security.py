"""One local administrator, bounded authentication and revocable sessions."""
import hmac
import secrets
import time
from collections import deque
from contextlib import contextmanager
from threading import Lock

from flask import g, request, session

from .kiri_client import KiriError


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
    if request.path not in {"/api/session", "/api/login"} and not g.sid:
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
