import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.config import Config
from backend.kiri_client import Connector
from backend.storage import MIGRATIONS, Storage
from fixtures import CID, IMAGES, NETWORKS, SECRET, FixtureTransport


class AppTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sockets = {alias: alias for alias in ("local", "offline", "docker", "denied", "partial")}
        self.config = Config(Path(self.temp.name), self.sockets)
        self.connector = Connector(self.sockets, FixtureTransport)
        self.store = Storage(self.config.data_dir)
        self.secret = "a correct test-only password"
        self.credential_hash = generate_password_hash(self.secret)
        self.store.set_password(self.credential_hash)
        self.app = create_app(self.config, connector=self.connector)
        self.web = self.app.test_client()
        self.csrf = self.web.get("/api/session").json["csrf"]

    def change(self, path, body=None, method="POST", origin="http://localhost"):
        return self.web.open(path, method=method, json=body if body is not None else {},
                             headers={"X-CSRF-Token": self.csrf, "Origin": origin})

    def login(self):
        response = self.change("/api/login", {"username": "admin", "password": self.secret})
        self.assertEqual(response.status_code, 200, response.json)
        self.csrf = response.json["csrf"]
        return response

    def profile(self, alias="local", name="Fixture"):
        response = self.change("/api/profiles", {"name": name, "host": "linux", "runtime": "docker", "endpoint": alias})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def test_unconfigured_health_and_session(self):
        with self.assertLogs("backend.app", "WARNING") as startup:
            blank = create_app(Config(self.config.data_dir / "blank", {})).test_client()
        self.assertIn("admin / admin", startup.output[0])
        with blank.get("/") as page:
            self.assertEqual(page.status_code, 200)
        self.assertEqual(blank.get("/healthz").json, {"status": "ok"})
        self.assertFalse(blank.get("/api/session").json["admin_ready"])
        self.assertEqual(blank.get("/api/install/linux").status_code, 401)

    def test_browser_setup_upgrades_an_empty_volume_and_locks_default_credentials(self):
        config = Config(self.config.data_dir / "old-empty", {})
        with patch("backend.storage.MIGRATIONS", MIGRATIONS[:1]):
            Storage(config.data_dir)
        app = create_app(config)
        self.web = app.test_client()
        first = self.web.get("/api/session").json
        self.assertTrue(first["setup_available"])
        self.assertFalse(first["setup_pending"])
        self.csrf = first["csrf"]
        new_account = {"username": "Operator", "password": self.secret, "confirmation": self.secret}
        self.assertEqual(self.change("/api/setup", new_account).json["error"], "setup_expired")
        response = self.change("/api/login", {"username": "admin", "password": "admin"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["setup_pending"])
        self.assertFalse(response.json["authenticated"])
        self.assertNotIn("endpoints", response.json)
        self.assertEqual(self.web.get("/api/install/linux").status_code, 401)
        self.assertEqual(self.change("/api/setup", new_account).json["error"], "csrf")
        self.csrf = response.json["csrf"]
        self.assertEqual(self.change("/api/setup", {**new_account, "password": "short"}).json["error"], "invalid_password")
        self.assertEqual(self.change("/api/setup", {**new_account, "confirmation": "different"}).json["error"], "password_mismatch")
        with self.web.session_transaction() as pending:
            pending["setup_until"] = 0
        self.assertEqual(self.change("/api/setup", new_account).json["error"], "setup_expired")
        response = self.change("/api/login", {"username": "admin", "password": "admin"})
        self.csrf = response.json["csrf"]
        configured = self.change("/api/setup", new_account)
        self.assertTrue(configured.json["authenticated"])
        self.assertFalse(configured.json["setup_available"])
        self.assertFalse(configured.json["setup_pending"])
        self.csrf = configured.json["csrf"]
        self.assertEqual(self.change("/api/setup", new_account).status_code, 409)
        self.assertEqual(self.change("/api/login", {"username": "admin", "password": "admin"}).status_code, 401)
        with self.assertNoLogs("backend.app", "WARNING"):
            self.web = create_app(config).test_client()
        self.csrf = self.web.get("/api/session").json["csrf"]
        self.assertTrue(self.change("/api/login", {"username": "Operator", "password": self.secret}).json["authenticated"])

    def test_default_login_is_unavailable_to_remote_peers_and_public_origin(self):
        config = Config(self.config.data_dir / "blank", {}, bind="0.0.0.0")
        with patch("backend.app.default_gateway", return_value=None):
            remote = create_app(config).test_client()
        peer = {"REMOTE_ADDR": "192.0.2.10"}
        state = remote.get("/api/session", environ_overrides=peer).json
        self.assertFalse(state["setup_available"])
        rejected = remote.post("/api/login", environ_overrides=peer, json={"username": "admin", "password": "admin"},
                               headers={"Origin": "http://localhost", "X-CSRF-Token": state["csrf"],
                                        "X-Forwarded-For": "127.0.0.1"})
        self.assertEqual(rejected.json["error"], "setup_required")
        with self.assertNoLogs("backend.app", "WARNING"):
            public = create_app(Config(config.data_dir, {}, public_origin="https://panel.invalid")).test_client()
        state = public.get("/api/session", base_url="https://panel.invalid").json
        self.assertFalse(state["setup_available"])
        rejected = public.post("/api/login", base_url="https://panel.invalid", json={"username": "admin", "password": "admin"},
                               headers={"Origin": "https://panel.invalid", "X-CSRF-Token": state["csrf"]})
        self.assertEqual(rejected.json["error"], "setup_required")

    def test_upgrade_preserves_existing_login_and_configuration(self):
        config = Config(self.config.data_dir / "old-admin", {})
        with patch("backend.storage.MIGRATIONS", MIGRATIONS[:1]):
            old = Storage(config.data_dir)
            old.update_preferences({"language": "pl"})
            with old.transaction() as conn:
                conn.execute("INSERT INTO admin VALUES (1,?)", (self.credential_hash,))
        self.web = create_app(config).test_client()
        state = self.web.get("/api/session").json
        self.assertTrue(state["admin_ready"])
        self.assertFalse(state["setup_available"])
        self.csrf = state["csrf"]
        self.assertEqual(self.login().json["preferences"]["language"], "pl")
        self.assertEqual(len(list(config.data_dir.glob("config-v1-*.sqlite3"))), 1)

    def test_install_download_is_auth_only(self):
        self.login()
        with self.web.get("/api/install/linux") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertIn(b"sha256sum", response.data)

    def test_auth_origin_cookie_and_revocation(self):
        self.assertEqual(self.web.get("/api/profiles/" + "a" * 32 + "/snapshot").status_code, 401)
        self.assertEqual(self.change("/api/login", {}, origin="https://not-local.invalid").json["error"], "csrf")
        old_csrf = self.csrf
        response = self.login()
        cookie = response.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertNotEqual(old_csrf, self.csrf)
        replay = self.web.get_cookie("dcc_kiri_session").value
        self.assertEqual(self.change("/api/logout").status_code, 200)
        self.web.set_cookie("dcc_kiri_session", replay)
        self.assertFalse(self.web.get("/api/session").json["authenticated"])

    def test_host_header_and_reverse_proxy(self):
        self.assertEqual(self.web.get("/healthz", headers={"Host": "untrusted.invalid"}).status_code, 400)
        app = create_app(Config(self.config.data_dir, {}, public_origin="https://panel.invalid"))
        proxied = app.test_client()
        session = proxied.get("/api/session", base_url="https://panel.invalid")
        self.assertIn("Secure", session.headers["Set-Cookie"])
        self.assertIn("max-age", session.headers["Strict-Transport-Security"])
        self.assertEqual(proxied.get("/healthz", headers={"Host": "127.0.0.1:8796"}).status_code, 200)
        login = proxied.post("/api/login", base_url="https://panel.invalid", json={"username": "admin", "password": self.secret},
                            headers={"Origin": "http://panel.invalid", "X-CSRF-Token": session.json["csrf"],
                                     "X-Forwarded-Proto": "https", "X-Forwarded-Host": "panel.invalid"})
        self.assertEqual(login.status_code, 403)

    def test_login_throttled(self):
        for _ in range(7):
            response = self.change("/api/login", {"username": "admin", "password": "wrong"})
            self.assertEqual(response.json["error"], "credentials")
        self.login()
        hold = self.change("/api/login", {"username": "admin", "password": self.secret})
        self.assertEqual(hold.status_code, 429)
        self.assertEqual(hold.headers["Retry-After"], "60")

    def test_persist_profiles_settings_and_revision(self):
        self.login()
        local, second = self.profile(), self.profile("offline", "Other fixture")
        self.assertEqual(self.change(f"/api/profiles/{second['id']}/active", method="PUT").json["active"], second["id"])
        values = {"language": "pl", "theme": "light", "interval": 15, "onboarded": True}
        self.assertEqual(self.change("/api/preferences", values, "PUT").json["theme"], "light")
        persisted = Storage(self.config.data_dir)
        self.assertEqual(persisted.preferences(), {**values, "active": second["id"]})
        form = {key: local[key] for key in ("host", "runtime", "endpoint", "name", "revision")}
        response = self.change(f"/api/profiles/{local['id']}", {**form, "name": "Renamed"}, "PUT")
        self.assertEqual(response.json["revision"], 2)
        self.assertEqual(self.change(f"/api/profiles/{local['id']}", {"revision": 1}, "DELETE").status_code, 409)
        self.assertEqual(self.change(f"/api/profiles/{second['id']}", {"revision": 1}, "DELETE").status_code, 200)
        self.assertIsNone(persisted.preferences()["active"])
        self.assertEqual(persisted.profiles()[0]["name"], "Renamed")
        self.assertNotIn(self.secret.encode(), persisted.path.read_bytes())

    def test_bad_preference_and_endpoint_inputs(self):
        self.login()
        self.assertEqual(self.change("/api/preferences", {"interval": True}, "PUT").status_code, 400)
        self.assertEqual(self.change("/api/preferences", {"language": []}, "PUT").status_code, 400)
        for alias in ("https://example.invalid/anything", "/var/run/docker.sock", "../kiri", "159.0.2.1"):
            response = self.change("/api/profiles/test", {"name": "invalid", "host": "linux", "runtime": "native", "endpoint": alias})
            self.assertEqual(response.json, {"error": "endpoint_disabled"})

    def test_wrong_engine_offline_permissions_and_partial(self):
        self.login()
        for alias, error in (("offline", "socket_missing"), ("docker", "bad_engine"), ("denied", "permission_denied")):
            profile = self.profile(alias)
            self.assertEqual(self.web.get(f"/api/profiles/{profile['id']}/snapshot").json, {"error": error})
        partial = self.profile("partial")
        value = self.web.get(f"/api/profiles/{partial['id']}/snapshot").json
        self.assertEqual(value["checks"]["volumes"], "unsupported")
        self.assertNotIn("volumes", value["counts"])
        self.assertEqual(value["counts"]["containers"], 6)

    def test_inventory_details_compose_and_monitoring(self):
        self.login()
        prefix = f"/api/profiles/{self.profile()['id']}"
        snapshot = self.web.get(prefix + "/snapshot").json
        self.assertEqual(snapshot["counts"], {"containers": 6, "images": 6, "volumes": 3, "networks": 5, "compose": 2})
        self.assertEqual((snapshot["running"], snapshot["stopped"]), (4, 1))
        self.assertNotIn(SECRET, str(snapshot))
        self.assertEqual(self.web.get(prefix + "/inventory/compose").json["items"][0]["name"], "northstar")
        for kind, key, field, expected in [("containers", CID, "health", "healthy"),
                                           ("images", IMAGES[0]["Id"], "architecture", "amd64"),
                                           ("volumes", "northstar_pg", "containers", ["northstar-web"]),
                                           ("networks", NETWORKS[0]["Id"], "containers", ["northstar-web"])]:
            response = self.web.get(f"{prefix}/inventory/{kind}/{key}")
            self.assertEqual(response.json["item"][field], expected)
            self.assertNotIn(SECRET, response.get_data(as_text=True))
            self.assertNotIn("/private/fixture", response.get_data(as_text=True))
        self.assertGreater(self.web.get(f"{prefix}/containers/{CID}/stats").json["cpu_percent"], 0)
        self.assertEqual(self.web.get(prefix + "/disk").json["image_layers_bytes"], 449593344)
        logs = self.web.get(f"{prefix}/containers/{CID}/logs?tail=50").json["text"]
        self.assertIn("Serving fixture requests", logs)
        self.assertIn("[REDACTED]", logs)
        self.assertNotIn(SECRET, logs)
        self.assertEqual(self.web.get(f"{prefix}/containers/{CID}/logs?tail=1000").status_code, 400)
        self.assertEqual(self.change(f"{prefix}/containers/{CID}/start").status_code, 404)
        self.assertEqual(self.web.get(f"{prefix}/inventory/volumes/%2e%2e").status_code, 400)
