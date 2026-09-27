from __future__ import annotations

import argparse
import math
import shutil
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "dcc_icon.png"
SOURCE_BACKUP = ROOT.parent / "dcc_icon_original_before_alpha.png"
RUNTIME_PNG = ROOT / "icon.png"
UPSTREAM_RUNTIME_PNG = ROOT / "upstream_assets" / "icon.png"
WINDOWS_ICO = ROOT / "icon.ico"
UPSTREAM_WINDOWS_ICO = ROOT / "upstream_assets" / "icon.ico"
REPO_BUILDER_RUNTIME_PNG = ROOT / "repo_builder_icon.png"
UPSTREAM_REPO_BUILDER_PNG = ROOT / "upstream_assets" / "repo_builder_icon.png"
REPO_BUILDER_ICO = ROOT / "repo_builder_icon.ico"
UPSTREAM_REPO_BUILDER_ICO = ROOT / "upstream_assets" / "repo_builder_icon.ico"
LINUX_ICON_ROOT = ROOT / "assets" / "icons" / "hicolor"

PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
TARGET_OCCUPANCY = 0.94
BACKGROUND_THRESHOLD = 62
ALPHA_ZERO_LEVEL = 5
ALPHA_FULL_LEVEL = 56


def alpha_range(image: Image.Image) -> tuple[int, int]:
    return image.convert("RGBA").getchannel("A").getextrema()


def occupancy(image: Image.Image, threshold: int = 24) -> float:
    alpha = image.convert("RGBA").getchannel("A")
    mask = alpha.point(lambda value: 255 if value >= threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return 0.0
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return max(width / image.width, height / image.height)


def _border_connected_background(rgb: Image.Image) -> tuple[Image.Image, Image.Image]:
    red, green, blue = rgb.split()
    brightest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    candidates = brightest.point(lambda value: 255 if value <= BACKGROUND_THRESHOLD else 0)
    connected = candidates.copy()
    width, height = connected.size
    for seed in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if connected.getpixel(seed) == 255:
            ImageDraw.floodfill(connected, seed, 128, thresh=0)
    exterior = connected.point(lambda value: 255 if value == 128 else 0)
    return exterior, brightest


def _meaningful_alpha_from_border_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    exterior, brightest = _border_connected_background(rgba.convert("RGB"))

    def ramp(value: int) -> int:
        if value <= ALPHA_ZERO_LEVEL:
            return 0
        if value >= ALPHA_FULL_LEVEL:
            return 255
        normalized = (value - ALPHA_ZERO_LEVEL) / float(ALPHA_FULL_LEVEL - ALPHA_ZERO_LEVEL)
        smooth = normalized * normalized * (3.0 - 2.0 * normalized)
        return max(0, min(255, round(255 * smooth)))

    exterior_alpha = brightest.point(ramp)
    alpha = Image.new("L", rgba.size, 255)
    alpha.paste(exterior_alpha, mask=exterior)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.7))
    rgba.putalpha(alpha)
    return rgba


def _crop_for_canvas_occupancy(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value >= 24 else 0).getbbox()
    if bbox is None:
        raise ValueError("icon alpha mask is empty")

    object_width = bbox[2] - bbox[0]
    object_height = bbox[3] - bbox[1]
    side = int(math.ceil(max(object_width, object_height) / TARGET_OCCUPANCY))
    side = max(max(object_width, object_height) + 2, min(side, min(rgba.size)))

    center_x = (bbox[0] + bbox[2]) / 2.0
    center_y = (bbox[1] + bbox[3]) / 2.0
    left = int(round(center_x - side / 2.0))
    top = int(round(center_y - side / 2.0))
    left = max(0, min(left, rgba.width - side))
    top = max(0, min(top, rgba.height - side))
    return rgba.crop((left, top, left + side, top + side))


def prepare_canonical_source() -> Image.Image:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing icon source: {SOURCE}")

    original = Image.open(SOURCE)
    rgba = original.convert("RGBA")
    before = alpha_range(rgba)
    if before == (255, 255):
        if not SOURCE_BACKUP.exists():
            shutil.copyfile(SOURCE, SOURCE_BACKUP)
        rgba = _meaningful_alpha_from_border_background(rgba)
        rgba = _crop_for_canvas_occupancy(rgba)
        rgba.save(SOURCE, "PNG", optimize=True, compress_level=9)
    else:
        rgba = Image.open(SOURCE).convert("RGBA")

    if rgba.width != rgba.height:
        raise SystemExit(f"Icon source must be square, got {rgba.size}")
    if alpha_range(rgba)[0] >= 255:
        raise SystemExit("Icon source still has no meaningful alpha")
    return rgba


