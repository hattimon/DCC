from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "dcc_icon_glass_master.png"
RUNTIME_PNG = ROOT / "icon.png"
UPSTREAM_RUNTIME_PNG = ROOT / "upstream_assets" / "icon.png"
WINDOWS_ICO = ROOT / "icon.ico"
UPSTREAM_WINDOWS_ICO = ROOT / "upstream_assets" / "icon.ico"
LINUX_ICON_ROOT = ROOT / "assets" / "icons" / "hicolor"

PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def resize_rgba(image: Image.Image, size: int) -> Image.Image:
    """Resize RGBA while premultiplying alpha to avoid bright/dark edge halos."""
    rgba = image.convert("RGBA")
    premultiplied = rgba.convert("RGBa")
    resized = premultiplied.resize((size, size), Image.Resampling.LANCZOS)
    return resized.convert("RGBA")


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing icon source: {SOURCE}")

    master = Image.open(SOURCE).convert("RGBA")
    if master.width != master.height:
        raise SystemExit(f"Icon source must be square, got {master.size}")

    generated: dict[int, Path] = {}
    for size in PNG_SIZES:
        target = LINUX_ICON_ROOT / f"{size}x{size}" / "apps" / "docker-control-center.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        resize_rgba(master, size).save(target, "PNG", optimize=True)
        generated[size] = target

    # Qt runtime uses icon.png in source mode and receives upstream_assets/icon.png
    # at the root of PyInstaller bundles.
    runtime = resize_rgba(master, 512)
    runtime.save(RUNTIME_PNG, "PNG", optimize=True)
    runtime.save(UPSTREAM_RUNTIME_PNG, "PNG", optimize=True)

    master.save(WINDOWS_ICO, "ICO", sizes=[(size, size) for size in ICO_SIZES])
    master.save(UPSTREAM_WINDOWS_ICO, "ICO", sizes=[(size, size) for size in ICO_SIZES])


if __name__ == "__main__":
    main()
