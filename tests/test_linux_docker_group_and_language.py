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
            _translate_menus=lambda: calls.append("translate"),
        )
        stub._apply_language_after_menu_close = lambda: dcc.MainWindow._apply_language_after_menu_close(stub)
        scheduled = []

        with (
            patch.object(dcc.os, "name", "posix"),
            patch.object(dcc.QTimer, "singleShot", side_effect=lambda delay, callback: scheduled.append((delay, callback))),
        ):
            dcc.MainWindow.set_language(stub, "PL")

        self.assertEqual(stub.lang, "PL")
        self.assertIs(stub.texts, dcc.TEXTS["PL"])
        settings.setValue.assert_called_once_with("language", "PL")
        self.assertEqual(calls, [])
        self.assertEqual(len(scheduled), 1)
        self.assertGreaterEqual(scheduled[0][0], 100)

        scheduled[0][1]()
        self.assertEqual(calls, ["apply", "translate"])
        self.assertNotIn("menus", calls)

    def test_windows_language_change_keeps_existing_immediate_behavior(self):
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

        with (
            patch.object(dcc.os, "name", "nt"),
            patch.object(dcc.QTimer, "singleShot", side_effect=lambda delay, callback: scheduled.append((delay, callback))),
        ):
            dcc.MainWindow.set_language(stub, "PL")

        self.assertEqual(calls, ["apply"])
        self.assertEqual(scheduled[0][0], 0)
        scheduled[0][1]()
        self.assertEqual(calls, ["apply", "menus"])

    def test_linux_group_lookup_distinguishes_configured_membership(self):
        configured = subprocess.CompletedProcess(
            ["id", "-nG", "alice"], 0, "alice sudo docker\n", ""
        )
        active = subprocess.CompletedProcess(["id", "-nG"], 0, "alice sudo\n", "")
        stub = SimpleNamespace(linux_target_username=lambda: "alice")

        with (
            patch.object(dcc.os, "name", "posix"),
            patch.object(dcc.shutil, "which", return_value="/usr/bin/id"),
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
            linux_target_username=lambda: "alice",
            _run_subprocess_stream=lambda command, emit: captured.append(list(command))
            or subprocess.CompletedProcess(command, 0, "", ""),
        )
        output = []

        with (
            patch.object(dcc.shutil, "which", side_effect=lambda name: {"pkexec": "/usr/bin/pkexec", "usermod": "/usr/sbin/usermod"}.get(name)),
            patch.object(dcc.Path, "is_file", return_value=True),
        ):
            result = dcc.MainWindow._run_linux_docker_group_setup_stream(stub, [], output.append)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured[0][:3], ["/usr/bin/pkexec", "/bin/sh", "-c"])
        self.assertIn("usermod -aG docker alice", captured[0][3])
        self.assertIn("groupadd docker", captured[0][3])
        self.assertEqual(output, ["adding"])

    def test_linux_docker_context_resolves_docker_desktop_socket(self):
        stub = SimpleNamespace()
        context_show = subprocess.CompletedProcess(
            ["docker", "context", "show"], 0, "desktop-linux\n", ""
        )
        context_inspect = subprocess.CompletedProcess(
            ["docker", "context", "inspect", "desktop-linux"],
            0,
            '[{"Endpoints":{"docker":{"Host":"unix:///home/karol/.docker/desktop/docker-cli.sock"}}}]',
            "",
        )

        with (
            patch.object(dcc.os, "name", "posix"),
            patch.dict(dcc.os.environ, {}, clear=True),
            patch.object(dcc.shutil, "which", side_effect=lambda name: "/usr/bin/docker" if name == "docker" else None),
            patch.object(dcc.subprocess, "run", side_effect=[context_show, context_inspect]),
        ):
            endpoint, source = dcc.MainWindow._linux_docker_endpoint_info(stub, refresh=True)

        self.assertEqual(endpoint, "unix:///home/karol/.docker/desktop/docker-cli.sock")
        self.assertEqual(source, "desktop-linux")

    def test_linux_build_client_uses_resolved_context_endpoint(self):
        endpoint = "unix:///home/karol/.docker/desktop/docker-cli.sock"
        stub = SimpleNamespace(linux_docker_endpoint=Mock(return_value=endpoint))

        with (
            patch.object(dcc.os, "name", "posix"),
            patch.object(dcc.docker, "DockerClient") as docker_client,
        ):
            dcc.MainWindow.build_local_docker_client(stub)

        docker_client.assert_called_once_with(base_url=endpoint, timeout=dcc.DOCKER_HTTP_TIMEOUT)
        stub.linux_docker_endpoint.assert_called_once_with(refresh=True)

    def test_docker_desktop_context_does_not_require_docker_group_relaunch(self):
        stub = SimpleNamespace(
            linux_docker_uses_system_socket=lambda: False,
            linux_docker_group_configured=lambda: True,
            linux_docker_group_active=lambda: False,
        )
        with patch.object(dcc.os, "name", "posix"):
            self.assertFalse(dcc.MainWindow.linux_docker_group_requires_relaunch(stub))

    def test_linux_target_username_prefers_non_root_desktop_user(self):
        stub = SimpleNamespace()
        with (
            patch.object(dcc.os, "name", "posix"),
            patch.dict(dcc.os.environ, {"SUDO_USER": "karol", "USER": "root", "LOGNAME": "root"}, clear=True),
            patch.object(dcc.getpass, "getuser", return_value="root"),
        ):
            username = dcc.MainWindow.linux_target_username(stub)

        self.assertEqual(username, "karol")

    def test_first_run_confirms_group_configured_while_relogin_is_pending(self):
        main_window = SimpleNamespace(
            is_local_docker_available=lambda: False,
            linux_docker_auto_install_supported=lambda: True,
            linux_docker_group_configured=lambda: True,
            linux_docker_group_active=lambda: False,
            linux_docker_group_setup_supported=lambda: True,
            linux_docker_uses_system_socket=lambda: True,
            remote_profiles=[],
        )
        stub = SimpleNamespace(
            texts=dcc.TEXTS["EN"],
            main_window=main_window,
            system_label=Mock(),
            docker_status=Mock(),
            install_docker_button=Mock(),
            add_docker_group_button=Mock(),
            profiles_count_label=Mock(),
            key_paths_label=Mock(),
        )

        with (
            patch.object(dcc.shutil, "which", side_effect=lambda name: "/usr/bin/docker" if name == "docker" else None),
            patch.object(dcc, "detect_local_os_name", return_value="MX Linux"),
        ):
            dcc.FirstRunWizardDialog.refresh_state(stub)

        stub.docker_status.setText.assert_called_with(dcc.TEXTS["EN"]["dependencies_docker_group_session"])
        stub.docker_status.setStyleSheet.assert_called_with("color: #58d68d;")
        stub.add_docker_group_button.setText.assert_called_with(dcc.TEXTS["EN"]["first_run_docker_group_added"])
        stub.add_docker_group_button.setEnabled.assert_called_with(False)

    def test_linux_platform_text_uses_linux_specific_description(self):
        stub = SimpleNamespace(texts=dcc.TEXTS["EN"])
        with patch.object(dcc.os, "name", "posix"):
            subtitle = dcc.MainWindow.platform_text(stub, "hero_subtitle")
            local_info = dcc.MainWindow.platform_text(stub, "local_profiles_text")

        self.assertIn("local Docker Engine", subtitle)
        self.assertNotIn("WSL", subtitle)
        self.assertIn("docker ps", local_info)
        self.assertNotIn("PowerShell", local_info)

    def test_local_connect_does_not_hit_socket_before_new_docker_group_is_active(self):
        stub = SimpleNamespace(
            current_backend="remote",
            current_wsl_distro="Ubuntu",
            active_remote_profile=object(),
            client=object(),
            linux_docker_group_requires_relaunch=lambda: True,
            update_infrastructure_ui=Mock(),
            show_local_docker_unavailable=Mock(),
            build_local_docker_client=Mock(),
        )

        with (
            patch.object(dcc.os, "name", "posix"),
            patch.object(dcc.shutil, "which", side_effect=lambda name: "/usr/bin/docker" if name == "docker" else None),
        ):
            dcc.MainWindow.connect_local_docker(stub)

        self.assertEqual(stub.current_backend, "local")
        self.assertIsNone(stub.client)
        stub.build_local_docker_client.assert_not_called()
        stub.show_local_docker_unavailable.assert_called_once_with()

    def test_linux_docker_group_relaunch_uses_sg_docker(self):
        stub = SimpleNamespace(texts=dcc.TEXTS["EN"])
        with (
            patch.object(dcc.shutil, "which", side_effect=lambda name: "/usr/bin/sg" if name == "sg" else None),
            patch.object(dcc.sys, "frozen", True, create=True),
            patch.object(dcc.sys, "executable", "/opt/dcc/DockerControlCenter"),
            patch.object(dcc.sys, "argv", ["DockerControlCenter", "--example"]),
        ):
            program, arguments, working_directory = dcc.MainWindow._linux_docker_group_relaunch_command(stub)

        self.assertEqual(program, "/usr/bin/sg")
        self.assertEqual(arguments[:2], ["docker", "-c"])
        self.assertIn("/opt/dcc/DockerControlCenter", arguments[2])
        self.assertIn("--example", arguments[2])
        self.assertTrue(working_directory.replace("\\", "/").endswith("/opt/dcc"))


if __name__ == "__main__":
    unittest.main()
