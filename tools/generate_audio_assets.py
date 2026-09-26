from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO_ROOT = ROOT / "assets" / "audio"
SAMPLE_RATE = 22_050


THEMES = {
    "night": {"root": 82.41, "mode": (1.0, 1.1892, 1.4983), "pulse": 2.0, "air": 0.015},
    "black": {"root": 110.00, "mode": (1.0, 1.2599, 1.4983), "pulse": 4.0, "air": 0.010},
    "dark": {"root": 73.42, "mode": (1.0, 1.3348, 1.5874), "pulse": 1.5, "air": 0.020},
    "light": {"root": 196.00, "mode": (1.0, 1.2599, 1.4983), "pulse": 3.0, "air": 0.008},
    "day": {"root": 146.83, "mode": (1.0, 1.1892, 1.4983), "pulse": 0.75, "air": 0.012},
}


def _clip(value: float) -> int:
    return max(-32767, min(32767, int(value * 32767)))


def _write_wave(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b"".join(struct.pack("<h", _clip(sample)) for sample in samples))


def _fade(index: int, count: int, seconds: float = 0.18) -> float:
    fade_samples = max(1, int(SAMPLE_RATE * seconds))
    return min(1.0, index / fade_samples, (count - 1 - index) / fade_samples)


def _noise(seed: int) -> tuple[int, float]:
    seed = (1664525 * seed + 1013904223) & 0xFFFFFFFF
    return seed, ((seed / 0xFFFFFFFF) * 2.0) - 1.0


def generate_ambient(theme: str, seconds: float = 8.0) -> None:
    cfg = THEMES[theme]
    count = int(SAMPLE_RATE * seconds)
    root = cfg["root"]
    mode = cfg["mode"]
    pulse = cfg["pulse"]
    air = cfg["air"]
    seed = sum(ord(char) for char in theme) + 139
    samples: list[float] = []
    for i in range(count):
        t = i / SAMPLE_RATE
        seed, n = _noise(seed)
        pad = (
            math.sin(2 * math.pi * root * mode[0] * t)
            + 0.58 * math.sin(2 * math.pi * root * mode[1] * t + 0.8)
            + 0.42 * math.sin(2 * math.pi * root * mode[2] * t + 1.7)
        ) / 2.0
        shimmer = 0.18 * math.sin(2 * math.pi * root * 2.0 * t + 0.35 * math.sin(2 * math.pi * 0.12 * t))
        gate = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(2 * math.pi * pulse * t))
        sample = (0.105 * pad + 0.03 * shimmer) * gate + air * n
        samples.append(sample * _fade(i, count, 0.28))
    _write_wave(AUDIO_ROOT / theme / "ambient.wav", samples)


def _event_wave(theme: str, notes: tuple[float, ...], seconds: float, descending: bool = False) -> list[float]:
    root = THEMES[theme]["root"] * 2.0
    count = int(SAMPLE_RATE * seconds)
    samples: list[float] = []
    note_count = len(notes)
    for i in range(count):
        t = i / SAMPLE_RATE
        pos = min(note_count - 1, int((i / max(1, count)) * note_count))
        ratio = notes[note_count - 1 - pos] if descending else notes[pos]
        frequency = root * ratio
        attack = min(1.0, t / 0.018)
        release = max(0.0, 1.0 - (t / seconds)) ** 2.2
        tone = math.sin(2 * math.pi * frequency * t) + 0.22 * math.sin(2 * math.pi * frequency * 2.0 * t)
        samples.append(0.26 * tone * attack * release)
    return samples


def generate_events(theme: str) -> None:
    majorish = (1.0, 1.2599, 1.4983)
    rising = (1.0, 1.1892, 1.4983)
    restart = (1.0, 1.4983, 1.1225, 1.6818)
    error = (1.0, 0.9439, 0.7937)
    events = {
        "start.wav": _event_wave(theme, rising, 0.34),
        "stop.wav": _event_wave(theme, rising, 0.34, descending=True),
        "restart.wav": _event_wave(theme, restart, 0.48),
        "success.wav": _event_wave(theme, majorish, 0.42),
        "error.wav": _event_wave(theme, error, 0.48),
        "remove.wav": _event_wave(theme, (1.0, 0.8409, 0.6674), 0.40),
    }
    for name, samples in events.items():
        _write_wave(AUDIO_ROOT / theme / name, samples)


def write_licenses() -> None:
    text = """# DCC audio assets\n\nAll WAV files under this directory are generated procedurally by\n`tools/generate_audio_assets.py`. They contain no third-party recordings,\nstock samples, loops, or downloaded audio. They are project assets intended\nto be distributed with Docker Control Center.\n"""
    (AUDIO_ROOT / "LICENSES.md").write_text(text, encoding="utf-8")


def main() -> None:
    for theme in THEMES:
        generate_ambient(theme)
        generate_events(theme)
    write_licenses()
    print(f"Generated procedural audio assets in {AUDIO_ROOT}")


if __name__ == "__main__":
    main()
