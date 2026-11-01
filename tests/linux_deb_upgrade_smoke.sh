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
(cd "$root" && grep "DockerControlCenter_${old_version}_amd64.deb$" "$old_sums" | sha256sum --check)

sudo apt-get update -qq
sudo apt-get install -y "$old_deb"
mkdir -p "$HOME/.docker-control-center" "$HOME/.config/DockerControlCenter"
printf '%s\n' 'profile-preservation-sentinel' > "$HOME/.docker-control-center/docker_connection_profiles.json"
printf '%s\n' 'settings-preservation-sentinel' > "$HOME/.config/DockerControlCenter/DockerControlCenter.conf"
sha256sum "$HOME/.docker-control-center/docker_connection_profiles.json" "$HOME/.config/DockerControlCenter/DockerControlCenter.conf" > "$root/before.sha256"

new_deb="$GITHUB_WORKSPACE/release/DockerControlCenter_${new_version}_amd64.deb"
test -f "$new_deb"
sudo apt-get install -y "$new_deb"
installed="$(dpkg-query -W -f='${Version} ${Architecture}' docker-control-center)"
test "$installed" = "${new_version} amd64"
sha256sum "$HOME/.docker-control-center/docker_connection_profiles.json" "$HOME/.config/DockerControlCenter/DockerControlCenter.conf" > "$root/after.sha256"
cmp "$root/before.sha256" "$root/after.sha256"
echo "Debian upgrade OK: $old_version -> $installed; profile and settings preserved."
