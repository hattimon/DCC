import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QSettings, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionButton, QTableWidget, QTableWidgetItem

import DockerControlCenter as dcc


THEMES = ("day", "light", "dark", "black", "night")


def indicator_rect(checkbox):
    option = QStyleOptionButton()
    checkbox.initStyleOption(option)
    return checkbox.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, checkbox)


def mouse_click_indicator(checkbox):
    checkbox.resize(max(220, checkbox.sizeHint().width() + 24), max(36, checkbox.sizeHint().height() + 8))
    checkbox.show()
    QApplication.processEvents()
    QTest.mouseClick(
        checkbox,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        indicator_rect(checkbox).center(),
    )
    QApplication.processEvents()


def mouse_click_label(checkbox):
    rect = indicator_rect(checkbox)
    point = QPoint(min(checkbox.width() - 4, rect.right() + 30), checkbox.rect().center().y())
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    QApplication.processEvents()


class _SelectAllHarness:
    on_select_all = dcc.MainWindow.on_select_all
    sync_group_checkbox = dcc.MainWindow.sync_group_checkbox


class CheckboxRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_eight_reported_checkboxes_toggle_via_real_mouse_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)

            app_dialog = dcc.AppSettingsDialog(settings, dcc.TEXTS["EN"])
            for checkbox in (
                app_dialog.auto_start_checkbox,
                app_dialog.auto_updates_checkbox,
                app_dialog.update_notifications_checkbox,
            ):
                before = checkbox.isChecked()
                mouse_click_indicator(checkbox)
                self.assertNotEqual(checkbox.isChecked(), before)

            theme_dialog = dcc.ThemeSettingsDialog(settings, dcc.TEXTS["EN"])
            for checkbox in (
                theme_dialog.neon_enabled_checkbox,
                theme_dialog.neon_checkbox,
                theme_dialog.audio_enabled_checkbox,
            ):
                before = checkbox.isChecked()
                mouse_click_indicator(checkbox)
                self.assertNotEqual(checkbox.isChecked(), before)

            magnet = dcc.QCheckBox("Magnet")
            magnet.setChecked(True)
            harness = type("MagnetHarness", (), {})()
            harness.settings = settings
            harness.container_column_magnet = True
            harness._save_container_column_widths = lambda: None
            harness._apply_container_column_magnet = lambda: None
            magnet.toggled.connect(lambda enabled: dcc.MainWindow.set_container_column_magnet(harness, enabled))
            mouse_click_indicator(magnet)
            self.assertFalse(magnet.isChecked())
            self.assertEqual(str(settings.value("containers/column_magnet", "true")).lower(), "false")
            mouse_click_indicator(magnet)
            self.assertTrue(magnet.isChecked())
            self.assertEqual(str(settings.value("containers/column_magnet", "true")).lower(), "true")

            select = _SelectAllHarness()
            select.table = QTableWidget(0, 12)
            select.select_all_checkbox = dcc.QCheckBox("Select all")
            select.group_checkboxes = {}
            select._updating_group_selection = False
            for name in ("alpha", "beta"):
                row = select.table.rowCount()
                select.table.insertRow(row)
                child = dcc.QCheckBox()
                select.table.setCellWidget(row, 0, child)
                item = QTableWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, {"row_type": "container", "group": ""})
                select.table.setItem(row, 2, item)
            select.select_all_checkbox.stateChanged.connect(select.on_select_all)
            mouse_click_indicator(select.select_all_checkbox)
            self.assertTrue(all(select.table.cellWidget(row, 0).isChecked() for row in range(2)))
            mouse_click_indicator(select.select_all_checkbox)
            self.assertTrue(all(not select.table.cellWidget(row, 0).isChecked() for row in range(2)))

            app_dialog.deleteLater()
            theme_dialog.deleteLater()
            magnet.deleteLater()
            select.select_all_checkbox.deleteLater()
            select.table.deleteLater()

    def test_checked_indicator_is_visible_and_clickable_in_all_five_themes(self):
        for theme in THEMES:
            accent = QColor(dcc.effective_accent_color(theme, dcc.DEFAULT_ACCENT_COLOR))
            self.app.setProperty("dcc_checkbox_accent", accent.name())
            self.app.setStyleSheet(
                dcc.gaming_stylesheet(theme, 0.0, False, 100, False, dcc.DEFAULT_ACCENT_COLOR)
            )
            checkbox = dcc.QCheckBox(f"{theme} checkbox")
            mouse_click_indicator(checkbox)
            self.assertTrue(checkbox.isChecked(), theme)
            self.assertEqual(checkbox._current_check_accent().name().lower(), accent.name().lower(), theme)

            image = checkbox.grab().toImage()
            rect = indicator_rect(checkbox)
            hits = 0
            for y in range(max(0, rect.top()), min(image.height(), rect.bottom() + 1)):
                for x in range(max(0, rect.left()), min(image.width(), rect.right() + 1)):
                    color = image.pixelColor(x, y)
                    if (
                        abs(color.red() - accent.red()) <= 45
                        and abs(color.green() - accent.green()) <= 45
                        and abs(color.blue() - accent.blue()) <= 45
                    ):
                        hits += 1
            self.assertGreater(hits, 2, theme)

            mouse_click_label(checkbox)
            self.assertFalse(checkbox.isChecked(), theme)
            checkbox.deleteLater()

    def test_magnet_defaults_on_and_theme_changes_do_not_reset_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            default_value = str(settings.value("containers/column_magnet", "true")).lower()
            self.assertIn(default_value, {"1", "true", "yes"})

            checkbox = dcc.QCheckBox("Magnet")
            checkbox.setChecked(True)
            for theme in THEMES:
                self.app.setProperty(
                    "dcc_checkbox_accent",
                    dcc.effective_accent_color(theme, dcc.DEFAULT_ACCENT_COLOR),
                )
                self.app.setStyleSheet(
                    dcc.gaming_stylesheet(theme, 0.0, False, 100, False, dcc.DEFAULT_ACCENT_COLOR)
                )
                QApplication.processEvents()
                self.assertTrue(checkbox.isChecked(), theme)
            checkbox.deleteLater()

    def test_refresh_does_not_preemptively_clear_select_all(self):
        source = (Path(__file__).resolve().parents[1] / "DockerControlCenter.py").read_text(encoding="utf-8")
        start = source.index("    def refresh_containers(self):")
        end = source.index("    def refresh_monitoring(self):", start)
        refresh_body = source[start:end]
        self.assertNotIn("self.select_all_checkbox.setChecked(False)", refresh_body)


if __name__ == "__main__":
    unittest.main()
