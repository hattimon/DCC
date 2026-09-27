import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows Shell Link integration test")
class ShortcutAppIdWindowsTests(unittest.TestCase):
    def test_helper_sets_app_user_model_ids_on_real_temporary_shortcuts(self):
        powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        helper = ROOT / "packaging" / "windows" / "set_shortcut_app_id.ps1"
        script = r"""
param([Parameter(Mandatory=$true)][string]$HelperPath, [Parameter(Mandatory=$true)][string]$ScratchPath)
$ErrorActionPreference = 'Stop'
$wsh = New-Object -ComObject WScript.Shell
$mainPath = Join-Path $ScratchPath 'main.lnk'
$repoPath = Join-Path $ScratchPath 'repo.lnk'
foreach ($path in @($mainPath, $repoPath)) {
    $shortcut = $wsh.CreateShortcut($path)
    $shortcut.TargetPath = Join-Path $env:WINDIR 'System32\notepad.exe'
    $shortcut.Save()
}
$logPath = Join-Path $ScratchPath 'shortcut-appids.log'
& $HelperPath -MainShortcut $mainPath -MainAppId 'Hattimon.DCC.Test' -RepoShortcut $repoPath -RepoAppId 'Hattimon.DCC.RepoBuilder.Test' -LogPath $logPath
$shell = New-Object -ComObject Shell.Application
$folder = $shell.Namespace($ScratchPath)
$mainId = $folder.ParseName('main.lnk').ExtendedProperty('System.AppUserModel.ID')
$repoId = $folder.ParseName('repo.lnk').ExtendedProperty('System.AppUserModel.ID')
if ($mainId -ne 'Hattimon.DCC.Test') { throw "Wrong main shortcut ID: '$mainId'" }
if ($repoId -ne 'Hattimon.DCC.RepoBuilder.Test') { throw "Wrong Repo Builder shortcut ID: '$repoId'" }
if (-not (Test-Path -LiteralPath $logPath)) { throw 'Shortcut identity log was not created.' }
Write-Output "$mainId|$repoId"
"""

        with tempfile.TemporaryDirectory(prefix="DCC139-shortcuts-") as scratch:
            scratch_path = Path(scratch)
            driver = scratch_path / "verify-shortcuts.ps1"
            driver.write_text(script, encoding="utf-8-sig")
            result = subprocess.run(
                [
                    str(powershell),
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(driver),
                    "-HelperPath",
                    str(helper),
                    "-ScratchPath",
                    str(scratch_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            self.assertIn("Hattimon.DCC.Test|Hattimon.DCC.RepoBuilder.Test", result.stdout)


if __name__ == "__main__":
    unittest.main()
