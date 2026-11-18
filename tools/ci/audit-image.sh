#!/usr/bin/env bash
set -euo pipefail

source_image="$1"
platform="$2"
report="$3"
status=0
GRYPE_CHECK_FOR_APP_UPDATE=false grype "$source_image" --platform "$platform" --by-cve \
  --fail-on high --output "json=$report" || status=$?
if [[ -s "$report" ]]; then
  jq -r '.matches[] | select(.vulnerability.severity == "High" or .vulnerability.severity == "Critical")
    | [.vulnerability.severity, .vulnerability.id, .artifact.name, .artifact.version,
       .vulnerability.fix.state, ((.vulnerability.fix.versions // []) | join(", "))] | @tsv' "$report" | sort -u
fi
exit "$status"
