import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton, QTableWidget, QTableWidgetItem

import DockerControlCenter as dcc


class _GroupSelectionHarness:
    on_group_checkbox_changed = dcc.MainWindow.on_group_checkbox_changed
    sync_group_checkbox = dcc.MainWindow.sync_group_checkbox
    sync_select_all_checkbox = dcc.MainWindow.sync_select_all_checkbox
    get_selected_names = dcc.MainWindow.get_selected_names
    refresh_dynamic_theme_elements = dcc.MainWindow.refresh_dynamic_theme_elements


class GroupSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def build_harness(self):
        harness = _GroupSelectionHarness()
        harness.table = QTableWidget(0, 12)
        harness.select_all_checkbox = QCheckBox()
        harness.group_checkboxes = {"project:alpha": QCheckBox()}
        harness._updating_group_selection = False

        for name in ("alpha-web", "alpha-db"):
            row = harness.table.rowCount()
            harness.table.insertRow(row)
            checkbox = QCheckBox()
            harness.table.setCellWidget(row, 0, checkbox)
            name_item = QTableWidgetItem(name)
            name_item.setData(
                Qt.ItemDataRole.UserRole,
                {"row_type": "container", "group": "project:alpha"},
            )
            harness.table.setItem(row, 2, name_item)
        return harness

    def test_group_checkbox_selects_every_container_for_bulk_actions(self):
        harness = self.build_harness()

        harness.on_group_checkbox_changed("project:alpha", Qt.CheckState.Checked.value)

        self.assertEqual(harness.get_selected_names(), ["alpha-web", "alpha-db"])
        self.assertTrue(harness.group_checkboxes["project:alpha"].isChecked())
        self.assertTrue(harness.select_all_checkbox.isChecked())

    def test_group_checkbox_tracks_manual_child_selection(self):
        harness = self.build_harness()
        harness.on_group_checkbox_changed("project:alpha", Qt.CheckState.Checked.value)

        first_child = harness.table.cellWidget(0, 0)
        first_child.setChecked(False)
        harness.sync_group_checkbox("project:alpha")

        self.assertFalse(harness.group_checkboxes["project:alpha"].isChecked())
        self.assertFalse(harness.select_all_checkbox.isChecked())

    def test_group_header_caption_is_rendered_once_by_button(self):
        harness = _GroupSelectionHarness()
        harness.table = QTableWidget(0, 12)
        harness.texts = {
            "group_summary": "{count} containers · {running} running · networks: {networks}",
            "group_select_all": "Select group",
            "group_display_expand": "Expand group",
            "group_display_collapse": "Collapse group",
        }
        harness.collapsed_groups = set()
        harness.group_checkboxes = {}
        harness.accent_color = "#33f0ff"
        harness.current_theme = "black"
        harness.container_table_zoom = 100
        harness.group_network_summary = lambda _containers: "alpha-net"
        harness.group_storage_key = lambda key: f"project:{key}"
        harness.group_display_name = lambda key: f"Project: {key}"
        harness.on_group_checkbox_changed = lambda *_args: None
        harness.toggle_container_group = lambda *_args: None

        container = type("Container", (), {"status": "running"})()
        dcc.MainWindow.insert_group_header(harness, "alpha", [container])

        metadata_item = harness.table.item(0, 0)
        self.assertIsNotNone(metadata_item)
        self.assertEqual(metadata_item.text(), "")
        header_widget = harness.table.cellWidget(0, 0)
        self.assertIsNotNone(header_widget)
        button = header_widget.findChild(QPushButton)
        self.assertIsNotNone(button)
        self.assertIn("Project: alpha", button.text())
        self.assertEqual(button.objectName(), "containerGroupButton")
        self.assertEqual(button.styleSheet(), "")

        harness.accent_color = "#ff4bd8"
        harness.refresh_dynamic_theme_elements()
        self.assertEqual(metadata_item.foreground().color().name(), "#ff4bd8")
        self.assertEqual(metadata_item.background().color().red(), 255)
        self.assertEqual(metadata_item.background().color().green(), 75)
        self.assertEqual(metadata_item.background().color().blue(), 216)


if __name__ == "__main__":
    unittest.main()
