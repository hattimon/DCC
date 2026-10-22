"""Password-protected web panel for selected Docker image updates."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

import docker
from flask import Flask, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from updater import UpdateService, normalized_repository
from i18n import localize_payload, strings, translate_text


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.instance = secrets.token_urlsafe(12)
        self._history: dict[str, dict[str, Any]] = {}
        self._state: dict[str, Any] = {"id": None, "instance": self.instance, "kind": None, "status": "idle", "progress": "", "results": []}

    def snapshot(self, job_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._state if job_id is None or self._state["id"] == job_id else self._history.get(job_id)
            if state is None:
                raise KeyError(job_id)
            return json.loads(json.dumps(state))

    def start(self, kind: str, work: Callable[[Callable[[str], None]], Any]) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            if self._state["status"] in {"queued", "running"}:
                return False, self.snapshot()
            if self._state["id"]:
                self._history[self._state["id"]] = self.snapshot()
                if len(self._history) > 20:
                    self._history.pop(next(iter(self._history)))
            job_id = secrets.token_urlsafe(12)
            self._state = {
                "id": job_id,
                "instance": self.instance,
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


class AutoUpdateStore:
    """Persist opt-in startup updates by stable container name and image repository."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Nieprawidłowy format ustawień automatycznych aktualizacji.")
        containers = payload.get("containers", {})
        if not isinstance(containers, dict):
            raise ValueError("Nieprawidłowy format ustawień automatycznych aktualizacji.")
        return {
            str(name): str(repository)
            for name, repository in containers.items()
            if isinstance(name, str) and isinstance(repository, str) and name and repository
        }

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            try:
                return self._read()
            except (OSError, ValueError) as exc:
                logging.getLogger(__name__).warning(
                    "Could not read DCC updater startup-update settings (%s); automatic updates are treated as disabled.",
                    type(exc).__name__,
                )
                return {}

    def is_enabled(self, name: str, image: str) -> bool:
        repository = normalized_repository(image) if image else ""
        return bool(repository and self.snapshot().get(name) == repository)

    def set(self, name: str, image: str, enabled: bool) -> dict[str, str]:
        with self._lock:
            containers = self._read()
            if enabled:
                repository = normalized_repository(image)
                if not name or not image or not repository:
                    raise ValueError("Nie można zapisać automatycznej aktualizacji bez nazwy i obrazu kontenera.")
                containers[name] = repository
            else:
                containers.pop(name, None)
            _atomic_write(
                self.path,
                json.dumps({"schema": 1, "containers": containers}, ensure_ascii=False, indent=2) + "\n",
            )
            return containers


