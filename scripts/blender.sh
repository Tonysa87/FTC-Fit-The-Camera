#!/usr/bin/env bash
# Run the project-local headless Blender with the given arguments.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER="${BLENDER:-$(ls -d "$ROOT"/.tools/blender-*-linux-x64 2>/dev/null | sort -V | tail -1)/blender}"
[ -x "$BLENDER" ] || BLENDER="$(bash "$ROOT/scripts/get_blender.sh" | tail -1)"
exec "$BLENDER" "$@"
