import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QRectF, QSettings, Qt, QTimer
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

import DockerControlCenter as dcc
import RepoBuilder as repo_builder

ROOT = Path(__file__).resolve().parents[1]


def _dispose_widget(widget):
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


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
            dialog = dcc.ThemeSettingsDialog(settings, dcc.TEXTS["PL"])
            self.assertEqual(dialog.neon_color_combo.currentData(), "#123456")
            self.assertIn("#123456", dialog.neon_color_combo.currentText())
            header_index = dialog.neon_color_combo.findText(dcc.TEXTS["PL"]["neon_muted_header"])
            self.assertGreaterEqual(header_index, 0)
            self.assertFalse(dialog.neon_color_combo.model().item(header_index).isEnabled())
            _dispose_widget(dialog)

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

    def test_repo_builder_light_and_day_use_theme_palette_surfaces(self):
        for theme in ("light", "day"):
            with tempfile.TemporaryDirectory() as tmp:
                settings = QSettings(str(Path(tmp) / f"{theme}.ini"), QSettings.Format.IniFormat)
                settings.setValue("theme", theme)
                palette = dcc.palette_for_theme(theme)
                with patch.object(repo_builder, "QSettings", return_value=settings), patch.object(
                    repo_builder.RepoBuilderWindow, "_load_default_checkout"
                ):
                    window = repo_builder.RepoBuilderWindow()
                window._apply_theme()
                qss = QApplication.instance().styleSheet()
                self.assertIn(palette["solid0"], qss)
                self.assertIn(palette["fg"], qss)
                for selector in (
                    "QMainWindow#repoBuilderWindow",
                    "QWidget#repoBuilderRoot",
                    "QWidget#repoBuilderListPanel",
                    "QWidget#repoBuilderTabPage",
                    "QTabWidget#repoBuilderTabs::pane",
                    "QTabWidget#repoBuilderTabs QTabBar::tab",
                    "QLabel#repoBuilderStatus",
                    "QComboBox, QLineEdit, QTextEdit, QPlainTextEdit, QListWidget",
                    "QPushButton",
                    "QLabel, QCheckBox, QRadioButton",
                ):
                    self.assertIn(selector, qss)
                self.assertNotIn("background: #0e0f11", qss.lower())
                self.assertNotIn("background: #18191c", qss.lower())
                window.close()

    def test_repo_builder_rejects_mei_catalog_as_persistent_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unsafe_root = root / "_MEI1234"
            unsafe_root.mkdir()
            unsafe_catalog = unsafe_root / "dcc-catalog.json"
            unsafe_catalog.write_text('{"apps": []}\n', encoding="utf-8")
            settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            with patch.object(repo_builder, "QSettings", return_value=settings), patch.object(
                repo_builder.RepoBuilderWindow, "_load_default_checkout"
            ):
                window = repo_builder.RepoBuilderWindow()
            window.repo_root.setText(str(unsafe_root))
            window.catalog_file.setText(unsafe_catalog.name)
            with patch.object(repo_builder.QMessageBox, "warning") as warning:
                window.load_catalog()
            warning.assert_called_once()
            self.assertIsNone(window.catalog_path)
            self.assertFalse(settings.contains("repo_builder/last_catalog_path"))
            self.assertNotIn("_MEI", window.status.text())
            _dispose_widget(window)

    def test_repo_builder_save_as_defaults_to_permanent_user_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            documents = home / "Documents"
            documents.mkdir(parents=True)
            settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            with patch.object(repo_builder, "QSettings", return_value=settings), patch.object(
                repo_builder.RepoBuilderWindow, "_load_default_checkout"
            ):
                window = repo_builder.RepoBuilderWindow()
            window.repo_root.clear()
            window.catalog_path = None
            chosen = root / "chosen.json"
            with patch.object(repo_builder.Path, "home", return_value=home), patch.object(
                repo_builder.QFileDialog, "getSaveFileName", return_value=(str(chosen), "JSON (*.json)")
            ) as save_dialog, patch.object(window, "_capture_valid_form", return_value=True), patch.object(
                window, "_write_catalog_atomic", return_value=True
            ):
                self.assertTrue(window.save_catalog_as())
            self.assertEqual(Path(save_dialog.call_args.args[2]), documents / "dcc-catalog.json")
            _dispose_widget(window)

    def test_container_view_state_restores_scroll_selection_checks_and_groups(self):
        class Harness:
            pass

        harness = Harness()
        harness.table = QTableWidget(0, 12)
        harness.table.resize(420, 150)
        harness.table.show()
        harness.group_checkboxes = {}
        harness.collapsed_groups = {"project:alpha"}
        harness.sync_group_checkbox = lambda _key: None
        harness.get_selected_names = lambda: dcc.MainWindow.get_selected_names(harness)
        harness._container_row_anchor = lambda row: dcc.MainWindow._container_row_anchor(harness, row)
        harness._find_container_row_anchor = lambda anchor: dcc.MainWindow._find_container_row_anchor(harness, anchor)

        def populate():
            harness.table.setRowCount(0)
            for row in range(40):
                harness.table.insertRow(row)
                checkbox = QCheckBox()
                harness.table.setCellWidget(row, 0, checkbox)
                item = QTableWidgetItem(f"container-{row:02d}")
                item.setData(Qt.ItemDataRole.UserRole, {"row_type": "container", "group": "project:alpha"})
                harness.table.setItem(row, 2, item)
                harness.table.setRowHeight(row, 30)
            for column in range(12):
                harness.table.setColumnWidth(column, 120)
            QApplication.processEvents()

        populate()
        harness.table.cellWidget(10, 0).setChecked(True)
        harness.table.cellWidget(12, 0).setChecked(True)
        harness.table.selectRow(10)
        harness.table.verticalScrollBar().setValue(min(260, harness.table.verticalScrollBar().maximum()))
        harness.table.horizontalScrollBar().setValue(min(180, harness.table.horizontalScrollBar().maximum()))
        QApplication.processEvents()
        before_top = harness.table.rowAt(0)
        before_horizontal = harness.table.horizontalScrollBar().value()
        state = dcc.MainWindow._capture_container_view_state(harness)

        populate()
        harness.collapsed_groups = {"project:other"}
        dcc.MainWindow._restore_container_view_state(harness, state)
        QApplication.processEvents()

        self.assertEqual(harness.collapsed_groups, {"project:alpha"})
        self.assertTrue(harness.table.cellWidget(10, 0).isChecked())
        self.assertTrue(harness.table.cellWidget(12, 0).isChecked())
        self.assertEqual(harness.table.currentRow(), 10)
        self.assertEqual(harness.table.horizontalScrollBar().value(), before_horizontal)
        self.assertGreater(harness.table.verticalScrollBar().value(), 0)
        self.assertEqual(harness.table.rowAt(0), before_top)
        _dispose_widget(harness.table)

    def test_column_magnet_persists_and_sorting_keeps_real_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)

            class Harness:
                pass

            harness = Harness()
            harness.settings = settings
            harness.container_column_magnet = False
            harness._save_container_column_widths = lambda: None
            harness._apply_container_column_magnet = lambda: None
            dcc.MainWindow.set_container_column_magnet(harness, True)
            self.assertTrue(harness.container_column_magnet)
            self.assertEqual(str(settings.value("containers/column_magnet")).lower(), "true")

            harness.table = QTableWidget(0, 12)
            harness.table.setHorizontalHeader(dcc.ResizeGripHeader(Qt.Orientation.Horizontal, harness.table))
            harness.texts = dcc.TEXTS["EN"]
            harness.container_sort_column = None
            harness.container_sort_direction = None
            harness.last_containers = []
            harness.render_container_table = MagicMock()
            harness._set_table_headers = lambda: dcc.MainWindow._set_table_headers(harness)
            dcc.MainWindow._set_table_headers(harness)
            self.assertEqual(harness.table.columnCount(), 12)
            self.assertIsInstance(harness.table.horizontalHeader(), dcc.ResizeGripHeader)
            dcc.MainWindow.on_container_header_clicked(harness, 5)
            self.assertEqual((harness.container_sort_column, harness.container_sort_direction), (5, "desc"))
            dcc.MainWindow.on_container_header_clicked(harness, 5)
            self.assertEqual((harness.container_sort_column, harness.container_sort_direction), (5, "asc"))
            dcc.MainWindow.on_container_header_clicked(harness, 5)
            self.assertEqual((harness.container_sort_column, harness.container_sort_direction), (None, None))
            self.assertEqual(harness.table.columnCount(), 12)
            _dispose_widget(harness.table)

    def test_magnet_checkmark_and_column_grips_render_with_accent(self):
        accent = QColor("#ff00ff")

        checkbox = dcc.VisibleCheckBox("Magnes")
        checkbox.resize(120, 32)
        checkbox.setChecked(True)
        checkbox.setAccentColor(accent.name())
        checkbox.show()
        QApplication.processEvents()
        checkbox_pixmap = QPixmap(checkbox.size())
        checkbox_pixmap.fill(Qt.GlobalColor.transparent)
        checkbox.render(checkbox_pixmap)
        checkbox_image = checkbox_pixmap.toImage()
        checkbox_hits = sum(
            1
            for y in range(checkbox_image.height())
            for x in range(checkbox_image.width())
            if checkbox_image.pixelColor(x, y).red() > 220
            and checkbox_image.pixelColor(x, y).blue() > 220
            and checkbox_image.pixelColor(x, y).green() < 80
        )
        self.assertGreater(checkbox_hits, 2)
        self.assertEqual(checkbox._check_accent.name().lower(), accent.name().lower())
        _dispose_widget(checkbox)

        table = QTableWidget(1, 3)
        header = dcc.ResizeGripHeader(Qt.Orientation.Horizontal, table)
        table.setHorizontalHeader(header)
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(column, 100)
        header.setGripColor(accent.name())
        dots = header._grip_dot_rects(QRectF(0, 0, 100, 30))
        self.assertEqual(len(dots), 3)
        self.assertEqual(len({round(dot.center().x(), 2) for dot in dots}), 1)
        self.assertEqual([round(dot.center().y(), 2) for dot in dots], [11.0, 15.0, 19.0])
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeMode.Interactive)
        self.assertEqual(header._grip_color.name().lower(), accent.name().lower())
        _dispose_widget(table)

    def test_resize_grips_are_visible_in_the_rendered_header_and_keep_resize_sort(self):
        table = QTableWidget(2, 4)
        table.setHorizontalHeaderLabels(["Name", "Image", "Status", "Ports"])
        header = dcc.ResizeGripHeader(Qt.Orientation.Horizontal, table)
        table.setHorizontalHeader(header)
        table.setStyleSheet(
            "QHeaderView::section { background: #30343b; color: #eeeeee; "
            "padding: 5px 10px 5px 6px; border: 0; }"
        )
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(column, 120)
        header.setSectionsClickable(True)
        header.setGripColor("#ff334d")
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        table.resize(560, 160)
        table.show()
        self.app.processEvents()

        def accent_pixels(section):
            pixmap = header.viewport().grab()
            self.assertIsInstance(pixmap, QPixmap)
            image = pixmap.toImage()
            boundary = header.sectionViewportPosition(section) + header.sectionSize(section)
            center_y = header.height() // 2
            hits = 0
            for y in range(max(0, center_y - 8), min(image.height(), center_y + 9)):
                for x in range(max(0, boundary - 8), min(image.width(), boundary)):
                    color = image.pixelColor(x, y)
                    if color.red() > 180 and color.green() < 130 and color.blue() < 150:
                        hits += 1
            return hits

        self.assertGreaterEqual(accent_pixels(0), 18, "the first real header divider needs a visible accent grip")
        self.assertLess(accent_pixels(3), 8, "the final visible section must not show a resize grip")

        clicked = []
        header.sectionClicked.connect(clicked.append)
        click_x = header.sectionViewportPosition(1) + header.sectionSize(1) // 2
        QTest.mouseClick(
            header.viewport(),
            Qt.MouseButton.LeftButton,
            pos=QPoint(click_x, header.height() // 2),
        )
        self.assertEqual(clicked, [1])

        old_width = header.sectionSize(0)
        divider_x = header.sectionViewportPosition(0) + old_width - 1
        middle_y = header.height() // 2
        QTest.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(divider_x, middle_y))
        QTest.mouseMove(header.viewport(), QPoint(divider_x + 24, middle_y), delay=80)
        QTest.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(divider_x + 24, middle_y))
        self.app.processEvents()
        self.assertGreaterEqual(header.sectionSize(0), old_width + 18)
        self.assertGreaterEqual(accent_pixels(0), 18, "the grip must follow the resized section boundary")
        _dispose_widget(table)

    def test_header_grips_render_with_contrast_in_all_five_themes(self):
        table = QTableWidget(1, 3)
        table.setHorizontalHeaderLabels(["Name", "Status", "CPU"])
        header = dcc.ResizeGripHeader(Qt.Orientation.Horizontal, table)
        table.setHorizontalHeader(header)
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(column, 110)
        header.setStretchLastSection(False)
        table.resize(390, 120)
        table.show()

        for theme in ("day", "light", "dark", "black", "night"):
            colors = dcc.palette_for_theme(theme)
            table.setStyleSheet(
                "QHeaderView::section { background: %s; color: %s; padding: 4px 8px; border: 0; }"
                % (colors["solid0"], colors["fg"])
            )
            grip_color = QColor(dcc.effective_accent_color(theme, "#33f0ff"))
            header.setGripColor(grip_color.name())
            QApplication.processEvents()

            image = header.viewport().grab().toImage()
            boundary = header.sectionViewportPosition(0) + header.sectionSize(0)
            center_y = header.height() // 2
            background = QColor(colors["solid0"])
            hits = 0
            for y in range(max(0, center_y - 8), min(image.height(), center_y + 9)):
                for x in range(max(0, boundary - 8), min(image.width(), boundary)):
                    color = image.pixelColor(x, y)
                    if (
                        abs(color.red() - grip_color.red()) <= 55
                        and abs(color.green() - grip_color.green()) <= 55
                        and abs(color.blue() - grip_color.blue()) <= 55
                    ):
                        hits += 1
            self.assertGreaterEqual(hits, 12, f"{theme} needs a visible accent grip")
            color_distance = (
                abs(grip_color.red() - background.red())
                + abs(grip_color.green() - background.green())
                + abs(grip_color.blue() - background.blue())
            )
            self.assertGreater(color_distance, 100, f"{theme} accent should remain distinct from the header surface")
            self.assertGreaterEqual(header.sectionSize(0), 24)
            self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeMode.Interactive)

        _dispose_widget(table)

    def test_frozen_child_processes_use_persistent_directory_and_clean_bootloader_state(self):
        bundle = Path(r"C:\Users\Kosmo\AppData\Local\Temp\_MEI123456")
        executable = Path(r"C:\Program Files\DCC\DockerControlCenter.exe")
        base_environment = {
            "PATH": os.pathsep.join((str(bundle), str(bundle / "bin"), r"C:\Windows\System32")),
            "_PYI_APPLICATION_HOME_DIR": str(bundle),
            "_PYI_PARENT_PROCESS_LEVEL": "1",
            "PYINSTALLER_RESET_ENVIRONMENT": "1",
            "KEEP_ME": "yes",
        }

        with (
            patch.object(dcc.sys, "frozen", True, create=True),
            patch.object(dcc.sys, "executable", str(executable)),
            patch.object(dcc.sys, "_MEIPASS", str(bundle), create=True),
        ):
            self.assertEqual(dcc.application_working_directory(), executable.parent)
            child_environment = dcc.external_process_environment(base_environment)
            self.assertEqual(child_environment["PATH"], r"C:\Windows\System32")
            self.assertEqual(child_environment["KEEP_ME"], "yes")
            self.assertNotIn("_PYI_APPLICATION_HOME_DIR", child_environment)
            self.assertNotIn("_PYI_PARENT_PROCESS_LEVEL", child_environment)
            self.assertNotIn("PYINSTALLER_RESET_ENVIRONMENT", child_environment)

            class FakeEnvironment:
                values = dict(base_environment)

                @classmethod
                def systemEnvironment(cls):
                    return cls()

                def keys(self):
                    return list(self.values)

                def value(self, key):
                    return self.values.get(key, "")

                def remove(self, key):
                    self.values.pop(key, None)

                def insert(self, key, value):
                    self.values[key] = value

            class FakeProcess:
                instance = None

                def __init__(self):
                    self.environment = None
                    FakeProcess.instance = self

                def setProgram(self, value):
                    self.program = value

                def setArguments(self, value):
                    self.arguments = value

                def setWorkingDirectory(self, value):
                    self.working_directory = value

                def setProcessEnvironment(self, value):
                    self.environment = value

                def startDetached(self):
                    return True

            with patch.object(dcc, "QProcess", FakeProcess), patch.object(dcc, "QProcessEnvironment", FakeEnvironment):
                self.assertTrue(
                    dcc.start_detached_process(
                        str(executable), [], str(executable.parent), restart_frozen_application=True
                    )
                )
            process = FakeProcess.instance
            self.assertEqual(process.working_directory, str(executable.parent))
            self.assertNotIn("_PYI_APPLICATION_HOME_DIR", process.environment.values)
            self.assertEqual(process.environment.values["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_theme_settings_intro_is_one_line_with_requested_section_spacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            dialog = dcc.ThemeSettingsDialog(settings, dcc.TEXTS["PL"])
            dialog.show()
            self.app.processEvents()
            intro_form = dialog.layout().itemAt(0).layout()
            intro = intro_form.itemAt(0).widget()
            form = intro_form.itemAt(1).layout()
            visual_heading = form.itemAt(0).widget()
            gap = visual_heading.y() - (intro.y() + intro.height())
            self.assertEqual(intro.text(), "Ustawienia startowe i wygląd dla lokalnej integracji z Docker.")
            self.assertFalse(intro.wordWrap())
            self.assertLessEqual(intro.height(), intro.fontMetrics().lineSpacing() + 4)
            self.assertGreaterEqual(gap, 8)
            self.assertLessEqual(gap, 16)
            _dispose_widget(dialog)

    def test_column_magnet_grips_and_scroll_state_contract_is_present(self):
        source = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        self.assertIn('self.settings.value("containers/column_magnet", "true")', source)
        self.assertIn("class ResizeGripHeader(QHeaderView)", source)
        self.assertIn("for offset in (-4.0, 0.0, 4.0)", source)
        self.assertIn("header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)", source)
        self.assertIn("_capture_container_view_state", source)
        self.assertIn("_restore_container_view_state", source)
        self.assertIn('"horizontal": horizontal.value()', source)
        self.assertIn('"anchor_offset": anchor_offset', source)

    def test_theme_menu_starts_with_settings_then_day_light_dark_black_night(self):
        source = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        settings_pos = source.index('self.action_theme_settings = self.theme_menu.addAction')
        separator_pos = source.index("self.theme_menu.addSeparator()", settings_pos)
        day_pos = source.index("self.action_theme_day =", separator_pos)
        light_pos = source.index("self.action_theme_light =", day_pos)
        dark_pos = source.index("self.action_theme_dark =", light_pos)
        black_pos = source.index("self.action_theme_black =", dark_pos)
        night_pos = source.index("self.action_theme_night =", black_pos)
        self.assertLess(settings_pos, separator_pos)
        self.assertLess(separator_pos, day_pos)
        self.assertLess(day_pos, light_pos)
        self.assertLess(light_pos, dark_pos)
        self.assertLess(dark_pos, black_pos)
        self.assertLess(black_pos, night_pos)
        self.assertIn('self.action_theme_settings.triggered.connect(self.open_theme_settings_dialog)', source)

    def test_theme_settings_and_general_app_settings_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            theme_dialog = dcc.ThemeSettingsDialog(settings, dcc.TEXTS["EN"])
            self.assertEqual(
                [theme_dialog.theme_combo.itemData(i) for i in range(theme_dialog.theme_combo.count())],
                ["day", "light", "dark", "black", "night"],
            )
            self.assertEqual(theme_dialog.audio_profile_combo.itemData(0), "auto")
            self.assertEqual(theme_dialog.master_slider.minimum(), 0)
            self.assertEqual(theme_dialog.master_slider.maximum(), 100)
            self.assertEqual(theme_dialog.intro_slider.minimum(), 0)
            self.assertEqual(theme_dialog.effects_slider.maximum(), 100)
            self.assertFalse(hasattr(theme_dialog, "auto_start_checkbox"))
            _dispose_widget(theme_dialog)

            app_dialog = dcc.AppSettingsDialog(settings, dcc.TEXTS["EN"])
            self.assertTrue(hasattr(app_dialog, "auto_start_checkbox"))
            self.assertTrue(hasattr(app_dialog, "auto_updates_checkbox"))
            self.assertFalse(hasattr(app_dialog, "theme_combo"))
            self.assertFalse(hasattr(app_dialog, "audio_profile_combo"))
            self.assertFalse(hasattr(app_dialog, "master_slider"))
            _dispose_widget(app_dialog)

    def test_theme_settings_cancel_restores_runtime_state_exactly(self):
        initial = {
            "theme": "night",
            "neon_enabled": True,
            "neon_animate": False,
            "accent_color": "#33f0ff",
            "audio_enabled": True,
            "audio_profile": "black",
            "audio_master_volume": 80,
            "audio_intro_volume": 30,
            "audio_effects_volume": 55,
        }

        class RuntimeParent(QWidget):
            def __init__(self):
                super().__init__()
                self.state = dict(initial)
                self.audio_enabled = initial["audio_enabled"]
                self.audio_profile = initial["audio_profile"]
                self.audio_master_volume = initial["audio_master_volume"]
                self.audio_intro_volume = initial["audio_intro_volume"]
                self.audio_effects_volume = initial["audio_effects_volume"]

            def capture_theme_settings_state(self):
                return dict(self.state)

            def apply_theme_settings_state(self, state, persist=False, play_intro=False):
                self.state = dict(state)
                self.audio_enabled = bool(state["audio_enabled"])
                self.audio_profile = str(state["audio_profile"])
                self.audio_master_volume = int(state["audio_master_volume"])
                self.audio_intro_volume = int(state["audio_intro_volume"])
                self.audio_effects_volume = int(state["audio_effects_volume"])

        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "dcc.ini"), QSettings.Format.IniFormat)
            for key, value in (
                ("theme", initial["theme"]),
                ("neon_enabled", "true"),
                ("neon_animate", "false"),
                ("accent_color", initial["accent_color"]),
                ("audio/enabled", "true"),
                ("audio/profile", initial["audio_profile"]),
                ("audio/master_volume", initial["audio_master_volume"]),
                ("audio/intro_volume", initial["audio_intro_volume"]),
                ("audio/effects_volume", initial["audio_effects_volume"]),
            ):
                settings.setValue(key, value)
            parent = RuntimeParent()
            dialog = dcc.ThemeSettingsDialog(settings, dcc.TEXTS["EN"], parent)
            dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("day"))
            dialog.audio_profile_combo.setCurrentIndex(dialog.audio_profile_combo.findData("light"))
            dialog.audio_enabled_checkbox.setChecked(False)
            dialog.master_slider.setValue(25)
            dialog.intro_slider.setValue(70)
            dialog.effects_slider.setValue(10)
            self.assertNotEqual(parent.state, initial)
            dialog.reject()
            self.assertEqual(parent.state, initial)
            _dispose_widget(parent)


if __name__ == "__main__":
    unittest.main()