def create_app(
    data_dir: str | Path | None = None,
    service_factory: Callable[[], UpdateService] | None = None,
    *,
    print_credentials: bool = True,
    startup_auto_updates: bool = False,
    startup_self_update: bool = False,
) -> Flask:
    app = Flask(__name__, template_folder="templates")
    data_path = Path(data_dir or os.environ.get("DCC_UPDATER_DATA", "/data"))
    data_path.mkdir(parents=True, exist_ok=True)
    password_path = data_path / "admin_password_hash"
    secret_path = data_path / "secret_key"
    auto_update_store = AutoUpdateStore(data_path / "auto_update_containers.json")
    language_path = data_path / "language"
    language_lock = threading.RLock()

    def current_language() -> str:
        selected = session.get("language")
        if selected in {"en", "pl"}:
            return selected
        try:
            saved = language_path.read_text(encoding="utf-8").strip()
        except OSError:
            saved = "en"
        return saved if saved in {"en", "pl"} else "en"

    @app.context_processor
    def language_context():
        language = current_language()
        return {"lang": language, "ui": strings(language), "translate": lambda text: translate_text(text, language)}

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
    app.extensions["dcc_updater_auto_updates"] = auto_update_store
    startup_lock = threading.RLock()
    startup_state = {
        "scheduled": startup_auto_updates or startup_self_update,
        "auto_updates_pending": startup_auto_updates,
        "awaiting_panel_decision": False,
        "panel_update_started": False,
    }

    def finish_startup(result: dict[str, Any]) -> dict[str, Any]:
        with startup_lock:
            startup_state["auto_updates_pending"] = False
        return result

    def get_service() -> UpdateService:
        if service_factory:
            return service_factory()
        try:
            docker_timeout = max(30, min(int(os.environ.get("DCC_UPDATER_DOCKER_TIMEOUT", "180")), 600))
        except ValueError:
            docker_timeout = 180
        client = docker.from_env(timeout=docker_timeout)
        return UpdateService(client, wait_seconds=int(os.environ.get("DCC_UPDATER_HEALTH_TIMEOUT", "60")))

    def annotate_auto_update_state(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enabled = auto_update_store.snapshot()
        for item in results:
            name = str(item.get("name") or "")
            image = str(item.get("current_image") or "")
            repository = normalized_repository(image) if image else ""
            auto_supported = item.get("auto_update_supported", item.get("supported", False))
            item["auto_update_on_startup"] = bool(
                auto_supported and name and repository and enabled.get(name) == repository
            )
        return results

    def run_startup_auto_updates(
        progress: Callable[[str], None], *, skip_panel_check: bool = False, scan_all: bool = False,
    ) -> dict[str, Any]:
        service = None
        deadline = time.monotonic() + max(30, min(int(os.environ.get("DCC_UPDATER_DOCKER_WAIT", "180")), 600))
        while True:
            try:
                service = get_service()
                ping = getattr(service.client, "ping", None)
                if callable(ping):
                    ping()
                else:
                    service.client.containers.list(all=True)
                break
            except Exception as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Docker nie uruchomił się przed upływem limitu oczekiwania.") from exc
                progress("Oczekiwanie na gotowość Docker po restarcie hosta…")
                time.sleep(3)

        if startup_self_update and not skip_panel_check:
            try:
                self_update = service.check_self_update(progress)
                if self_update.get("update_available"):
                    with startup_lock:
                        startup_state["awaiting_panel_decision"] = True
                    progress("Dostępna aktualizacja panelu. Otwórz panel i wybierz Aktualizuj albo Nie teraz.")
                    return {
                        "self_update": self_update,
                        "awaiting_panel_decision": True,
                        "updates": [],
                        "containers": [],
                    }
                elif not self_update.get("checked"):
                    progress(self_update.get("message", "Nie udało się sprawdzić aktualizacji panelu; obecny panel działa dalej."))
            except Exception as exc:
                progress(f"Nie udało się sprawdzić aktualizacji panelu ({type(exc).__name__}); obecny panel działa dalej.")

        if not startup_auto_updates and not scan_all:
            return finish_startup({"updates": [], "containers": []})

        enabled = auto_update_store.snapshot() if startup_auto_updates else {}
        if not enabled and not scan_all:
            progress("Panel sprawdzony; automatyczne aktualizacje innych kontenerów nie są włączone.")
            return finish_startup({"updates": [], "containers": []})

        scanned = service.scan(progress)

        by_name = {str(item.get("name") or ""): item for item in scanned}
        queued: list[dict[str, Any]] = []
        for name, repository in enabled.items():
            item = by_name.get(name)
            if not item or normalized_repository(str(item.get("current_image") or "")) != repository:
                continue
            if item.get("auto_update_supported", item.get("supported")) and item.get("update_available"):
                queued.append(item)

        if not queued:
            progress("Kolejka automatyczna zakończona: brak dostępnych aktualizacji.")
            return finish_startup({"updates": [], "containers": annotate_auto_update_state(scanned)})

        progress(f"Kolejka automatyczna: {len(queued)} kontenerów; aktualizacja po jednym kontenerze naraz.")
        outcomes = service.update_selected([str(item["id"]) for item in queued], progress)
        progress("Kolejka zakończona. Ponowne skanowanie kontenerów…")
        updated = annotate_auto_update_state(service.scan(progress))
        return finish_startup({"updates": outcomes, "containers": updated})

    def schedule_startup_auto_updates() -> threading.Thread:
        try:
            default_delay = "0" if startup_self_update else "12"
            delay = max(0, min(int(os.environ.get(
                "DCC_UPDATER_SELF_UPDATE_STARTUP_DELAY" if startup_self_update else "DCC_UPDATER_STARTUP_DELAY",
                default_delay,
            )), 300))
        except ValueError:
            delay = 0 if startup_self_update else 12

        def wait_for_queue() -> None:
            time.sleep(delay)
            def startup_work(progress):
                with startup_lock:
                    if not startup_state["scheduled"]:
                        return {"updates": [], "containers": []}
                    startup_state["scheduled"] = False
                return run_startup_auto_updates(progress)

            while True:
                with startup_lock:
                    if not startup_state["scheduled"]:
                        return
                started, _state = manager.start("auto_update", startup_work)
                if started:
                    return
                # Startup work waits behind any scan or manual update already in progress.
                time.sleep(1)

        thread = threading.Thread(target=wait_for_queue, name="dcc-updater-startup-queue", daemon=True)
        thread.start()
        return thread

    def validate_container_name(value: Any) -> str:
        name = str(value or "").strip().lstrip("/")
        if not name or len(name) > 128 or any(char in name for char in "\r\n\0"):
            raise ValueError("Nieprawidłowa nazwa kontenera.")
        return name

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
        if request.endpoint in {"health", "login", "static", "set_language"}:
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
        if response.is_json:
            response.set_data(app.json.dumps(localize_payload(response.get_json(), current_language())))
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
                return make_response(translate_text("Nieprawidłowy token bezpieczeństwa. Odśwież stronę.", current_language()), 400)
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
                    language = current_language()
                    session.clear()
                    session["authenticated"] = True
                    session["language"] = language
                    session["csrf_token"] = secrets.token_urlsafe(32)
                    session.permanent = True
                    with language_lock:
                        _atomic_write(language_path, language)
                    login_attempts.pop(remote, None)
                    return redirect(url_for("index"))
                attempts.append(now)
                login_attempts[remote] = attempts
                message = "Nieprawidłowe hasło."
        return render_template("login.html", csrf_token=token, message=message)

    @app.post("/language")
    def set_language():
        if not csrf_valid():
            return translate_text("Nieprawidłowy token bezpieczeństwa. Odśwież stronę.", current_language()), 400
        language = request.form.get("language")
        if language not in {"en", "pl"}:
            return "Unsupported language", 400
        session["language"] = language
        if authenticated():
            with language_lock:
                _atomic_write(language_path, language)
        return redirect(url_for("index" if authenticated() else "login"))

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
        try:
            return jsonify(manager.snapshot(request.args.get("id")))
        except KeyError:
            return jsonify({"error": "Wynik zadania wygasł. Odśwież stan kontenerów."}), 404

    @app.post("/api/scan")
    def scan():
        payload = request.get_json(silent=True) or {}
        defer_panel_update = payload.get("defer_panel_update") is True
        with startup_lock:
            if startup_state["panel_update_started"]:
                return jsonify({"error": "Trwa aktualizacja panelu. Poczekaj na jego ponowne uruchomienie."}), 409
            if startup_state["awaiting_panel_decision"] and not defer_panel_update:
                return jsonify({"error": "Najpierw wybierz Aktualizuj panel albo Nie teraz."}), 409

        def work(progress):
            with startup_lock:
                if startup_state["panel_update_started"]:
                    raise RuntimeError("Trwa aktualizacja panelu. Poczekaj na jego ponowne uruchomienie.")
                if startup_state["awaiting_panel_decision"] and not defer_panel_update:
                    raise RuntimeError("Najpierw wybierz Aktualizuj panel albo Nie teraz.")
                startup_state["awaiting_panel_decision"] = False
                resume_startup = startup_state["auto_updates_pending"]
            if resume_startup:
                return run_startup_auto_updates(progress, skip_panel_check=True, scan_all=True)
            return annotate_auto_update_state(get_service().scan(progress))

        started, state = manager.start("scan", work)
        return jsonify(state), (202 if started else 409)

    @app.post("/api/self-update/check")
    def check_self_update():
        def work(progress):
            with startup_lock:
                startup_state["scheduled"] = False
                startup_state["awaiting_panel_decision"] = False
            result = get_service().check_self_update(progress)
            with startup_lock:
                startup_state["awaiting_panel_decision"] = bool(result.get("update_available"))
            progress(result.get("message", "Sprawdzanie aktualizacji panelu zakończone."))
            return result

        started, state = manager.start("self_update_check", work)
        return jsonify(state), (202 if started else 409)

    @app.post("/api/self-update")
    def update_self():
        def work(progress):
            result = get_service().start_self_update(progress)
            with startup_lock:
                startup_state["awaiting_panel_decision"] = False
                startup_state["panel_update_started"] = bool(result.get("started"))
            progress(result.get("message", "Aktualizacja panelu zakończona."))
            return result

        started, state = manager.start("self_update", work)
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
            containers_after = annotate_auto_update_state(service.scan(progress))
            return {"updates": outcomes, "containers": containers_after}

        started, state = manager.start("update", work)
        return jsonify(state), (202 if started else 409)

    @app.post("/api/auto-update")
    def set_auto_update():
        payload = request.get_json(silent=True) or {}
        try:
            name = validate_container_name(payload.get("name"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"error": "Pole enabled musi mieć wartość true albo false."}), 400

        image = ""
        if enabled:
            container_id = str(payload.get("container_id") or "").strip()
            if not container_id or len(container_id) > 128:
                return jsonify({"error": "Brak prawidłowego identyfikatora kontenera."}), 400
            try:
                service = get_service()
                container = service.client.containers.get(container_id)
            except Exception:
                return jsonify({"error": "Kontener nie jest już dostępny. Odśwież skan."}), 404
            name = str(getattr(container, "name", "") or "").lstrip("/")
            if service._is_self(container):
                return jsonify({"error": "Panel aktualizujący nie może aktualizować samego siebie."}), 400
            if service._is_compose(container):
                return jsonify({
                    "error": "Automatyczna aktualizacja Compose jest wyłączona. Usługi Compose aktualizuj ręcznie po sprawdzeniu zależności i konfiguracji."
                }), 400
            reason = service._unsupported_reason(container)
            if reason:
                return jsonify({"error": reason}), 400
            image = str((container.attrs.get("Config") or {}).get("Image") or "")
            if not image:
                return jsonify({"error": "Kontener nie ma obrazu, dla którego można włączyć aktualizacje."}), 400

        try:
            auto_update_store.set(name, image, enabled)
        except Exception as exc:
            return jsonify({"error": f"Nie udało się zapisać ustawienia ({type(exc).__name__})."}), 500
        message = "Automatyczna aktualizacja przy starcie została włączona." if enabled else "Automatyczna aktualizacja przy starcie została wyłączona."
        return jsonify({"name": name, "enabled": enabled, "message": message})

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

    if startup_auto_updates or startup_self_update:
        app.extensions["dcc_updater_startup_thread"] = schedule_startup_auto_updates()
    return app


app = create_app(
    startup_auto_updates=os.environ.get("DCC_UPDATER_AUTO_UPDATE_ON_START", "0") == "1",
    startup_self_update=os.environ.get("DCC_UPDATER_SELF_UPDATE_ON_START", "0") == "1",
)
