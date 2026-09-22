#!/usr/bin/env python3
"""Generate consistent DCC store icons and hero cards from catalog metadata.

The script prefers a public Simple Icons mark for known projects, then falls
back to a GitHub organisation avatar, and finally renders a local monogram.
Generated PNGs are repository assets so DCC can load them through the catalog
without requiring an application release.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "dcc-catalog.json"
MEDIA_DIR = ROOT / "catalog" / "media"
ICON_DIR = MEDIA_DIR / "icons"
HERO_DIR = MEDIA_DIR / "heroes"

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication


SIMPLE_ICON_SLUGS = {
    "Agent Zero": "",
    "Ollama": "ollama",
    "NocoDB": "nocodb",
    "Stirling PDF": "stirlingpdf",
    "IT-Tools": "",
    "Dozzle": "",
    "Beszel Hub": "",
    "ChangeDetection.io": "",
    "Alpine Linux": "alpinelinux",
    "Debian": "debian",
    "Ubuntu": "ubuntu",
    "BusyBox": "busybox",
    "Node.js": "nodedotjs",
    "Python": "python",
    "Golang": "go",
    "Apache HTTPD": "apache",
    "PostgreSQL": "postgresql",
    "MySQL": "mysql",
    "MongoDB": "mongodb",
    "RabbitMQ": "rabbitmq",
    "NATS": "natsdotio",
    "Memcached": "memcached",
    "WordPress": "wordpress",
    "Nextcloud": "nextcloud",
    "Open WebUI": "openwebui",
    "Vane (dawniej Perplexica)": "",
    "SearXNG": "searxng",
    "Portainer CE": "portainer",
    "Nginx": "nginx",
    "Caddy": "caddy",
    "Redis": "redis",
    "MariaDB": "mariadb",
    "Adminer": "",
    "Eclipse Mosquitto": "eclipsemosquitto",
    "Node-RED": "nodered",
    "Gitea": "gitea",
    "Jellyfin": "jellyfin",
    "Uptime Kuma": "uptimekuma",
    "Pi-hole": "pihole",
    "Home Assistant": "homeassistant",
    "Grafana": "grafana",
    "Prometheus": "prometheus",
    "InfluxDB": "influxdb",
    "Plex Media Server": "plex",
    "SFTPGo Community": "",
    "File Browser": "",
    "ntfy": "ntfy",
    "Gotify": "gotify",
    "Vaultwarden": "vaultwarden",
    "Memos": "memos",
    "Vikunja": "vikunja",
    "Linkding": "",
    "Actual Budget": "actualbudget",
    "CyberChef": "cyberchef",
    "OpenSpeedTest": "",
    "AdGuard Home": "adguard",
    "Qdrant": "qdrant",
    "AnythingLLM": "",
    "Duplicati": "duplicati",
    "Forgejo": "forgejo",
    "Glances": "",
    "VictoriaMetrics": "victoriametrics",
    "Audiobookshelf": "audiobookshelf",
    "SmartWAN Manager": "",
}

CUSTOM_BRAND_ASSETS = {
    "SmartWAN Manager": "https://raw.githubusercontent.com/hattimon/SmartWAN-Manager/main/docs/aurelka-status.svg",
}


ACCENTS = {
    "ai": "#9b7cff",
    "automation": "#f0a83a",
    "administration": "#58c7ff",
    "monitoring": "#54d88a",
    "tools": "#8ea3b7",
    "web": "#4fc3d7",
    "devops": "#ff8a5b",
    "smart home": "#35d1b3",
    "media": "#ef6aa9",
    "network": "#4ab5ff",
    "databases": "#5e8df5",
    "messaging": "#f79b4c",
    "cache": "#ffca55",
    "runtime": "#55d6a8",
    "base": "#95a1b2",
    "backup": "#8bd45a",
    "security": "#ff6b6b",
    "finance": "#e7c84f",
    "notifications": "#f56f91",
    "productivity": "#bb79f0",
}


def http_get(url: str, timeout: int = 7) -> bytes:
    request = Request(url, headers={"User-Agent": "DCC-store-media/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def slugify(value: str) -> str:
    text = value.lower().replace("node.js", "nodejs")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "app"


def github_avatar_url(source_url: str) -> str:
    match = re.match(r"^https?://github\.com/([^/]+)/", source_url or "", re.I)
    if not match:
        return ""
    return f"https://github.com/{match.group(1)}.png?size=512"


def category_group(app: dict) -> str:
    raw = str(app.get("category_en") or app.get("category") or "Application")
    raw = raw.replace("›", "/")
    raw = re.sub(r"[^\x00-\x7f]+", " ", raw)
    return (raw.split("/")[0].strip() or "Application")


def accent_for(app: dict) -> QColor:
    key = category_group(app).lower()
    for prefix, color in ACCENTS.items():
        if key.startswith(prefix):
            return QColor(color)
    return QColor("#65d7e8")


def initials(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name.replace(".io", ""))
    if not words:
        return "DCC"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def pixmap_from_svg(svg: bytes, size: int = 360) -> QPixmap | None:
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        return None
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(12, 12, size - 24, size - 24))
    painter.end()
    return QPixmap.fromImage(image)


def smartwan_logo_from_svg(svg: bytes) -> QPixmap | None:
    """Crop the original Aurelka WAN guardian artwork into a square app mark."""
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        return None
    image = QImage(1200, 360, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 1200, 360))
    painter.end()
    return QPixmap.fromImage(image).copy(88, 78, 174, 174)


def pixmap_from_raster(data: bytes) -> QPixmap | None:
    pixmap = QPixmap()
    if not pixmap.loadFromData(data):
        return None
    return pixmap


def fetch_brand_pixmap(app: dict) -> tuple[QPixmap | None, str]:
    name = str(app.get("name") or "")
    custom_asset = CUSTOM_BRAND_ASSETS.get(name, "")
    if custom_asset:
        try:
            data = http_get(custom_asset)
            pixmap = smartwan_logo_from_svg(data) if name == "SmartWAN Manager" else pixmap_from_svg(data)
            if pixmap is not None:
                return pixmap, f"project artwork: {custom_asset}"
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
    slug = SIMPLE_ICON_SLUGS.get(name, "")
    if slug:
        try:
            data = http_get(f"https://cdn.simpleicons.org/{slug}")
            pixmap = pixmap_from_svg(data)
            if pixmap is not None:
                return pixmap, f"Simple Icons: {slug}"
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
    avatar = github_avatar_url(str(app.get("source_url") or ""))
    if avatar:
        try:
            pixmap = pixmap_from_raster(http_get(avatar))
            if pixmap is not None:
                return pixmap, "GitHub organisation avatar"
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
    return None, "generated monogram"


def draw_round_rect(painter: QPainter, rect: QRectF, radius: float, color: QColor) -> None:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, color)


def draw_logo_tile(painter: QPainter, app: dict, logo: QPixmap | None, rect: QRectF, accent: QColor) -> None:
    draw_round_rect(painter, rect, 28, QColor(31, 34, 40, 245))
    painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 145), 2))
    painter.drawRoundedRect(rect, 28, 28)
    if logo is not None and not logo.isNull():
        target = rect.adjusted(28, 28, -28, -28)
        scaled = logo.scaled(int(target.width()), int(target.height()), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        x = target.x() + (target.width() - scaled.width()) / 2
        y = target.y() + (target.height() - scaled.height()) / 2
        painter.drawPixmap(int(x), int(y), scaled)
        return
    painter.setPen(QColor("#eef4f8"))
    font = QFont("Segoe UI", 42)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initials(str(app.get("name") or "APP")))


def render_icon(app: dict, logo: QPixmap | None, output: Path) -> None:
    accent = accent_for(app)
    image = QImage(256, 256, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    draw_logo_tile(painter, app, logo, QRectF(14, 14, 228, 228), accent)
    painter.end()
    image.save(str(output), "PNG")


def elide_text(font: QFont, text: str, max_width: int) -> str:
    metrics = QFontMetrics(font)
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max_width)


def render_hero(app: dict, logo: QPixmap | None, output: Path) -> None:
    width, height = 1200, 420
    accent = accent_for(app)
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#111318"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0.0, QColor("#171a20"))
    gradient.setColorAt(0.62, QColor("#111318"))
    gradient.setColorAt(1.0, QColor(9, 11, 14))
    painter.fillRect(image.rect(), gradient)

    # Subtle geometric depth that stays neutral in every DCC theme.
    painter.setPen(QPen(QColor(255, 255, 255, 10), 1))
    for x in range(-180, width + 180, 56):
        painter.drawLine(x, 0, x + 240, height)
    glow = QColor(accent)
    glow.setAlpha(32)
    painter.setBrush(glow)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(width - 350, -190, 480, 480))
    painter.drawEllipse(QRectF(20, height - 120, 260, 260))

    painter.fillRect(0, height - 5, width, 5, accent)
    draw_logo_tile(painter, app, logo, QRectF(58, 82, 230, 230), accent)

    left = 340
    name = str(app.get("name") or "Application")
    category = category_group(app)
    description = str(app.get("description_en") or app.get("description") or app.get("image") or "")

    tag_font = QFont("Segoe UI", 16)
    tag_font.setBold(True)
    painter.setFont(tag_font)
    painter.setPen(accent)
    painter.drawText(QRectF(left, 74, 760, 34), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, category.upper())

    title_font = QFont("Segoe UI", 34)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#f4f7fb"))
    title = elide_text(title_font, name, 790)
    painter.drawText(QRectF(left, 115, 800, 62), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

    desc_font = QFont("Segoe UI", 17)
    painter.setFont(desc_font)
    painter.setPen(QColor("#b7c0cb"))
    desc = elide_text(desc_font, description.replace("\n", " "), 790)
    painter.drawText(QRectF(left, 186, 800, 44), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, desc)

    chip_font = QFont("Segoe UI", 13)
    chip_font.setBold(True)
    painter.setFont(chip_font)
    chip_text = "SELF-HOSTED  •  DCC APP STORE"
    chip_metrics = QFontMetrics(chip_font)
    chip_width = chip_metrics.horizontalAdvance(chip_text) + 32
    chip_rect = QRectF(left, 257, chip_width, 42)
    draw_round_rect(painter, chip_rect, 14, QColor(35, 39, 46, 230))
    painter.setPen(QColor("#dce3ea"))
    painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, chip_text)

    image_name = str(app.get("image") or "")
    meta_font = QFont("Consolas", 12)
    painter.setFont(meta_font)
    painter.setPen(QColor("#788594"))
    painter.drawText(QRectF(left, 320, 790, 34), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide_text(meta_font, image_name, 790))
    painter.end()
    image.save(str(output), "PNG")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-catalog", action="store_true", help="write generated icon_url values into dcc-catalog.json")
    parser.add_argument(
        "--generated-heroes",
        action="store_true",
        help="also render/link synthetic hero cards; real project screenshots are preferred in the store",
    )
    args = parser.parse_args()

    # Keep a strong QApplication reference for the whole render.  QPixmap can
    # terminate the process on some Qt builds when the temporary application
    # object is garbage-collected between iterations.
    qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    apps = payload.get("apps") or []
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    if args.generated_heroes:
        HERO_DIR.mkdir(parents=True, exist_ok=True)

    sources: dict[str, str] = {}
    rendered: set[str] = set()
    for app in apps:
        name = str(app.get("name") or "Application")
        file_slug = slugify(name)
        icon_rel = f"catalog/media/icons/{file_slug}.png"
        hero_rel = f"catalog/media/heroes/{file_slug}.png"
        icon_path = ROOT / icon_rel
        hero_path = ROOT / hero_rel
        if file_slug not in rendered:
            logo, source = fetch_brand_pixmap(app)
            sources[name] = source
            render_icon(app, logo, icon_path)
            if args.generated_heroes:
                render_hero(app, logo, hero_path)
            rendered.add(file_slug)
            print(f"{name}: {source}")
        if args.write_catalog:
            app["icon_url"] = icon_rel
            if args.generated_heroes:
                app["hero_image_url"] = hero_rel

    if args.write_catalog:
        CATALOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = MEDIA_DIR / "SOURCES.json"
    report.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    media_kind = "icon/hero pairs" if args.generated_heroes else "icons"
    print(f"Generated {len(rendered)} {media_kind} in {MEDIA_DIR}")
    qt_app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
