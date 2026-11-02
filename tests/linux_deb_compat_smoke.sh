#!/usr/bin/env bash
set -euo pipefail

deb_path="${1:?usage: linux_deb_compat_smoke.sh path/to/package.deb}"
test -f "$deb_path"
deb_path="$(readlink -f "$deb_path")"

depends="$(dpkg-deb -f "$deb_path" Depends)"
grep -Eq '(^|, )[[:space:]]*libpulse0([, ]|$)' <<< "$depends"
grep -Eq '(^|, )[[:space:]]*pkexec([, ]|$)' <<< "$depends"
! grep -Eq '(^|, )[[:space:]]*policykit-1([, ]|$)' <<< "$depends"

apt-get update -qq
apt-get install -y "$deb_path" desktop-file-utils xvfb xauth fonts-dejavu-core

installed="$(dpkg-query -W -f='${Version} ${Architecture}' docker-control-center)"
test "$installed" = "1.3.12 amd64"
desktop_file=/usr/share/applications/docker-control-center.desktop
desktop_exec="$(sed -n 's/^Exec=//p' "$desktop_file")"
test "$desktop_exec" = /usr/bin/docker-control-center
test -x "$desktop_exec"
desktop-file-validate "$desktop_file"

user=dcc-deb-smoke
if ! id "$user" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$user"
fi
root="${RUNNER_TEMP:-/tmp}/dcc-deb-compat-smoke"
install -d -o "$user" -g "$user" -m 0700 "$root/home" "$root/config" "$root/data" "$root/runtime"
set +e
timeout --signal=TERM --kill-after=3s 15s runuser -u "$user" -- env \
  HOME="$root/home" \
  XDG_CONFIG_HOME="$root/config" \
  XDG_DATA_HOME="$root/data" \
  XDG_RUNTIME_DIR="$root/runtime" \
  QT_QPA_PLATFORM=xcb \
  xvfb-run -a "$desktop_exec" > "$root/desktop-start.log" 2>&1
launch_status=$?
set -e
if [[ "$launch_status" -ne 124 ]]; then
  cat "$root/desktop-start.log"
  echo "Desktop did not remain running under Debian stable (status $launch_status)." >&2
  exit 1
fi

echo "Debian stable package install and X11 launch OK: $installed."
