from __future__ import annotations

import hashlib
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO_ROOT = ROOT / "assets" / "audio"
SAMPLE_RATE = 22_050
PROFILES = ("night", "black", "dark", "light", "day")
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
LEGACY_FILES = {"ambient.wav", "start.wav", "stop.wav", "restart.wav", "remove.wav"}


def validate() -> list[str]:
    errors: list[str] = []
    signatures: dict[str, tuple[str, ...]] = {}
    wav_paths = sorted(AUDIO_ROOT.glob("*/*.wav"))
    if len(wav_paths) < 65:
        errors.append(f"expected at least 65 WAV files, found {len(wav_paths)}")

    for profile in PROFILES:
        profile_hashes: list[str] = []
        directory = AUDIO_ROOT / profile
        legacy = sorted(path.name for path in directory.glob("*.wav") if path.name in LEGACY_FILES)
        if legacy:
            errors.append(f"{profile}: legacy loop-era WAV files remain: {', '.join(legacy)}")
        for filename in FILES:
            path = directory / filename
            if not path.is_file():
                errors.append(f"missing: {path}")
                continue
            if path.stat().st_size <= 44:
                errors.append(f"empty WAV: {path}")
                continue
            try:
                with wave.open(str(path), "rb") as handle:
                    channels = handle.getnchannels()
                    width = handle.getsampwidth()
                    rate = handle.getframerate()
                    frames = handle.getnframes()
                    raw = handle.readframes(frames)
                if channels != 1:
                    errors.append(f"{path}: channels={channels}, expected 1")
                if width != 2:
                    errors.append(f"{path}: sample width={width}, expected 2")
                if rate != SAMPLE_RATE:
                    errors.append(f"{path}: sample rate={rate}, expected {SAMPLE_RATE}")
                if frames <= 0:
                    errors.append(f"{path}: no frames")
                    continue
                duration = frames / rate
                if filename == "intro.wav":
                    if not (2.0 <= duration <= 6.0):
                        errors.append(f"{path}: intro duration {duration:.3f}s outside 2-6s")
                elif duration >= 2.0:
                    errors.append(f"{path}: event SFX too long ({duration:.3f}s)")
                samples = struct.unpack(f"<{len(raw) // 2}h", raw)
                if not samples or max(abs(value) for value in samples) >= 32_767:
                    errors.append(f"{path}: clipped or invalid PCM")
                profile_hashes.append(hashlib.sha256(raw).hexdigest())
            except (wave.Error, EOFError) as exc:
                errors.append(f"{path}: invalid WAV header ({exc})")
        signatures[profile] = tuple(profile_hashes)

    if len(set(signatures.values())) != len(PROFILES):
        errors.append("audio profiles are not synthesis-distinct")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    count = sum(1 for path in AUDIO_ROOT.glob("*/*.wav") if path.is_file())
    print(f"PASS: {count} WAV files; 5 distinct profiles; valid PCM; no clipping; intro durations 2-6s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
