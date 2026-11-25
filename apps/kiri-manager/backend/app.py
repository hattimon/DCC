"""HTTP API for local settings and authenticated Kiri inventory."""
import os
import re
import secrets

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from . import resources
from .config import ROOT, VERSION, Config
from .kiri_client import Connector, KiriError, validate_key
from .security import (UNSAFE_NAME, LoginGate, begin_setup, csrf_token, default_gateway,
                       enforce_access, local_setup_peer, setup_pending, valid_password, valid_username)
from .storage import DEFAULT_ADMIN_USERNAME, SESSION_TTL, Storage

HOSTS = {"linux", "wsl", "macos"}
RUNTIMES = {"docker", "kiri", "native"}
PREFS = {"language", "theme", "interval", "onboarded"}
PROFILE_FIELDS = {"name", "host", "runtime", "endpoint"}
INTERVALS = {0, 15, 30, 60, 120}
ID = re.compile(r"[a-f0-9]{32}")


def json_object(fields, *, required=()):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or body.keys() - fields or set(required) - body.keys():
        raise KiriError("bad_input", 400)
    return body


def token_error(error):
    response = jsonify(error=error.code)
    if error.code == "login_limited":
        response.headers["Retry-After"] = "60"
    return response, error.status


def create_app(config=None, *, connector=None, demo=False):
    config = config or Config.from_env(os.environ)
    store = Storage(config.data_dir)
    connector = connector if connector is not None else Connector(config.sockets)
    gate = LoginGate()
    gateway = default_gateway() if config.bind == "0.0.0.0" and not config.public_origin else None
    app = Flask(__name__, static_folder=str(ROOT / "frontend" / "assets"), static_url_path="/assets")
    app.config.update(
        SECRET_KEY=secrets.token_bytes(32), TRUSTED_HOSTS=config.trusted_hosts,
        MAX_CONTENT_LENGTH=8192, SESSION_COOKIE_NAME="dcc_kiri_session",
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=bool(config.public_origin), SESSION_COOKIE_PATH="/",
        SESSION_REFRESH_EACH_REQUEST=False, PERMANENT_SESSION_LIFETIME=SESSION_TTL,
    )
    if not demo and not config.public_origin and store.credentials() is None:
        app.logger.warning("First sign-in from the host: admin / admin. Set your own password in the browser.")

    @app.before_request
    def authorize():
        if request.routing_exception is not None:
            raise request.routing_exception
        if request.path.startswith("/api/"):
            enforce_access(store, config.public_origin)

    @app.after_request
    def headers(response):
        response.headers.update({
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                                       "img-src 'self'; connect-src 'self'; font-src 'self'; "
                                       "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cross-Origin-Resource-Policy": "same-origin",
        })
        if not request.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store"
        if config.public_origin:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    app.register_error_handler(KiriError, token_error)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error={400: "bad_request", 404: "not_found", 405: "method",
                              413: "request_too_large"}.get(error.code, "server_error")), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        # A traceback or upstream error may contain paths, credentials or engine data.
        app.logger.error("Unhandled panel error of type %s", type(error).__name__)
        return jsonify(error="server_error"), 500

    def profile(profile_id):
        row = store.profile(profile_id) if ID.fullmatch(profile_id) else None
        if row is None:
            raise KiriError("profile_missing", 404)
        return row

    def profile_values(extra=()):
        data = json_object(PROFILE_FIELDS | set(extra), required=PROFILE_FIELDS | set(extra))
        if any(not isinstance(data[key], str) for key in PROFILE_FIELDS):
            raise KiriError("bad_input", 400)
        name = data["name"].strip()
        if (not 1 <= len(name) <= 64 or UNSAFE_NAME.search(name)
                or data["host"] not in HOSTS or data["runtime"] not in RUNTIMES):
            raise KiriError("bad_input", 400)
        if data["endpoint"] not in connector.sockets:
            raise KiriError("endpoint_disabled", 409)
        data["name"] = name
        return data

    def revision_value(body):
        value = body.get("revision")
        if type(value) is not int or not 1 <= value < 2**31:
            raise KiriError("bad_input", 400)
        return value

    def local_setup_available():
        return not config.public_origin and local_setup_peer(gateway)

    def session_payload():
        admin_ready = store.credentials() is not None
        setup_available = not admin_ready and local_setup_available()
        payload = {"authenticated": bool(g.sid), "admin_ready": admin_ready,
                   "setup_available": setup_available, "setup_pending": setup_available and setup_pending(),
                   "csrf": csrf_token(), "version": VERSION}
        if g.sid:
            payload.update(preferences=store.preferences(), profiles=store.profiles(),
                           endpoints=sorted(connector.sockets), demo=demo)
        return jsonify(payload)

    def sign_in(password_hash):
        token = secrets.token_urlsafe(32)
        if not store.add_session(token, password_hash):
            raise KiriError("credentials", 401)
        if g.sid:
            store.revoke_session(g.sid)
        session.clear()
        session.permanent = True
        session["sid"] = g.sid = token
        return session_payload()

    @app.get("/")
    def index():
        return send_from_directory(ROOT / "frontend", "index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/api/session")
    def session_info():
        return session_payload()

    @app.get("/api/install/linux")
    def linux_setup():
        return send_from_directory(ROOT, "setup-kiri-linux.sh", as_attachment=True, mimetype="text/plain")

    @app.post("/api/login")
    def login():
        body = json_object({"username", "password"}, required={"username", "password"})
        username, password = body["username"], body["password"]
        if not valid_username(username) or not valid_password(password, minimum=1):
            raise KiriError("bad_input", 400)
        with gate.allow():
            credentials = store.credentials()
            if credentials is None:
                if not local_setup_available():
                    raise KiriError("setup_required", 403)
                if (username, password) != (DEFAULT_ADMIN_USERNAME, "admin"):
                    raise KiriError("credentials", 401)
                begin_setup()
                return session_payload()
            password_hash = credentials["password_hash"]
            if not check_password_hash(password_hash, password) or username != credentials["username"]:
                raise KiriError("credentials", 401)
            return sign_in(password_hash)

    @app.post("/api/setup")
    def setup():
        if not local_setup_available():
            raise KiriError("setup_required", 403)
        if store.credentials() is not None:
            raise KiriError("setup_complete", 409)
        if not setup_pending():
            raise KiriError("setup_expired", 403)
        fields = {"username", "password", "confirmation"}
        body = json_object(fields, required=fields)
        username, password = body["username"], body["password"]
        if not valid_username(username):
            raise KiriError("invalid_username", 400)
        if not valid_password(password):
            raise KiriError("invalid_password", 400)
        if body["confirmation"] != password:
            raise KiriError("password_mismatch", 400)
        with gate.allow():
            password_hash = generate_password_hash(password)
            if not store.set_password(password_hash, username=username):
                raise KiriError("setup_complete", 409)
            return sign_in(password_hash)

    @app.post("/api/logout")
    def logout():
        json_object(set())
        store.revoke_session(g.sid)
        g.sid = None
        session.clear()
        return session_payload()

    @app.put("/api/preferences")
    def preferences():
        changes = json_object(PREFS)
        validators = {
            "language": lambda value: isinstance(value, str) and value in {"en", "pl"},
            "theme": lambda value: isinstance(value, str) and value in {"dark", "light"},
            "interval": lambda value: type(value) is int and value in INTERVALS,
            "onboarded": lambda value: type(value) is bool,
        }
        if any(not validators[key](value) for key, value in changes.items()):
            raise KiriError("bad_input", 400)
        return jsonify(store.update_preferences(changes))

    @app.post("/api/profiles")
    def create_profile():
        result = store.create_profile(profile_values())
        if result is None:
            raise KiriError("profile_limit", 409)
        return jsonify(result), 201

    @app.put("/api/profiles/<profile_id>")
    def update_profile(profile_id):
        profile(profile_id)
        values = profile_values(("revision",))
        if not store.update_profile(profile_id, revision_value(values), values):
            raise KiriError("profile_conflict", 409)
        return jsonify(profile(profile_id))

    @app.delete("/api/profiles/<profile_id>")
    def delete_profile(profile_id):
        profile(profile_id)
        body = json_object({"revision"}, required={"revision"})
        if not store.delete_profile(profile_id, revision_value(body)):
            raise KiriError("profile_conflict", 409)
        return jsonify(ok=True)

    @app.put("/api/profiles/<profile_id>/active")
    def active_profile(profile_id):
        json_object(set())
        if not ID.fullmatch(profile_id) or not store.activate(profile_id):
            raise KiriError("profile_missing", 404)
        return jsonify(active=profile_id)

    @app.post("/api/profiles/test")
    def test_profile():
        values = profile_values()
        with connector.connect(values["endpoint"]) as kiri:
            overview = resources.snapshot(kiri)
        return jsonify(engine=overview["engine"], checks=overview["checks"], at=overview["at"])

    @app.get("/api/profiles/<profile_id>/status")
    def status(profile_id):
        with connector.connect(profile(profile_id)["endpoint"]) as kiri:
            return jsonify(engine=kiri.identity)

    @app.get("/api/profiles/<profile_id>/snapshot")
    def snapshot(profile_id):
        with connector.connect(profile(profile_id)["endpoint"]) as kiri:
            return jsonify(resources.snapshot(kiri))

    @app.get("/api/profiles/<profile_id>/inventory/<kind>")
    def inventory(profile_id, kind):
        if kind not in {*resources.DETAIL, "compose"}:
            raise KiriError("not_found", 404)
        with connector.connect(profile(profile_id)["endpoint"]) as kiri:
            resource = "containers" if kind == "compose" else kind
            payload = resources.INVENTORY[resource](kiri.read(resource))
            return jsonify(items=resources.projects(payload) if kind == "compose" else payload,
                           engine=kiri.identity)

    @app.get("/api/profiles/<profile_id>/inventory/<kind>/<key>")
    def details(profile_id, kind, key):
        if kind not in resources.DETAIL:
            raise KiriError("not_found", 404)
        validate_key(kind, key)
        with connector.connect(profile(profile_id)["endpoint"]) as kiri:
            value = kiri.details(kind, key)
            if not isinstance(value, dict):
                raise KiriError("bad_response")
            item = resources.DETAIL[kind](value)
            if kind == "volumes":
                try:
                    item["containers"] = [
                        row["name"] for entry in resources.rows(kiri.volume_users(key))
                        if (row := resources.container(entry))["name"]
                    ][:150]
                except KiriError as error:
                    if error.code in {"bad_engine", "socket_changed"}:
                        raise
                    item["containers"] = None
                    item["attachments_error"] = error.code
            return jsonify(item=item)

    @app.get("/api/profiles/<profile_id>/containers/<key>/stats")
    def stats(profile_id, key):
        validate_key("containers", key)
        with connector.connect(profile(profile_id)["endpoint"]) as kiri:
            return jsonify(resources.stats(kiri.container_stats(key)))

    @app.get("/api/profiles/<profile_id>/containers/<key>/logs")
    def logs(profile_id, key):
        validate_key("containers", key)
        tail = request.args.get("tail", "100")
        if not re.fullmatch(r"[1-9][0-9]{0,2}", tail) or int(tail) > 200:
            raise KiriError("bad_input", 400)
        with connector.connect(profile(profile_id)["endpoint"]) as kiri:
            content_type, body = kiri.container_logs(key, int(tail))
            return jsonify(text=resources.sanitized_logs(content_type, body))

    @app.get("/api/profiles/<profile_id>/disk")
    def disk(profile_id):
        with connector.connect(profile(profile_id)["endpoint"]) as kiri:
            return jsonify(resources.disk_usage(kiri.read("disk")))

    return app
