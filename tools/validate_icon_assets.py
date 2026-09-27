from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "dcc_icon.png"
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def alpha_range(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return rgba.getchannel("A").getextrema()


def validate_png(path: Path, size: int, occupancy_bounds: tuple[float, float] | None = None) -> None:
    with Image.open(path) as image:
        if image.size != (size, size) or image.mode != "RGBA":
            raise ValueError(f"unexpected PNG format: {path} {image.size} {image.mode}")
        minimum, maximum = image.getchannel("A").getextrema()
        if minimum >= 255 or maximum != 255:
            raise ValueError(f"PNG lacks meaningful alpha: {path} alpha={(minimum, maximum)}")
        if occupancy_bounds is not None:
            mask = image.getchannel("A").point(lambda value: 255 if value >= 24 else 0)
            bbox = mask.getbbox()
            if bbox is None:
                raise ValueError(f"empty alpha bbox: {path}")
            occupancy = max((bbox[2] - bbox[0]) / size, (bbox[3] - bbox[1]) / size)
            if not (occupancy_bounds[0] <= occupancy <= occupancy_bounds[1]):
                raise ValueError(f"unexpected canvas occupancy: {path} {occupancy:.4f}")


def ico_entries(path: Path) -> list[dict[str, int]]:
    data = path.read_bytes()
    if len(data) < 6:
        raise ValueError(f"invalid ICO: {path}")
    reserved, icon_type, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or icon_type != 1 or count <= 0:
        raise ValueError(f"invalid ICO header: {path}")
    entries = []
    for index in range(count):
        offset = 6 + index * 16
        width, height, _colors, _reserved, planes, bpp, size, image_offset = struct.unpack(
            "<BBBBHHII", data[offset : offset + 16]
        )
        entries.append(
            {
                "width": 256 if width == 0 else width,
                "height": 256 if height == 0 else height,
                "planes": planes,
                "bpp": bpp,
                "size": size,
                "offset": image_offset,
            }
        )
    return entries


def validate_ico(path: Path) -> None:
    data = path.read_bytes()
    entries = ico_entries(path)
    sizes = {(entry["width"], entry["height"]) for entry in entries}
    expected = {(size, size) for size in ICO_SIZES}
    if sizes != expected:
        raise ValueError(f"wrong ICO sizes for {path}: {sorted(sizes)}")
    for entry in entries:
        if entry["planes"] not in (0, 1) or entry["bpp"] != 32:
            raise ValueError(f"ICO entry is not 32-bit: {path} {entry}")
        start = entry["offset"]
        end = start + entry["size"]
        payload = data[start:end]
        if end > len(data) or not payload.startswith(PNG_SIGNATURE):
            raise ValueError(f"invalid PNG-backed ICO frame: {path} {entry}")
        with Image.open(BytesIO(payload)) as image:
            rgba = image.convert("RGBA")
            if rgba.size != (entry["width"], entry["height"]):
                raise ValueError(f"ICO frame size mismatch: {path} {entry}")
            minimum, maximum = rgba.getchannel("A").getextrema()
            if minimum >= 255 or maximum != 255:
                raise ValueError(f"ICO frame lacks alpha: {path} {entry}")


def main() -> int:
    try:
        generator = (ROOT / "tools" / "generate_icon_assets.py").read_text(encoding="utf-8")
        if 'SOURCE = ROOT / "assets" / "dcc_icon.png"' not in generator:
            raise ValueError("assets/dcc_icon.png is not the canonical source")
        for banned in ("dcc_icon_glass_master", "dcc_icon-best", "icon_master.svg", "icon_master.png"):
            if banned in generator:
                raise ValueError(f"generator still references obsolete source: {banned}")

        with Image.open(SOURCE) as source:
            source_size = source.size[0]
        validate_png(SOURCE, source_size, (0.92, 0.96))
        source_alpha = alpha_range(SOURCE)

        runtime_paths = (
            ROOT / "icon.png",
            ROOT / "upstream_assets" / "icon.png",
            ROOT / "repo_builder_icon.png",
            ROOT / "upstream_assets" / "repo_builder_icon.png",
        )
        for path in runtime_paths:
            validate_png(path, 512)
        if len({path.read_bytes() for path in runtime_paths}) != 1:
            raise ValueError("runtime PNG outputs are not identical")

        ico_paths = (
            ROOT / "icon.ico",
            ROOT / "upstream_assets" / "icon.ico",
            ROOT / "repo_builder_icon.ico",
            ROOT / "upstream_assets" / "repo_builder_icon.ico",
        )
        for path in ico_paths:
            validate_ico(path)
        if len({path.read_bytes() for path in ico_paths}) != 1:
            raise ValueError("ICO outputs are not identical")

        for size in PNG_SIZES:
            app_dir = ROOT / "assets" / "icons" / "hicolor" / f"{size}x{size}" / "apps"
            main_icon = app_dir / "docker-control-center.png"
            repo_icon = app_dir / "dcc-repo-builder.png"
            validate_png(main_icon, size)
            validate_png(repo_icon, size)
            if main_icon.read_bytes() != repo_icon.read_bytes():
                raise ValueError(f"hicolor icons differ at {size}x{size}")
    except (OSError, ValueError, struct.error) as exc:
        print(f"ERROR: {exc}")
        return 1

    with Image.open(SOURCE) as source:
        alpha = source.getchannel("A")
        bbox = alpha.point(lambda value: 255 if value >= 24 else 0).getbbox()
        occupancy = max((bbox[2] - bbox[0]) / source.width, (bbox[3] - bbox[1]) / source.height)
    print(
        "PASS: canonical DCC icon pipeline valid; "
        f"source_alpha={source_alpha}; occupancy={occupancy:.4f}; "
        f"ICO={ICO_SIZES}; hicolor={PNG_SIZES}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
