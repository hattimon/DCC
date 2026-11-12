"""Remote ingress and controller regressions without hosted zrok credentials."""
import hashlib
import io
import ipaddress
import json
import secrets
import tarfile
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import unittest
from test_web import WebTests as WebFixture
from remote_access import (DIGEST, ENVIRONMENT, IMAGE, LABEL, PANEL_NETWORK_POOL,
                           PANEL_NETWORK_PREFIX, RemoteAccess, RemoteError, SETTINGS, UPDATE_CONTROL_LABEL,
                           PANEL_TARGET, ShareConflict, UPDATE_TICKET, WAIT, name_origin, unshare)


def enrollment_archive():
    buffer = io.BytesIO()
    data = b'{"ziti_identity":"fixture-env","zrok_token":"FixtureAccount123"}'
    member = tarfile.TarInfo(".zrok2/environment.json")
    member.size = len(data)
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


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
        self.host = "fixture-dcc.shares.zrok.io"
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

    def recovery_fixture(self, *, persistent=True):
        self.enable_fixture_mfa()
        self.remote.save({"identity": "fixture", "origin": self.origin, "name": "fixture-dcc"})
        panel = SimpleNamespace(id="panel", attrs={"Image": "sha256:" + "b" * 64})
        self.remote.route = self.route
        self.remote.remember_recovery(self.user, self.remote.epoch, panel.attrs["Image"],
                                      resume_after_restart=persistent, resume_after_update=True)
        self.remote.route = None
        sidecar = Mock(attrs={"State": {"Running": False, "Status": "exited"}})
        client = Mock()
        self.remote.client_factory = lambda: client
        return panel, sidecar, client

    def test_long_internet_outage_recovers_without_permanently_stopping_tunnel(self):
        self.enable_fixture_mfa()
        self.route["verified"] = True
        self.remote.route = self.route
        self.remote.last_connection = time.time()
        snapshots = []

        def sleep(delay):
            snapshots.append((self.remote.tunnel, self.route["verified"], delay))
            if len(snapshots) == 11:
                self.remote.route = None

        with patch.object(self.remote, "probe", side_effect=[False] * 10 + [True]), \
                patch.object(self.remote, "stop") as stop, \
                patch("remote_access.time", SimpleNamespace(sleep=sleep, time=time.time, monotonic=time.monotonic)):
            self.remote.monitor(self.route)
        stop.assert_not_called()
        self.assertTrue(all(value[:2] == ("reconnecting", False) for value in snapshots[:10]))
        self.assertEqual(snapshots[-1][:2], ("active", True))
        self.assertTrue(all(value[2] <= 30 for value in snapshots))

    def test_startup_recovery_requires_saved_opt_in_and_keeps_public_gate_closed(self):
        panel, sidecar, client = self.recovery_fixture()
        restarted = RemoteAccess(self.app, self.state, client_factory=lambda: client)
        restarted.available = True
        with patch("remote_access.local_container", return_value=panel), \
                patch.object(restarted, "container", return_value=sidecar), \
                patch.object(restarted, "validate_container"), \
                patch.object(restarted, "restore"), \
                patch.object(restarted, "reservation", return_value={
                    "reserved": True, "namespaceName": "shares.zrok.io", "namespaceToken": "public"}), \
                patch.object(restarted, "command"), patch("remote_access.threading.Thread"):
            sidecar.attrs["NetworkSettings"] = {"Networks": {restarted.ingress: {"IPAddress": self.peer}}}
            self.assertTrue(restarted.recover_once())
        self.assertIsNotNone(restarted.route)
        self.assertFalse(restarted.route["verified"])
        self.assertTrue(restarted.route["resume_after_update"])
        self.remote.route = restarted.route
        self.assertEqual(self.tunnel("/login").status_code, 503)
        restarted.available = False
        self.assertNotIn("identity", restarted.status())

    def test_legacy_install_and_session_only_recovery_do_not_enable_after_restart(self):
        panel, sidecar, client = self.recovery_fixture(persistent=False)
        self.assertIsNotNone(self.remote.recovery)
        self.assertNotIn("recovery", self.remote.saved())
        restarted = RemoteAccess(self.app, self.state, client_factory=lambda: client)
        restarted.available = True
        with patch.object(restarted, "enable") as enable:
            self.assertFalse(restarted.recover_once())
        enable.assert_not_called()

    def test_recovery_retries_provider_outage_with_backoff_and_preserves_consent(self):
        panel, sidecar, client = self.recovery_fixture()
        with patch("remote_access.local_container", return_value=panel), \
                patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"), \
                patch.object(self.remote, "enable", side_effect=[RemoteError("Provider unavailable"), None]) as enable, \
                patch("remote_access.time.monotonic", return_value=100):
            self.assertFalse(self.remote.recover_once())
            self.assertFalse(self.remote.recover_once())
            self.assertEqual(enable.call_count, 1)
            self.assertEqual(self.remote.tunnel, "reconnecting")
            self.assertTrue(self.remote.saved()["recovery"]["resume_after_restart"])
            with patch("remote_access.time.monotonic", return_value=111):
                self.assertTrue(self.remote.recover_once())
        self.assertEqual(enable.call_count, 2)
        self.assertEqual(self.remote.recovery_failures, 0)

    def test_disabled_access_revokes_persistent_recovery_before_stopping_container(self):
        panel, sidecar, client = self.recovery_fixture()
        with patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "enable") as enable:
            self.remote.perform("disable", {}, self.user, self.remote.epoch)
            self.assertIsNone(self.remote.recovery)
            self.assertNotIn("recovery", self.remote.saved())
            self.assertFalse(self.remote.recover_once())
        enable.assert_not_called()

    def test_security_revocation_prevents_recovery_and_forgets_startup_consent(self):
        self.recovery_fixture()
        self.state.execute("DELETE FROM mfa WHERE user_id=?", (self.user,))
        with patch.object(self.remote, "enable") as enable:
            self.assertFalse(self.remote.recover_once())
        enable.assert_not_called()
        self.assertEqual(self.remote.tunnel, "blocked")
        self.assertNotIn("recovery", self.remote.saved())

    def test_pending_updater_handoff_and_changed_image_cannot_be_bypassed_by_startup(self):
        panel, sidecar, client = self.recovery_fixture()
        self.state.execute("INSERT INTO settings VALUES(?,?)", (UPDATE_TICKET, self.state.encode_profile({"proof": "fixture"})))
        with patch("remote_access.local_container", return_value=panel), \
                patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"), patch.object(self.remote, "enable") as enable:
            self.assertFalse(self.remote.recover_once())
            self.state.execute("DELETE FROM settings WHERE user_id=?", (UPDATE_TICKET,))
            panel.attrs["Image"] = "sha256:" + "c" * 64
            self.assertFalse(self.remote.recover_once())
        enable.assert_not_called()

    def test_unexpected_sidecar_exit_enters_recovery_without_revoking_access(self):
        panel, sidecar, client = self.recovery_fixture()
        self.remote.route = self.route
        with patch.object(self.remote, "container", return_value=sidecar), patch.object(self.remote, "probe") as probe:
            self.remote.monitor(self.route)
        probe.assert_not_called()
        self.assertIsNone(self.remote.route)
        self.assertEqual(self.remote.tunnel, "reconnecting")
        self.assertTrue(self.remote.saved()["recovery"]["resume_after_restart"])

    def test_disable_during_recovery_cannot_restore_saved_intent(self):
        panel, sidecar, client = self.recovery_fixture()

        def disabled(*args, **kwargs):
            self.remote.perform("disable", {}, self.user, self.remote.epoch)
            raise RemoteError("Public access was disabled during startup.")

        with patch("remote_access.local_container", return_value=panel), \
                patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"), patch.object(self.remote, "enable", side_effect=disabled):
            self.assertFalse(self.remote.recover_once())
        self.assertIsNone(self.remote.recovery)
        self.assertEqual(self.remote.tunnel, "disabled")
        self.assertNotIn("recovery", self.remote.saved())

    def test_updater_handoff_preserves_restart_consent_and_binds_it_to_replacement(self):
        original, sidecar, client = self.recovery_fixture()
        self.route.update(verified=True, resume_after_update=True)
        self.remote.route = self.route
        sidecar.attrs["State"]["Running"] = True
        target = "sha256:" + "a" * 64
        replacement = SimpleNamespace(id="replacement", attrs={"Image": target})
        client.images.get.return_value.attrs = {
            "RepoTags": ["ghcr.io/hattimon/dcc-web:0.2.9"],
            "Config": {"Labels": {UPDATE_CONTROL_LABEL: "1"}},
        }

        def enabled(*args, **kwargs):
            self.remote.route = self.route

        with patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"), patch.object(self.remote, "enable", side_effect=enabled), \
                patch("remote_access.threading.Thread") as worker:
            self.assertTrue(self.remote.pause_for_update(client, original, "proof", target))
            self.assertTrue(self.remote.resume_after_update(client, replacement, "proof"))
            worker.call_args.kwargs["target"]()
        recovery = self.remote.saved()["recovery"]
        self.assertEqual(recovery["panel_image"], target)
        self.assertTrue(recovery["resume_after_restart"])
        self.assertTrue(recovery["resume_after_update"])

    def test_verified_update_handoff_retries_failed_launch_and_survives_another_restart(self):
        original, sidecar, client = self.recovery_fixture()
        self.route.update(verified=True, resume_after_update=True)
        self.remote.route = self.route
        sidecar.attrs["State"]["Running"] = True
        target = "sha256:" + "a" * 64
        replacement = SimpleNamespace(id="replacement", attrs={"Image": target})
        client.images.get.return_value.attrs = {
            "RepoTags": ["ghcr.io/hattimon/dcc-web:0.2.9"],
            "Config": {"Labels": {UPDATE_CONTROL_LABEL: "1"}},
        }
        with patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"), \
                patch.object(self.remote, "enable", side_effect=RemoteError("Provider unavailable")), \
                patch("remote_access.threading.Thread") as worker:
            self.assertTrue(self.remote.pause_for_update(client, original, "proof", target))
            self.assertTrue(self.remote.resume_after_update(client, replacement, "proof"))
            worker.call_args.kwargs["target"]()
        self.assertEqual(self.remote.tunnel, "reconnecting")
        self.assertEqual(self.remote.saved()["recovery"]["panel_image"], target)
        restarted = RemoteAccess(self.app, self.state, client_factory=lambda: client)
        restarted.available = True
        with patch("remote_access.local_container", return_value=replacement), \
                patch.object(restarted, "container", return_value=sidecar), \
                patch.object(restarted, "validate_container"), patch.object(restarted, "enable") as enable:
            self.assertTrue(restarted.recover_once())
        enable.assert_called_once_with(sidecar, self.user, restarted.epoch, resume_after_update=True)

    def test_recovery_refuses_modified_sidecar_isolation(self):
        panel, sidecar, client = self.recovery_fixture()
        with patch("remote_access.local_container", return_value=panel), \
                patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container", side_effect=RemoteError("Isolation changed")), \
                patch.object(self.remote, "enable") as enable:
            self.assertFalse(self.remote.recover_once())
        enable.assert_not_called()

    def test_manual_enable_preserves_explicit_restart_consent_on_provider_failure(self):
        panel, sidecar, client = self.recovery_fixture()

        def enabled(*args, **kwargs):
            self.remote.route = self.route

        with patch("remote_access.local_container", return_value=panel), \
                patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "enable", side_effect=RemoteError("Provider unavailable")) as enable:
            with self.assertRaises(RemoteError):
                self.remote.perform("enable", {"resume_after_restart": False}, self.user, self.remote.epoch)
            self.assertIsNone(self.remote.recovery)
            self.assertNotIn("recovery", self.remote.saved())
            with self.assertRaises(RemoteError):
                self.remote.perform("enable", {"resume_after_restart": True, "resume_after_update": True},
                                    self.user, self.remote.epoch)
            self.assertTrue(self.remote.saved()["recovery"]["resume_after_restart"])
            self.assertTrue(self.remote.saved()["recovery"]["resume_after_update"])
            enable.side_effect = enabled
            self.remote.perform("enable", {"resume_after_restart": True}, self.user, self.remote.epoch)
        self.assertTrue(self.remote.saved()["recovery"]["resume_after_restart"])

    def test_stopped_tunnel_can_issue_an_update_ticket_with_existing_consent(self):
        original, sidecar, client = self.recovery_fixture()
        target = "sha256:" + "a" * 64
        client.images.get.return_value.attrs = {
            "RepoTags": ["ghcr.io/hattimon/dcc-web:0.3.3"],
            "Config": {"Labels": {UPDATE_CONTROL_LABEL: "1"}},
        }
        with patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"):
            self.assertTrue(self.remote.pause_for_update(client, original, "proof", target))
        sidecar.stop.assert_not_called()
        ticket = self.state.decode_profile(self.state.rows("SELECT data FROM settings WHERE user_id=?", (UPDATE_TICKET,))[0]["data"])
        self.assertEqual(ticket["target"], target)
        self.assertTrue(ticket["recovery"]["resume_after_restart"])

    def test_legacy_update_adopts_only_persisted_consent_from_matching_backup(self):
        original, _, client = self.recovery_fixture()
        original.id = "b" * 64
        original.attrs.update(
            Name="/dcc-backup-" + original.id[:10], State={"Status": "exited"},
            Config={"Image": "ghcr.io/hattimon/dcc-web:0.3.2", "Labels": {UPDATE_CONTROL_LABEL: "1"}},
            Mounts=[{"Destination": "/data", "Type": "volume", "Source": "/volumes/web", "RW": True}])
        replacement = SimpleNamespace(id="c" * 64, attrs=dict(
            original.attrs, Image="sha256:" + "c" * 64,
            Config={"Image": "ghcr.io/hattimon/dcc-web:0.3.3", "Labels": {UPDATE_CONTROL_LABEL: "1"}}))
        client.containers.get.return_value = original
        matching_mounts = replacement.attrs.pop("Mounts")
        self.assertFalse(self.remote.adopt_update_recovery(client, replacement, original.id))
        replacement.attrs["Mounts"] = matching_mounts
        self.assertTrue(self.remote.adopt_update_recovery(client, replacement, original.id))
        self.assertEqual(self.remote.saved()["recovery"]["panel_image"], replacement.attrs["Image"])
        self.assertIsNone(self.remote.route)
        with self.remote.intent:
            self.remote.forget_recovery()
        self.assertFalse(self.remote.adopt_update_recovery(client, replacement, original.id))

    def test_reconfiguration_cancels_recovery_and_leaves_access_disabled(self):
        panel, sidecar, client = self.recovery_fixture()
        with patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "configure"), patch.object(self.remote, "enable") as enable:
            self.remote.perform("configure", {"name": "other-name"}, self.user, self.remote.epoch)
            self.assertFalse(self.remote.recover_once())
        enable.assert_not_called()
        self.assertIsNone(self.remote.recovery)
        self.assertNotIn("recovery", self.remote.saved())

    def test_update_resume_requires_consent_and_accepts_only_the_expected_image_once(self):
        self.enable_fixture_mfa()
        self.route["verified"] = True
        self.remote.route = self.route
        sidecar = Mock(attrs={"State": {"Running": True}})
        target = "sha256:" + "a" * 64
        client = Mock()
        client.images.get.return_value.attrs = {
            "RepoTags": ["ghcr.io/hattimon/dcc-web:0.2.9"],
            "Config": {"Labels": {UPDATE_CONTROL_LABEL: "1"}},
        }
        original = SimpleNamespace(id="original", attrs={"Image": "sha256:old"})
        replacement = SimpleNamespace(id="replacement", attrs={"Image": target})
        with patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"), patch.object(self.remote, "enable") as enable, \
                patch("remote_access.threading.Thread") as worker:
            self.assertFalse(self.remote.pause_for_update(client, original, "proof", target))
            sidecar.stop.assert_not_called()
            self.route["resume_after_update"] = True
            self.assertTrue(self.remote.pause_for_update(client, original, "proof", target))
            sidecar.stop.assert_called_once_with(timeout=12)
            self.assertIsNone(self.remote.route)
            foreign = SimpleNamespace(id="foreign", attrs={"Image": "sha256:foreign"})
            self.assertFalse(self.remote.resume_after_update(client, foreign, "proof"))
            self.assertFalse(self.remote.resume_after_update(client, replacement, "wrong"))
            self.assertTrue(self.remote.resume_after_update(client, replacement, "proof"))
            worker.call_args.kwargs["target"]()
            enable.assert_called_once_with(sidecar, self.user, self.remote.epoch, resume_after_update=True)
            self.assertFalse(self.remote.resume_after_update(client, original, "proof"))
            self.remote.route = self.route
            self.assertTrue(self.remote.pause_for_update(client, original, "other-proof", target))
            with patch("remote_access.time.time", return_value=time.time() + 601):
                self.assertFalse(self.remote.resume_after_update(client, replacement, "other-proof"))
            self.assertFalse(self.remote.resume_after_update(client, replacement, "other-proof"))

    def test_panel_network_subnet_avoids_docker_ranges_and_configured_hosts(self):
        candidates = tuple(PANEL_NETWORK_POOL.subnets(new_prefix=PANEL_NETWORK_PREFIX))
        first = candidates[int(self.remote.owner[:8], 16) % len(candidates)]
        host = str(first.network_address + 2)
        self.state.save_profile("remote-lan", {
            "name": "Remote LAN", "kind": "ssh", "host": host, "port": 22,
            "permissions": ["read"],
        })
        existing = SimpleNamespace(name="occupied-range", attrs={"IPAM": {"Config": [
            {"Subnet": "198.18.0.0/24"},
        ]}})
        client = Mock()
        client.networks.list.return_value = [existing]

        subnet = ipaddress.ip_network(self.remote.panel_network_subnet(client))

        self.assertTrue(subnet.subnet_of(PANEL_NETWORK_POOL))
        self.assertFalse(subnet.overlaps(ipaddress.ip_network("198.18.0.0/24")))
        self.assertNotIn(ipaddress.ip_address(host), subnet)

    def test_legacy_ingress_network_migrates_even_before_remote_profiles_exist(self):
        panel = SimpleNamespace(id="panel-container")
        container = Mock()
        container.id = "remote-sidecar"
        container.attrs = {"Config": {"Labels": {LABEL: self.remote.owner}},
                           "State": {"Running": True}}
        owner_id = self.remote.owner

        class FakeNetwork:
            def __init__(self, name, subnet, containers=None):
                self.name = name
                self.id = "network-" + name
                self.attrs = {
                    "Labels": {LABEL: owner_id}, "Driver": "bridge", "Internal": True,
                    "IPAM": {"Config": [{"Subnet": subnet}]},
                    "Containers": dict(containers or {}),
                }

            def reload(self):
                return None

            def disconnect(self, value, force=False):
                self.attrs["Containers"].pop(value.id, None)

            def connect(self, value, aliases=None):
                self.attrs["Containers"][value.id] = {"Aliases": aliases or []}

            def remove(self):
                networks.pop(self.name, None)

        old = FakeNetwork(self.remote.ingress, "192.168.0.0/20", {
            panel.id: {"Aliases": ["dcc-remote-panel"]}, container.id: {"Aliases": []},
        })
        networks = {old.name: old}
        created = []
        client = Mock()
        client.containers.get.return_value = container

        def get_network(name):
            if name not in networks:
                from docker.errors import NotFound
                raise NotFound("missing network")
            return networks[name]

        def list_networks():
            return list(networks.values())

        def create_network(name, **kwargs):
            pools = kwargs["ipam"].get("Config")
            subnet = pools[0]["Subnet"]
            value = FakeNetwork(name, subnet)
            networks[name] = value
            created.append(value)
            return value

        client.networks.get.side_effect = get_network
        client.networks.list.side_effect = list_networks
        client.networks.create.side_effect = create_network
        with patch.object(self.remote, "validate_container"), \
                patch("remote_access.local_container", return_value=panel):
            repaired = self.remote.repair_panel_network(client)

        self.assertTrue(repaired)
        self.assertTrue(container.stop.called)
        self.assertEqual(len(created), 1)
        subnet = ipaddress.ip_network(created[0].attrs["IPAM"]["Config"][0]["Subnet"])
        self.assertFalse(subnet.overlaps(ipaddress.ip_network("192.168.0.0/20")))
        self.assertIn(panel.id, created[0].attrs["Containers"])
        self.assertIn(container.id, created[0].attrs["Containers"])
        self.assertEqual(created[0].attrs["Containers"][panel.id]["Aliases"], ["dcc-remote-panel"])
        self.assertEqual(self.remote.network_error, "")

    def test_interrupted_network_migration_recreates_missing_ingress(self):
        panel = SimpleNamespace(id="panel-container")
        container = Mock()
        container.id = "remote-sidecar"
        container.attrs = {
            "Config": {
                "Labels": {LABEL: self.remote.owner}, "Image": IMAGE, "User": "2171:2171",
                "Entrypoint": ["/bin/sh", "-c"], "Cmd": [WAIT],
                "Env": [f"{key}={value}" for key, value in ENVIRONMENT.items()],
            },
            "HostConfig": {
                "ReadonlyRootfs": True, "CapDrop": ["ALL"], "CapAdd": [], "PortBindings": {},
                "Devices": [], "DeviceRequests": [], "LogConfig": {"Type": "none"},
                "RestartPolicy": {"Name": "no"}, "SecurityOpt": ["no-new-privileges:true"],
            },
            "NetworkSettings": {"Networks": {self.remote.egress: {}}},
            "Mounts": [], "State": {"Running": False},
        }

        class FakeNetwork:
            def __init__(self, name, subnet):
                self.name = name
                self.attrs = {
                    "Labels": {LABEL: self_owner}, "Driver": "bridge", "Internal": True,
                    "IPAM": {"Config": [{"Subnet": subnet}]}, "Containers": {},
                }

            def connect(self, value, aliases=None):
                self.attrs["Containers"][value.id] = {"Aliases": aliases or []}

        self_owner = self.remote.owner
        created = []
        client = Mock()
        client.containers.get.return_value = container
        from docker.errors import NotFound
        client.networks.get.side_effect = NotFound("missing ingress")
        client.networks.list.return_value = []

        def create_network(name, **kwargs):
            subnet = kwargs["ipam"].get("Config")[0]["Subnet"]
            value = FakeNetwork(name, subnet)
            created.append(value)
            return value

        client.networks.create.side_effect = create_network

        repaired = self.remote.repair_panel_network(client, panel=panel)

        self.assertTrue(repaired)
        self.assertEqual(len(created), 1)
        subnet = ipaddress.ip_network(created[0].attrs["IPAM"]["Config"][0]["Subnet"])
        self.assertTrue(subnet.subnet_of(PANEL_NETWORK_POOL))
        self.assertIn(panel.id, created[0].attrs["Containers"])
        self.assertIn(container.id, created[0].attrs["Containers"])

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

    def test_can_poll_workspace_tunnel_jobs_without_default_local_profile(self):
        self.state.save_profile("custom-local", {
            "name": "Local Docker", "kind": "local", "permissions": ["read", "install"],
        })
        self.state.execute("DELETE FROM profiles WHERE id=?", ("local",))
        self.enable_fixture_mfa()
        with self.client.session_transaction() as session:
            session["mfa_verified"] = True
        actions = ("configure", "enable", "restart")
        codes = [f"{number:016X}" for number in range(1, len(actions) + 1)]
        self.state.execute("UPDATE mfa SET recovery=? WHERE user_id=?", (
            json.dumps([hashlib.sha256(code.encode()).hexdigest() for code in codes]), self.user,
        ))
        local_https = {
            "base_url": "https://localhost",
            "environ_overrides": {"REMOTE_ADDR": "192.0.2.20"},
        }
        with patch.object(self.remote, "perform", return_value={"accepted": True}) as perform:
            for action, code in zip(actions, codes):
                with self.subTest(action=action):
                    approval = self.confirmation("remote-access." + action, "dcc-remote-access", "workspace")
                    response = self.request("admin/remote-access/" + action, {
                        "profile": "custom-local", "confirmation": approval,
                        "current_password": "ReviewPassword-44-long", "otp": code,
                    }, **local_https)
                    self.assertEqual(response.status_code, 202, response.json)
                    path = "/api/jobs/" + response.json["id"]
                    poll = self.client.get(path, **local_https)
                    self.assertEqual(poll.status_code, 200, poll.json)
                    self.assertEqual(self.wait(response), {"accepted": True})
                    self.assertEqual(perform.call_args.args[0], action)
        self.assertEqual(perform.call_count, len(actions))
        self.assertEqual(self.app.test_client().get(path).status_code, 401)
        self.state.execute("UPDATE users SET role='viewer' WHERE id=?", (self.user,))
        self.assertEqual(self.client.get(path, **local_https).status_code, 403)

    def test_provider_namespace_and_name_conflict(self):
        for zone in ("share.zrok.io", "shares.zrok.io"):
            self.assertEqual(name_origin("fixture-dcc", {"namespaceToken": "public", "namespaceName": zone}),
                             "https://fixture-dcc." + zone)
        for name, token, zone in (
            ("fixture-dcc", "public", "attacker.invalid"),
            ("fixture-dcc", "public", "shares.zrok.io.attacker.invalid"),
            ("fixture-dcc", "private", "shares.zrok.io"),
            ("fixture.dcc", "public", "shares.zrok.io"),
        ):
            with self.subTest(name=name, namespace=zone), self.assertRaises(RemoteError):
                name_origin(name, {"namespaceToken": token, "namespaceName": zone})
        self.remote.save({"identity":"fixture"})
        container = Mock()
        with patch.object(self.remote,"restore"), patch.object(self.remote,"stop"), \
                patch.object(self.remote,"reservation",return_value={"reserved":True}):
            with self.assertRaisesRegex(RemoteError,"existing reservation"):
                self.remote.configure(container, {"name":"fixture-dcc"})

    def test_pending_hosted_reservation_can_be_completed_without_token_or_duplicate_name(self):
        self.remote.save({"identity": "fixture", "pending_name": "fixture-dcc"})
        self.remote.available = False
        status = self.remote.status()
        self.assertEqual(status["pending_name"], "fixture-dcc")
        self.assertTrue(status["enrolled"])
        self.assertNotIn("identity", status)
        reservation = {"reserved": True, "namespaceName": "shares.zrok.io", "namespaceToken": "public"}
        container = Mock()
        with patch.object(self.remote, "restore"), patch.object(self.remote, "stop"), \
                patch.object(self.remote, "reservation", return_value=reservation) as lookup, \
                patch.object(self.remote, "command") as command:
            with self.assertRaisesRegex(RemoteError, "pending reservation"):
                self.remote.configure(container, {"name": "different-name"})
            self.remote.configure(container, {"name": ""})
        lookup.assert_called_with(container, "fixture-dcc")
        command.assert_not_called()
        self.assertEqual(self.remote.saved(), {
            "identity": "fixture", "name": "fixture-dcc", "origin": self.origin,
        })
        self.assertIsNone(self.remote.status()["pending_name"])

    def test_configure_encrypts_enrollment_and_retains_verified_reservation(self):
        identity = b"fixture-archive-with-secret"
        container = Mock()
        reservation = {"reserved":True, "namespaceName":"shares.zrok.io", "namespaceToken":"public"}
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
        reservation = {"reserved":True, "namespaceName":"shares.zrok.io", "namespaceToken":"public", "shareToken":"fixture"}
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

    def test_stale_share_recovery_releases_exact_token_and_reopens_existing_name(self):
        panel, sidecar, client = self.recovery_fixture()
        sidecar.attrs["NetworkSettings"] = {"Networks": {self.remote.ingress: {"IPAddress": self.peer}}}
        reserved = {"reserved": True, "namespaceName": "shares.zrok.io", "namespaceToken": "public"}
        token = "StaleShare123"
        occupied = dict(reserved, shareToken=token)
        listed = {"shares": [dict(shareToken=token, envZId="fixture-env", shareMode="public",
                                   backendMode="proxy", target=PANEL_TARGET)]}
        with patch("remote_access.local_container", return_value=panel), \
                patch.object(self.remote, "container", return_value=sidecar), \
                patch.object(self.remote, "validate_container"), \
                patch.object(self.remote, "restore", return_value=enrollment_archive()), \
                patch.object(self.remote, "reservation", side_effect=[occupied] * 5 + [reserved]), \
                patch.object(self.remote, "command", side_effect=[json.dumps(listed).encode(), b""]) as command, \
                patch("remote_access.time.sleep"), patch("remote_access.threading.Thread"), \
                patch("remote_access.public_health", return_value=(502, "")), \
                patch("remote_access.unshare", return_value=200) as remove:
            self.assertTrue(self.remote.recover_once())
        remove.assert_called_once_with("fixture-env", "FixtureAccount123", token)
        self.assertIn(b"fixture-dcc " + self.host.encode(), command.call_args.kwargs["data"])
        self.assertEqual(self.remote.route["origin"], self.origin)
        self.assertFalse(self.remote.route["verified"])

    def test_reclaim_does_not_remove_foreign_reachable_or_changed_share(self):
        self.enable_fixture_mfa()
        token = "StaleShare123"
        config = {"name": "fixture-dcc", "origin": self.origin}
        listed = dict(shareToken=token, envZId="fixture-env", shareMode="public", backendMode="proxy", target=PANEL_TARGET)
        for share, status, current in ((dict(listed, envZId="foreign-env"), 502, token),
                                       (dict(listed, target="http://other:8080"), 502, token),
                                       (listed, 200, token), (listed, 502, "NewShare123")):
            with self.subTest(share=share, status=status, current=current), \
                    patch.object(self.remote, "command", return_value=json.dumps({"shares": [share]}).encode()), \
                    patch.object(self.remote, "saved_reservation", return_value={"shareToken": current}), \
                    patch("remote_access.public_health", return_value=(status, "")), \
                    patch("remote_access.unshare") as remove:
                with self.assertRaises(ShareConflict):
                    self.remote.reclaim_stale_share(Mock(), config, token, enrollment_archive(), self.user, self.remote.epoch)
                remove.assert_not_called()

    def test_unshare_uses_exact_provider_request(self):
        with patch("remote_access.http.client.HTTPSConnection") as https:
            connection = https.return_value
            connection.getresponse.return_value.status = 200
            self.assertEqual(unshare("fixture-env", "FixtureAccount123", "StaleShare123"), 200)
            https.assert_called_once_with("api-v2.zrok.io", timeout=10)
            method, path, payload, headers = connection.request.call_args.args
            self.assertEqual((method, path), ("DELETE", "/api/v2/unshare"))
            self.assertEqual(json.loads(payload), {"envZId": "fixture-env", "shareToken": "StaleShare123"})
            self.assertEqual(headers["x-token"], "FixtureAccount123")

    def test_probe_rechecks_reconnection_and_blocklist_fails_closed(self):
        self.enable_fixture_mfa()
        self.remote.route = self.route
        snapshots = []
        def sleep(delay):
            snapshots.append((self.remote.tunnel, self.route["verified"]))
            if len(snapshots) == 3:
                self.remote.route = None
        with patch.object(self.remote,"probe",side_effect=[False,True,False]), \
                patch("remote_access.time", SimpleNamespace(sleep=sleep, time=time.time, monotonic=time.monotonic)):
            self.remote.monitor(self.route)
        self.assertEqual(snapshots, [("connecting",False),("active",True),("reconnecting",False)])
        blocklist = self.state.directory / "dcc-remote-blocked-digests.txt"
        blocklist.write_text("malformed", encoding="ascii")
        self.assertTrue(self.remote.blocked())
        blocklist.write_text(DIGEST+"\n", encoding="ascii")
        self.assertTrue(self.remote.blocked())


del WebFixture
