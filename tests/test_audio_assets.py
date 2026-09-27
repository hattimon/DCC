import os
import hashlib
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings

import DockerControlCenter as dcc


ROOT = Path(__file__).resolve().parents[1]
THEMES = ("night", "black", "dark", "light", "day")
FILES = (
    "intro.wav",
    "container_start_requested.wav",
    "container_started.wav",
    "container_stop_requested.wav",
    "container_stopped.wav",
    "container_restart_requested.wav",
    "container_restart_completed.wav",
    "install_completed.wav",
    "uninstall_completed.wav",
    "host_connected.wav",
    "success.wav",
    "warning.wav",
    "error.wav",
)
LEGACY = {"ambient.wav", "start.wav", "stop.wav", "restart.wav", "remove.wav"}


class AudioAssetTests(unittest.TestCase):
    def test_all_theme_audio_assets_are_valid_wave_files(self):
        signatures = {}
        for theme in THEMES:
            hashes = []
            for filename in FILES:
                path = ROOT / "assets" / "audio" / theme / filename
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 44, path)
                with wave.open(str(path), "rb") as handle:
                    self.assertEqual(handle.getnchannels(), 1)
                    self.assertEqual(handle.getsampwidth(), 2)
                    self.assertEqual(handle.getframerate(), 22_050)
                    self.assertGreater(handle.getnframes(), 0)
                    duration = handle.getnframes() / handle.getframerate()
                    raw = handle.readframes(handle.getnframes())
                if filename == "intro.wav":
                    self.assertGreaterEqual(duration, 2.0)
                    self.assertLessEqual(duration, 6.0)
                else:
                    self.assertLess(duration, 2.0)
                hashes.append(hashlib.sha256(raw).hexdigest())
            signatures[theme] = tuple(hashes)
            self.assertFalse(LEGACY.intersection(path.name for path in (ROOT / "assets" / "audio" / theme).glob("*.wav")))

        self.assertEqual(sum(1 for _ in (ROOT / "assets" / "audio").glob("*/*.wav")), 65)
        self.assertEqual(len(set(signatures.values())), len(THEMES))

        licenses = (ROOT / "assets" / "audio" / "LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("generated procedurally", licenses.lower())
        self.assertIn("no third-party recordings", licenses.lower())
        self.assertIn("no external samples", licenses.lower())

    def test_resource_resolver_supports_packaged_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            packaged_root = Path(tmp) / "_MEI-dcc-test"
            expected = packaged_root / "assets" / "audio" / "night" / "intro.wav"
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"RIFF" + b"\0" * 64)
            resolved = dcc.audio_asset_path("night", "intro.wav", packaged_root)
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

    def test_profiles_auto_follow_theme_and_manual_profile_is_stable(self):
        self.assertEqual(dcc.effective_audio_profile("auto", "day"), "day")
        self.assertEqual(dcc.effective_audio_profile("auto", "night"), "night")
        self.assertEqual(dcc.effective_audio_profile("black", "day"), "black")

        owner = SimpleNamespace(
            audio_profile="black",
            current_theme="night",
            accent_color="#33f0ff",
            neon_enabled=True,
            neon_animate=True,
        )
        manager = dcc.AudioManager(owner)
        self.assertEqual(manager.effective_profile(), "black")
        owner.current_theme = "day"
        owner.accent_color = "#ff00ff"
        owner.neon_enabled = False
        owner.neon_animate = False
        self.assertEqual(manager.effective_profile(), "black")

    def test_audio_settings_defaults_fallback_and_clamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "audio.ini"), QSettings.Format.IniFormat)
            loaded = dcc.load_audio_settings(settings)
            self.assertEqual(
                loaded,
                {
                    "enabled": True,
                    "profile": "auto",
                    "master_volume": 100,
                    "intro_volume": 35,
                    "effects_volume": 65,
                },
            )

            settings.setValue("audio/ambient_volume", 47)
            settings.setValue("audio/master_volume", 140)
            settings.setValue("audio/effects_volume", -12)
            loaded = dcc.load_audio_settings(settings)
            self.assertEqual(loaded["intro_volume"], 47)
            self.assertEqual(loaded["master_volume"], 100)
            self.assertEqual(loaded["effects_volume"], 0)

            settings.setValue("audio/intro_volume", 61)
            settings.setValue("audio/profile", "invalid")
            loaded = dcc.load_audio_settings(settings)
            self.assertEqual(loaded["intro_volume"], 61)
            self.assertEqual(loaded["profile"], "auto")

    def test_effective_volume_math_and_live_update(self):
        owner = SimpleNamespace(
            audio_profile="auto",
            current_theme="day",
            audio_master_volume=50,
            audio_intro_volume=40,
            audio_effects_volume=60,
        )
        manager = dcc.AudioManager(owner)
        self.assertEqual(manager.effective_volumes(), (0.20, 0.30))

        intro_output = MagicMock()
        effect = MagicMock()
        manager.audio_output = intro_output
        manager.sfx_effects = {"success": effect}
        manager.apply_volumes()
        intro_output.setVolume.assert_called_once_with(0.20)
        effect.setVolume.assert_called_once_with(0.30)

    def test_volume_persistence_clamps_and_audio_off_keeps_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "audio.ini"), QSettings.Format.IniFormat)

            class Harness:
                audio_master_volume = 100
                audio_intro_volume = 35
                audio_effects_volume = 65

            harness = Harness()
            harness.settings = settings
            harness._apply_audio_volumes = lambda: None
            dcc.MainWindow.set_audio_volumes(harness, 150, -1, 77, persist=True)
            self.assertEqual((harness.audio_master_volume, harness.audio_intro_volume, harness.audio_effects_volume), (100, 0, 77))
            self.assertEqual(int(settings.value("audio/master_volume")), 100)
            self.assertEqual(int(settings.value("audio/intro_volume")), 0)
            self.assertEqual(int(settings.value("audio/effects_volume")), 77)

            harness.audio_enabled = True
            harness.music_enabled = True
            harness.audio_manager = SimpleNamespace(stop_all=MagicMock())
            harness._load_audio_theme = lambda force=False: True
            harness.play_audio_intro = MagicMock()
            harness.update_music_button = lambda: None
            dcc.MainWindow.toggle_music(harness)
            self.assertFalse(harness.audio_enabled)
            self.assertEqual((harness.audio_master_volume, harness.audio_intro_volume, harness.audio_effects_volume), (100, 0, 77))

    def test_audio_manager_intro_is_one_shot_and_restarts_without_overlap(self):
        class Player:
            def __init__(self):
                self.stops = 0
                self.positions = []
                self.plays = 0

            def stop(self):
                self.stops += 1

            def setPosition(self, value):
                self.positions.append(value)

            def play(self):
                self.plays += 1

        owner = SimpleNamespace(
            audio_enabled=True,
            audio_profile="auto",
            current_theme="day",
            audio_master_volume=100,
            audio_intro_volume=35,
            audio_effects_volume=65,
        )
        manager = dcc.AudioManager(owner)
        manager.media_player = Player()
        manager.load_profile = lambda force=False: True
        manager.play_intro()
        manager.play_intro()
        self.assertEqual(manager.media_player.plays, 2)
        self.assertEqual(manager.media_player.positions, [0, 0])
        self.assertEqual(manager.media_player.stops, 2)

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

    def test_container_audio_baseline_and_real_transitions_do_not_spam(self):
        played = []
        harness = SimpleNamespace(
            _container_status_baseline=None,
            _pending_container_actions={},
            play_audio_event=played.append,
            normalized_container_audio_state=dcc.MainWindow.normalized_container_audio_state,
        )
        stopped = [SimpleNamespace(name="demo", status="exited")]
        running = [SimpleNamespace(name="demo", status="running")]
        dcc.MainWindow.process_container_audio_transitions(harness, stopped)
        self.assertEqual(played, [])
        dcc.MainWindow.process_container_audio_transitions(harness, running)
        self.assertEqual(played, ["container_started"])
        dcc.MainWindow.process_container_audio_transitions(harness, running)
        self.assertEqual(played, ["container_started"])
        dcc.MainWindow.process_container_audio_transitions(harness, stopped)
        self.assertEqual(played, ["container_started", "container_stopped"])

    def test_pending_restart_completion_emits_once(self):
        played = []
        harness = SimpleNamespace(
            _container_status_baseline={"demo": "running"},
            _pending_container_actions={"demo": "restart"},
            play_audio_event=played.append,
            normalized_container_audio_state=dcc.MainWindow.normalized_container_audio_state,
        )
        running = [SimpleNamespace(name="demo", status="running")]
        dcc.MainWindow.process_container_audio_transitions(harness, running)
        dcc.MainWindow.process_container_audio_transitions(harness, running)
        self.assertEqual(played, ["container_restart_completed"])

    def test_user_container_actions_emit_request_and_uninstall_completion(self):
        played = []

        class Container:
            name = "demo"
            status = "running"

            def reload(self):
                pass

            def start(self):
                pass

            def stop(self):
                pass

            def restart(self):
                pass

            def remove(self, force=False):
                self.removed_force = force

        harness = SimpleNamespace(
            _pending_container_actions={},
            _container_status_baseline={"demo": "running"},
            validate_container_action=lambda _container, _action: None,
            play_audio_event=played.append,
            autostart_supported=lambda _container: True,
        )
        container = Container()
        for action in ("start", "stop", "restart"):
            dcc.MainWindow.execute_container_action(harness, container, action)
        dcc.MainWindow.execute_container_action(harness, container, "remove")
        self.assertEqual(
            played,
            [
                "container_start_requested",
                "container_stop_requested",
                "container_restart_requested",
                "uninstall_completed",
            ],
        )
        self.assertNotIn("demo", harness._pending_container_actions)
        self.assertNotIn("demo", harness._container_status_baseline)

    def test_install_completed_only_after_successful_progress_dialog(self):
        played = []
        harness = SimpleNamespace(
            run_container_with_repair_stream=lambda *_args, **_kwargs: None,
            texts={},
            play_audio_event=played.append,
        )

        class SuccessDialog:
            def __init__(self, *_args, **_kwargs):
                self.success = True

            def exec(self):
                return 0

        class FailedDialog:
            def __init__(self, *_args, **_kwargs):
                self.success = False

            def exec(self):
                return 0

        with patch.object(dcc, "CommandProgressDialog", SuccessDialog):
            self.assertTrue(dcc.MainWindow.execute_smart_container_command_with_progress(harness, [], "t", "s"))
        with patch.object(dcc, "CommandProgressDialog", FailedDialog):
            self.assertFalse(dcc.MainWindow.execute_smart_container_command_with_progress(harness, [], "t", "s"))
        self.assertEqual(played, ["install_completed", "error"])

    def test_audio_manager_transition_baseline_and_restart_dedup(self):
        owner = SimpleNamespace(
            audio_profile="auto",
            current_theme="day",
            audio_master_volume=100,
            audio_intro_volume=35,
            audio_effects_volume=65,
            audio_output=None,
            media_player=None,
            sfx_effects={},
            _audio_theme="",
            _container_status_baseline=None,
            _pending_container_actions={},
            _host_connection_state=False,
        )
        manager = dcc.AudioManager(owner)
        played = []
        manager.play_event = played.append
        stopped = [SimpleNamespace(name="demo", status="exited")]
        running = [SimpleNamespace(name="demo", status="running")]
        manager.process_container_transitions(stopped)
        manager.process_container_transitions(stopped)
        manager.process_container_transitions(running)
        manager.process_container_transitions(running)
        self.assertEqual(played, ["container_started"])
        manager.pending_container_actions["demo"] = "restart"
        manager.process_container_transitions(running)
        manager.process_container_transitions(running)
        self.assertEqual(played, ["container_started", "container_restart_completed"])

    def test_audio_manager_host_connected_dedup(self):
        owner = SimpleNamespace(
            audio_profile="auto",
            current_theme="day",
            audio_master_volume=100,
            audio_intro_volume=35,
            audio_effects_volume=65,
            audio_output=None,
            media_player=None,
            sfx_effects={},
            _audio_theme="",
            _container_status_baseline=None,
            _pending_container_actions={},
            _host_connection_state=False,
        )
        manager = dcc.AudioManager(owner)
        played = []
        manager.play_event = played.append
        manager.set_host_connected(True)
        manager.set_host_connected(True)
        manager.set_host_connected(False)
        manager.set_host_connected(True)
        self.assertEqual(played, ["host_connected", "host_connected"])

    def test_host_connected_only_on_disconnected_to_connected_transition(self):
        played = []
        harness = SimpleNamespace(_host_connection_state=False, play_audio_event=played.append)
        dcc.MainWindow.set_host_status_indicator(harness, True)
        dcc.MainWindow.set_host_status_indicator(harness, True)
        dcc.MainWindow.set_host_status_indicator(harness, False)
        dcc.MainWindow.set_host_status_indicator(harness, True)
        self.assertEqual(played, ["host_connected", "host_connected"])

    def test_audio_generator_and_validator_are_release_assets(self):
        generator = (ROOT / "tools" / "generate_audio_assets.py").read_text(encoding="utf-8")
        validator = (ROOT / "tools" / "validate_audio_assets.py").read_text(encoding="utf-8")
        self.assertIn('"intro.wav"', generator)
        self.assertIn("LEGACY_FILES", generator)
        self.assertIn("expected at least 65 WAV", validator)
        self.assertNotIn("generate_ambient", generator)
        source = (ROOT / "DockerControlCenter.py").read_text(encoding="utf-8")
        self.assertIn("class AudioManager:", source)
        self.assertIn("QMediaPlayer.Loops.Once", source)


if __name__ == "__main__":
    unittest.main()
