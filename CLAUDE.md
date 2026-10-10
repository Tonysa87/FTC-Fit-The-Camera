# FTC – Fit The Camera (Blender 5.2+ extension)

Single-image camera calibration add-on. User docs: `README.md` (Italian). History:
`docs/CHANGELOG.md`. Original spec: `FTC – Specifica addon Blender 5.2+.md` (says
"Camera Match": the final name is **FTC**, package `fit_the_camera`, tab "FTC").

## Working with the user
- The user (Antonio) writes Italian: reply in Italian. Full autonomy on technical
  choices; ask only for real product decisions.
- He tests the GUI himself on **Windows** Blender 5.2: when a build is ready give the
  zip path `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\fit_the_camera-<ver>.zip`
  and short step-by-step test instructions.
- Bump `version` in both `fit_the_camera/blender_manifest.toml` and `pixi.toml`
  for each build he installs. Commit at milestones (git, branch `main`).

## Commands (pixi, Ubuntu/WSL)
- `pixi run check` = lint + pytest + manifest validate + headless Blender tests. Run before every build.
- `pixi run build` -> `dist/`. `pixi run gui-tests` is optional: GUI Blender under
  WSLg (X11 + software GL) often stalls at startup in the GL driver — not our code.
- Blender 5.2.2 Linux lives in `.tools/` (downloaded by `scripts/get_blender.sh`).
  Test scripts isolate every `BLENDER_USER_*` dir; never touch `~/.config/blender`.
- Headless `gpu.init()` + `GPUOffScreen` works (llvmpipe): used to test drawing and to
  render overlay snapshots for visual checks.

## Architecture
- `solver/` is numpy-only (no bpy), imported by pytest via `tests/conftest.py`
  (puts `fit_the_camera/` on `sys.path`; `solver` and `exif` import standalone).
- `calibrate.py` bridges settings (`camera.data.ftc`, see `props.py`) to the solver:
  `solve()`, `refresh()` (results + cache), `update()` (writes camera),
  `settings_changed()` (property update callback), `uncertainty()` (nudges every
  guide handle by 1‰ of the long side), `alignment_matrix()`, `seed_third_axis()`.
- Camera is written only during a live calibration session or via Apply/align ops.
- Modal operator state lives in `ops_modal.Session` (not the operator): draw handler
  reads it; `session.view` (frame rect) is cached from the last draw because camera
  and view matrices only agree at draw time.

## Conventions (keep consistent)
- Image px: origin bottom-left, y up; handles normalised 0..1. Camera = Blender
  (looks along -Z). `CameraSolution.rotation` is camera->world.
- **Axis sign**: +axis runs along the group's FIRST guide, first -> second handle
  (`solver/vp.orient_along`, image-velocity based, stable at infinity). Arrow drawn.
- Reference planes XY / XZ / YZ (`solver/common.plane_frame`), walls with local y up.
- Sensor = long side of the uncropped sensor; non 4:3/3:2 images are centred crops
  of a 4:3 sensor (`exif.native_frame`). 35 mm equivalent uses the native diagonal.
- UI strings in English, Italian in `translations.py` (only add-on specific phrases:
  registered translations are global). Every button needs a tooltip (test enforces).
- Line widths 1 px; handles are thin target symbols in the axis colour.

## Lessons from real photos (`samples/`, git-ignored: GPS; measured lines in `tests/data/`)
- Two floor vanishing points leave the vertical unmeasured (±6° on the lift photo):
  third-axis line or 3 VPs fix it; known focal brings it under 1°.
- A far vanishing point (frontal wall) makes the focal indeterminate.
- "Parallel-looking" lines often are not (light rails, separate facades).
- EXIF focal can be wrong (zoomed/cropped deck photo: guides say ~8800 px, EXIF main
  camera ~2966 px) -> guide-misfit warning.
- Straighten horizon on a rolled photo breaks the fit (warned with removed roll).
- Known focal as a robust (Cauchy, ±5%) prior in the LM (`solver/refine.py`), two
  starts (guides' own focal and the known one): 2 VPs measure f to ~2% with 2 px
  noise, a rectangle only to ~11% (so EXIF dominates there). The deck photo's 3×
  wrong EXIF is overruled by 3 VPs but not by 2 (one VP far away).
- Default guides/rectangle are generated for the known focal (`default_handles`),
  otherwise "guides overrule the known focal" fires on untouched guides.

## Scale cube
`solver/scale.py`: base corner = base ray ∩ reference plane through the origin,
vertical edge along the plane normal on the camera's side, top handle -> closest
point on that edge (`closest_param_on_line`). Shown top handle = projected top
corner (`draw.handle_co`), used for pick and drag too.

## Open work
- Possible: magnifier near the cursor while dragging; more than two lines per VP.
