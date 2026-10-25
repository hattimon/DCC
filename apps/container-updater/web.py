"""Password-protected web panel for selected Docker image updates."""

from __future__ import annotations

import hmac
import json
import logging
import os
import posixpath
import shlex
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
from scheduler import ScheduleStore, validate_config
from reports import ReportStore
from notifications import NotificationService
from registry_access import RegistryAccessStore
from compose_manager import SafeComposeManager
from compose_config import ComposeBlocked


class JobManager:
    def __init__(self, on_complete=None) -> None:
        self._lock = threading.RLock()
        self.instance = secrets.token_urlsafe(12)
        self.on_complete = on_complete
        self.mutation_guard = None
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
            if (self.mutation_guard and kind in {'update', 'auto_update', 'self_update', 'schedule', 'compose_execute'}
                    and self.mutation_guard()):
                return False, {**self.snapshot(), 'error': 'compose_admin_intervention'}
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
            finally:
                if self.on_complete:
                    try:
                        self.on_complete(self.snapshot(job_id))
                    except Exception:
                        logging.getLogger(__name__).exception("Could not record completed updater job.")

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
    start_scheduler: bool = False,
) -> Flask:
    app = Flask(__name__, template_folder="templates")
    data_path = Path(data_dir or os.environ.get("DCC_UPDATER_DATA", "/data"))
    data_path.mkdir(parents=True, exist_ok=True)
    password_path = data_path / "admin_password_hash"
    secret_path = data_path / "secret_key"
    auto_update_store = AutoUpdateStore(data_path / "auto_update_containers.json")
    registry_access = RegistryAccessStore(data_path / "registry_credentials.json")
    app.extensions['dcc_updater_registry_access'] = registry_access
    language_path = data_path / "language"
    language_lock = threading.RLock()
    preferences_path = data_path / "preferences.json"
    preferences_lock = threading.RLock()
    preferences = {"theme": "red", "sounds_enabled": True, "sound_style": "soft", "show_unavailable": False}
    themes = ("red", "green", "blue", "navy", "violet", "amber")
    sound_styles = ("soft", "chime", "digital")
    try:
        saved_preferences = json.loads(preferences_path.read_text(encoding="utf-8"))
        if isinstance(saved_preferences, dict):
            if saved_preferences.get("theme") in themes:
                preferences["theme"] = saved_preferences["theme"]
            if isinstance(saved_preferences.get("sounds_enabled"), bool):
                preferences["sounds_enabled"] = saved_preferences["sounds_enabled"]
            if isinstance(saved_preferences.get("show_unavailable"), bool):
                preferences["show_unavailable"] = saved_preferences["show_unavailable"]
            if saved_preferences.get("sound_style") in sound_styles:
                preferences["sound_style"] = saved_preferences["sound_style"]
    except (OSError, ValueError, TypeError):
        pass
    infrastructure_lock = threading.RLock()
    infrastructure_cache = {"expires": 0, "result": {"available": False}}

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
        with preferences_lock:
            appearance = dict(preferences)
        return {"lang": language, "ui": strings(language), "translate": lambda text: translate_text(text, language),
                "preferences": appearance, "themes": themes, "sound_styles": sound_styles}

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

    report_store = ReportStore(data_path / "reports.json")
    notifier = NotificationService(data_path / "notifications.json", report_store)
    report_store.on_event = notifier.enqueue
    manager = JobManager(on_complete=report_store.record_job)
    app.extensions["dcc_updater_reports"] = report_store
    app.extensions["dcc_updater_notifications"] = notifier
    schedule_store = ScheduleStore(data_path / "schedule.json")
    app.extensions["dcc_updater_schedule"] = schedule_store
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
    scan_cache_lock = threading.RLock()
    scan_cache_path = data_path / "last_scan.json"
    scan_settings_path = data_path / "scan_settings.json"
    scan_settings = {"auto_scan_on_refresh": False}
    try:
        saved_settings = json.loads(scan_settings_path.read_text(encoding="utf-8"))
        if isinstance(saved_settings, dict):
            scan_settings["auto_scan_on_refresh"] = saved_settings.get("auto_scan_on_refresh") is True
    except (OSError, ValueError, TypeError):
        pass
    scan_cache: dict[str, Any] = {"containers": [], "scanned_at": None}
    try:
        saved_scan = json.loads(scan_cache_path.read_text(encoding="utf-8"))
        timestamp = saved_scan.get("scanned_at") if isinstance(saved_scan, dict) else None
        saved_containers = saved_scan.get("containers") if isinstance(saved_scan, dict) else None
        if (isinstance(timestamp, (int, float)) and 0 < timestamp < 1e12
                and isinstance(saved_containers, list) and all(isinstance(item, dict) for item in saved_containers)):
            scan_cache.update(containers=saved_containers, scanned_at=timestamp)
    except (OSError, ValueError, TypeError):
        pass

    def remember_scan(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with scan_cache_lock:
            scan_cache.update(containers=json.loads(json.dumps(results)), scanned_at=time.time())
            try:
                _atomic_write(scan_cache_path, json.dumps(scan_cache, ensure_ascii=False))
            except OSError:
                logging.getLogger(__name__).warning("Could not persist the last scan; retaining it in memory.")
        return results

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
        return UpdateService(client, wait_seconds=int(os.environ.get("DCC_UPDATER_HEALTH_TIMEOUT", "60")), registry_auth_loader=registry_access.for_image)

    compose_manager = SafeComposeManager(data_path, get_service, report_store)
    app.extensions['dcc_updater_compose'] = compose_manager
    manager.mutation_guard = compose_manager.store.requires_intervention

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
                report_store.resolve_panel(self_update.get("current_image_id"))
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
            return finish_startup({"updates": [], "containers": remember_scan(annotate_auto_update_state(scanned))})

        progress(f"Kolejka automatyczna: {len(queued)} kontenerów; aktualizacja po jednym kontenerze naraz.")
        outcomes = service.update_selected([str(item["id"]) for item in queued], progress, automatic=True)
        progress("Kolejka zakończona. Ponowne skanowanie kontenerów…")
        updated = remember_scan(annotate_auto_update_state(service.scan(progress)))
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
                    if schedule_store.snapshot()["pending"]:
                        startup_state["auto_updates_pending"] = False
                        return {"updates": [], "containers": []}
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

    def run_scheduled_work(progress, now: float) -> dict[str, Any]:
        pending = schedule_store.snapshot()["pending"]
        if pending:
            if pending["phase"] != "awaiting_restart":
                schedule_store.finish("error", "Poprzednie wykonanie harmonogramu zostało przerwane; nie ponowiono zmian kontenerów.")
                return {"updates": [], "ok": False, "message": schedule_store.snapshot()["last_run"]["message"]}
            if now >= pending.get("deadline", 0):
                schedule_store.finish("error", "Panel nie zakończył aktualizacji w terminie. Kontenerów nie zaktualizowano.")
                report_store.resolve_panel(failed_message=schedule_store.snapshot()["last_run"]["message"])
                return {"updates": [], "ok": False, "message": schedule_store.snapshot()["last_run"]["message"]}
            service = get_service()
            panel = service._find_self_container()
            attrs = getattr(panel, "attrs", {})
            health = (attrs.get("State") or {}).get("Health") or {}
            if (attrs.get("Image") != pending.get("expected_image")
                    or (attrs.get("State") or {}).get("Status") != "running"
                    or (health and health.get("Status") != "healthy")):
                return {"updates": [], "waiting": True, "message": "Oczekiwanie na uruchomienie nowej wersji panelu; kontenery pozostają bez zmian."}
            schedule_store.phase("containers", manager.instance)
            report_store.resolve_panel(attrs.get("Image"))
        else:
            pending = schedule_store.claim(manager.instance, now)
            if pending is None:
                return {"updates": []}
            service = get_service()
        config = pending["config"]
        try:
            if config["panel_first"] and pending["phase"] == "running":
                checked = service.check_self_update(progress)
                if not checked.get("checked"):
                    raise RuntimeError(checked.get("message") or "Nie udało się sprawdzić wersji panelu; harmonogram wstrzymany.")
                if checked.get("update_available"):
                    if not checked.get("supported"):
                        raise RuntimeError(checked.get("message") or "Aktualizacja panelu jest zablokowana; kontenerów nie zaktualizowano.")
                    def prepare(image):
                        schedule_store.phase("awaiting_restart", manager.instance, expected_image=image, deadline=time.time() + 600)
                        report_store.panel_started(image)
                    result = service.start_self_update(progress, prepare_restart=prepare)
                    if result.get("started"):
                        with startup_lock:
                            startup_state["panel_update_started"] = True
                        return result
                    if result.get("update_available") or not result.get("checked"):
                        raise RuntimeError(result.get("message") or "Aktualizacja panelu nie powiodła się; kontenery pozostają bez zmian.")
            schedule_store.phase("containers", manager.instance)
            scanned = remember_scan(annotate_auto_update_state(service.scan(progress)))
            outcomes = []
            if config["action"] in {"update", "update_all"}:
                by_name = {item["name"]: item for item in scanned}
                selected = []
                # All mode is resolved from this run's scan, including services
                # installed after the schedule was saved. The panel stays separate.
                targets = config["targets"] if config["action"] == "update" else [
                    {"name": item["name"], "repository": normalized_repository(item.get("current_image", ""))}
                    for item in scanned if not item.get("is_panel") and (item.get("update_available") or item.get("check_error"))
                ]
                for target in targets:
                    item = by_name.get(target["name"])
                    if item is None or normalized_repository(item.get("current_image", "")) != target["repository"]:
                        outcomes.append({"name": target["name"], "ok": False, "result": "Kontener zniknął lub zmienił repozytorium obrazu; pominięto aktualizację."})
                    elif item.get("is_panel") or item.get("is_compose") or not item.get("supported") or not item.get("auto_update_supported", item.get("supported")):
                        reason = ("Automatyczna aktualizacja Compose jest wyłączona. Usługi Compose aktualizuj ręcznie po sprawdzeniu zależności i konfiguracji."
                                  if item.get("is_compose") else item.get("auto_update_reason") or item.get("message") or "Automatyczna aktualizacja tego kontenera jest zablokowana.")
                        outcomes.append({"name": target["name"], "ok": False, "result": reason})
                    elif item.get("check_error"):
                        outcomes.append({"name": target["name"], "ok": False, "result": item.get("message") or "Nie udało się sprawdzić obrazu kontenera."})
                    elif item.get("update_available"):
                        selected.append(item["id"])
                if selected:
                    outcomes.extend(service.update_selected(selected, progress, automatic=True))
                    scanned = remember_scan(annotate_auto_update_state(service.scan(progress)))
            failed = [item for item in outcomes if not item.get("ok")]
            message = "Harmonogram zakończony."
            if failed:
                message = " | ".join(f"{item['name']}: {item['result']}" for item in failed)[:3000]
            schedule_store.finish("error" if failed else "success", message)
            return {"updates": outcomes, "containers": scanned, "message": message, "ok": not failed, "action": config["action"]}
        except Exception as exc:
            message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else f"Harmonogram zatrzymany ({type(exc).__name__})."
            schedule_store.finish("error", message[:3000])
            report_store.resolve_panel(failed_message=message)
            return {"updates": [], "message": message, "ok": False}

    def scheduler_tick(now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        if not schedule_store.due(manager.instance, moment):
            if compose_manager.store.due(moment):
                started, _state = manager.start('compose_schedule', lambda progress: compose_manager.run_due(moment, progress))
                return started
            return False
        def work(progress):
            try:
                return run_scheduled_work(progress, moment)
            except Exception as exc:
                message = f"Harmonogram zatrzymany ({type(exc).__name__})."
                if schedule_store.snapshot()["pending"]:
                    schedule_store.finish("error", message)
                return {"updates": [], "message": message, "ok": False}
        started, _state = manager.start("schedule", work)
        return started

    app.extensions["dcc_updater_scheduler_tick"] = scheduler_tick
    scheduler_stop = threading.Event()
    app.extensions["dcc_updater_scheduler_stop"] = scheduler_stop

    def schedule_loop() -> None:
        while not scheduler_stop.is_set():
            try:
                scheduler_tick()
            except Exception:
                logging.getLogger(__name__).exception("Scheduled updater work could not be queued.")
            scheduler_stop.wait(5)

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
        with scan_cache_lock:
            cached = json.loads(json.dumps(scan_cache))
            cached.update(scan_settings)
        cached["containers"] = annotate_auto_update_state(cached["containers"])
        return jsonify(cached)

    @app.get('/api/compose/projects')
    def compose_projects():
        return jsonify({'projects': compose_manager.projects(), 'automation_default': 'off'})

    @app.post('/api/compose/discover')
    def compose_discover():
        started, state = manager.start('compose_discover', lambda progress: {
            'projects': compose_manager.discover(progress, check_updates=True)})
        return jsonify(state), (202 if started else 409)

    @app.get('/api/compose/projects/<project>/history')
    def compose_history(project):
        return jsonify({'operations': compose_manager.store.history(project)})

    @app.get('/api/compose/operations/<operation>')
    def compose_operation(operation):
        try:
            return jsonify(compose_manager.store.get(operation))
        except ComposeBlocked as exc:
            return jsonify({'error': str(exc)}), 404

    @app.post('/api/compose/projects/<project>/settings')
    def compose_settings(project):
        try:
            compose_manager.require_project(project)
            return jsonify(compose_manager.store.save_settings(project, request.get_json(silent=True)))
        except (ComposeBlocked, ValueError, TypeError):
            return jsonify({'error': 'compose_settings_invalid'}), 400

    @app.post('/api/compose/projects/<project>/<action>')
    def compose_action(project, action):
        try:
            compose_manager.require_project(project)
        except ComposeBlocked as exc:
            return jsonify({'error': str(exc)}), 404
        if action not in ('analyze', 'dry-run', 'backup'):
            return jsonify({'error': 'compose_action_invalid'}), 400
        def work(progress):
            return (compose_manager.check_backup(project) if action == 'backup' else
                    compose_manager.analyze(project, progress, dry_run=action == 'dry-run'))
        started, state = manager.start('compose_' + action, work)
        return jsonify(state), (202 if started else 409)

    @app.post('/api/compose/operations/<operation>/<action>')
    def compose_operation_action(operation, action):
        try:
            if action in ('approve', 'cancel'):
                if manager.snapshot()['status'] in {'queued', 'running'}:
                    return jsonify({'error': 'project_locked'}), 409
                return jsonify(compose_manager.approve(operation) if action == 'approve' else compose_manager.cancel(operation))
            if action != 'execute':
                return jsonify({'error': 'compose_action_invalid'}), 400
            current = compose_manager.store.get(operation)
            if current['state'] != 'READY' or not current.get('approved') or current.get('dry_run'):
                raise ComposeBlocked('consent_required')
            started, state = manager.start('compose_execute', lambda progress: compose_manager.execute(operation, progress))
            return jsonify(state), (202 if started else 409)
        except ComposeBlocked as exc:
            return jsonify({'error': str(exc)}), 409

    @app.get("/api/infrastructure")
    def infrastructure():
        # Query the Docker daemon, never the updater image's /etc/os-release.
        # This is independent of scans and never contacts an image registry.
        with infrastructure_lock:
            if time.monotonic() < infrastructure_cache["expires"]:
                return jsonify(infrastructure_cache["result"])
            client = None
            try:
                client = service_factory().client if service_factory else docker.from_env(timeout=5)
                info = client.info()
                def field(key):
                    return str(info.get(key) or "").replace("\n", " ").replace("\r", " ")[:200]
                result = {"available": True, "name": field("Name"), "operating_system": field("OperatingSystem"),
                          "os_type": field("OSType"), "architecture": field("Architecture"),
                          "kernel_version": field("KernelVersion"), "docker_version": field("ServerVersion"),
                          "cpus": info.get("NCPU") if type(info.get("NCPU")) is int else None,
                          "memory_bytes": info.get("MemTotal") if type(info.get("MemTotal")) is int else None}
            except Exception:
                result = {"available": False, "message": "Nie udało się odczytać infrastruktury hosta Docker."}
            finally:
                if client is not None and not service_factory:
                    client.close()
            infrastructure_cache.update(result=result, expires=time.monotonic() + (30 if result["available"] else 5))
            return jsonify(result)

    @app.get("/api/preferences")
    def get_preferences():
        with preferences_lock:
            return jsonify(dict(preferences))

    @app.get('/api/registry-access')
    def get_registry_access():
        return jsonify(registry_access.public())

    @app.post('/api/registry-access')
    def save_registry_access():
        payload = request.get_json(silent=True)
        if not isinstance(payload,dict):return jsonify({'error':'Nieprawidłowe dane rejestru.'}),400
        try:
            result = registry_access.change(payload.get('registry'),payload.get('action','save'),payload.get('username',''),payload.get('password',''))
        except (ValueError,OSError) as exc:
            return jsonify({'error':str(exc) if isinstance(exc,ValueError) else 'Nie udało się zapisać danych rejestru.'}),400
        return jsonify({**result,'message':'Dane rejestru zapisane. Ponów skan, aby sprawdzić dostęp.'})

    @app.post('/api/advanced/mount-plan')
    def mount_plan():
        payload = request.get_json(silent=True)
        if not isinstance(payload,dict):return jsonify({'error':'Nieprawidłowe ustawienia dostępu.'}),400
        path = payload.get('path')
        read_capability = payload.get('read_capability',False)
        if (not isinstance(path,str) or not path.startswith('/') or len(path)>500 or any(char in path for char in '\r\n\0,')
                or '..' in path.split('/') or not isinstance(read_capability,bool)):
            return jsonify({'error':'Podaj bezwzględną ścieżkę katalogu Linux bez .. i przecinków.'}),400
        path = posixpath.normpath(path)
        try:
            service = get_service()
            roots = getattr(service,'compose_roots',('/home','/opt','/srv','/mnt','/media','/root'))
            if not any(path.startswith(root.rstrip('/')+'/') for root in roots):
                return jsonify({'error':'Wybierz konkretny podkatalog w dozwolonej lokalizacji Compose, np. /srv/apps/projekt.'}),400
            panel = service._find_self_container()
            if panel is None:raise ValueError('Panel container unavailable')
            name = str(panel.name).lstrip('/')
            labels = ((panel.attrs.get('Config') or {}).get('Labels') or {})
            stamp = time.strftime('%Y%m%d-%H%M%S',time.gmtime())
            backup = f'{name}-access-backup-{stamp}'
            quote = shlex.quote
            inspect = f'umask 077\ndocker inspect {quote(name)} > {quote(backup+".json")}\ndocker inspect --format '+quote('{{json .Mounts}}')+f' {quote(name)}'
            parameter = '--mount '+quote(f'type=bind,source={path},target={path},readonly')
            if read_capability:parameter += ' --cap-add=DAC_READ_SEARCH'
            result = {'name':name,'path':path,'inspect':inspect,'parameter':parameter,'compose':bool(labels.get('com.docker.compose.project')),
                      'read_capability':read_capability}
            if result['compose']:
                files = [item.strip() for item in str(labels.get('com.docker.compose.project.config_files') or '').split(',') if item.strip()]
                working = labels.get('com.docker.compose.project.working_dir')
                service_name = labels.get('com.docker.compose.service')
                if not files or not working or not service_name:raise ValueError('Incomplete Compose metadata')
                base = ['docker','compose','--project-name',labels['com.docker.compose.project'],'--project-directory',working]
                for file in files:base.extend(['--file',file])
                result['apply'] = shlex.join([*base,'up','-d','--no-deps',service_name])
                result['prepare'] = '\n'.join(f'cp -p -- {quote(file)} {quote(file+".dcc-access-before-"+stamp)}' for file in files)
                result['undo'] = '\n'.join(f'cp -p -- {quote(file+".dcc-access-before-"+stamp)} {quote(file)}' for file in files)+'\n'+result['apply']
                result['compose_snippet'] = 'services:\n  '+json.dumps(service_name)+':\n    volumes:\n      - type: bind\n        source: '+json.dumps(path)+'\n        target: '+json.dumps(path)+'\n        read_only: true\n'+('    cap_add:\n      - DAC_READ_SEARCH\n' if read_capability else '')
            else:
                result['prepare'] = f'docker stop --time 30 {quote(name)}\ndocker rename {quote(name)} {quote(backup)}'
                result['undo'] = f'docker stop --time 30 {quote(name)}\ndocker rm {quote(name)}\ndocker rename {quote(backup)} {quote(name)}\ndocker start {quote(name)}'
            return jsonify(result)
        except Exception:
            return jsonify({'error':'Nie udało się odczytać konfiguracji panelu. Sprawdź instrukcję jego instalacji przed zmianą montowań.'}),400

    @app.post("/api/preferences")
    def save_preferences():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Nieprawidłowe ustawienia wyglądu lub dźwięków."}), 400
        with preferences_lock:
            updated = {key: payload.get(key, value) for key, value in preferences.items()}
            if (updated["theme"] not in themes or not isinstance(updated["sounds_enabled"], bool) or not isinstance(updated["show_unavailable"], bool)
                    or updated["sound_style"] not in sound_styles):
                return jsonify({"error": "Nieprawidłowe ustawienia wyglądu lub dźwięków."}), 400
            try:
                _atomic_write(preferences_path, json.dumps(updated))
            except OSError:
                return jsonify({"error": "Nie udało się zapisać ustawień panelu."}), 500
            preferences.update(updated)
            return jsonify({**preferences, "message": "Ustawienia panelu zapisane."})

    @app.post("/api/scan-settings")
    def set_scan_settings():
        enabled = (request.get_json(silent=True) or {}).get("auto_scan_on_refresh")
        if not isinstance(enabled, bool):
            return jsonify({"error": "Pole auto_scan_on_refresh musi mieć wartość true albo false."}), 400
        with scan_cache_lock:
            try:
                _atomic_write(scan_settings_path, json.dumps({"auto_scan_on_refresh": enabled}))
            except OSError:
                return jsonify({"error": "Nie udało się zapisać ustawienia automatycznego skanowania."}), 500
            scan_settings["auto_scan_on_refresh"] = enabled
        return jsonify({"auto_scan_on_refresh": enabled, "message": "Automatyczne skanowanie po odświeżeniu włączone." if enabled else "Automatyczne skanowanie po odświeżeniu wyłączone."})

    @app.get("/api/schedule")
    def get_schedule():
        return jsonify(schedule_store.snapshot())

    @app.get("/api/reports")
    def get_reports():
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            page = 1
        return jsonify(report_store.snapshot(page, request.args.get("issues_only") == "1"))

    @app.get("/api/notifications")
    def get_notifications():
        return jsonify(notifier.public())

    @app.post("/api/notifications")
    def set_notifications():
        try:
            result = notifier.save(request.get_json(silent=True))
        except (ValueError, OSError) as exc:
            return jsonify({"error": str(exc) if isinstance(exc, ValueError) else "Nie udało się zapisać ustawień powiadomień."}), 400
        return jsonify({**result, "message": "Ustawienia powiadomień zapisane."})

    @app.post("/api/notifications/test")
    def test_notifications():
        try:
            payload = request.get_json(silent=True)
            notifier.test(payload.get("channel") if isinstance(payload, dict) else None)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"message": "Powiadomienie testowe wysłane."})

    @app.post("/api/schedule")
    def save_schedule():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Nieprawidłowe ustawienia harmonogramu."}), 400
        try:
            # Bind selected names to their current repositories, just like restart
            # opt-ins. A different image reusing a name never inherits permission.
            targets = payload.get("targets", [])
            if not isinstance(targets, list) or len(targets) > 100:
                raise ValueError("Harmonogram może zawierać najwyżej 100 wybranych kontenerów.")
            resolved = []
            service = None
            for target in targets:
                name = validate_container_name(target.get("name") if isinstance(target, dict) else None)
                if payload.get("enabled") is not True or payload.get("action") != "update":
                    resolved.append({"name": name, "repository": target.get("repository", "")})
                    continue
                service = service or get_service()
                container = service.client.containers.get(name)
                if service._is_self(container) or service._is_compose(container):
                    raise ValueError("Wybierz samodzielne kontenery. Compose wymaga ręcznej aktualizacji, a panel ma osobny przełącznik.")
                blocker = service._unsupported_reason(container)
                if blocker:
                    raise ValueError(blocker)
                dependency_check = getattr(service, "automatic_dependency_blocker", None)
                if callable(dependency_check):
                    blocker = dependency_check(container, service.client.containers.list(all=True))
                    if blocker:
                        raise ValueError(blocker)
                image = str((container.attrs.get("Config") or {}).get("Image") or "")
                if not image:
                    raise ValueError("Kontener nie ma obrazu, dla którego można włączyć aktualizacje.")
                resolved.append({"name": str(container.name).lstrip("/"), "repository": normalized_repository(image)})
            payload = {**payload, "targets": resolved}
            config = validate_config(payload)
            result = schedule_store.save(config)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"Nie udało się zapisać harmonogramu ({type(exc).__name__})."}), 400
        return jsonify({**result, "message": "Harmonogram zapisany."})

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
            return remember_scan(annotate_auto_update_state(get_service().scan(progress)))

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
            result = get_service().start_self_update(progress, prepare_restart=report_store.panel_started)
            if not result.get("started") and result.get("update_available"):
                report_store.resolve_panel(failed_message=result.get("message"))
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
            containers_after = remember_scan(annotate_auto_update_state(service.scan(progress)))
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
            list_containers = getattr(service.client.containers, "list", None)
            if callable(list_containers):
                reason = service.automatic_dependency_blocker(container, list_containers(all=True))
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
    if start_scheduler:
        thread = threading.Thread(target=schedule_loop, name="dcc-updater-scheduler", daemon=True)
        thread.start()
        app.extensions["dcc_updater_scheduler_thread"] = thread
        app.extensions["dcc_updater_notification_thread"] = notifier.start()
    return app


app = create_app(
    startup_auto_updates=os.environ.get("DCC_UPDATER_AUTO_UPDATE_ON_START", "0") == "1",
    startup_self_update=os.environ.get("DCC_UPDATER_SELF_UPDATE_ON_START", "0") == "1",
    start_scheduler=True,
)
