import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NSIS = Path(r"C:\Program Files (x86)\NSIS\makensis.exe")
EXE = ROOT / "dist" / "DockerControlCenter.exe"


@unittest.skipUnless(os.name == "nt" and NSIS.exists() and EXE.exists(),
                     "Requires Windows, NSIS and built DCC")
class InstallerRestartTests(unittest.TestCase):
    def test_installer_launch_ignores_deleted_parent_extraction(self):
        source = (ROOT / "DockerControlCenter.nsi").read_text(encoding="utf-8-sig")
        self.assertEqual(source.count("Call LaunchDccClean"), 2)
        function = "Function LaunchDccClean" + source.split(
            "Function LaunchDccClean", 1)[1].split("FunctionEnd", 1)[0] + "FunctionEnd"
        # Exercise the production launch function, waiting for self-check instead of GUI.
        function = function.replace(
            'Exec \'"$InstDir\\${APP_EXE}"\'',
            'ExecWait \'"$InstDir\\${APP_EXE}" --self-check\' $0\n  SetErrorLevel $0')
        with tempfile.TemporaryDirectory(prefix="dcc-restart-") as directory:
            scratch = Path(directory)
            harness = scratch / "restart.exe"
            script = scratch / "restart.nsi"
            script.write_text(
                'Unicode True\nRequestExecutionLevel user\nSilentInstall silent\n'
                f'OutFile "{harness}"\n!define APP_EXE "{EXE.name}"\n'
                f'Section\n  StrCpy $InstDir "{EXE.parent}"\n'
                '  Call LaunchDccClean\nSectionEnd\n' + function,
                encoding="utf-8-sig")
            subprocess.run([str(NSIS), str(script)], check=True, capture_output=True)
            environment = dict(os.environ)
            environment.update({
                "_PYI_ARCHIVE_FILE": str(EXE),
                "_PYI_APPLICATION_HOME_DIR": str(scratch / "_MEI_deleted"),
                "_PYI_PARENT_PROCESS_LEVEL": "1",
                "PYINSTALLER_RESET_ENVIRONMENT": "0",
            })
            result = subprocess.run([str(harness)], env=environment, timeout=60)
            self.assertEqual(result.returncode, 0)
