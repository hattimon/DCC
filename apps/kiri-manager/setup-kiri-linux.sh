#!/usr/bin/env bash
# Run on an explicitly chosen, trusted Ubuntu or Debian host. Usage defaults to a plan.
set -euo pipefail

case "${1---plan}" in
  --plan|--apply) mode="${1---plan}" ;;
  *) printf 'Usage: bash setup-kiri-linux.sh [--plan|--apply]\n' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || exit 2
if [[ $(uname -s) != Linux || ! -r /etc/os-release || ! -d /run/systemd/system ]] || grep -qi microsoft /proc/sys/kernel/osrelease; then
  printf 'This helper requires a Debian or Ubuntu host running systemd.\n' >&2
  exit 2
fi
host_id=$(sed -n -E 's/^ID="?([a-z0-9_-]+)"?$/\1/p' /etc/os-release)
case "$host_id" in
  ubuntu|debian) ;;
  *) printf 'Use the official installer for this OS: https://docs.runkiri.com/install/\n' >&2; exit 2 ;;
esac

version=0.2.2
arch=$(dpkg --print-architecture)
case "$arch" in
  amd64) digest=24798125ee50bb24db86594a9ee1469b1032d9b2ffd7da616b06e40763c723b9 ;;
  arm64) digest=5388bd5651db97a23d7eb9f057881522cbad8a27b3463d293f337b8c8797d7f2 ;;
  *) printf 'Only Debian/Ubuntu amd64 and arm64 packages are prepared.\n' >&2; exit 2 ;;
esac
package="kiri-lite_${version}_${arch}.deb"
socket=/run/kiri/docker.sock

installed=false
for name in kiri kiri-lite; do
  if [[ $(dpkg-query -W -f='${Status}' "$name" 2>/dev/null || :) == 'install ok installed' ]]; then
    installed=true
    printf 'Found an existing %s package. It will be reused as installed.\n' "$name"
  fi
done
printf 'Host %s/%s. The plan starts kiri.service and checks %s.\n' "$host_id" "$arch" "$socket"
if [[ "$installed" == false ]]; then
  printf 'The plan downloads and verifies %s from the official release.\n' "$package"
fi
[[ "$mode" == --apply ]] || exit 0

elevate=()
if (( EUID != 0 )); then
  elevate=(sudo --)
  sudo -v
fi
if [[ "$installed" == false ]]; then
  scratch=$(mktemp -d)
  trap 'rm -f -- "$scratch/$package"; rmdir -- "$scratch"' EXIT
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --max-time 90 --max-filesize 67108864 --output "$scratch/$package" \
    "https://github.com/libracoder/kiri/releases/download/v$version/$package"
  printf '%s  %s\n' "$digest" "$scratch/$package" | sha256sum -c --status
  [[ $(dpkg-deb -f "$scratch/$package" Package) == kiri-lite ]]
  [[ $(dpkg-deb -f "$scratch/$package" Version) == "$version" ]]
  [[ $(dpkg-deb -f "$scratch/$package" Architecture) == "$arch" ]]
  "${elevate[@]}" apt-get install -y --no-install-recommends "$scratch/$package"
fi

"${elevate[@]}" systemctl start kiri.service
if [[ ! -S "$socket" || -L "$socket" ]]; then
  printf 'The dedicated Kiri socket did not become available. Check kiri.service.\n' >&2
  exit 1
fi
printf 'Kiri socket ready. Use these values with compose.kiri-socket.yaml and then run the connection test.\n'
printf 'KIRI_SOCKET_PATH=%s\nKIRI_SOCKET_GID=%s\n' "$socket" "$(stat -c %g -- "$socket")"
printf 'Panel setup: https://github.com/hattimon/DCC/tree/kiri-manager-v0.1.0/apps/kiri-manager/docs\n'
