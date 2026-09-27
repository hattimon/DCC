import os
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import DockerControlCenter as dcc


ROOT = Path(__file__).resolve().parents[1]


class Release139Tests(unittest.TestCase):
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
        self.assertIn("-ArgumentList '/DCCUPDATE=1'", source)
        self.assertIn('"-DccProcessId"', source)
        for path in (ROOT / "DockerControlCenter.nsi", ROOT / "upstream_assets" / "DockerControlCenter.nsi"):
            nsi = path.read_text(encoding="utf-8-sig").lower()
            self.assertNotIn("taskkill", nsi)
            self.assertNotIn("stop-process", nsi)
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
        self.assertIn("-ArgumentList '/DCCUPDATE=1'", source)

    def test_release_notes_and_expected_asset_names(self):
        notes = (ROOT / "release" / "RELEASE_NOTES_1.3.9.md").read_text(encoding="utf-8")
        self.assertIn("DockerControlCenter-Setup-1.3.9.exe", notes)
        self.assertIn("DockerControlCenter_1.3.9_amd64.deb", notes)
        self.assertIn("SHA256SUMS-1.3.9.txt", notes)


if __name__ == "__main__":
    unittest.main()
