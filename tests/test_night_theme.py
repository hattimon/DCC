import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

import DockerControlCenter as dcc


class _FakeContainers:
    def list(self, all=True):
        return []


class _FakeClient:
    containers = _FakeContainers()


class NightThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_night_theme_is_bilingual_and_has_background(self):
        self.assertEqual(dcc.TEXTS["EN"]["theme_night"], "Night")
        self.assertEqual(dcc.TEXTS["PL"]["theme_night"], "Noc")
        background = dcc.resolve_background_path("night")
        self.assertEqual(background.name.lower(), "night.png")
        self.assertTrue(background.exists())

    def test_night_palette_and_default_accent_are_red(self):
        palette = dcc.palette_for_theme("night")
        self.assertEqual(palette["solid0"], "#090b0f")
        self.assertEqual(dcc.effective_accent_color("night", dcc.DEFAULT_ACCENT_COLOR), dcc.NIGHT_ACCENT_COLOR)
        self.assertEqual(dcc.effective_accent_color("night", "#b26bff"), "#b26bff")
        qss = dcc.gaming_stylesheet("night", 0.0, False, 100, False, dcc.DEFAULT_ACCENT_COLOR)
        self.assertIn(dcc.NIGHT_ACCENT_COLOR, qss)

    def test_settings_theme_combo_contains_night(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            dialog = dcc.AppSettingsDialog(settings, dcc.TEXTS["PL"])
            index = dialog.theme_combo.findData("night")
            self.assertGreaterEqual(index, 0)
            self.assertEqual(dialog.theme_combo.itemText(index), "Noc")
            dialog.close()

    def test_store_accepts_night_theme_and_uses_night_accent(self):
        class Parent:
            current_theme = "night"
            accent_color = dcc.DEFAULT_ACCENT_COLOR

        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            parent = Parent()
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["EN"], lang="EN", parent=None)
            dialog.catalog_theme = parent.current_theme
            dialog.catalog_accent = dcc.effective_accent_color(parent.current_theme, parent.accent_color)
            colors = dialog._catalog_visual_colors()
            self.assertEqual(colors["accent"], dcc.NIGHT_ACCENT_COLOR)
            self.assertIn("rgba(13, 10, 13", colors["surface"])
            dialog.close()


if __name__ == "__main__":
    unittest.main()
