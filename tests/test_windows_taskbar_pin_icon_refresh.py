import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows Shell Link integration test")
class WindowsTaskbarPinIconRefreshTests(unittest.TestCase):
    def test_helper_refreshes_only_dcc_pins_and_preserves_their_targets(self):
        powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        helper = ROOT / "packaging" / "windows" / "set_shortcut_app_id.ps1"
        script = r"""
param([Parameter(Mandatory=$true)][string]$HelperPath, [Parameter(Mandatory=$true)][string]$ScratchPath)
$ErrorActionPreference = 'Stop'
$wsh = New-Object -ComObject WScript.Shell
$pinnedDir = Join-Path $ScratchPath 'pinned'
New-Item -ItemType Directory -Path $pinnedDir | Out-Null
$mainTarget = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$repoTarget = Join-Path $env:WINDIR 'System32\notepad.exe'
$otherTarget = Join-Path $env:WINDIR 'System32\cmd.exe'
$mainPath = Join-Path $ScratchPath 'main.lnk'
$repoPath = Join-Path $ScratchPath 'repo.lnk'
$pinMainPath = Join-Path $pinnedDir 'DCC.lnk'
$pinRepoPath = Join-Path $pinnedDir 'DCC Repo Builder.lnk'
$otherPath = Join-Path $pinnedDir 'Other.lnk'
foreach ($entry in @(
    @{ Path = $mainPath; Target = $mainTarget },
    @{ Path = $repoPath; Target = $repoTarget },
    @{ Path = $pinMainPath; Target = $mainTarget },
    @{ Path = $pinRepoPath; Target = $repoTarget },
    @{ Path = $otherPath; Target = $otherTarget }
)) {
    $shortcut = $wsh.CreateShortcut($entry.Path)
    $shortcut.TargetPath = $entry.Target
    $shortcut.Save()
}
$logPath = Join-Path $ScratchPath 'shortcut-appids.log'
& $HelperPath -MainShortcut $mainPath -MainAppId 'Hattimon.DCC.Test' -RepoShortcut $repoPath -RepoAppId 'Hattimon.DCC.RepoBuilder.Test' -LogPath $logPath -PinnedShortcutDirectory $pinnedDir
$pinMain = $wsh.CreateShortcut($pinMainPath)
$pinRepo = $wsh.CreateShortcut($pinRepoPath)
$other = $wsh.CreateShortcut($otherPath)
$otherIconBefore = $other.IconLocation
if ([IO.Path]::GetFullPath($pinMain.TargetPath) -ne [IO.Path]::GetFullPath($mainTarget)) { throw 'DCC pin target changed.' }
if ([IO.Path]::GetFullPath($pinRepo.TargetPath) -ne [IO.Path]::GetFullPath($repoTarget)) { throw 'Repo Builder pin target changed.' }
if ($pinMain.IconLocation -ne "$mainTarget,0") { throw "Wrong DCC pin icon: '$($pinMain.IconLocation)'" }
if ($pinRepo.IconLocation -ne "$repoTarget,0") { throw "Wrong Repo Builder pin icon: '$($pinRepo.IconLocation)'" }
if ($other.IconLocation -ne $otherIconBefore) { throw 'An unrelated pinned shortcut was changed.' }
if (-not (Test-Path -LiteralPath $logPath)) { throw 'Shortcut identity log was not created.' }
Write-Output "$($pinMain.IconLocation)|$($pinRepo.IconLocation)"
"""

        with tempfile.TemporaryDirectory(prefix="DCC139-taskbar-pins-") as scratch:
            scratch_path = Path(scratch)
            driver = scratch_path / "verify-taskbar-pins.ps1"
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
                timeout=45,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            self.assertIn("powershell.exe,0|", result.stdout)
            self.assertIn("notepad.exe,0", result.stdout)


if __name__ == "__main__":
    unittest.main()
