import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QTableWidget, QTableWidgetItem

import DockerControlCenter as dcc


class _GroupSelectionHarness:
    on_group_checkbox_changed = dcc.MainWindow.on_group_checkbox_changed
    sync_group_checkbox = dcc.MainWindow.sync_group_checkbox
    sync_select_all_checkbox = dcc.MainWindow.sync_select_all_checkbox
    get_selected_names = dcc.MainWindow.get_selected_names


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


if __name__ == "__main__":
    unittest.main()
