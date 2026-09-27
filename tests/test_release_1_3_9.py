import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import DockerControlCenter as dcc


ROOT = Path(__file__).resolve().parents[1]


class Release139Tests(unittest.TestCase):
    def test_external_process_run_resets_bundle_dll_path_only_during_spawn(self):
        bundle = Path(r"C:\Users\Kosmo\AppData\Local\Temp\_MEI123456")
        dll_path_changes = []
        process = Mock()
        process.args = ["tool.exe", "--version"]
        process.communicate.return_value = ("tool 1.0\n", "")
        process.poll.return_value = 0

        def popen(*args, **kwargs):
            self.assertEqual(dll_path_changes, [None])
            self.assertNotIn("_PYI_PARENT_PROCESS_LEVEL", kwargs["env"])
            self.assertNotIn(str(bundle), kwargs["env"]["PATH"])
            self.assertEqual(kwargs["stdout"], dcc.subprocess.PIPE)
            self.assertEqual(kwargs["stderr"], dcc.subprocess.PIPE)
            return process

        with (
            patch.object(dcc, "_is_frozen_windows_application", return_value=True),
            patch.object(dcc.sys, "frozen", True, create=True),
            patch.object(dcc.sys, "_MEIPASS", str(bundle), create=True),
            patch.dict(
                dcc.os.environ,
                {"PATH": f"{bundle};C:\\Windows\\System32", "_PYI_PARENT_PROCESS_LEVEL": "1"},
                clear=True,
            ),
            patch.object(dcc, "_set_dll_search_directory", side_effect=dll_path_changes.append),
            patch.object(dcc.subprocess, "Popen", side_effect=popen),
        ):
            result = dcc.run_external_process(
                ["tool.exe", "--version"], capture_output=True, text=True, timeout=5, check=True
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "tool 1.0\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(dll_path_changes, [None, str(bundle)])

    def test_external_process_popen_cleans_environment_and_restores_dll_path(self):
        bundle = Path(r"C:\Users\Kosmo\AppData\Local\Temp\_MEI123456")
        dll_path_changes = []
        process = Mock()

        def popen(*args, **kwargs):
            self.assertEqual(dll_path_changes, [None])
            self.assertNotIn("_PYI_PARENT_PROCESS_LEVEL", kwargs["env"])
            self.assertNotIn(str(bundle), kwargs["env"]["PATH"])
            return process

        with (
            patch.object(dcc, "_is_frozen_windows_application", return_value=True),
            patch.object(dcc.sys, "frozen", True, create=True),
            patch.object(dcc.sys, "_MEIPASS", str(bundle), create=True),
            patch.dict(
                dcc.os.environ,
                {"PATH": f"{bundle};C:\\Windows\\System32", "_PYI_PARENT_PROCESS_LEVEL": "1"},
                clear=True,
            ),
            patch.object(dcc, "_set_dll_search_directory", side_effect=dll_path_changes.append),
            patch.object(dcc.subprocess, "Popen", side_effect=popen),
        ):
            result = dcc.start_external_process(["tool.exe", "--version"])

        self.assertIs(result, process)
        self.assertEqual(dll_path_changes, [None, str(bundle)])

    def test_external_process_timeout_kills_and_drains_child(self):
        process = Mock()
        process.args = ["slow-tool.exe"]
        process.communicate.side_effect = [
            dcc.subprocess.TimeoutExpired(process.args, 0.01, output=b"partial"),
            (b"complete", b""),
        ]

        with patch.object(dcc, "start_external_process", return_value=process):
            with self.assertRaises(dcc.subprocess.TimeoutExpired) as caught:
                dcc.run_external_process(process.args, capture_output=True, timeout=0.01)

        process.kill.assert_called_once_with()
        self.assertEqual(process.communicate.call_count, 2)
        self.assertEqual(process.communicate.call_args_list[0].kwargs, {"input": None, "timeout": 0.01})
        self.assertEqual(process.communicate.call_args_list[1].args, ())
        self.assertEqual(caught.exception.output, b"complete")
        self.assertEqual(caught.exception.stderr, b"")

    def test_external_process_restores_bundle_dll_path_after_spawn_failure(self):
        bundle = Path(r"C:\Users\Kosmo\AppData\Local\Temp\_MEI123456")
        dll_path_changes = []

        with (
            patch.object(dcc, "_is_frozen_windows_application", return_value=True),
            patch.object(dcc.sys, "_MEIPASS", str(bundle), create=True),
            patch.object(dcc, "_set_dll_search_directory", side_effect=dll_path_changes.append),
        ):
            with self.assertRaisesRegex(RuntimeError, "spawn failed"):
                dcc._launch_with_system_dll_search_path(lambda: (_ for _ in ()).throw(RuntimeError("spawn failed")))

        self.assertEqual(dll_path_changes, [None, str(bundle)])

    def test_release_version_metadata(self):
        self.assertEqual(dcc.APP_VERSION, "1.3.9")
        for path in (ROOT / "DockerControlCenter.nsi", ROOT / "upstream_assets" / "DockerControlCenter.nsi"):
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn('!define APP_VERSION "1.3.9"', text)

    def test_update_path_138_to_139_is_available(self):
        class VersionHarness:
            _parse_version_value = dcc.MainWindow._parse_version_value

        harness = VersionHarness()
        with patch.object(dcc, "APP_VERSION", "1.3.8"):
            self.assertTrue(dcc.MainWindow._is_newer_version(harness, "v1.3.9"))
            self.assertFalse(dcc.MainWindow._is_newer_version(harness, "v1.3.8"))

    def test_windows_discovery_selects_versioned_setup_asset(self):
        release = {
            "tag_name": "v1.3.9",
            "assets": [
                {"name": "DockerControlCenter_1.3.9_amd64.deb", "browser_download_url": "deb"},
                {"name": "DCCRepoBuilder.exe", "browser_download_url": "wrong"},
                {"name": "DockerControlCenter-Setup-1.3.9.exe", "browser_download_url": "setup"},
            ],
        }
        with patch.object(dcc.sys, "platform", "win32"):
            asset = dcc.MainWindow.select_update_installer_asset(None, release)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["name"], "DockerControlCenter-Setup-1.3.9.exe")

    def test_windows_updater_handoff_and_nsis_guards_remain(self):
        source = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        self.assertIn("dcc-update-handoff.log", source)
        self.assertIn("Start-Sleep -Milliseconds 1200", source)
        self.assertIn("while (Get-Process -Id $DccProcessId -ErrorAction SilentlyContinue)", source)
        self.assertIn("-ArgumentList @('/S', '/DCCUPDATE=1')", source)
        self.assertIn("does not match expected version", source)
        self.assertIn("Show-UpdateFailure $reason", source)
        self.assertIn('"-DccProcessId"', source)
        for path in (ROOT / "DockerControlCenter.nsi", ROOT / "upstream_assets" / "DockerControlCenter.nsi"):
            nsi = path.read_text(encoding="utf-8-sig").lower()
            self.assertNotIn("taskkill", nsi)
            self.assertNotIn("stop-process", nsi)
            self.assertIn("dcc-update-handoff*.ps1", nsi)
            self.assertIn("setsilent silent", nsi)
            self.assertNotIn('execwait \'"$instdir\\${app_exe}" --self-check\'', nsi)

    def test_windows_installer_shortcuts_graceful_close_and_relaunch(self):
        for path in (ROOT / "DockerControlCenter.nsi", ROOT / "upstream_assets" / "DockerControlCenter.nsi"):
            nsi = path.read_text(encoding="utf-8-sig")
            self.assertIn("DCC - Docker Control Center.lnk", nsi)
            self.assertIn("DCC Repo Builder.lnk", nsi)
            self.assertIn("Uninstall DCC.lnk", nsi)
            self.assertIn("CloseMainWindow", nsi)
            self.assertIn("DCC jest obecnie uruchomione. Aplikacja musi zostać zamknięta przed instalacją lub aktualizacją. Zamknąć DCC i kontynuować?", nsi)
            self.assertIn("DCC is currently running. The application must be closed before installation or update. Close DCC and continue?", nsi)
            self.assertIn("/DCCUPDATE=", nsi)
            self.assertIn("SHChangeNotify", nsi)

    def test_nsis_source_is_utf8_and_shortcut_identity_failure_is_nonfatal(self):
        root_nsi = ROOT / "DockerControlCenter.nsi"
        build_nsi = ROOT / "upstream_assets" / "DockerControlCenter.nsi"
        self.assertEqual(root_nsi.read_bytes(), build_nsi.read_bytes())
        self.assertTrue(build_nsi.read_bytes().startswith(b"\xef\xbb\xbf"))
        nsi = build_nsi.read_text(encoding="utf-8-sig")
        self.assertIn("-LogPath \"$InstDir\\shortcut-appids.log\"", nsi)
        self.assertIn("Skróty utworzono", nsi)
        self.assertIn("Installation will continue.", nsi)
        failed_block = nsi.split("shortcut_ids_failed:", 1)[1].split("shortcut_ids_ready:", 1)[0]
        self.assertIn("DetailPrint", failed_block)
        self.assertIn("FileWrite", failed_block)
        self.assertNotIn("Abort", failed_block)

        helper = (ROOT / "packaging" / "windows" / "set_shortcut_app_id.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Marshal.QueryInterface(unknown, ref propertyStoreId, out storePointer)", helper)
        self.assertNotIn("Marshal.QueryInterface(unknown, in propertyStoreId", helper)
        self.assertIn("Write-ShortcutHelperLog", helper)
        self.assertIn("User Pinned\\TaskBar", helper)
        self.assertIn('IconLocation = "$target,0"', helper)
        self.assertIn("PinnedShortcutDirectory", helper)

    def test_windows_identity_and_version_resources(self):
        source = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        repo = (ROOT / "RepoBuilder.py").read_text(encoding="utf-8")
        self.assertIn('MAIN_APP_USER_MODEL_ID = "Hattimon.DCC"', source)
        self.assertIn('REPO_BUILDER_APP_USER_MODEL_ID = "Hattimon.DCC.RepoBuilder"', source)
        self.assertIn("set_windows_app_user_model_id(MAIN_APP_USER_MODEL_ID)", source)
        self.assertIn("REPO_BUILDER_APP_USER_MODEL_ID", repo)
        main_version = (ROOT / "packaging" / "windows" / "DockerControlCenter.version.txt").read_text(encoding="utf-8")
        repo_version = (ROOT / "packaging" / "windows" / "RepoBuilder.version.txt").read_text(encoding="utf-8")
        self.assertIn("DCC - Docker Control Center", main_version)
        self.assertIn("DCC Repo Builder", repo_version)
        self.assertIn("1.3.9", main_version)
        self.assertIn("1.3.9", repo_version)

    def test_stage_c_start_menu_icons_registration_and_running_process_flow(self):
        for path in (ROOT / "DockerControlCenter.nsi", ROOT / "upstream_assets" / "DockerControlCenter.nsi"):
            nsi = path.read_text(encoding="utf-8-sig")
            self.assertIn('!define START_MENU_DIR "DCC"', nsi)
            self.assertIn('CreateShortcut "$SMPROGRAMS\\${START_MENU_DIR}\\DCC - Docker Control Center.lnk" "$InstDir\\${APP_EXE}"', nsi)
            self.assertIn('CreateShortcut "$SMPROGRAMS\\${START_MENU_DIR}\\DCC Repo Builder.lnk" "$InstDir\\${REPO_BUILDER_EXE}"', nsi)
            self.assertIn('CreateShortcut "$SMPROGRAMS\\${START_MENU_DIR}\\Uninstall DCC.lnk" "$InstDir\\Uninstall.exe"', nsi)
            self.assertIn('Delete "$SMPROGRAMS\\Docker Control Center\\Docker Control Center.lnk"', nsi)
            self.assertIn('Delete "$DESKTOP\\Docker Control Center.lnk"', nsi)
            self.assertIn('DisplayName" "${APP_NAME}', nsi)
            self.assertIn('DisplayVersion" "${APP_VERSION}', nsi)
            self.assertIn('CloseMainWindow', nsi)
            self.assertIn('Sleep 500', nsi)
            self.assertIn('DockerControlCenter,DCCRepoBuilder', nsi)
            self.assertIn('SHChangeNotify', nsi)
            self.assertEqual(nsi.count("Page custom LaunchDccPage LaunchDccLeave"), 1)
        main_spec = (ROOT / "DockerControlCenter.spec").read_text(encoding="utf-8")
        repo_spec = (ROOT / "RepoBuilder.spec").read_text(encoding="utf-8")
        shortcut_helper = (ROOT / "packaging" / "windows" / "set_shortcut_app_id.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("upstream_assets/icon.ico", main_spec)
        self.assertIn("upstream_assets/repo_builder_icon.ico", repo_spec)
        self.assertIn("set_shortcut_app_id.ps1", nsi)
        self.assertIn("Hattimon.DCC", nsi)
        self.assertIn("Hattimon.DCC.RepoBuilder", nsi)
        self.assertIn("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3", shortcut_helper)
        self.assertIn("PropertyId = 5", shortcut_helper)

    def test_stage_c_manual_launch_checkbox_is_default_on_and_update_relaunch_is_single_owner(self):
        for path in (ROOT / "DockerControlCenter.nsi", ROOT / "upstream_assets" / "DockerControlCenter.nsi"):
            nsi = path.read_text(encoding="utf-8-sig")
            self.assertIn('Page custom LaunchDccPage LaunchDccLeave', nsi)
            self.assertIn('"Uruchom DCC"', nsi)
            self.assertIn('"Launch DCC"', nsi)
            self.assertIn('${NSD_Check} $LaunchDccCheckbox', nsi)
            self.assertIn('${NSD_GetState} $LaunchDccCheckbox $0', nsi)
            self.assertIn('StrCmp $UpdateMode "1" launch_after_install', nsi)
            self.assertIn('StrCmp $UpdateMode "1" launch_page_done', nsi)
        source=(ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        self.assertIn("dcc-update-handoff.log", source)
        self.assertIn("while (Get-Process -Id $DccProcessId -ErrorAction SilentlyContinue)", source)
        self.assertIn("Start-Sleep -Milliseconds 1200", source)
        self.assertIn("-ArgumentList @('/S', '/DCCUPDATE=1')", source)

    def test_release_notes_and_expected_asset_names(self):
        notes = (ROOT / "release" / "RELEASE_NOTES_1.3.9.md").read_text(encoding="utf-8")
        self.assertIn("DockerControlCenter-Setup-1.3.9.exe", notes)
        self.assertIn("DockerControlCenter_1.3.9_amd64.deb", notes)
        self.assertIn("SHA256SUMS-1.3.9.txt", notes)


if __name__ == "__main__":
    unittest.main()
