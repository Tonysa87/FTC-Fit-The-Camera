# FTC – Fit The Camera (Blender 5.2+ extension)

Single-image camera calibration add-on. User docs: `README.md` (English, GitHub /
Extensions audience) and `README.it.md` (Italian); developer docs
`docs/DEVELOPMENT.md` (Italian); publishing on extensions.blender.org:
`docs/PUBLISHING.md`. History: `docs/CHANGELOG.md`. Original spec: `FTC – Specifica addon Blender 5.2+.md` (says
"Camera Match": the final name is **FTC**, package `fit_the_camera`, tab "FTC").

## Status / next session
- **v1.0.0** (0.6.1 + Render section: Prepare Render, Object Roles; no Shadow Catcher
  Plane) is committed and built but **not yet tested in the GUI**. Next session:
  the user tests it on Windows following `docs/TEST_GUI.md`; fix what he reports.
- GitHub: https://github.com/Tonysa87/FTC---Fit-The-Camera (public, `origin`),
  release v1.0.0 with the zip. Not yet submitted to extensions.blender.org: needs
  the GUI test, icon (PNG ≤256 px), featured image, ≥1 preview (`docs/PUBLISHING.md`).
- `dist/` is git-ignored; only the latest zip matters (older ones may have been
  rebuilt by `blender-tests` with newer code before a version bump).

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
- `bash scripts/probe.sh <name>` runs a diagnostic in headless Blender on a fresh
  build (`scripts/probes/`, output in `dist/probes/`): `paneltest` (every panel
  section with a mock layout that validates props/operators), `drawall` (overlay in
  864 configs), `dragsim` (modal drag code on the cube handles), `planes`,
  `timing`, `snap` (overlay PNGs), `render` (Cycles render through Prepare
  Render). Panels cannot be drawn headless otherwise; set ui_scale in mocks (it is
  0 in background mode).

## Architecture
- `solver/` is numpy-only (no bpy), imported by pytest via `tests/conftest.py`
  (puts `fit_the_camera/` on `sys.path`; `solver` and `exif` import standalone).
- `calibrate.py` bridges settings (`camera.data.ftc`, see `props.py`) to the solver:
  `solve()`, `refresh()` (results + cache), `update()` (writes camera),
  `settings_changed()` (property update callback), `uncertainty()` (nudges every
  guide handle by 1‰ of the long side), `alignment_matrix()`, `seed_third_axis()`.
- Focal: `focal_source()` -> "KNOWN" / "AUTO" (known refined by the guides) /
  "SOLVE"; 1 VP and horizon always KNOWN, solved principal point always SOLVE.
  `_focal_inputs()` maps it to `focal_px` / `known_focal_px` for the solvers.
- `default_handles()` builds the default layout for the known focal (VPs at
  ±focal from the centre, rectangle projected by a virtual camera, shrunk to fit
  and kept in front); `HANDLE_DEFAULTS` is the fallback and the "untouched"
  reference of `seed_third_axis`.
- Camera is written only during a live calibration session or via Apply/align ops.
- Modal operator state lives in `ops_modal.Session` (not the operator): draw handler
  reads it; `session.view` (frame rect) is cached from the last draw because camera
  and view matrices only agree at draw time.

- Session robustness: `Session` keeps the camera pointer (`session_camera()`
  follows renames), `cancel()` + `end_session()` clear the draw handler and the
  header (`clear_header`, any screen); the modal ends when the area's camera
  (`calibrate.space_camera`) is no longer the session camera; `undo_post` /
  `redo_post` re-solve; `ops_align.apply_now` calls `settings_changed` in a session.
- `ops_align.active_face` returns the BMesh with the face: a face outlives a
  freed BMesh only by luck (ReferenceError).
- Ctrl+Z is always the session's undo (no undo step is pushed while the modal
  runs: Blender's undo would drop the session's edits). `modal` wraps `_modal`
  and ends the session on an exception. `draw.session_camera` follows renames.
