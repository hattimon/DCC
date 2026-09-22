#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  DISTRO_ID="${ID:-unknown}"
  DISTRO_LIKE="${ID_LIKE:-}"
else
  DISTRO_ID="unknown"
  DISTRO_LIKE=""
fi

if [[ "$DISTRO_ID" != "debian" && "$DISTRO_ID" != "ubuntu" && "$DISTRO_ID" != "linuxmint" && "$DISTRO_ID" != "mx" && " $DISTRO_LIKE " != *" debian "* ]]; then
  echo "Warning: build host is not identified as Debian-family: ${DISTRO_ID} (${DISTRO_LIKE})" >&2
fi

VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path('DockerControlCenter.py').read_text(encoding='utf-8')
match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', text, re.MULTILINE)
if not match:
    raise SystemExit('APP_VERSION not found')
print(match.group(1))
PY
)"

ARCH="$(dpkg --print-architecture)"
BUILD_VENV="${DCC_BUILD_VENV:-/tmp/dcc-venv-${USER:-user}}"
BUILD_WORK="${DCC_BUILD_WORK:-/tmp/dcc-build-${USER:-user}}"
BUILD_DIST="${DCC_BUILD_DIST:-/tmp/dcc-dist-${USER:-user}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -x "$BUILD_VENV/bin/python" ]]; then
  rm -rf "$BUILD_VENV"
  if ! "$PYTHON_BIN" -m venv "$BUILD_VENV" 2>/dev/null; then
    echo "python3-venv is unavailable; using a user-local virtualenv fallback." >&2
    "$PYTHON_BIN" -m pip install --user --upgrade virtualenv
    "$PYTHON_BIN" -m virtualenv "$BUILD_VENV"
  fi
fi
"$BUILD_VENV/bin/python" -m pip install --upgrade pip wheel
"$BUILD_VENV/bin/python" -m pip install -r "$ROOT_DIR/requirements-build.txt"

rm -rf "$BUILD_WORK" "$BUILD_DIST"
DCC_ROOT="$ROOT_DIR" "$BUILD_VENV/bin/python" -m PyInstaller \
  --noconfirm \
  --workpath "$BUILD_WORK" \
  --distpath "$BUILD_DIST" \
  "$ROOT_DIR/packaging/linux/DockerControlCenter-linux.spec"

DCC_ROOT="$ROOT_DIR" "$BUILD_VENV/bin/python" -m PyInstaller \
  --noconfirm \
  --workpath "$BUILD_WORK/repo-builder" \
  --distpath "$BUILD_DIST" \
  "$ROOT_DIR/packaging/linux/RepoBuilder-linux.spec"

APP_BINARY="$BUILD_DIST/DockerControlCenter"
REPO_BUILDER_BINARY="$BUILD_DIST/DCCRepoBuilder"
if [[ ! -x "$APP_BINARY" ]]; then
  echo "Linux executable was not produced: $APP_BINARY" >&2
  exit 2
fi
if [[ ! -x "$REPO_BUILDER_BINARY" ]]; then
  echo "Linux Repo Builder executable was not produced: $REPO_BUILDER_BINARY" >&2
  exit 3
fi

"$APP_BINARY" --self-check
QT_QPA_PLATFORM=offscreen "$REPO_BUILDER_BINARY" --self-check

PKG_ROOT="$BUILD_WORK/deb-root"
rm -rf "$PKG_ROOT"
install -d \
  "$PKG_ROOT/DEBIAN" \
  "$PKG_ROOT/usr/bin" \
  "$PKG_ROOT/usr/share/applications" \
  "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps" \
  "$PKG_ROOT/usr/share/pixmaps"

install -m 0755 "$APP_BINARY" "$PKG_ROOT/usr/bin/docker-control-center"
install -m 0755 "$REPO_BUILDER_BINARY" "$PKG_ROOT/usr/bin/dcc-repo-builder"
install -m 0644 "$ROOT_DIR/packaging/linux/docker-control-center.desktop" "$PKG_ROOT/usr/share/applications/docker-control-center.desktop"
install -m 0644 "$ROOT_DIR/packaging/linux/dcc-repo-builder.desktop" "$PKG_ROOT/usr/share/applications/dcc-repo-builder.desktop"
install -m 0644 "$ROOT_DIR/upstream_assets/icon.png" "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps/docker-control-center.png"
install -m 0644 "$ROOT_DIR/upstream_assets/icon.png" "$PKG_ROOT/usr/share/pixmaps/docker-control-center.png"

cat > "$PKG_ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 0755 "$PKG_ROOT/DEBIAN/postinst"

cat > "$PKG_ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 0755 "$PKG_ROOT/DEBIAN/postrm"

cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: docker-control-center
Version: $VERSION
Section: admin
Priority: optional
Architecture: $ARCH
Maintainer: Docker Control Center <noreply@localhost>
Depends: libc6, libstdc++6, libgl1, libegl1, libdbus-1-3, libfontconfig1, libx11-6, libx11-xcb1, libxcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xfixes0, libxcb-xkb1, libxkbcommon-x11-0, openssh-client, xdg-utils, policykit-1
Suggests: docker.io
Description: Docker Control Center
 Desktop GUI for managing Docker Desktop or the local Docker Engine and remote Docker/Balena hosts over SSH profiles and tunnels on Debian-family Linux.
EOF

OUTPUT_DIR="$ROOT_DIR/release"
mkdir -p "$OUTPUT_DIR"
OUTPUT_DEB="$OUTPUT_DIR/DockerControlCenter_${VERSION}_${ARCH}.deb"
rm -f "$OUTPUT_DEB"
dpkg-deb --root-owner-group --build "$PKG_ROOT" "$OUTPUT_DEB"
dpkg-deb --info "$OUTPUT_DEB"
echo "$OUTPUT_DEB"
