#!/usr/bin/env bash
set -euo pipefail

event="$1"
before="$2"
publish_image="$3"
current="$(tr -d '\r\n' < apps/container-updater/VERSION)"
[[ "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
previous=""
if [[ "$event" == push && "$before" =~ ^[0-9a-f]{40}$ ]]; then
  previous="$(git show "$before:apps/container-updater/VERSION" 2>/dev/null | tr -d '\r\n' || true)"
fi
if [[ "$event" == workflow_dispatch && "$publish_image" == true ]] ||
   [[ "$event" == push && "$previous" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$current" != "$previous" ]]; then
  echo "publish=true"
else
  echo "publish=false"
fi
