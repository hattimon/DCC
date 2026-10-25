"""Selective checks must never scan or update unselected containers."""

import copy
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DCC_UPDATER_DATA", tempfile.mkdtemp(prefix="dcc-selected-scan-"))

from updater import UpdateService
from web import create_app


def container(identifier, name=None, labels=None):
    return SimpleNamespace(id=identifier, name=name or identifier, attrs={
        "Image": "sha256:" + identifier,
        "Config": {"Image": f"example/{identifier}:latest", "Labels": labels or {}},
        "HostConfig": {"NetworkMode": "bridge"},
        "NetworkSettings": {"Networks": {"bridge": {}}},
        "State": {"Status": "running"},
    })


class SelectedServiceScanTests(unittest.TestCase):
    def setUp(self):
        self.containers = [container("cinema", "cinema-hub"), container("other"),
                           container("panel", "dcc-container-updater"),
                           container("helper", labels={"com.hattimon.dcc-updater-self-update-helper": "true"})]
        self.client = SimpleNamespace(containers=SimpleNamespace(list=Mock(return_value=self.containers)),
                                      images=SimpleNamespace(get=Mock(return_value=SimpleNamespace(attrs={}))))
        self.catalog = Mock(return_value=[])
        self.service = UpdateService(self.client, catalog_loader=self.catalog)
        self.service._registry_digest = Mock(return_value=(False, ""))

    def test_single_scan_only_contacts_selected_image_and_retains_all_dependency_metadata(self):
        with patch.object(self.service, "automatic_dependency_blocker", return_value="dependency") as blocker:
            result = self.service.scan(container_ids=["cinema"])
        self.assertEqual([item["id"] for item in result], ["cinema"])
        self.assertEqual(self.service._registry_digest.call_args.args[0], "example/cinema:latest")
        self.assertEqual(self.service._registry_digest.call_count, 1)
        self.client.images.get.assert_called_once_with("sha256:cinema")
        self.assertEqual([item.id for item in blocker.call_args.args[1]], ["cinema", "other", "panel"])
        self.assertFalse(result[0]["auto_update_supported"])
        self.assertGreater(result[0]["checked_at"], 0)
        self.assertFalse(result[0]["scan_pending"])

    def test_multiple_ids_are_deduplicated_and_progress_counts_only_selection(self):
        progress = []
        result = self.service.scan(progress.append, container_ids=["other", "cinema", "other"])
        self.assertEqual([item["id"] for item in result], ["other", "cinema"])
        self.assertEqual(self.service._registry_digest.call_count, 2)
        self.assertIn("1/2", progress[0])
        self.assertIn("2/2", progress[1])

    def test_missing_id_and_empty_selection_never_fall_back_to_scanning_all(self):
        self.assertEqual(self.service.scan(container_ids=[]), [])
        result = self.service.scan(container_ids=["removed"])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["missing"])
        self.assertTrue(result[0]["check_error"])
        self.catalog.assert_not_called()
        self.service._registry_digest.assert_not_called()
        self.client.images.get.assert_not_called()

    def test_inventory_does_not_load_images_catalog_or_registry(self):
        result = self.service.inventory()
        self.assertEqual([item["id"] for item in result], ["cinema", "other", "panel"])
        self.assertTrue(result[0]["scan_pending"])
        self.assertFalse(result[0]["supported"])
        self.assertTrue(result[2]["is_panel"])
        self.catalog.assert_not_called()
        self.service._registry_digest.assert_not_called()
        self.client.images.get.assert_not_called()

    def test_full_scan_still_checks_every_container_except_helpers(self):
        result = self.service.scan()
        self.assertEqual([item["id"] for item in result], ["cinema", "other", "panel"])
        self.assertEqual(self.service._registry_digest.call_count, 2)

    def test_failed_inspection_is_reported_without_stopping_remaining_selection(self):
        with patch.object(self.service, "inspect_container", side_effect=[RuntimeError(), {"id": "other"}]):
            result = self.service.scan(container_ids=["cinema", "other"])
        self.assertTrue(result[0]["check_error"])
        self.assertEqual(result[1]["id"], "other")
        self.assertGreater(result[1]["checked_at"], 0)


class SelectedWebScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = [
            {"id": "cinema", "name": "cinema-hub", "current_image": "example/cinema:latest",
             "supported": True, "update_available": False, "checked_at": 100, "status": "running"},
            {"id": "other", "name": "other", "current_image": "example/other:latest",
             "supported": True, "update_available": True, "checked_at": 101, "status": "running",
             "message": "keep this result"},
        ]
        self.path = Path(self.temp.name) / "last_scan.json"
        self.path.write_text(json.dumps({"containers": self.old, "scanned_at": 101}), encoding="utf-8")
        self.service = SimpleNamespace(
            inventory=Mock(return_value=copy.deepcopy(self.old)),
            scan=Mock(side_effect=self.scan_result), update_selected=Mock(),
            check_self_update=Mock(return_value={"checked": True, "update_available": True}),
        )
        self.app = create_app(self.temp.name, service_factory=lambda: self.service, print_credentials=False)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(authenticated=True, csrf_token="test-token")
        self.headers = {"X-CSRF-Token": "test-token"}

    def tearDown(self):
        self.temp.cleanup()

    def scan_result(self, _progress, *, container_ids=None):
        return [{**item, "update_available": True, "checked_at": time.time()}
                for item in copy.deepcopy(self.old) if container_ids is None or item["id"] in container_ids]

    def wait(self):
        manager = self.app.extensions["dcc_updater_jobs"]
        deadline = time.monotonic() + 3
        while manager.snapshot()["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(.01)
        state = manager.snapshot()
        self.assertEqual(state["status"], "done", state)
        return state["results"]

    def post(self, payload):
        return self.client.post("/api/scan", json=payload, headers=self.headers)

    def test_selected_scan_preserves_unselected_cache_and_its_timestamp_after_restart(self):
        self.assertEqual(self.post({"container_ids": ["cinema", "cinema"]}).status_code, 202)
        result = self.wait()
        self.assertTrue(result["partial"])
        self.assertEqual(result["scanned_count"], 1)
        self.service.scan.assert_called_once()
        self.assertEqual(self.service.scan.call_args.kwargs, {"container_ids": ["cinema"]})
        self.service.update_selected.assert_not_called()
        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["containers"][1], self.old[1])
        self.assertGreater(persisted["containers"][0]["checked_at"], 101)
        restored = create_app(self.temp.name, service_factory=lambda: self.service, print_credentials=False)
        client = restored.test_client()
        with client.session_transaction() as state:
            state.update(authenticated=True)
        self.assertEqual(client.get("/api/containers").get_json()["containers"][1]["checked_at"], 101)

    def test_invalid_selection_does_not_start_full_scan(self):
        for payload in ([], "bad", {"container_ids": []}, {"container_ids": None},
                        {"container_ids": "cinema"}, {"container_ids": [1]}, {"container_ids": [""]},
                        {"container_ids": [" "]}, {"container_ids": ["x" * 129]},
                        {"container_ids": ["cinema"] * 101}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload).status_code, 400)
        self.service.scan.assert_not_called()

    def test_inventory_is_available_before_first_scan_without_any_registry_scan(self):
        self.path.unlink()
        service = UpdateService(SimpleNamespace(containers=SimpleNamespace(list=lambda **_: [container("cinema")])))
        self.service.inventory.side_effect = service.inventory
        fresh = create_app(self.temp.name, service_factory=lambda: self.service, print_credentials=False)
        client = fresh.test_client()
        with client.session_transaction() as state:
            state.update(authenticated=True)
        cached = client.get("/api/containers").get_json()
        self.assertIsNone(cached["scanned_at"])
        self.assertEqual(cached["containers"][0]["id"], "cinema")
        self.assertTrue(cached["containers"][0]["scan_pending"])
        self.service.scan.assert_not_called()

    def test_inventory_error_falls_back_to_previous_results(self):
        self.service.inventory.side_effect = RuntimeError()
        result = self.client.get("/api/containers")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["containers"][1]["message"], "keep this result")

    def test_partial_scan_reports_count_and_errors_only_for_checked_containers(self):
        self.old[1].update(check_error=True, message="old registry error")
        self.assertEqual(self.post({"container_ids": ["cinema"]}).status_code, 202)
        self.wait()
        reports = self.app.extensions["dcc_updater_reports"]
        deadline = time.monotonic() + 2
        while not reports.snapshot()["total"] and time.monotonic() < deadline:
            time.sleep(.01)
        event = reports.snapshot()["entries"][0]
        self.assertEqual((event["status"], event["scanned"]), ("success", 1))

    def test_selection_requires_csrf_and_authentication(self):
        self.assertEqual(self.client.post("/api/scan", json={"container_ids": ["cinema"]}).status_code, 400)
        self.assertEqual(self.app.test_client().post("/api/scan", json={"container_ids": ["cinema"]}).status_code, 401)
        self.service.scan.assert_not_called()

    def test_scans_are_serialized_including_selected_checks(self):
        release = threading.Event()
        def blocked_scan(*_, **__):
            release.wait(2)
            return []
        self.service.scan.side_effect = blocked_scan
        try:
            self.assertEqual(self.post({"container_ids": ["cinema"]}).status_code, 202)
            self.assertEqual(self.post({"container_ids": ["other"]}).status_code, 409)
        finally:
            release.set()
        # Wait for the released background worker before removing its data directory.
        deadline = time.monotonic() + 3
        while self.app.extensions["dcc_updater_jobs"].snapshot()["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.app.extensions["dcc_updater_jobs"].snapshot()["status"], "done")

    def test_selected_check_never_runs_pending_startup_updates(self):
        with patch.dict(os.environ, {"DCC_UPDATER_STARTUP_DELAY": "300"}):
            self.app = create_app(self.temp.name, service_factory=lambda: self.service,
                                  print_credentials=False, startup_auto_updates=True)
        self.app.extensions["dcc_updater_auto_updates"].set("other", "example/other:latest", True)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(authenticated=True, csrf_token="test-token")
        self.assertEqual(self.client.post("/api/self-update/check", json={}, headers=self.headers).status_code, 202)
        self.wait()
        self.assertEqual(self.post({"container_ids": ["cinema"]}).status_code, 409)
        self.assertEqual(self.post({"container_ids": ["cinema"], "defer_panel_update": True}).status_code, 202)
        self.assertTrue(self.wait()["partial"])
        self.service.update_selected.assert_not_called()
        self.assertEqual(self.service.scan.call_args.kwargs["container_ids"], ["cinema"])


if __name__ == "__main__":
    unittest.main()
