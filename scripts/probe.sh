#!/usr/bin/env bash
# Run a diagnostic probe from scripts/probes/ in headless Blender against the
# latest build, in a throw-away user profile. Usage: bash scripts/probe.sh <name>
#   dragsim   drives the modal operator's drag code on the scale cube handles
#   paneltest draws every panel section with a validating mock layout (432 configs)
#   drawall   draws the overlay offscreen in 864 configurations
#   planes    default calibration validity per reference plane
#   timing    refresh time per mode and focal option
#   snap      renders overlay snapshots (vp.png, rect.png) into the output dir
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:?probe name}"
OUT="${2:-$ROOT/dist/probes}"
mkdir -p "$OUT"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
export BLENDER_USER_RESOURCES="$SANDBOX/user"
for kind in CONFIG SCRIPTS EXTENSIONS DATAFILES; do
    export "BLENDER_USER_$kind=$SANDBOX/user/${kind,,}"
    mkdir -p "$SANDBOX/user/${kind,,}"
done
bash "$ROOT/scripts/build.sh" >/dev/null
ZIP="$(ls -t "$ROOT"/dist/fit_the_camera-*.zip | head -1)"
bash "$ROOT/scripts/blender.sh" --background --command extension install-file -r user_default -e "$ZIP" >/dev/null
bash "$ROOT/scripts/blender.sh" --background --python "$ROOT/scripts/probes/$NAME.py" -- "$ROOT" "$OUT" 2>&1 \
    | grep -vE "EGL|MESA|^Blender|^$|Read blend"
