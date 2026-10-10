#!/usr/bin/env bash
# Build the extension zip into dist/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/dist"
bash "$ROOT/scripts/blender.sh" --factory-startup --command extension build \
    --source-dir "$ROOT/fit_the_camera" --output-dir "$ROOT/dist"
