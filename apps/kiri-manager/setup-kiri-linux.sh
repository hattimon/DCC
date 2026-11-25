#!/usr/bin/env bash
# Run on an explicitly chosen, trusted Ubuntu or Debian host. Usage defaults to a plan.
set -euo pipefail

usage() {
  printf 'Usage: bash setup-kiri-linux.sh [--plan|--apply] [--grant-panel-access]\n' >&2
  exit 2
}

case "${1---plan}" in
  --plan|--apply) mode="${1---plan}" ;;
  *) usage ;;
esac
[[ $# -le 2 ]] || usage
case "${2-}" in
  '') grant_access=false ;;
  --grant-panel-access) grant_access=true ;;
  *) usage ;;
esac
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
panel_user=dcc-kiri-panel
panel_uid=10001
panel_shell=/usr/sbin/nologin
panel_entry=''

if [[ "$grant_access" == true ]]; then
  if panel_entry=$(getent passwd "$panel_user"); then
    IFS=: read -r _ _ existing_uid _ _ _ existing_shell <<< "$panel_entry"
    if [[ "$existing_uid" != "$panel_uid" || "$existing_shell" != "$panel_shell" ||
          $(getent passwd "$panel_uid") != "$panel_entry" ]]; then
      printf 'The account %s is reserved for the panel. Resolve the host account conflict first.\n' "$panel_user" >&2
      exit 2
    fi
  else
    if getent passwd "$panel_uid" >/dev/null; then
      printf 'Host UID %s is already in use. Resolve the host account conflict first.\n' "$panel_uid" >&2
      exit 2
    fi
  fi
  printf 'The plan authorizes the dedicated non-login account %s (UID %s) for the Kiri socket.\n' "$panel_user" "$panel_uid"
fi

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

if [[ "$grant_access" == true ]]; then
  if [[ -z "$panel_entry" ]]; then
    "${elevate[@]}" useradd --uid "$panel_uid" --user-group --no-create-home --shell "$panel_shell" "$panel_user"
  fi
  "${elevate[@]}" /usr/bin/kiri host-access "$panel_user"
fi

printf 'Kiri socket ready. Use these values with compose.kiri-socket.yaml and then run the connection test.\n'
printf 'KIRI_SOCKET_PATH=%s\nKIRI_SOCKET_GID=%s\n' "$socket" "$(stat -c %g -- "$socket")"
printf 'Panel setup: https://github.com/hattimon/DCC/tree/kiri-manager-v0.1.1/apps/kiri-manager/docs\n'