- Aspect: `ops_load.match_image_aspect` keeps the render width/percentage and sets
  the height (pixel aspect included); Apply only after a successful solve.
- `calibrate.seed_reference`: Cube -> Reference with untouched (default) reference
  handles lays them out for the current scale; `seed_cube` falls back near the
  origin when its handles would leave the image (floor base on a wall plane).
- `calibrate.transform_overridden`: keyframes/NLA/drivers on transform or lens,
  enabled constraints, animated parents -> red warning.
- `ops_render.sync_photo` (render_pre handler + Load Image/upright) keeps the
  compositor's "FTC Photo" node on the scene camera's photo.
- Generated images: call `image.update()` after `pixels.foreach_set` before
  `save()`, or stale pixels are written. `pack()` of a generated image always
  stores PNG: the upright copy is saved as a temp JPEG, packed, then deleted.
- Generic words ("Results", "Yaw") are translated in the private "FTC" context.

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
- Line widths 1 px; handles are thin target symbols in the axis colour; arrows
  `draw.ARROW_SIZE` (10.5 px, +50% asked by the user).
- The world is always right-handed: the third axis is derived (`draw.third_axis`,
  signed) and its guide arrow follows the solution (`draw.runs_backwards`).
  Flipping axis 3 flips axis 2, or axis 1 when axis 2 is Z (`ops_modal.flip_axis`,
  used by the ⇄ buttons and by F; F clamps a stale `active_vp`).
- Handles in `ops_modal.SCALE_KEYS` (origin, reference, cube) never reset the
  pitch correction. Session undo goes through `ops_modal.push_undo` (capped).
- Enum items are stored by index in .blend files: never reorder them
  (`scale_mode`: CUBE took index 0 from the old DISTANCE, REFERENCE stays 1).
- Lengths in scene units; cube presets are metres divided by
  `unit_settings.scale_length`; overlay labels go through `draw.length_text`.

## Lessons from real photos (`samples/`, git-ignored: GPS; measured lines in `tests/data/`)
- Two floor vanishing points leave the vertical unmeasured (±6° on the lift photo):
  third-axis line or 3 VPs fix it; known focal brings it under 1°.
- A far vanishing point (frontal wall) makes the focal indeterminate.
- "Parallel-looking" lines often are not (light rails, separate facades).
- EXIF focal can be wrong (zoomed/cropped deck photo: guides say ~8800 px, EXIF main
  camera ~2966 px) -> guide-misfit warning.
- Straighten horizon on a rolled photo breaks the fit (warned with removed roll).
- Known focal ("Known + Guides"): Gaussian prior (±5% ~ 1‰ guide noise) in the
  LM; the guides overrule it only if the known-focal fit misfits > 1° and their
  own fit is < 75% of that (`solver/vp.refine_known_focal`). A Cauchy prior was
  tried and rejected: 10–25 px guide errors threw away a correct EXIF focal.
  2 VPs measure f to ~2% with 2 px noise; a rectangle cannot detect even a 3x
  wrong focal (corners within ~9 px), so it keeps the known value. The deck's 3x
  wrong EXIF is overruled by 3 VPs, not by 2 (one VP far away).
- Default guides/rectangle are generated for the known focal (`default_handles`),
  otherwise "guides overrule the known focal" fires on untouched guides.

