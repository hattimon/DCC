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


class DayThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_day_theme_uses_day_background_and_dark_text(self):
        self.assertEqual(dcc.TEXTS["EN"]["theme_day"], "Day")
        self.assertEqual(dcc.TEXTS["PL"]["theme_day"], "Day")
        background = dcc.resolve_background_path("day")
        self.assertEqual(background.name.lower(), "day.png")
        self.assertTrue(background.exists())
        self.assertEqual(dcc.palette_for_theme("day")["fg"], "#101820")

    def test_day_stylesheet_keeps_light_surfaces_translucent(self):
        qss = dcc.gaming_stylesheet("day", 0.0, False, 100, False, dcc.DEFAULT_ACCENT_COLOR)
        self.assertIn("rgba(255,255,255,0.46)", qss)
        self.assertIn("rgba(255,255,255,0.34)", qss)
        self.assertIn("rgba(255,255,255,0.56)", qss)
        self.assertIn("rgba(251,251,247,0.94)", qss)
        self.assertIn("rgba(251,251,247,0.96)", qss)
        self.assertIn("rgba(255,255,255,0.24)", qss)
        self.assertIn("rgba(230,239,244,0.18)", qss)
        self.assertIn("color: #101820", qss)

    def test_profile_and_group_menus_are_at_least_ninety_percent_opaque(self):
        for theme, expected_combo, expected_popup in (
            ("dark", "rgba(29,42,67,0.94)", "rgba(29,42,67,0.96)"),
            ("black", "rgba(24,29,36,0.94)", "rgba(24,29,36,0.96)"),
            ("night", "rgba(23,18,22,0.94)", "rgba(23,18,22,0.96)"),
        ):
            qss = dcc.gaming_stylesheet(theme, 0.0, False, 100, False, dcc.DEFAULT_ACCENT_COLOR)
            self.assertIn(expected_combo, qss)
            self.assertIn(expected_popup, qss)

    def test_day_is_listed_above_light_in_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            dialog = dcc.AppSettingsDialog(settings, dcc.TEXTS["PL"])
            day_index = dialog.theme_combo.findData("day")
            light_index = dialog.theme_combo.findData("light")
            self.assertEqual(day_index, 0)
            self.assertEqual(light_index, 1)
            self.assertEqual(dialog.theme_combo.itemText(day_index), "Day")
            dialog.close()

    def test_store_day_surfaces_remain_translucent(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["EN"], lang="EN")
            dialog.catalog_theme = "day"
            colors = dialog._catalog_visual_colors()
            self.assertEqual(colors["title"], "#101820")
            self.assertEqual(colors["surface"], "rgba(255, 255, 255, 112)")
            self.assertEqual(colors["card_bg"], "rgba(255, 255, 255, 142)")
            configuration_fields = (
                dialog.name_edit,
                dialog.image_edit,
                dialog.cport_edit,
                dialog.hport_edit,
                dialog.extra_edit,
                dialog.command_edit,
                dialog.cli_combo,
            )
            self.assertTrue(all(field.minimumHeight() >= 30 for field in configuration_fields))
            dialog.close()


if __name__ == "__main__":
    unittest.main()
