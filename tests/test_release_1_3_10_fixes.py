import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QWidget

import DockerControlCenter as dcc


class LocalPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(os.name == "nt", "Windows launch flags")
    def test_interactive_windows_shells_request_visible_console(self):
        with patch.object(dcc, "start_external_process") as launch:
            dcc.MainWindow.open_powershell(None, "ssh demo@example.test")
            self.assertEqual(launch.call_args.kwargs["creationflags"],
                             dcc.subprocess.CREATE_NEW_CONSOLE)
            dcc.launch_interactive_terminal(["ssh", "demo@example.test"])
            self.assertEqual(launch.call_args.kwargs["creationflags"],
                             dcc.subprocess.CREATE_NEW_CONSOLE)

    def test_refresh_waits_for_cleanup_even_after_thread_stops(self):
        thread = Mock()
        thread.isRunning.return_value = False
        window = SimpleNamespace(client=Mock(), refresh_thread=thread)
        with patch.object(dcc, "QThread") as factory:
            dcc.MainWindow.refresh_containers(window)
            factory.assert_not_called()

    def test_modal_workflow_defers_periodic_refresh(self):
        window = SimpleNamespace(auto_refresh_enabled=True, client=Mock(),
                                 refresh_thread=None, refresh_containers=Mock())
        with patch.object(dcc.QApplication, "activeModalWidget", return_value=object()):
            dcc.MainWindow.on_auto_refresh_timeout(window)
        window.refresh_containers.assert_not_called()
        with patch.object(dcc.QApplication, "activeModalWidget", return_value=None):
            dcc.MainWindow.on_auto_refresh_timeout(window)
        window.refresh_containers.assert_called_once()

    def test_finished_thread_cannot_clear_another_refresh(self):
        old_thread, current_thread = Mock(), Mock()
        worker = Mock()
        window = SimpleNamespace(sender=lambda: old_thread,
                                 refresh_thread=current_thread, worker=worker)
        dcc.MainWindow.on_container_refresh_thread_finished(window)
        self.assertIs(window.refresh_thread, current_thread)
        self.assertIs(window.worker, worker)
        current_thread.deleteLater.assert_not_called()
        window.sender = lambda: current_thread
        dcc.MainWindow.on_container_refresh_thread_finished(window)
        self.assertIsNone(window.refresh_thread)
        self.assertIsNone(window.worker)
        current_thread.deleteLater.assert_called_once()

    def test_light_store_outer_labels_are_light_on_dark_background(self):
        old_style = self.app.styleSheet()
        self.app.setStyleSheet("QWidget { background: #202020; color: #eeeeee; }")
        try:
            for theme in ("day", "light"):
                parent = QWidget()
                parent.current_theme = theme
                client = SimpleNamespace(containers=SimpleNamespace(list=lambda **kw: []))
                with patch.object(dcc.NewContainerDialog, "refresh_external_catalogs"), \
                     patch.object(dcc.NewContainerDialog, "load_store_image"):
                    dialog = dcc.NewContainerDialog(client, dcc.TEXTS["EN"], parent=parent)
                    dialog.show()
                    self.app.processEvents()
                    for label in (dialog.store_subtitle, dialog.repo_status_label,
                                  dialog.store_categories_title):
                        label.ensurePolished()
                        color = label.palette().color(QPalette.ColorRole.WindowText)
                        self.assertGreater(color.lightness(), 200)
                    # Exercise rebuilding and selecting cards while deferred Qt
                    # layout/scroll callbacks from previous selections are pending.
                    for index in range(30):
                        dialog.search_edit.setText("" if index % 2 else "a")
                        if dialog.catalog_list.count():
                            dialog.catalog_list.setCurrentRow(index % dialog.catalog_list.count())
                        self.app.processEvents()
                    dialog.close()
                    parent.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    self.app.processEvents()
        finally:
            self.app.setStyleSheet(old_style)
