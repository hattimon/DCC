"""Optimize captured Playwright PNGs and compose the share card from the real dashboard."""
import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STEMS = (
    "dashboard-dark", "dashboard-light", "dashboard-dark-pl", "dashboard-light-pl",
    "containers", "images", "volumes", "networks", "compose", "wizard", "diagnostics", "mobile",
)
ROOT = Path(__file__).resolve().parents[1]


def font(name, size):
    windows = Path(os.environ.get("WINDIR", "/unavailable")) / "Fonts"
    options = {
        "bold": [windows / "segoeuib.ttf", "DejaVuSans-Bold.ttf"],
        "regular": [windows / "segoeui.ttf", "DejaVuSans.ttf"],
    }
    for path in options[name]:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "browser-artifacts" / "source")
    args = parser.parse_args()
    assets = ROOT / "site" / "assets"
    screenshots = assets / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    for name in STEMS:
        with Image.open(args.source / (name + ".png")) as image:
            image.convert("RGB").save(screenshots / (name + ".webp"), quality=87, method=6)

    cover = Image.new("RGB", (1200, 630), "#0b131e")
    draw = ImageDraw.Draw(cover)
    draw.rounded_rectangle((46, 46, 112, 108), 13, fill="#143a44", outline="#2f7b77", width=2)
    poly = [(79, 53), (100, 65), (100, 87), (79, 99), (58, 87), (58, 65)]
    draw.polygon(poly, fill="#68e4d5")
    draw.line((58, 65, 79, 77, 100, 65), fill="#10343b", width=2)
    draw.line((79, 77, 79, 99), fill="#10343b", width=2)
    draw.text((44, 181), "DCC Kiri", font=font("bold", 65), fill="#edf4fb")
    draw.text((44, 255), "Manager", font=font("bold", 65), fill="#edf4fb")
    draw.text((48, 360), "Manage Kiri containers\nand SSH profiles.",
              font=font("regular", 24), fill="#a7b8c9", spacing=8)
    with Image.open(args.source / "dashboard-dark.png") as image:
        image = image.convert("RGB")
        image.thumbnail((701, 457), Image.Resampling.LANCZOS)
        x, y = 458, (630 - image.height) // 2
        draw.rounded_rectangle((x - 8, y - 8, x + image.width + 7, y + image.height + 7), 13,
                               fill="#12202e", outline="#68e4d5", width=2)
        cover.paste(image, (x, y))
    cover.save(assets / "social-preview.png", optimize=True)


if __name__ == "__main__":
    main()
