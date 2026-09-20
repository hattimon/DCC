import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import DockerControlCenter as dcc


class LinuxDockerGroupAndLanguageTests(unittest.TestCase):
    def test_language_change_defers_menu_rebuild_until_signal_returns(self):
        calls = []
        settings = Mock()
        stub = SimpleNamespace(
            lang="EN",
            texts=dcc.TEXTS["EN"],
            settings=settings,
            apply_language=lambda: calls.append("apply"),
            _build_menus=lambda: calls.append("menus"),
        )
        scheduled = []

        with patch.object(dcc.QTimer, "singleShot", side_effect=lambda delay, callback: scheduled.append((delay, callback))):
            dcc.MainWindow.set_language(stub, "PL")

        self.assertEqual(stub.lang, "PL")
        self.assertIs(stub.texts, dcc.TEXTS["PL"])
        settings.setValue.assert_called_once_with("language", "PL")
        self.assertEqual(calls, ["apply"])
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 0)

        scheduled[0][1]()
        self.assertEqual(calls, ["apply", "menus"])

    def test_linux_group_lookup_distinguishes_configured_membership(self):
        configured = subprocess.CompletedProcess(
            ["id", "-nG", "alice"], 0, "alice sudo docker\n", ""
        )
        active = subprocess.CompletedProcess(["id", "-nG"], 0, "alice sudo\n", "")
        stub = SimpleNamespace()

        with (
            patch.object(dcc.os, "name", "posix"),
            patch.object(dcc.shutil, "which", return_value="/usr/bin/id"),
            patch.object(dcc.getpass, "getuser", return_value="alice"),
            patch.object(dcc.subprocess, "run", side_effect=[configured, active]),
        ):
            configured_groups = dcc.MainWindow._linux_user_groups(stub, configured=True)
            active_groups = dcc.MainWindow._linux_user_groups(stub, configured=False)

        self.assertIn("docker", configured_groups)
        self.assertNotIn("docker", active_groups)

    def test_docker_group_setup_uses_pkexec_without_collecting_password(self):
        captured = []
        stub = SimpleNamespace(
            texts={
                "docker_group_unsupported": "unsupported",
                "docker_group_already_member": "already",
                "docker_group_install_status": "adding",
            },
            linux_docker_group_setup_supported=lambda: True,
            linux_docker_group_configured=lambda: False,
            _run_subprocess_stream=lambda command, emit: captured.append(list(command))
            or subprocess.CompletedProcess(command, 0, "", ""),
        )
        output = []

        with (
            patch.object(dcc.getpass, "getuser", return_value="alice"),
            patch.object(dcc.shutil, "which", side_effect=lambda name: {"pkexec": "/usr/bin/pkexec", "usermod": "/usr/sbin/usermod"}.get(name)),
            patch.object(dcc.Path, "is_file", return_value=True),
        ):
            result = dcc.MainWindow._run_linux_docker_group_setup_stream(stub, [], output.append)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured, [["/usr/bin/pkexec", "/usr/sbin/usermod", "-aG", "docker", "alice"]])
        self.assertEqual(output, ["adding"])


if __name__ == "__main__":
    unittest.main()
