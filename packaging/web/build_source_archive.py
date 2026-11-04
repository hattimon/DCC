#!/usr/bin/env python3
"""Create a reproducible, self-contained DCC Web source ZIP."""
from __future__ import annotations

import argparse
from pathlib import Path
import stat
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "apps" / "dcc-web" / "VERSION").read_text(encoding="utf-8").strip()
ARCHIVE_ROOT = f"DCC-Web-{VERSION}"
OUTPUT = ROOT / "release" / f"DCC-Web-{VERSION}-source.zip"
EXCLUDED_PARTS = {".git", ".venv", ".data", ".review-data", "__pycache__", ".pytest_cache", "node_modules", "tests"}


def source_files() -> list[Path]:
    files = [ROOT / "LICENSE", ROOT / "dcc_catalog.py", ROOT / "dcc-catalog.json"]
    files.extend((ROOT / "catalog" / "media").rglob("*"))
    files.append(ROOT / "apps" / "container-updater" / "updater.py")
    remote_access = ROOT / "apps" / "dcc-remote-access"
    files.extend(remote_access / name for name in (
        "VERSION", "compose.yaml", "supervise.sh", "README.md", "README.pl.md", "SECURITY.md",
        "RELEASE_NOTES_0.1.0.md",
    ))
    files.extend((ROOT / "apps" / "dcc-web").rglob("*"))
    missing = [str(path.relative_to(ROOT)) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(", ".join(missing))
    result = []
    for path in files:
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        result.append(path)
    return sorted(set(result), key=lambda item: item.relative_to(ROOT).as_posix())


def build_archive(output: Path = OUTPUT) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in source_files():
            relative = path.relative_to(ROOT).as_posix()
            name = f"{ARCHIVE_ROOT}/{relative}"
            info = ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = ZIP_DEFLATED
            executable = path.suffix == ".sh"
            mode = stat.S_IFREG | (0o755 if executable else 0o644)
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes())
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    path = build_archive(args.output)
    print(f"Created {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
