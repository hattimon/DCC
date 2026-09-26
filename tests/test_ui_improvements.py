import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication

import DockerControlCenter as dcc
import RepoBuilder as repo_builder


class _LogContainer:
    def __init__(self, payload):
        self.payload = payload

    def logs(self, tail=200):
        return self.payload.encode("utf-8")


class _LogContainers:
    def __init__(self, payload):
        self.container = _LogContainer(payload)

    def get(self, _name):
        return self.container


class _LogClient:
    def __init__(self, payload):
        self.containers = _LogContainers(payload)


class UiImprovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_logs_search_is_case_insensitive_and_survives_refresh(self):
        client = _LogClient("Alpha\nalpha\nother\nALPHA")
        dialog = dcc.LogsDialog(client, "demo", dcc.TEXTS["EN"])
        dialog.search_edit.setText("alpha")
        self.assertEqual(len(dialog._search_matches), 3)
        self.assertEqual(dialog.result_label.text(), "1/3")
        dialog.next_result()
        self.assertEqual(dialog.result_label.text(), "2/3")
        dialog.previous_result()
        self.assertEqual(dialog.result_label.text(), "1/3")

        client.containers.container.payload = "alpha\nnone"
        dialog.load_logs()
        self.assertEqual(dialog.search_edit.text(), "alpha")
        self.assertEqual(dialog.result_label.text(), "1/1")
        self.assertEqual(dialog.text_edit.toPlainText(), "alpha\nnone")
        dialog.close()

    def test_auto_refresh_defaults_persistence_and_overlap_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            self.assertEqual(dcc.load_auto_refresh_settings(settings), (True, 10))

            class Harness:
                pass

            harness = Harness()
            harness.settings = settings
            harness.auto_refresh_enabled = True
            harness.auto_refresh_interval_s = 10
            harness.auto_refresh_timer = QTimer()
            harness.action_auto_refresh = None
            harness.auto_refresh_interval_actions = {}
            harness.client = object()
            harness.refresh_containers = MagicMock()
            harness.refresh_thread = MagicMock()
            harness.refresh_thread.isRunning.return_value = True

            dcc.MainWindow.set_auto_refresh_enabled(harness, False)
            self.assertFalse(harness.auto_refresh_timer.isActive())
            self.assertEqual(dcc.load_auto_refresh_settings(settings), (False, 10))
            dcc.MainWindow.set_auto_refresh_interval(harness, 30)
            self.assertEqual(dcc.load_auto_refresh_settings(settings), (False, 30))
            dcc.MainWindow.set_auto_refresh_enabled(harness, True)
            self.assertTrue(harness.auto_refresh_timer.isActive())
            dcc.MainWindow.on_auto_refresh_timeout(harness)
            harness.refresh_containers.assert_not_called()
            harness.refresh_thread.isRunning.return_value = False
            dcc.MainWindow.on_auto_refresh_timeout(harness)
            harness.refresh_containers.assert_called_once_with()
            harness.auto_refresh_timer.stop()

    def test_neon_palette_and_custom_color_persist(self):
        expected = {
            "#0b6b3a", "#168c88", "#36cfc9", "#23ff00", "#2457d6", "#4878a8",
            "#a52a35", "#7d1e3a", "#6f42c1", "#d89b00", "#c7a600", "#c65a1e",
        }
        self.assertTrue(expected.issubset({dcc.normalize_accent_color(value) for _label, value in dcc.NEON_PALETTE}))
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            settings.setValue("accent_color", "#123456")
            dialog = dcc.AppSettingsDialog(settings, dcc.TEXTS["PL"])
            self.assertEqual(dialog.neon_color_combo.currentData(), "#123456")
            self.assertIn("#123456", dialog.neon_color_combo.currentText())
            header_index = dialog.neon_color_combo.findText(dcc.TEXTS["PL"]["neon_muted_header"])
            self.assertGreaterEqual(header_index, 0)
            self.assertFalse(dialog.neon_color_combo.model().item(header_index).isEnabled())
            dialog.close()

    def test_all_themes_define_readable_control_surfaces(self):
        for theme in ("light", "day", "dark", "black", "night"):
            palette = dcc.palette_for_theme(theme)
            self.assertNotEqual(palette["fg"].lower(), palette["solid0"].lower())
            qss = dcc.gaming_stylesheet(theme, 0.25, False, 100, True, "#6F42C1")
            for selector in ("QDialog, QMessageBox", "QTabWidget::pane", "QCheckBox", "QTreeWidget", "QDoubleSpinBox"):
                self.assertIn(selector, qss)
            purple_hue = dcc.QColor("#6F42C1").hue()
            self.assertIsInstance(purple_hue, int)
            self.assertNotIn("#33f0ff", qss.lower())

        surface = dcc.BackgroundSurface("black", False, 72, "#6F42C1")
        self.assertEqual(surface._accent_color, "#6f42c1")
        surface.set_visual_state("night", True, 60, "#23FF00")
        self.assertEqual(surface._accent_color, "#23ff00")
        surface.close()

    def test_repo_builder_uses_settings_and_writes_utf8_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            settings.setValue("language", "PL")
            settings.setValue("theme", "day")
            settings.setValue("accent_color", "#0B6B3A")
            settings.setValue("neon_enabled", "false")
            settings.setValue("neon_animate", "true")
            target = root / "katalog.json"
            with patch.object(repo_builder, "QSettings", return_value=settings), patch.object(
                repo_builder.RepoBuilderWindow, "_load_default_checkout"
            ):
                window = repo_builder.RepoBuilderWindow()
            self.assertEqual(window.current_theme, "day")
            self.assertEqual(window.accent_color, "#0b6b3a")
            self.assertFalse(window.neon_enabled)
            self.assertTrue(window.neon_animate)
            window.catalog = {
                "apps": [{
                    "name": "Żółw",
                    "image": "example/turtle:latest",
                    "default_name": "zolw",
                    "category": "Narzędzia",
                    "category_en": "Tools",
                    "description": "Zażółć",
                    "description_en": "Turtle",
                    "engines": ["docker"],
                }]
            }
            with patch.object(repo_builder.QFileDialog, "getSaveFileName", return_value=(str(target), "JSON (*.json)")):
                self.assertTrue(window.save_catalog_as())
            raw = target.read_text(encoding="utf-8")
            self.assertIn("Żółw", raw)
            self.assertTrue(raw.endswith("\n"))
            self.assertEqual(json.loads(raw)["apps"][0]["description"], "Zażółć")
            self.assertEqual(settings.value("repo_builder/last_catalog_path"), str(target.resolve()))
            window.catalog["apps"][0]["description"] = "Gęślą"
            self.assertTrue(window.save_catalog())
            self.assertIn("Gęślą", target.read_text(encoding="utf-8"))
            self.assertFalse(repo_builder.RepoBuilderWindow._is_safe_catalog_path(root / "_MEI1234" / "catalog.json"))
            window.close()


if __name__ == "__main__":
    unittest.main()
