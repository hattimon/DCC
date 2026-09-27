from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO_ROOT = ROOT / "assets" / "audio"
SAMPLE_RATE = 22_050
PROFILES = ("night", "black", "dark", "light", "day")
EVENT_FILES = (
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
LEGACY_FILES = ("ambient.wav", "start.wav", "stop.wav", "restart.wav", "remove.wav")

PROFILE_CONFIG = {
    "night": {"root": 82.41, "harmonics": (1.0, 2.0, 3.0, 4.02), "drive": 2.3, "seed": 1901},
    "black": {"root": 110.00, "harmonics": (1.0, 2.01, 4.0, 6.03), "drive": 1.15, "seed": 2903},
    "dark": {"root": 73.42, "harmonics": (1.0, 1.5, 2.0, 2.997), "drive": 1.45, "seed": 3907},
    "light": {"root": 196.00, "harmonics": (1.0, 2.0, 3.0, 5.0), "drive": 0.72, "seed": 4909},
    "day": {"root": 146.83, "harmonics": (1.0, 1.5, 2.01, 3.0), "drive": 0.88, "seed": 5911},
}


def _clip(value: float) -> int:
    # Keep deliberate headroom so the validator can prove there is no clipping.
    return max(-31_000, min(31_000, int(value * 30_000)))


def _write_wave(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(sample) for sample in samples), default=0.0)
    if peak > 0.96:
        scale = 0.96 / peak
        samples = [sample * scale for sample in samples]
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for sample in samples:
            frames.extend(struct.pack("<h", _clip(sample)))
        handle.writeframes(bytes(frames))


def _envelope(t: float, duration: float, attack: float = 0.025, release: float = 0.18) -> float:
    attack_gain = min(1.0, t / max(attack, 1e-4))
    remaining = max(0.0, duration - t)
    release_gain = min(1.0, remaining / max(release, 1e-4))
    return max(0.0, attack_gain * release_gain)


def _noise(seed: int) -> tuple[int, float]:
    seed = (1664525 * seed + 1013904223) & 0xFFFFFFFF
    return seed, (seed / 0xFFFFFFFF) * 2.0 - 1.0


def _tone(profile: str, frequency: float, t: float, phase: float = 0.0) -> float:
    cfg = PROFILE_CONFIG[profile]
    harmonics = cfg["harmonics"]
    if profile == "night":
        raw = sum((1.0 / (index + 1)) * math.sin(2 * math.pi * frequency * ratio * t + phase) for index, ratio in enumerate(harmonics))
        return math.tanh(raw * cfg["drive"]) * 0.72
    if profile == "black":
        carrier = math.sin(2 * math.pi * frequency * t + phase)
        glass = math.sin(2 * math.pi * frequency * 4.01 * t + phase * 0.5)
        fm = math.sin(2 * math.pi * frequency * t + 1.4 * math.sin(2 * math.pi * 5.2 * t))
        return 0.42 * carrier + 0.22 * glass + 0.26 * fm
    if profile == "dark":
        reactor = math.sin(2 * math.pi * frequency * t + 0.8 * math.sin(2 * math.pi * 1.7 * t))
        sub = math.sin(2 * math.pi * frequency * 0.5 * t)
        overtone = math.sin(2 * math.pi * frequency * 2.997 * t)
        return 0.48 * reactor + 0.30 * sub + 0.16 * overtone
    if profile == "light":
        fundamental = math.sin(2 * math.pi * frequency * t + phase)
        chime = math.sin(2 * math.pi * frequency * 3.0 * t + 0.4) * math.exp(-5.0 * t)
        return 0.58 * fundamental + 0.30 * chime
    # Day: bell + wooden transient, spacious but intentionally not a quoted melody.
    bell = math.sin(2 * math.pi * frequency * t + phase)
    partial = math.sin(2 * math.pi * frequency * 1.503 * t + 0.6) * math.exp(-2.8 * t)
    wood = math.sin(2 * math.pi * frequency * 0.51 * t) * math.exp(-11.0 * t)
    return 0.48 * bell + 0.28 * partial + 0.22 * wood


