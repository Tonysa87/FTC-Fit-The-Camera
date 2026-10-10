#!/usr/bin/env bash
# Build the extension, install it into a throw-away Blender user profile and run
# the in-Blender tests headless.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
export BLENDER_USER_RESOURCES="$SANDBOX/user"
for kind in CONFIG SCRIPTS EXTENSIONS DATAFILES; do
    export "BLENDER_USER_$kind=$SANDBOX/user/${kind,,}"
    mkdir -p "$SANDBOX/user/${kind,,}"
done

bash "$ROOT/scripts/build.sh" >/dev/null
ZIP="$(ls -t "$ROOT"/dist/fit_the_camera-*.zip | head -1)"
bash "$ROOT/scripts/blender.sh" --background --command extension install-file -r user_default -e "$ZIP"
bash "$ROOT/scripts/blender.sh" --background --python-exit-code 1 \
    --python "$ROOT/tests_blender/test_addon.py" -- "$ROOT" "$SANDBOX"
