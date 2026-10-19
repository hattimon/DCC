"""Password-protected web panel for selected Docker image updates."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

import docker
from flask import Flask, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from updater import UpdateService


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {"id": None, "kind": None, "status": "idle", "progress": "", "results": []}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def start(self, kind: str, work: Callable[[Callable[[str], None]], Any]) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            if self._state["status"] in {"queued", "running"}:
                return False, self.snapshot()
            job_id = secrets.token_urlsafe(12)
            self._state = {
                "id": job_id,
                "kind": kind,
                "status": "queued",
                "progress": "Zadanie oczekuje na wykonanie.",
                "results": [],
                "started_at": time.time(),
            }

        def progress(message: str) -> None:
            with self._lock:
                if self._state.get("id") == job_id:
                    self._state["status"] = "running"
                    self._state["progress"] = str(message)[:300]

        def run() -> None:
            progress("Uruchamianie zadania…")
            try:
                result = work(progress)
                with self._lock:
                    if self._state.get("id") == job_id:
                        self._state.update(status="done", progress="Gotowe.", results=result or [])
            except Exception as exc:
                with self._lock:
                    if self._state.get("id") == job_id:
                        self._state.update(status="error", progress=f"Zadanie nie powiodło się ({type(exc).__name__}).", results=[])

        threading.Thread(target=run, name=f"dcc-updater-{kind}", daemon=True).start()
        return True, self.snapshot()


def _atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(path)


def create_app(
    data_dir: str | Path | None = None,
    service_factory: Callable[[], UpdateService] | None = None,
    *,
    print_credentials: bool = True,
) -> Flask:
    app = Flask(__name__, template_folder="templates")
    data_path = Path(data_dir or os.environ.get("DCC_UPDATER_DATA", "/data"))
    data_path.mkdir(parents=True, exist_ok=True)
    password_path = data_path / "admin_password_hash"
    secret_path = data_path / "secret_key"

    if not secret_path.exists():
        _atomic_write(secret_path, secrets.token_urlsafe(48))
    app.config.update(
        SECRET_KEY=secret_path.read_text(encoding="utf-8").strip(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("DCC_UPDATER_SECURE_COOKIE", "0") == "1",
        MAX_CONTENT_LENGTH=16 * 1024,
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    )

    initial_password = None
    if not password_path.exists():
        initial_password = secrets.token_urlsafe(18)
        _atomic_write(password_path, generate_password_hash(initial_password, method="scrypt"))
        if print_credentials:
            print(f"DCC_UPDATER_INITIAL_CREDENTIALS username=admin password={initial_password}", flush=True)

    manager = JobManager()
    app.extensions["dcc_updater_jobs"] = manager
    app.extensions["dcc_updater_data_dir"] = data_path
    app.extensions["dcc_updater_initial_password"] = initial_password

    def get_service() -> UpdateService:
        if service_factory:
            return service_factory()
        client = docker.from_env(timeout=30)
        return UpdateService(client, wait_seconds=int(os.environ.get("DCC_UPDATER_HEALTH_TIMEOUT", "60")))

    login_attempts: dict[str, list[float]] = {}

    def csrf_token() -> str:
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def csrf_valid() -> bool:
        supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        return bool(supplied and hmac.compare_digest(str(session.get("csrf_token", "")), str(supplied)))

    def authenticated() -> bool:
        return session.get("authenticated") is True

    @app.before_request
    def protect_routes():
        if request.endpoint in {"health", "login", "static"}:
            return None
        if not authenticated():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Wymagane logowanie."}), 401
            return redirect(url_for("login"))
        if request.method == "POST" and not csrf_valid():
            return jsonify({"error": "Nieprawidłowy token bezpieczeństwa. Odśwież stronę i spróbuj ponownie."}), 400
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if authenticated():
            return redirect(url_for("index"))
        message = ""
        token = csrf_token()
        if request.method == "POST":
            if not csrf_valid():
                return make_response("Nieprawidłowy token bezpieczeństwa. Odśwież stronę.", 400)
            now = time.time()
            remote = request.remote_addr or "unknown"
            attempts = [stamp for stamp in login_attempts.get(remote, []) if now - stamp < 600]
            login_attempts[remote] = attempts
            if len(attempts) >= 8:
                message = "Zbyt wiele prób. Odczekaj 10 minut i spróbuj ponownie."
            else:
                password = request.form.get("password", "")
                stored_hash = password_path.read_text(encoding="utf-8").strip()
                if check_password_hash(stored_hash, password):
                    session.clear()
                    session["authenticated"] = True
                    session["csrf_token"] = secrets.token_urlsafe(32)
                    session.permanent = True
                    login_attempts.pop(remote, None)
                    return redirect(url_for("index"))
                attempts.append(now)
                login_attempts[remote] = attempts
                message = "Nieprawidłowe hasło."
        return render_template("login.html", csrf_token=token, message=message)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        return render_template("index.html", csrf_token=csrf_token())

    @app.get("/api/containers")
    def containers():
        state = manager.snapshot()
        return jsonify(state.get("results", []))

    @app.get("/api/job")
    def job():
        return jsonify(manager.snapshot())

    @app.post("/api/scan")
    def scan():
        def work(progress):
            return get_service().scan(progress)

        started, state = manager.start("scan", work)
        return jsonify(state), (202 if started else 409)

    @app.post("/api/update")
    def update():
        payload = request.get_json(silent=True) or {}
        selected = payload.get("container_ids")
        if not isinstance(selected, list) or not selected or len(selected) > 100:
            return jsonify({"error": "Wybierz od 1 do 100 kontenerów."}), 400
        ids = list(dict.fromkeys(str(value)[:128] for value in selected if isinstance(value, str) and value.strip()))
        if not ids:
            return jsonify({"error": "Nie otrzymano prawidłowych identyfikatorów kontenerów."}), 400

        def work(progress):
            service = get_service()
            outcomes = service.update_selected(ids, progress)
            progress("Ponowne sprawdzanie stanu kontenerów…")
            containers_after = service.scan(progress)
            return {"updates": outcomes, "containers": containers_after}

        started, state = manager.start("update", work)
        return jsonify(state), (202 if started else 409)

    @app.post("/api/password")
    def change_password():
        payload = request.get_json(silent=True) or {}
        old_password = str(payload.get("old_password", ""))
        new_password = str(payload.get("new_password", ""))
        stored_hash = password_path.read_text(encoding="utf-8").strip()
        if not check_password_hash(stored_hash, old_password):
            return jsonify({"error": "Obecne hasło jest nieprawidłowe."}), 400
        if len(new_password) < 14:
            return jsonify({"error": "Nowe hasło musi mieć co najmniej 14 znaków."}), 400
        _atomic_write(password_path, generate_password_hash(new_password, method="scrypt"))
        return jsonify({"message": "Hasło zostało zmienione."})

    return app


app = create_app()
