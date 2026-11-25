"""Synthetic Windows named-pipe and Kiri container preflight tests."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from kiri_host import (KIRI_CONTAINER_SOCKET, KIRI_MANAGER_NAME, KIRI_MANAGER_VOLUME,
                       KIRI_PIPE, KIRI_RUNTIME_SOCKET, KiriPanelInstallError,
                       check_identity, install_panel_on_verified_kiri,
                       probe_windows_kiri, store_action, _pipe_failure, _panel_http_ready)
from fixtures import ENGINE, VERSION


IMAGE = "ghcr.io/hattimon/dcc-kiri-manager:0.1.2"
ISOLATED_DATA = str(Path(__file__).parent)


def fake_mount(**kwargs):
    return kwargs


class FakeResponse:
    headers = {"Server": ENGINE}

    def json(self):
        return VERSION


class FakeContainer:
    def __init__(self, name, status=0, image_tags=(), mounts=()):
        self.name, self.status = name, status
        self.image = SimpleNamespace(tags=list(image_tags))
        self.attrs = {"Mounts": list(mounts)}
        self.started = False
        self.removed = False
        self.remove_options = None

    def start(self):
        self.started = True

    def wait(self, timeout=0):
        return {"StatusCode": self.status}

    def remove(self, **kwargs):
        self.removed = True
        self.remove_options = kwargs


class FakeContainers:
    def __init__(self, *, installed=False, preflight_code=0):
        self.existing = [FakeContainer(KIRI_MANAGER_NAME)] if installed else []
        self.created = []
        self.preflight_code = preflight_code

    def list(self, all=False):
        assert all
        return list(self.existing)

    def create(self, image, **kwargs):
        panel = FakeContainer(kwargs.get("name", "test-preflight"), self.preflight_code)
        self.created.append((image, kwargs, panel))
        return panel


class FakeImages:
    def __init__(self):
        self.pulled = []

    def get(self, image):
        raise LookupError(image)

    def pull(self, image):
        self.pulled.append(image)


class FakeClient:
    def __init__(self, *, response=None, installed=False, preflight_code=0):
        self.response = response or FakeResponse()
        self.api = SimpleNamespace(_url=self.url, _get=self.get)
        self.containers = FakeContainers(installed=installed, preflight_code=preflight_code)
        self.images = FakeImages()
        self.closed = False

    def url(self, path, *, versioned_api=False):
        assert path == "/version" and not versioned_api
        return path

    def get(self, path):
        assert path == "/version"
        return self.response

    def close(self):
        self.closed = True


class WindowsKiriTest(unittest.TestCase):
    def test_engine_identity_is_not_a_context_name(self):
        self.assertEqual(check_identity(ENGINE, VERSION), "0.2.2")
        self.assertIsNone(check_identity("Docker/27.5.1", VERSION))
        self.assertIsNone(check_identity(ENGINE, {**VERSION, "Platform": {"Name": "Docker"}}))
        self.assertIsNone(check_identity(ENGINE, {**VERSION, "KiriVersion": "0.2.3"}))
        self.assertIsNone(check_identity(ENGINE, {**VERSION, "Components": []}))

    def test_windows_pipe_probe_ready_and_closed(self):
        client = FakeClient()
        urls = []

        def factory(**kwargs):
            urls.append(kwargs)
            return client

        found = probe_windows_kiri(client_factory=factory, windows=True, local_app_data=ISOLATED_DATA)
        self.assertEqual(found, {"status": "ready", "version": "0.2.2", "transport": "windows_named_pipe"})
        self.assertEqual(urls[0]["base_url"], KIRI_PIPE)
        self.assertTrue(client.closed)

    def test_windows_probe_missing_denied_and_wrong_engine(self):
        def missing(**kwargs):
            raise FileNotFoundError("local pipe unavailable")

        def denied(**kwargs):
            raise PermissionError("named pipe access denied")

        self.assertEqual(probe_windows_kiri(client_factory=missing, windows=True, local_app_data=ISOLATED_DATA)["status"], "missing")
        self.assertEqual(probe_windows_kiri(client_factory=denied, windows=True, local_app_data=ISOLATED_DATA)["reason"], "permission_denied")
        wrong = FakeClient(response=SimpleNamespace(headers={"Server": "Docker/27.5.1"}, json=lambda: VERSION))
        self.assertEqual(probe_windows_kiri(client_factory=lambda **_: wrong, windows=True)["reason"], "identity_unverified")
        self.assertEqual(probe_windows_kiri(windows=False), {"status": "unsupported", "reason": "windows_only"})

    def test_wrapped_pipe_errors_and_unknown_unreachable_are_separate(self):
        try:
            try:
                raise PermissionError("internal denied")
            except PermissionError as cause:
                raise RuntimeError("Docker transport") from cause
        except RuntimeError as wrapped:
            self.assertEqual(_pipe_failure(wrapped), "permission_denied")
        self.assertEqual(_pipe_failure(FileNotFoundError("missing")), "pipe_missing")
        self.assertEqual(_pipe_failure(OSError("unreachable")), "engine_unreachable")

        def offline(**kwargs):
            raise OSError("unreachable")

        found = probe_windows_kiri(client_factory=offline, windows=True, local_app_data=ISOLATED_DATA)
        self.assertEqual(found, {"status": "blocked", "reason": "engine_unreachable"})

    def test_store_requires_connection_and_preflight(self):
        self.assertEqual(store_action({"status": "ready"}), "connect")
        self.assertEqual(store_action({"status": "ready"}, connected=True), "install_panel")
        self.assertEqual(store_action({"status": "ready"}, connected=True, installed=True), "installed")
        self.assertEqual(store_action({"status": "missing"}), "install_kiri")
        self.assertEqual(store_action({"status": "blocked"}), "help")

    def test_existing_manager_and_invalid_image_are_never_modified(self):
        client = FakeClient(installed=True)
        with self.assertRaisesRegex(KiriPanelInstallError, "already_installed"):
            install_panel_on_verified_kiri(client, IMAGE, mount_factory=fake_mount)
        self.assertEqual(client.containers.created, [])
        self.assertEqual(client.images.pulled, [])
        with self.assertRaisesRegex(KiriPanelInstallError, "invalid_image"):
            install_panel_on_verified_kiri(client, "docker.io/untrusted:latest", mount_factory=fake_mount)
        self.assertFalse(client.containers.existing[0].removed)

    def test_existing_manager_under_a_custom_name_is_preserved(self):
        client = FakeClient()
        existing = FakeContainer("my-dashboard", image_tags=[IMAGE])
        client.containers.existing.append(existing)
        with self.assertRaisesRegex(KiriPanelInstallError, "already_installed"):
            install_panel_on_verified_kiri(client, IMAGE, mount_factory=fake_mount)
        self.assertEqual(client.containers.created, [])
        self.assertEqual(client.images.pulled, [])
        self.assertFalse(existing.removed)

    def test_unrecognized_container_using_manager_volume_is_preserved(self):
        client = FakeClient()
        existing = FakeContainer("my-old-panel", image_tags=["my-local-panel:latest"],
                                 mounts=[{"Type": "volume", "Name": KIRI_MANAGER_VOLUME}])
        client.containers.existing.append(existing)
        with self.assertRaisesRegex(KiriPanelInstallError, "already_installed"):
            install_panel_on_verified_kiri(client, IMAGE, mount_factory=fake_mount)
        self.assertFalse(existing.removed)
        self.assertEqual(client.containers.created, [])
        self.assertEqual(client.images.pulled, [])

    def test_failed_preflight_preserves_existing_data(self):
        client = FakeClient(preflight_code=1)
        with self.assertRaisesRegex(KiriPanelInstallError, "socket_preflight_failed"):
            install_panel_on_verified_kiri(client, IMAGE, mount_factory=fake_mount)
        self.assertEqual(len(client.containers.created), 1)
        _, preflight, disposable = client.containers.created[0]
        self.assertTrue(disposable.removed)
        self.assertNotIn("volumes", preflight)
        self.assertEqual(preflight["mounts"], [{"source": KIRI_RUNTIME_SOCKET,
                                              "target": KIRI_CONTAINER_SOCKET,
                                              "type": "bind", "read_only": True}])
        self.assertNotIn(KIRI_MANAGER_VOLUME, str(preflight))
        self.assertTrue(preflight["network_disabled"])
        self.assertEqual(preflight["user"], "10001:10001")

    def test_success_starts_panel_with_persistent_volume_only_after_preflight(self):
        client = FakeClient()
        self.assertEqual(install_panel_on_verified_kiri(
            client, IMAGE, mount_factory=fake_mount, panel_ready=lambda: True), KIRI_MANAGER_NAME)
        self.assertEqual(client.images.pulled, [IMAGE])
        self.assertEqual(len(client.containers.created), 2)
        _, preflight, test = client.containers.created[0]
        _, configured, panel = client.containers.created[1]
        self.assertTrue(test.started and test.removed)
        self.assertEqual(configured["name"], KIRI_MANAGER_NAME)
        self.assertTrue(panel.started and not panel.removed)
        self.assertEqual(configured["volumes"][KIRI_MANAGER_VOLUME], {"bind": "/data", "mode": "rw"})
        self.assertEqual(configured["mounts"], preflight["mounts"])
        self.assertNotIn(KIRI_RUNTIME_SOCKET, configured["volumes"])
        self.assertEqual(json.loads(configured["environment"]["KIRI_SOCKETS"]), {"auto": KIRI_CONTAINER_SOCKET})
        self.assertIn("Connector", preflight["command"][-1])
        self.assertEqual(configured["ports"], {"8796/tcp": ("127.0.0.1", 8796)})

    def test_unreachable_panel_is_removed_without_removing_data_volume(self):
        client = FakeClient()
        with self.assertRaisesRegex(KiriPanelInstallError, "panel_not_reachable"):
            install_panel_on_verified_kiri(client, IMAGE, mount_factory=fake_mount,
                                           panel_ready=lambda: False)
        self.assertEqual(len(client.containers.created), 2)
        _, preflight_opts, test = client.containers.created[0]
        _, panel_opts, panel = client.containers.created[1]
        self.assertTrue(test.started and test.removed)
        self.assertTrue(panel.started and panel.removed)
        self.assertEqual(test.remove_options, {"force": True, "v": True})
        self.assertEqual(panel.remove_options, {"force": True, "v": False})
        self.assertNotIn("volumes", preflight_opts)
        self.assertIn(KIRI_MANAGER_VOLUME, panel_opts["volumes"])

    def test_windows_http_probe_requires_panel_identity_marker(self):
        from unittest.mock import patch

        class Reply:
            status = 200

            def __init__(self, marker):
                self.marker = marker

            def getheader(self, key, default=""):
                return {"Content-Type": "application/json",
                        "X-DCC-Panel": self.marker}.get(key, default)

            def read(self, count):
                return b'{"status":"ok"}'

        class Connection:
            def __init__(self, host, port, timeout):
                self.host, self.port = host, port

            def request(self, method, path):
                self.method, self.path = method, path

            def getresponse(self):
                return Reply(self.marker)

            def close(self):
                pass

        with patch("kiri_host.http.client.HTTPConnection", Connection):
            Connection.marker = "kiri-manager"
            self.assertTrue(_panel_http_ready(timeout=.1))
            Connection.marker = "some-other-service"
            self.assertFalse(_panel_http_ready(timeout=.1))
