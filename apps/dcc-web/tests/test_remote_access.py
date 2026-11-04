"""Remote ingress and controller regressions without hosted zrok credentials."""
import hashlib
import json
import secrets
import time
from unittest.mock import Mock, patch

import unittest
from test_web import WebTests as WebFixture
from remote_access import DIGEST, RemoteError, SETTINGS, name_origin


class RemoteAccessTests(unittest.TestCase):
    setup_fixture = WebFixture.setUp
    request = WebFixture.request
    confirmation = WebFixture.confirmation
    wait = WebFixture.wait
    wait_scan = WebFixture.wait_scan

    def setUp(self):
        self.setup_fixture()
        self.remote = self.app.extensions["dcc_remote_access"]
        self.remote.available = True
        self.user = self.state.rows("SELECT id FROM users")[0]["id"]
        self.host = "fixture-dcc.share.zrok.io"
        self.peer = "172.28.19.2"
        self.origin = "https://" + self.host
        self.route = dict(host=self.host, peer=self.peer, origin=self.origin, owner=self.user,
                          nonce=secrets.token_urlsafe(32), lease=secrets.token_urlsafe(32), verified=False)

    def tunnel(self, path, method="GET", *, host=None, peer=None, headers=None, **kwargs):
        return self.client.open(path, method=method, base_url="http://" + (host or self.host),
                                environ_overrides={"dcc.remote_ingress": True, "REMOTE_ADDR": peer or self.peer},
                                headers=headers or {}, **kwargs)

    def enable_fixture_mfa(self):
        self.state.execute("INSERT INTO mfa VALUES(?,?,?,?,?,?,?)",
                           (self.user, b"test-only", 1, -1, "[]", 0, ""))

    def test_ingress_requires_exact_host_peer_mfa_and_verified_https(self):
        self.assertEqual(self.tunnel("/api/health").status_code, 400)
        self.remote.route = self.route
        self.assertEqual(self.tunnel("/api/health").status_code, 503)
        self.enable_fixture_mfa()
        for host, peer in (("localhost", self.peer), (self.host+":443", self.peer), (self.host, "172.28.19.9")):
            self.assertEqual(self.tunnel("/api/health", host=host, peer=peer,
                                         headers={"X-Forwarded-For":self.peer, "X-Forwarded-Proto":"https"}).status_code, 400)
        self.assertEqual(self.tunnel("/login").status_code, 503)
        probe = self.tunnel("/api/health", headers={"X-DCC-Remote-Probe":self.route["nonce"]})
        self.assertEqual(probe.status_code, 200)
        self.assertEqual(probe.headers["X-DCC-Remote-Probe"], self.route["nonce"])
        self.route["verified"] = True
        self.assertEqual(self.tunnel("/api/bootstrap").status_code, 401)
        self.client.delete_cookie("dcc_web_session", domain=self.host)
        login = self.tunnel("/login")
        self.assertIn("Strict-Transport-Security", login.headers)
        self.assertIn("Secure", login.headers["Set-Cookie"])
        self.assertIn("HttpOnly", login.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", login.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/health", base_url=self.origin).status_code, 400)
        self.app.config["DCC_REMOTE_BLOCKED_DIGESTS"] = {DIGEST}
        self.assertEqual(self.tunnel("/login").status_code, 503)
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_remote_login_recovery_code_csrf_role_and_rate_limit(self):
        self.enable_fixture_mfa()
        code = "0AA1100A00ABCCDD"
        self.state.execute("UPDATE mfa SET recovery=? WHERE user_id=?",
                           (json.dumps([hashlib.sha256(code.encode()).hexdigest()]), self.user))
        self.route["verified"] = True
        self.remote.route = self.route
        self.tunnel("/login")
        with self.client.session_transaction(base_url="http://" + self.host) as value:
            csrf = value["csrf"]
        credentials = {"username":"review-admin", "password":"ReviewPassword-44-long", "csrf":csrf, "otp":code}
        self.assertEqual(self.tunnel("/login","POST", data=credentials).status_code, 403)
        self.assertEqual(self.tunnel("/login","POST", data=credentials, headers={"Origin":"https://example.com"}).status_code, 403)
        self.assertEqual(self.tunnel("/login","POST", data=credentials, headers={"Origin":self.origin}).status_code, 302)
        self.assertEqual(self.tunnel("/api/bootstrap").status_code, 200)
        with self.client.session_transaction(base_url="http://" + self.host) as value:
            csrf = value["csrf"]
        self.assertEqual(self.tunnel("/api/admin/remote-access/disable","POST", json={},
                                     headers={"Origin":self.origin,"X-CSRF-Token":csrf}).status_code, 403)
        self.assertEqual(self.tunnel("/api/logout","POST", json={}, headers={"Origin":self.origin}).status_code, 403)
        self.assertEqual(self.tunnel("/api/logout","POST", json={},
                                     headers={"Origin":self.origin,"X-CSRF-Token":csrf}).status_code, 200)
        self.assertFalse(self.state.mfa.verify(self.user, code))
        for _ in range(8):
            self.state.execute("INSERT INTO attempts VALUES(?,?)", ("remote-access-login",time.time()))
        self.tunnel("/login")
        with self.client.session_transaction(base_url="http://" + self.host) as value:
            csrf = value["csrf"]
        self.assertEqual(self.tunnel("/login","POST", peer=self.peer, data=dict(credentials,csrf=csrf),
                                     headers={"Origin":self.origin,"X-Forwarded-For":"192.0.2.28"}).status_code, 429)

    def test_activation_requires_mfa_and_confirmations_and_keeps_secrets_private(self):
        response = self.request("admin/remote-access/enable", {})
        self.assertEqual(response.status_code, 409)
        confirmation = self.confirmation("remote-access.enable", "dcc-remote-access", "workspace")
        response = self.request("admin/remote-access/enable", {"confirmation":confirmation})
        self.assertEqual(response.status_code, 400)
        self.assertIn("2FA", response.json["error"])
        self.remote.save({"identity":"fixture-secret-identity", "origin":self.origin})
        row = self.state.rows("SELECT data FROM settings WHERE user_id=?", (SETTINGS,))[0]
        self.assertNotIn("fixture-secret-identity", row["data"])
        self.remote.available = False
        response = self.client.get("/api/admin/remote-access")
        self.assertNotIn("fixture-secret-identity", response.get_data(as_text=True))
        self.assertEqual(response.json["state"], "not-installed")

    def test_catalog_includes_managed_entry_and_preserves_category_order(self):
        result = self.client.get("/api/catalog?category=DCC").json
        apps = [app for app in result["apps"] if app["name"]=="DCC Remote Access"]
        self.assertEqual(len(apps), 1)
        self.assertEqual(result["categories"][:4], ["all","installed","DCC","AI"])
        self.assertEqual(self.request("install/preview", {"app":apps[0]["id"]}).status_code, 400)
        catalog = self.app.extensions["dcc_catalogs"]
        container = {"ID":"fixture", "Names":self.remote.name}
        def installed():
            return catalog.view(category="installed", containers=[container], managed_remote_name=self.remote.name)["apps"]
        self.assertEqual(installed(), [])
        container["Labels"] = "io.dcc.remote-access=" + self.remote.owner
        self.assertEqual([app["id"] for app in installed()], [apps[0]["id"]])

    def test_renamed_local_profile_can_install_and_see_remote_access_in_store(self):
        # Imported or renamed installations need not retain the original 'local' ID.
        self.state.save_profile("local-docker-2", {
            "name": "Local", "kind": "local", "permissions": ["read", "install"]
        })
        self.state.execute("DELETE FROM profiles WHERE id=?", ("local",))
        original_profiles = self.state.profiles()
        selected = "local-docker-2"
        response = self.client.get(f"/api/catalog?profile={selected}&category=DCC")
        self.assertEqual(response.status_code, 200)
        apps = [app for app in response.json["apps"] if app["name"] == "DCC Remote Access"]
        self.assertEqual(len(apps), 1)
        self.assertEqual(response.json["categories"][:4], ["all", "installed", "DCC", "AI"])

        container = {"ID": "remote-fixture", "Names": self.remote.name,
                     "Labels": "io.dcc.remote-access=" + self.remote.owner}
        with patch("fixtures.FakeBackend.containers", return_value=[container]):
            scanned = self.wait_scan(self.request("catalog/installed", {"profile": selected}))
        self.assertEqual(scanned["status"], "success")
        installed = self.client.get(f"/api/catalog?profile={selected}&category=installed").json
        self.assertEqual([app["id"] for app in installed["apps"] if app["name"] == "DCC Remote Access"],
                         [apps[0]["id"]])

        approval = self.confirmation("remote-access.install", "dcc-remote-access", "workspace")
        with patch.object(self.remote, "perform", return_value={"accepted": True}) as perform:
            self.wait(self.request("admin/remote-access/install", {"profile": selected, "confirmation": approval}))
            perform.assert_called_once()
        self.assertEqual(self.state.profiles(), original_profiles)

    def test_remote_access_refuses_unauthorized_or_nonlocal_profile(self):
        self.state.save_profile("readonly", {"name": "Readonly Local", "kind": "local",
                                               "permissions": ["read"]})
        self.state.save_profile("remote-host", {"name": "Other Docker", "kind": "tcp",
                                                  "endpoint": "tcp://192.0.2.4:2376",
                                                  "permissions": ["read", "install"]})
        self.state.save_profile("remote-context", {"name": "Other Context", "kind": "local",
                                                     "context": "external", "permissions": ["read", "install"]})
        for selected, expected_status in (("readonly", 403), ("remote-host", 409),
                                          ("remote-context", 409)):
            with self.subTest(selected=selected):
                catalog = self.client.get(f"/api/catalog?profile={selected}&category=DCC").json
                remote = [app for app in catalog["apps"] if app["name"] == "DCC Remote Access"]
                self.assertEqual(bool(remote), selected == "readonly")
                approval = self.confirmation("remote-access.install", "dcc-remote-access", "workspace")
                with patch.object(self.remote, "perform") as perform:
                    response = self.request("admin/remote-access/install", {
                        "profile": selected, "confirmation": approval
                    })
                    self.assertEqual(response.status_code, expected_status, response.json)
                    perform.assert_not_called()

    def test_provider_namespace_and_name_conflict(self):
        self.assertEqual(name_origin("fixture-dcc", {"namespaceToken":"public","namespaceName":"share.zrok.io"}), self.origin)
        with self.assertRaises(RemoteError):
            name_origin("fixture-dcc", {"namespaceToken":"public","namespaceName":"attacker.invalid"})
        self.remote.save({"identity":"fixture"})
        container = Mock()
        with patch.object(self.remote,"restore"), patch.object(self.remote,"stop"), \
                patch.object(self.remote,"reservation",return_value={"reserved":True}):
            with self.assertRaisesRegex(RemoteError,"existing reservation"):
                self.remote.configure(container, {"name":"fixture-dcc"})

    def test_configure_encrypts_enrollment_and_retains_verified_reservation(self):
        identity = b"fixture-archive-with-secret"
        container = Mock()
        reservation = {"reserved":True, "namespaceName":"share.zrok.io", "namespaceToken":"public"}
        with patch.object(self.remote,"restore"), patch.object(self.remote,"stop") as stop, \
                patch.object(self.remote,"reservation",side_effect=[None,reservation]), \
                patch.object(self.remote,"command",side_effect=[b"",identity,b""]) as command:
            self.remote.configure(container, {"name":"fixture-dcc","account_token":"MockAccountToken"})
        saved = self.remote.saved()
        self.assertEqual(saved["origin"], self.origin)
        self.assertEqual(self.state.vault.decrypt(saved["identity"].encode()), identity)
        self.assertNotIn("MockAccountToken", str(command.call_args_list[0].args))
        self.assertEqual(command.call_args_list[0].kwargs["data"], b"MockAccountToken\n")
        stop.assert_called_once_with(container)

    def test_existing_share_prevents_activation_and_revocation_closes_ingress(self):
        self.enable_fixture_mfa()
        self.remote.save({"identity":"fixture","origin":self.origin,"name":"fixture-dcc"})
        reservation = {"reserved":True, "namespaceName":"share.zrok.io", "namespaceToken":"public", "shareToken":"fixture"}
        container = Mock()
        with patch.object(self.remote,"restore"), patch.object(self.remote,"stop") as stop, \
                patch.object(self.remote,"reservation",return_value=reservation):
            with self.assertRaisesRegex(RemoteError,"still has a share"):
                self.remote.enable(container, self.user, self.remote.epoch)
            stop.assert_called_once_with(container)
        self.route["verified"] = True
        self.remote.route = self.route
        self.state.execute("DELETE FROM mfa WHERE user_id=?", (self.user,))
        self.assertEqual(self.tunnel("/login").status_code, 503)
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_probe_rechecks_reconnection_and_blocklist_fails_closed(self):
        self.enable_fixture_mfa()
        self.remote.route = self.route
        snapshots = []
        def sleep(delay):
            snapshots.append((self.remote.tunnel, self.route["verified"]))
            if len(snapshots) == 3:
                self.remote.route = None
        with patch.object(self.remote,"probe",side_effect=[False,True,False]), patch("remote_access.time.sleep",side_effect=sleep):
            self.remote.monitor(self.route)
        self.assertEqual(snapshots, [("connecting",False),("active",True),("reconnecting",False)])
        blocklist = self.state.directory / "dcc-remote-blocked-digests.txt"
        blocklist.write_text("malformed", encoding="ascii")
        self.assertTrue(self.remote.blocked())
        blocklist.write_text(DIGEST+"\n", encoding="ascii")
        self.assertTrue(self.remote.blocked())


del WebFixture