def _render_note_sequence(profile: str, ratios: tuple[float, ...], duration: float, gain: float = 0.48) -> list[float]:
    cfg = PROFILE_CONFIG[profile]
    count = int(SAMPLE_RATE * duration)
    note_duration = duration / len(ratios)
    samples: list[float] = []
    seed = int(cfg["seed"])
    for index in range(count):
        t = index / SAMPLE_RATE
        note_index = min(len(ratios) - 1, int(t / note_duration))
        local_t = t - note_index * note_duration
        frequency = float(cfg["root"]) * 2.0 * ratios[note_index]
        env = _envelope(local_t, note_duration, 0.012 if profile != "night" else 0.018, min(0.18, note_duration * 0.72))
        tone = _tone(profile, frequency, local_t, phase=note_index * 0.33)
        seed, noise = _noise(seed)
        transient = noise * math.exp(-28.0 * local_t) * (0.04 if profile in {"day", "dark"} else 0.018)
        samples.append((tone + transient) * env * gain)
    return samples


def generate_intro(profile: str) -> None:
    sequences = {
        "night": ((1.0, 1.0, 1.4983, 1.3348, 1.0, 0.7492), 3.35, 0.48),
        "black": ((1.0, 1.2599, 1.4983, 2.0, 1.4983, 2.3784, 2.0, 1.2599), 3.20, 0.43),
        "dark": ((0.5, 1.0, 1.3348, 1.6818, 1.0, 2.0), 3.65, 0.43),
        "light": ((1.0, 1.2599, 1.4983, 2.0, 1.6818), 2.90, 0.38),
        "day": ((1.0, 1.1892, 1.4983, 1.3348, 2.0, 1.4983), 3.80, 0.40),
    }
    ratios, duration, gain = sequences[profile]
    samples = _render_note_sequence(profile, ratios, duration, gain)
    _write_wave(AUDIO_ROOT / profile / "intro.wav", samples)


def generate_events(profile: str) -> None:
    event_specs = {
        "container_start_requested.wav": ((1.0, 1.1892), 0.32, 0.38),
        "container_started.wav": ((1.0, 1.2599, 1.4983), 0.46, 0.43),
        "container_stop_requested.wav": ((1.1892, 1.0), 0.32, 0.36),
        "container_stopped.wav": ((1.4983, 1.1892, 0.9439), 0.46, 0.40),
        "container_restart_requested.wav": ((1.0, 1.4983, 1.1225), 0.52, 0.40),
        "container_restart_completed.wav": ((1.1225, 1.4983, 2.0), 0.56, 0.44),
        "install_completed.wav": ((1.0, 1.2599, 1.4983, 2.0), 0.64, 0.45),
        "uninstall_completed.wav": ((1.4983, 1.1892, 1.0, 0.7492), 0.60, 0.40),
        "host_connected.wav": ((1.0, 1.4983, 2.0), 0.54, 0.42),
        "success.wav": ((1.0, 1.2599, 1.4983), 0.44, 0.42),
        "warning.wav": ((1.0, 1.1225, 1.0), 0.50, 0.38),
        "error.wav": ((1.0, 0.9439, 0.7937), 0.56, 0.43),
    }
    for filename, (ratios, duration, gain) in event_specs.items():
        _write_wave(AUDIO_ROOT / profile / filename, _render_note_sequence(profile, ratios, duration, gain))


def remove_legacy_assets(profile: str) -> None:
    directory = AUDIO_ROOT / profile
    for filename in LEGACY_FILES:
        (directory / filename).unlink(missing_ok=True)


def write_licenses() -> None:
    text = """# DCC audio assets

All WAV files under this directory are generated procedurally and locally by
`tools/generate_audio_assets.py`. They contain no third-party recordings,
no external samples, stock samples, downloaded audio, copyrighted melodies,
or background loops.

Each theme profile uses a separate synthesis configuration. `intro.wav` is a
short one-shot theme cue; all other WAV files are event sound effects.
"""
    (AUDIO_ROOT / "LICENSES.md").write_text(text, encoding="utf-8")


def main() -> None:
    for profile in PROFILES:
        remove_legacy_assets(profile)
        generate_intro(profile)
        generate_events(profile)
    write_licenses()
    count = sum(1 for path in AUDIO_ROOT.glob("*/*.wav") if path.is_file())
    print(f"Generated {count} procedural WAV assets in {AUDIO_ROOT}")


if __name__ == "__main__":
    main()
