import os
import tempfile
import unittest
import wave
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import DockerControlCenter as dcc


ROOT = Path(__file__).resolve().parents[1]
THEMES = ("night", "black", "dark", "light", "day")
FILES = ("ambient.wav", "start.wav", "stop.wav", "restart.wav", "success.wav", "error.wav", "remove.wav")


class AudioAssetTests(unittest.TestCase):
    def test_all_theme_audio_assets_are_valid_wave_files(self):
        for theme in THEMES:
            for filename in FILES:
                path = ROOT / "assets" / "audio" / theme / filename
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 44, path)
                with wave.open(str(path), "rb") as handle:
                    self.assertEqual(handle.getnchannels(), 1)
                    self.assertEqual(handle.getsampwidth(), 2)
                    self.assertEqual(handle.getframerate(), 22_050)
                    self.assertGreater(handle.getnframes(), 0)

        licenses = (ROOT / "assets" / "audio" / "LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("generated procedurally", licenses.lower())
        self.assertIn("no third-party recordings", licenses.lower())

    def test_resource_resolver_supports_packaged_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            packaged_root = Path(tmp) / "_MEI-dcc-test"
            expected = packaged_root / "assets" / "audio" / "night" / "ambient.wav"
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"RIFF" + b"\0" * 64)
            resolved = dcc.audio_asset_path("night", "ambient.wav", packaged_root)
            self.assertEqual(resolved, expected)
            self.assertTrue(resolved.is_file())

    def test_audio_packaging_references_assets_directory(self):
        windows_spec = (ROOT / "DockerControlCenter.spec").read_text(encoding="utf-8")
        windows_debug_spec = (ROOT / "DockerControlCenterDebug.spec").read_text(encoding="utf-8")
        linux_spec = (ROOT / "packaging" / "linux" / "DockerControlCenter-linux.spec").read_text(encoding="utf-8")
        linux_build = (ROOT / "packaging" / "linux" / "build_deb.sh").read_text(encoding="utf-8")
        for text in (windows_spec, windows_debug_spec, linux_spec):
            self.assertIn("assets/audio", text)
            self.assertNotIn("bg.mp3", text)
        self.assertIn('cp -a "$ROOT_DIR/assets/audio"', linux_build)

    def test_note_precedes_transparency_toggle_and_slider(self):
        source = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        note = source.index("local_layout.addWidget(self.btn_music)")
        toggle = source.index("local_layout.addWidget(self.btn_transparency)")
        slider = source.index("local_layout.addWidget(self.transparency_slider)")
        self.assertLess(note, toggle)
        self.assertLess(toggle, slider)

    def test_audio_event_is_silent_when_disabled(self):
        class Effect:
            def __init__(self):
                self.played = False

            def isPlaying(self):
                return False

            def stop(self):
                pass

            def play(self):
                self.played = True

        effect = Effect()
        harness = type("Harness", (), {"audio_enabled": False, "sfx_effects": {"start": effect}})()
        dcc.MainWindow.play_audio_event(harness, "start")
        self.assertFalse(effect.played)


if __name__ == "__main__":
    unittest.main()
