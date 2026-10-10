#!/usr/bin/env bash
# Run the modal operator end to end with simulated input. Needs a display
# (WSLg works): a Blender window opens for a few seconds and closes by itself.
# Optional: with software OpenGL under WSLg Blender occasionally stalls inside
# the GL driver, so the run is capped by a timeout.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
export BLENDER_USER_RESOURCES="$SANDBOX/user"
for kind in CONFIG SCRIPTS EXTENSIONS DATAFILES; do
    export "BLENDER_USER_$kind=$SANDBOX/user/${kind,,}"
    mkdir -p "$SANDBOX/user/${kind,,}"
done
OUT="${FTC_GUI_OUT:-$SANDBOX}"

bash "$ROOT/scripts/build.sh" >/dev/null
ZIP="$(ls -t "$ROOT"/dist/fit_the_camera-*.zip | head -1)"
bash "$ROOT/scripts/blender.sh" --background --command extension install-file -r user_default -e "$ZIP"
bash "$ROOT/scripts/blender.sh" --background --factory-startup \
    --python "$ROOT/tests_blender/make_photo.py" -- "$ROOT" "$OUT/gui.jpg" >/dev/null
bash "$ROOT/scripts/blender.sh" --background --python-expr \
    "import bpy; bpy.context.preferences.view.show_splash = False; bpy.ops.wm.save_userpref()" >/dev/null
rm -f "$OUT/gui_result.txt"
# WSLg: X11 with software GL is the configuration that starts reliably.
env -u WAYLAND_DISPLAY LIBGL_ALWAYS_SOFTWARE=1 PYTHONUNBUFFERED=1 timeout --kill-after=5 "${FTC_GUI_TIMEOUT:-120}" \
    bash "$ROOT/scripts/blender.sh" --enable-event-simulate --window-geometry 0 0 1400 900 \
    --python "$ROOT/tests_blender/test_gui.py" -- "$ROOT" "$OUT" || true
grep -q '^OK' "$OUT/gui_result.txt"