## Reference distance
`solver/vp.reference_distance`: the start = ray ∩ `ref_measure_plane` ("Measured
On", its own plane: the alignment `ref_plane` must not change the scale) through
the origin (anywhere on it); an in-plane axis -> the end on the plane too, Euclidean
length; the plane-normal axis -> a height on the normal line through the start.
(Until 1.0.0 both ends were taken on the axis line through the origin: 5% wrong
scale on the lift photo with the reference on the threshold, reported by the user.)

## Scale cube
`solver/scale.py`: base corner = base ray ∩ reference plane through the origin,
vertical edge along the plane normal on the camera's side, top handle -> closest
point on that edge via its image-space foot, height taken in absolute value.
Shown top handle = projected top corner (`draw.handle_co`), used for pick and
drag; the stored top is synced to it. Dragging the base moves the top with it
(scale kept); `calibrate.seed_cube` keeps the scale on plane / scale-mode changes
and migrates pre-cube files (camera distance kept). Seeding skips `suspended()`.

Cube UI: scale option *Scale Cube* (default) / *Reference Distance* in VP mode;
size presets 10 cm…10 m + custom. Cube and Reference Distance are mutually
exclusive on screen (`calibrate.reference_scales` hides the cube, asked by the
user); in RECT / HORIZON it is a visual check with only the base handle, toggled
by `show_cube` in the Opacity panel. Edges are drawn
in the colours of the world axes they run along; in the plane the cube extends
the way the camera looks (`-rotation[:, 2]`, an axis seen nearly across keeps +,
`scale.ACROSS`), on walls upwards: rules based on base or origin flipped it while
dragging (reported by the user). `uncertainty()` solves with the scale fixed. The top can't be dragged below
`ops_modal.MIN_CUBE_PX` above the base (it would flip).

## Render setup (`ops_render.py`)
- Standard view transform is the only one that gives back the sRGB photo
  (measured: AgX / PBR Neutral shift it ~9 levels median, >120 max). Exposure 0,
  look None, no curves / white balance; image output follows the scene.
- Blender 5 compositor: `scene.compositing_node_group` (a `CompositorNodeTree`
  data-block), `NodeGroupOutput` with a Color interface socket (no Composite
  node), menu options are input sockets (`Scale` "Type" = "Render Size",
  "Frame Type" = "Fit", "Extension X/Y" = "Extend" — Clip makes the 1 px border
  semi-transparent), Mix is `ShaderNodeMix` (sockets by identifier `A_Color`...).
  Our tree is tagged `ftc_compositing` and rebuilt; a user's tree gets a fake user.
- Cycles: with `use_pass_shadow_catcher` on, the shadows leave the Combined alpha
  (alpha 0 under the shadow) -> photo × pass, then Alpha Over. Transparent output
  needs the pass off (shadows in alpha). EEVEE: no shadow catcher.
- Roles: `Object.ftc_catcher` / `ftc_holdout`, get/set bools over the native
  `is_shadow_catcher` / `is_holdout`, mutually exclusive; `ftc.set_role` (CATCHER,
  HOLDOUT, NONE) for the selection. The user's rule: FTC never creates objects
  for roles and there is no "CG object" / "hidden" role (the default is the CG).
  A "New Shadow Catcher Plane" operator existed briefly and was removed on request.
- Engine / display / view / look enums are dynamic (static `enum_items` lists only
  NONE / EEVEE): set them with `_try_set` (TypeError when missing: custom OCIO,
  Cycles disabled). Alpha output: try `color_mode = "RGBA"`, else IMAGE + PNG.
  Selection changes only in Object Mode (`select_only`): changing the active
  object leaves an Edit Mode object stuck.
- Probe `render` writes `dist/probes/render_photo.png` / `render_alpha.png`.

## Known limitations
- A known rectangle cannot detect a zoomed photo (keeps the EXIF focal); two VPs
  with one far away cannot either. Three VPs can.
- Dragging the cube top horizontally changes the scale by the component along a
  tilted edge (by design: only the height along the edge counts).
- Old (<0.6) files: `use_known_focal` is gone, they start in "Known + Guides";
  their untouched hand-made default guides (~22 mm equivalent) may then warn.

## Open work
- Pending: the user's GUI test of 1.0.0 (`docs/TEST_GUI.md`).
- Possible: magnifier near the cursor while dragging; more than two lines per VP;
  turn the `paneltest` / `drawall` probes into regular Blender tests.
