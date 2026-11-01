#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${DCC_WEB_PYTHON:-python3}" "$SCRIPT_DIR/web.py" "$@"
