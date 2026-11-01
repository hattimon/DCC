#!/usr/bin/env bash
set -euo pipefail

old_version=1.3.10
new_version=1.3.11
root="${RUNNER_TEMP:-/tmp}/dcc-deb-upgrade-smoke"
mkdir -p "$root"
old_deb="$root/DockerControlCenter_${old_version}_amd64.deb"
old_sums="$root/SHA256SUMS-${old_version}.txt"
base="https://github.com/hattimon/DCC/releases/download/v${old_version}"
curl --fail --location --retry 3 "$base/DockerControlCenter_${old_version}_amd64.deb" --output "$old_deb"
curl --fail --location --retry 3 "$base/SHA256SUMS-${old_version}.txt" --output "$old_sums"
(cd "$root" && tr -d '\r' < "$old_sums" | grep -F "DockerControlCenter_${old_version}_amd64.deb" | sha256sum --check)

if [[ "$EUID" -eq 0 ]]; then
  APT_GET=(apt-get)
else
  APT_GET=(sudo apt-get)
fi
"${APT_GET[@]}" update -qq
old_deb_install_mode="${DCC_OLD_DEB_INSTALL_MODE:-apt}"
if [[ "$old_deb_install_mode" == "dpkg-force" ]]; then
  # Debian 13 no longer ships the policykit-1 binary package required by the
  # older release. Force-install only to model an existing pre-upgrade install;
  # the candidate must resolve all dependencies during the actual upgrade.
  dpkg --force-depends --install "$old_deb"
else
  "${APT_GET[@]}" install -y "$old_deb"
fi
old_installed="$(dpkg-query -W -f='${Version} ${Architecture}' docker-control-center)"
test "$old_installed" = "${old_version} amd64"
mkdir -p "$HOME/.docker-control-center" "$HOME/.config/DockerControlCenter"
printf '%s\n' 'profile-preservation-sentinel' > "$HOME/.docker-control-center/docker_connection_profiles.json"
printf '%s\n' 'settings-preservation-sentinel' > "$HOME/.config/DockerControlCenter/DockerControlCenter.conf"
sha256sum "$HOME/.docker-control-center/docker_connection_profiles.json" "$HOME/.config/DockerControlCenter/DockerControlCenter.conf" > "$root/before.sha256"

new_deb="$GITHUB_WORKSPACE/release/DockerControlCenter_${new_version}_amd64.deb"
test -f "$new_deb"
"${APT_GET[@]}" install -y "$new_deb"
"${APT_GET[@]}" check
installed="$(dpkg-query -W -f='${Version} ${Architecture}' docker-control-center)"
test "$installed" = "${new_version} amd64"
depends="$(dpkg-deb -f "$new_deb" Depends)"
grep -Eq '(^|, )[[:space:]]*libpulse0([, ]|$)' <<< "$depends"
grep -Eq '(^|, )[[:space:]]*pkexec([, ]|$)' <<< "$depends"
! grep -Eq '(^|, )[[:space:]]*policykit-1([, ]|$)' <<< "$depends"
desktop_file=/usr/share/applications/docker-control-center.desktop
desktop_exec="$(sed -n 's/^Exec=//p' "$desktop_file")"
test "$desktop_exec" = /usr/bin/docker-control-center
test -x "$desktop_exec"
desktop-file-validate "$desktop_file"
mkdir -p "$root/gui-home" "$root/gui-config" "$root/gui-data" "$root/gui-runtime"
chmod 0700 "$root/gui-runtime"
set +e
timeout --signal=TERM --kill-after=3s 15s xvfb-run -a env \
  HOME="$root/gui-home" \
  XDG_CONFIG_HOME="$root/gui-config" \
  XDG_DATA_HOME="$root/gui-data" \
  XDG_RUNTIME_DIR="$root/gui-runtime" \
  QT_QPA_PLATFORM=xcb \
  QT_DEBUG_PLUGINS=1 \
  "$desktop_exec" > "$root/desktop-start.log" 2>&1
launch_status=$?
set -e
if [[ "$launch_status" -ne 124 ]]; then
  cat "$root/desktop-start.log"
  echo "Desktop launcher exited before remaining open for the smoke-test window (status $launch_status)." >&2
  exit 1
fi
sha256sum "$HOME/.docker-control-center/docker_connection_profiles.json" "$HOME/.config/DockerControlCenter/DockerControlCenter.conf" > "$root/after.sha256"
cmp "$root/before.sha256" "$root/after.sha256"
echo "Debian upgrade and desktop launch OK: $old_version -> $installed; profile and settings preserved."
