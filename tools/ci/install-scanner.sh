#!/usr/bin/env bash
set -euo pipefail

case "$1" in
  gitleaks)
    repo=gitleaks/gitleaks; tag=v8.30.1; asset=gitleaks_8.30.1_linux_x64.tar.gz
    sha=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb ;;
  grype)
    repo=anchore/grype; tag=v0.122.0
    case "$(uname -m)" in
      x86_64) arch=amd64; sha=e697e6f7224637df87e267e4318cc027feae99a8e1b80280241d32b9ee5d4920 ;;
      aarch64) arch=arm64; sha=7ebb44a7e69f8ca2491040e140a802117b2bf3ca8360d3856b3e0b9fe79962c4 ;;
      *) echo 'Unsupported architecture for Grype' >&2; exit 2 ;;
    esac
    asset="grype_0.122.0_linux_${arch}.tar.gz" ;;
  actionlint)
    repo=rhysd/actionlint; tag=v1.7.12; asset=actionlint_1.7.12_linux_amd64.tar.gz
    sha=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 ;;
  *) echo 'Unknown scanner' >&2; exit 2 ;;
esac

install_dir="$RUNNER_TEMP/dcc-audit-bin"
mkdir -p "$install_dir"
archive="$(mktemp)"
trap 'rm -f -- "$archive"' EXIT
curl --proto '=https' --proto-redir '=https' --fail --location --silent --show-error \
  --retry 2 --retry-max-time 45 --max-time 30 \
  "https://github.com/$repo/releases/download/$tag/$asset" --output "$archive"
printf '%s  %s\n' "$sha" "$archive" | sha256sum --check --status
tar -xzf "$archive" -C "$install_dir" "$1"
printf '%s\n' "$install_dir" >> "$GITHUB_PATH"
