"""Offscreen Qt tests for the asynchronous Windows Store Kiri workflow.

All probes and installations are mocked. No running container engine is used.
"""

import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import DockerControlCenter as dcc


class KiriStoreQtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patches = [
            patch.object(dcc.NewContainerDialog, "refresh_external_catalogs", return_value=None),
            patch.object(dcc.NewContainerDialog, "load_store_image", return_value=None),
            patch.object(dcc.NewContainerDialog, "load_ai_models", return_value=None),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def wait_for(self, predicate, seconds=3):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.012)
        self.app.processEvents()
        return predicate()

    def test_slow_pipe_probe_does_not_block_store_and_updates_connect_button(self):
        verified = {"status": "ready", "version": "0.2.2", "transport": "windows_named_pipe"}

        def slow_probe():
            time.sleep(0.25)
            return verified

        with patch.object(dcc, "probe_windows_kiri", side_effect=slow_probe):
            dialog = dcc.NewContainerDialog(None, dcc.TEXTS["PL"], lang="PL")
            try:
                template = next(t for t in dialog.catalog if dcc.is_manager_template(t))
                started = time.monotonic()
                dialog.update_store_card(template)
                self.assertLess(time.monotonic() - started, 0.15)
                self.assertFalse(dialog.btn_store_primary.isEnabled())
                self.assertIn("Sprawdzanie", dialog.store_install_state_label.text())
                self.assertTrue(self.wait_for(lambda: dialog._kiri_probe_result == verified))
                dialog.update_store_card(template)
                self.assertEqual(dialog.btn_store_primary.text(), "Połącz")
                self.assertTrue(dialog.btn_store_primary.isEnabled())
                if dialog.selected_catalog_template() == template:
                    self.assertTrue(dialog.btn_quick_deploy.isEnabled())
                self.assertTrue(self.wait_for(lambda: dialog._kiri_probe_thread is None))
            finally:
                dialog.close()

    def test_install_worker_reports_safe_failure_and_success(self):
        worker = dcc.KiriStoreInstallWorker(object(), "image:fixture")
        events = []
        worker.finished.connect(lambda success, detail: events.append((success, detail)))
        with patch.object(dcc, "install_panel_on_verified_kiri", side_effect=dcc.KiriPanelInstallError("socket_preflight_failed")):
            worker.run()
        with patch.object(dcc, "install_panel_on_verified_kiri", return_value="dcc-kiri-manager"):
            worker.run()
        self.assertEqual(events, [(False, "socket_preflight_failed"), (True, "dcc-kiri-manager")])


if __name__ == "__main__":
    unittest.main()
