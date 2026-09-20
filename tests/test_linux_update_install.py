import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import DockerControlCenter as dcc


class _Signal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class _FakeProcess:
    class ProcessChannelMode:
        MergedChannels = object()

    class ProcessError:
        FailedToStart = object()

    def __init__(self, _parent=None):
        self.finished = _Signal()
        self.errorOccurred = _Signal()
        self.started = None
        self.cwd = None
        self.deleted = False

    def setWorkingDirectory(self, cwd):
        self.cwd = cwd

    def setProcessChannelMode(self, _mode):
        pass

    def start(self, program, args):
        self.started = (program, list(args))

    def readAllStandardOutput(self):
        return b""

    def deleteLater(self):
        self.deleted = True


class _StatusBar:
    def __init__(self):
        self.messages = []

    def showMessage(self, message, *_args):
        self.messages.append(message)


class LinuxUpdateInstallTests(unittest.TestCase):
    def make_window_stub(self):
        texts = {
            "status_ready": "ready",
            "msg_error": "error",
            "info_update_download_failed": "download failed",
            "info_update_linux_auth_title": "password required",
            "info_update_linux_auth": "enter password",
            "info_update_linux_installing": "installing",
            "info_update_linux_installed": "installed",
            "info_update_linux_install_failed": "install failed",
        }
        status = _StatusBar()
        stub = SimpleNamespace(
            texts=texts,
            update_install_process=None,
            _status=status,
            statusBar=lambda: status,
            on_linux_update_install_finished=lambda *args: None,
            on_linux_update_install_error=lambda *args: None,
            close=lambda: None,
        )
        return stub

    def test_linux_pkexec_update_keeps_app_open_until_installer_finishes(self):
        stub = self.make_window_stub()
        scheduled = []
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "DockerControlCenter_1.3.5_amd64.deb"
            package.write_bytes(b"deb")
            with (
                patch.object(dcc.sys, "platform", "linux"),
                patch.object(dcc, "QProcess", _FakeProcess),
                patch.object(dcc.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
                patch.object(dcc.QMessageBox, "information") as information,
                patch.object(dcc.QTimer, "singleShot", side_effect=lambda delay, callback: scheduled.append((delay, callback))),
            ):
                dcc.MainWindow.on_update_download_finished(stub, True, str(package), "")

        self.assertIsInstance(stub.update_install_process, _FakeProcess)
        self.assertEqual(
            stub.update_install_process.started,
            ("/usr/bin/pkexec", ["/usr/bin/apt-get", "install", "-y", str(package.resolve())]),
        )
        self.assertEqual(scheduled, [])
        information.assert_called_once()
        self.assertIn("installing", stub._status.messages)

    def test_linux_update_closes_only_after_successful_install(self):
        stub = self.make_window_stub()
        process = _FakeProcess()
        stub.update_install_process = process
        scheduled = []
        with (
            patch.object(dcc.QMessageBox, "information") as information,
            patch.object(dcc.QTimer, "singleShot", side_effect=lambda delay, callback: scheduled.append((delay, callback))),
        ):
            dcc.MainWindow.on_linux_update_install_finished(stub, 0, None)

        self.assertIsNone(stub.update_install_process)
        self.assertTrue(process.deleted)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 250)
        information.assert_called_once()


if __name__ == "__main__":
    unittest.main()
