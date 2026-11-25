"""Build the /DCC/kiri-manager/ Pages artifact. The output directory must be new."""
import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "https://hattimon.github.io/DCC"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-url")
    args = parser.parse_args()
    base = args.base_url.rstrip("/") if args.base_url else None
    if base is not None and base != EXPECTED:
        raise SystemExit("Unexpected GitHub Pages base URL. Review repository Pages configuration.")
    args.output.mkdir(parents=True, exist_ok=False)
    target = args.output / "kiri-manager"
    shutil.copytree(ROOT / "site", target)
    if not (target / "assets" / "social-preview.png").exists():
        raise SystemExit("Generate the verified Playwright screenshots and social card before building Pages.")
    for file, locale in ((target / "index.html", ""), (target / "pl" / "index.html", "pl/")):
        if not base:
            continue
        url = f"{base}/kiri-manager/"
        content = file.read_text(encoding="utf-8")
        addition = (f'<link rel="canonical" href="{url}{locale}">\n'
                    f'  <link rel="alternate" hreflang="en" href="{url}">\n'
                    f'  <link rel="alternate" hreflang="pl" href="{url}pl/">\n'
                    f'  <meta property="og:url" content="{url}{locale}">')
        content = content.replace("<!-- pages-canonical -->", addition)
        content = re.sub(r'content="(?:\.\./)?assets/social-preview\.png"',
                         f'content="{url}assets/social-preview.png"', content)
        file.write_text(content, encoding="utf-8")
    (args.output / ".nojekyll").touch()
    destination = "kiri-manager/"
    (args.output / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>DCC Kiri Manager</title><meta name="dcc-pages-owner" content="kiri-manager">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="refresh" content="0; url={destination}">'
        f'<a href="{destination}">DCC Kiri Manager</a></html>\n', encoding="utf-8")


if __name__ == "__main__":
    main()
