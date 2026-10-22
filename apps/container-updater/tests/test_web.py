import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DCC_UPDATER_DATA", tempfile.mkdtemp(prefix="dcc-updater-tests-"))

from updater import UpdateService
from web import AutoUpdateStore, JobManager, create_app


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(self.temp.name, print_credentials=False)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def _csrf(self, page="/login"):
        response = self.client.get(page)
        self.assertEqual(response.status_code, 200)
        import re
        match = re.search(rb'name="csrf-token" content="([^"]+)"', response.data)
        if not match:
            match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        return match.group(1).decode()

    def test_panel_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        api = self.client.get("/api/containers")
        self.assertEqual(api.status_code, 401)

    def test_login_requires_csrf_token_and_valid_password(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        rejected = self.client.post("/login", data={"password": password})
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.post("/login", data={"csrf_token": csrf, "password": password})
        self.assertEqual(accepted.status_code, 302)
        panel = self.client.get("/")
        self.assertEqual(panel.status_code, 200)
        self.assertIn(b"Docker", panel.data)
        self.assertIn("Compose wymaga ręcznej aktualizacji".encode(), panel.data)
        self.assertIn("Tylko ręcznie (Compose)".encode(), panel.data)

    def test_api_post_requires_csrf_token(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        response = self.client.post("/api/scan")
        self.assertEqual(response.status_code, 400)

    def test_panel_exposes_manual_self_update_controls(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        response = self.client.get("/")
        self.assertIn("Sprawdź aktualizację panelu".encode(), response.data)
        self.assertIn("Aktualizuj panel".encode(), response.data)

    def test_self_update_actions_require_authentication_and_csrf(self):
        self.assertEqual(self.client.post("/api/self-update/check").status_code, 401)
        self.assertEqual(self.client.post("/api/self-update").status_code, 401)
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        self.assertEqual(self.client.post("/api/self-update/check").status_code, 400)
        self.assertEqual(self.client.post("/api/self-update").status_code, 400)

    def test_password_change_checks_length_and_current_password(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        csrf = self._csrf("/")
        short = self.client.post("/api/password", json={"old_password": password, "new_password": "short"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(short.status_code, 400)
        changed = self.client.post("/api/password", json={"old_password": password, "new_password": "a-much-better-password"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(changed.status_code, 200)

    def test_auto_update_preferences_persist_and_are_bound_to_image_repository(self):
        path = Path(self.temp.name) / "auto_update_containers.json"
        store = AutoUpdateStore(path)
        store.set("media", "ghcr.io/example/media:1.0", True)
        self.assertTrue(store.is_enabled("media", "ghcr.io/example/media:1.1"))
        self.assertFalse(store.is_enabled("media", "ghcr.io/example/other:1.1"))

        reloaded = AutoUpdateStore(path)
        self.assertTrue(reloaded.is_enabled("media", "ghcr.io/example/media:2.0"))
        reloaded.set("media", "", False)
        self.assertFalse(store.is_enabled("media", "ghcr.io/example/media:1.0"))

    def test_corrupt_auto_update_settings_fail_closed_without_overwriting_file(self):
        path = Path(self.temp.name) / "auto_update_containers.json"
        path.write_text("{invalid", encoding="utf-8")
        store = AutoUpdateStore(path)
        self.assertEqual(store.snapshot(), {})
        with self.assertRaises(ValueError):
            store.set("media", "ghcr.io/example/media:1.0", True)
        self.assertEqual(path.read_text(encoding="utf-8"), "{invalid")

    def test_auto_update_api_requires_login_and_saves_only_supported_containers(self):
        container = SimpleNamespace(
            id="a1b2c3d4",
            name="media",
            attrs={
                "Config": {"Image": "ghcr.io/example/media:1.0", "Labels": {}},
                "HostConfig": {"NetworkMode": "bridge", "AutoRemove": False},
                "NetworkSettings": {"Networks": {"bridge": {}}},
                "State": {"Status": "running"},
            },
        )

        class Containers:
            def get(self, identifier):
                if identifier in {container.id, container.name}:
                    return container
                raise KeyError(identifier)

        service = UpdateService(SimpleNamespace(containers=Containers()), catalog_loader=lambda: [])
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(directory, service_factory=lambda: service, print_credentials=False)
            app.config["TESTING"] = True
            client = app.test_client()
            password = app.extensions["dcc_updater_initial_password"]
            login_page = client.get("/login")
            import re
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', login_page.data).group(1).decode()
            client.post("/login", data={"csrf_token": csrf, "password": password})
            panel = client.get("/")
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', panel.data).group(1).decode()

            enabled = client.post(
                "/api/auto-update",
                json={"name": "media", "container_id": container.id, "enabled": True},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(enabled.status_code, 200)
            store = app.extensions["dcc_updater_auto_updates"]
            self.assertTrue(store.is_enabled("media", "ghcr.io/example/media:1.0"))

            disabled = client.post(
                "/api/auto-update",
                json={"name": "media", "enabled": False},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(disabled.status_code, 200)
            self.assertFalse(store.is_enabled("media", "ghcr.io/example/media:1.0"))

    def test_compose_auto_update_is_rejected(self):
        container = SimpleNamespace(
            id="compose-id",
            name="media",
            attrs={
                "Config": {
                    "Image": "ghcr.io/example/media:1.0",
                    "Labels": {"com.docker.compose.project": "media"},
                },
            },
        )

        class Containers:
            def get(self, _identifier):
                return container

        service = UpdateService(SimpleNamespace(containers=Containers()), catalog_loader=lambda: [])
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            app = create_app(directory, service_factory=lambda: service, print_credentials=False)
            app.config["TESTING"] = True
            client = app.test_client()
            password = app.extensions["dcc_updater_initial_password"]
            login_page = client.get("/login")
            import re
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', login_page.data).group(1).decode()
            client.post("/login", data={"csrf_token": csrf, "password": password})
            panel = client.get("/")
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', panel.data).group(1).decode()
            response = client.post(
                "/api/auto-update",
                json={"name": "media", "container_id": container.id, "enabled": True},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("Compose", response.get_json()["error"])

    def test_job_manager_never_runs_two_container_jobs_at_once(self):
        manager = JobManager()
        entered = threading.Event()
        release = threading.Event()

        def work(_progress):
            entered.set()
            release.wait(2)
            return []

        started, _state = manager.start("update", work)
        self.assertTrue(started)
        self.assertTrue(entered.wait(1))
        second_started, _state = manager.start("auto_update", lambda _progress: [])
        self.assertFalse(second_started)
        release.set()
        deadline = time.monotonic() + 2
        while manager.snapshot()["status"] != "done" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(manager.snapshot()["status"], "done")

    def test_startup_checks_and_updates_panel_even_when_other_auto_updates_are_off(self):
        checked = threading.Event()
        calls = []

        class FakeClient:
            def ping(self):
                calls.append("ping")

        class FakeService:
            client = FakeClient()

            def check_self_update(self, _progress):
                calls.append("check")
                return {"checked": True, "update_available": True, "supported": True}

            def start_self_update(self, _progress):
                calls.append("start")
                return {"checked": True, "update_available": True, "started": True, "message": "started"}

            def scan(self, _progress):
                raise AssertionError("Other automatic updates are disabled in this test.")

        def run_startup(_manager, kind, work):
            self.assertEqual(kind, "auto_update")
            work(lambda _message: None)
            checked.set()
            return True, {}

        with patch.dict(os.environ, {"DCC_UPDATER_SELF_UPDATE_STARTUP_DELAY": "0"}), \
                patch.object(JobManager, "start", run_startup):
            create_app(
                self.temp.name,
                service_factory=FakeService,
                print_credentials=False,
                startup_auto_updates=False,
                startup_self_update=True,
            )
            self.assertTrue(checked.wait(2))

        self.assertEqual(calls, ["ping", "check", "start"])


if __name__ == "__main__":
    unittest.main()
