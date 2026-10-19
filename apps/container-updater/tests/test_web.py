import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DCC_UPDATER_DATA", tempfile.mkdtemp(prefix="dcc-updater-tests-"))

from web import create_app


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

    def test_api_post_requires_csrf_token(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        response = self.client.post("/api/scan")
        self.assertEqual(response.status_code, 400)

    def test_password_change_checks_length_and_current_password(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        csrf = self._csrf("/")
        short = self.client.post("/api/password", json={"old_password": password, "new_password": "short"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(short.status_code, 400)
        changed = self.client.post("/api/password", json={"old_password": password, "new_password": "a-much-better-password"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(changed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