def _small_size_profile(image: Image.Image, size: int) -> Image.Image:
    if size not in {16, 24, 32}:
        return image
    alpha = image.getchannel("A")
    rgb = image.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(1.055)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.075)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.22)
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def resize_rgba(image: Image.Image, size: int) -> Image.Image:
    """Resize each target directly from source using premultiplied alpha."""
    rgba = image.convert("RGBA")
    premultiplied = rgba.convert("RGBa")
    resized = premultiplied.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    return _small_size_profile(resized, size)


def _png_payload(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.convert("RGBA").save(stream, "PNG", optimize=True, compress_level=9)
    return stream.getvalue()


def write_ico(path: Path, frames: dict[int, Image.Image]) -> None:
    payloads = [(size, _png_payload(frames[size])) for size in ICO_SIZES]
    offset = 6 + 16 * len(payloads)
    entries = []
    data_parts = []
    for size, payload in payloads:
        encoded_size = 0 if size == 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                encoded_size,
                encoded_size,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        data_parts.append(payload)
        offset += len(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(payloads)) + b"".join(entries) + b"".join(data_parts))


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(path, "PNG", optimize=True, compress_level=9)


def generate_assets(master: Image.Image) -> None:
    frames = {size: resize_rgba(master, size) for size in PNG_SIZES}

    for size, frame in frames.items():
        app_dir = LINUX_ICON_ROOT / f"{size}x{size}" / "apps"
        _save_png(frame, app_dir / "docker-control-center.png")
        _save_png(frame, app_dir / "dcc-repo-builder.png")

    runtime = frames[512]
    for target in (
        RUNTIME_PNG,
        UPSTREAM_RUNTIME_PNG,
        REPO_BUILDER_RUNTIME_PNG,
        UPSTREAM_REPO_BUILDER_PNG,
    ):
        _save_png(runtime, target)

    ico_frames = {size: resize_rgba(master, size) for size in ICO_SIZES}
    for target in (
        WINDOWS_ICO,
        UPSTREAM_WINDOWS_ICO,
        REPO_BUILDER_ICO,
        UPSTREAM_REPO_BUILDER_ICO,
    ):
        write_ico(target, ico_frames)


def generate_preview(master: Image.Image, output: Path) -> None:
    dark_sizes = (512, 256, 128, 64, 48, 32, 24, 16)
    light_sizes = (64, 48, 32, 24, 16)
    width = 1480
    height = 760
    preview = Image.new("RGB", (width, height), (34, 37, 43))
    draw = ImageDraw.Draw(preview)
    draw.text((28, 18), "DCC final icon - dark neutral background", fill=(235, 238, 243))

    x = 28
    baseline = 570
    for size in dark_sizes:
        frame = resize_rgba(master, size)
        preview.paste(frame, (x, baseline - size), frame)
        draw.text((x, baseline + 10), str(size), fill=(220, 224, 230))
        x += size + 28

    light_top = 620
    draw.rectangle((0, light_top, width, height), fill=(239, 241, 244))
    draw.text((28, light_top + 14), "Light background", fill=(30, 33, 38))
    x = 28
    baseline = light_top + 118
    for size in light_sizes:
        frame = resize_rgba(master, size)
        preview.paste(frame, (x, baseline - size), frame)
        draw.text((x, baseline + 4), str(size), fill=(30, 33, 38))
        x += size + 42

    output.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output, "PNG", optimize=True, compress_level=9)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path, default=None)
    args = parser.parse_args()

    master = prepare_canonical_source()
    generate_assets(master)
    if args.preview is not None:
        generate_preview(master, args.preview)

    print(f"source={SOURCE}")
    print(f"source_size={master.width}x{master.height}")
    print(f"source_alpha={alpha_range(master)}")
    print(f"canvas_occupancy={occupancy(master):.4f}")
    print(f"ico_sizes={','.join(str(size) for size in ICO_SIZES)}")
    print(f"hicolor_sizes={','.join(str(size) for size in PNG_SIZES)}")


if __name__ == "__main__":
    main()
