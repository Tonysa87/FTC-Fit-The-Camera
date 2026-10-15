# SPDX-License-Identifier: GPL-3.0-or-later
"""In-Blender tests, run headless by scripts/blender_tests.sh.

Usage: blender --background --python tests_blender/test_addon.py -- <project root> <scratch dir>
"""

import ast
import contextlib
import importlib
import math
import os
import struct
import sys
import traceback
from types import SimpleNamespace

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

ROOT, SCRATCH = sys.argv[-2:]
sys.path += [os.path.join(ROOT, "tests"), os.path.join(ROOT, "fit_the_camera")]

import exif  # noqa: E402
from exif_builder import ASCII, RATIONAL, SHORT, build_tiff  # noqa: E402
from synthetic import make_camera  # noqa: E402

PKG = "bl_ext.user_default.fit_the_camera"
calibrate = importlib.import_module(PKG + ".calibrate")

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def fresh_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


def write_photo(name, size, tiff=None):
    """Save a JPEG of the given size, optionally with an EXIF block, and return its path."""
    img = bpy.data.images.new("tmp_" + name, *size)
    img.pixels.foreach_set(np.full(size[0] * size[1] * 4, 0.5, dtype=np.float32))
    img.update()  # without it save() writes stale pixels
    path = os.path.join(SCRATCH, name)
    img.filepath_raw = path
    img.file_format = "JPEG"
    img.save()
    bpy.data.images.remove(img)
    if tiff is not None:
        with open(path, "rb") as f:
            raw = f.read()
        app1 = b"Exif\0\0" + tiff
        with open(path, "wb") as f:
            f.write(raw[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + raw[2:])
    return path


def camera_tiff(focal=24.0, focal35=36, make="TestMake", model="TestModel 1", orientation=1, direction=None):
    gps = None
    if direction is not None:
        gps = [(exif.GPS_DIRECTION_REF, ASCII, "T"), (exif.GPS_DIRECTION, RATIONAL, [(int(direction * 100), 100)])]
    return build_tiff(
        ifd0=[(exif.TAG_MAKE, ASCII, make), (exif.TAG_MODEL, ASCII, model), (exif.TAG_ORIENTATION, SHORT, orientation)],
        exif_ifd=[(exif.TAG_FOCAL_LENGTH, RATIONAL, [(int(focal * 10), 10)]), (exif.TAG_FOCAL_35MM, SHORT, focal35)],
        gps_ifd=gps,
    )


def load(path):
    result = bpy.ops.ftc.load_image(filepath=path)
    assert result == {"FINISHED"}, result
    cam = bpy.context.scene.camera
    assert cam is not None
    return cam


EDGES = {
    "X": [((-2, -2, 0), (2, -2, 0)), ((-2, 2, 3), (2, 2, 3))],
    "Y": [((-2, -2, 0), (-2, 2, 0)), ((2, -2, 3), (2, 2, 3))],
}


def axis_label(syn, axis):
    """EDGES run from their first to their second point along +axis: the solver's sign convention."""
    return "+" + axis


def set_guides_from(settings, syn):
    """Place the 2-VP guides, origin, reference and principal point from a synthetic camera."""
    w, h = syn.image_size

    def norm(p):
        return (float(p[0] / w), float(p[1] / h))

    for i, axis in enumerate(("X", "Y"), start=1):
        keys = calibrate.vp_keys(i)
        (a1, b1), (a2, b2) = (syn.segment(a, b) for a, b in EDGES[axis])
        for key, p in zip(keys, (a1, b1, a2, b2)):
            calibrate.set_handle(settings, key, norm(p))
    calibrate.set_handle(settings, "origin", norm(syn.project([0, 0, 0])[0]))
    calibrate.set_handle(settings, "ref_a", norm(syn.project([0, 0, 0])[0]))
    calibrate.set_handle(settings, "ref_b", norm(syn.project([2, 0, 0])[0]))
    calibrate.set_handle(settings, "pp", norm(syn.principal_point))
    with calibrate.suspended():
        settings.mode = "VP"
        settings.vp_count = "2"
        settings.vp1_axis = axis_label(syn, "X")
        settings.vp2_axis = axis_label(syn, "Y")
        settings.scale_mode = "REFERENCE"
        settings.ref_axis = "X"
        settings.ref_length = 2.0
        settings.pp_mode = "MANUAL"


def check_projection(scene, cam, syn, anchor=None):
    """Blender's own projection of world points must match the synthetic camera."""
    anchor = anchor or Matrix.Identity(4)
    bpy.context.view_layer.update()
    w, h = syn.image_size
    worst = 0.0
    for x in (-3.0, 0.0, 2.5):
        for y in (-2.0, 1.0, 3.0):
            for z in (0.0, 1.5):
                expected = syn.project([x, y, z])[0] / (w, h)
                got = world_to_camera_view(scene, cam, anchor @ Vector((x, y, z)))
                worst = max(worst, abs(got.x - expected[0]) * w, abs(got.y - expected[1]) * h)
    assert worst < 0.5, f"projection differs by {worst:.3f} px"


# ----------------------------------------------------------------------------


@test
def extension_is_enabled():
    assert PKG in bpy.context.preferences.addons
    assert hasattr(bpy.types.Camera, "ftc")
    assert hasattr(bpy.ops.ftc, "calibrate")


@test
def load_image_reads_exif():
    scene = fresh_scene()
    cam = load(write_photo("exif.jpg", (1200, 800), camera_tiff(direction=123.5)))
    s = cam.data.ftc
    data = s.camera_data
    assert s.image is not None and s.image.size[:] == (1200, 800)
    assert (scene.render.resolution_x, scene.render.resolution_y) == (1200, 800)
    assert cam.data.show_background_images and cam.data.background_images[0].image == s.image
    assert (data.make, data.model) == ("TestMake", "TestModel 1")
    assert data.focal_mm_state == "EXIF" and abs(data.focal_mm - 24.0) < 1e-4
    assert data.focal_35mm_state == "EXIF" and data.focal_35mm == 36
    # Crop factor 1.5 on a 3:2 frame: 24 mm long side.
    assert data.sensor_mm_state == "EXIF" and abs(data.sensor_mm - 24.0) < 0.01
    assert data.direction_state == "EXIF" and abs(data.direction - 123.5) < 1e-3
    assert len(s.handles) == len(calibrate.HANDLE_DEFAULTS)
    assert s.results.valid, s.results.error  # default guides solve


@test
def missing_exif_is_flagged_and_manual_entry_marks_state():
    fresh_scene()
    cam = load(write_photo("plain.jpg", (800, 600)))
    data = cam.data.ftc.camera_data
    assert data.focal_mm_state == data.focal_35mm_state == data.sensor_mm_state == "MISSING"
    assert calibrate.known_focal_px(cam.data.ftc) is None
    data.focal_35mm = 28.0
    assert data.focal_35mm_state == "MANUAL"
    assert calibrate.known_focal_px(cam.data.ftc) is not None


def _calibrated_camera(size, pp=None, **angles):
    scene = fresh_scene()
    cam = load(write_photo(f"conv_{size[0]}x{size[1]}.jpg", size))
    syn = make_camera(image_size=size, principal_point=pp, **angles)
    set_guides_from(cam.data.ftc, syn)
    solution = calibrate.update(bpy.context, cam, apply=True)
    assert solution is not None, cam.data.ftc.results.error
    return scene, cam, syn


@test
def blender_projection_matches_landscape():
    scene, cam, syn = _calibrated_camera((1920, 1080))
    check_projection(scene, cam, syn)
    assert cam.data.sensor_fit == "HORIZONTAL"
    # Unknown sensor: the 35 mm equivalent one, on the diagonal of the native 4:3
    # frame (1920 x 1440) like an entered 35 mm equivalent focal length.
    sensor = math.hypot(36.0, 24.0) * 1920 / math.hypot(1920, 1440)
    assert abs(cam.data.sensor_width - sensor) < 1e-4
    assert abs(cam.data.lens - 35.0 * sensor / 36.0) < 0.05


@test
def blender_projection_matches_portrait_with_shift():
    scene, cam, syn = _calibrated_camera((1080, 1620), pp=(500.0, 860.0), pitch=-8.0, yaw=20.0, roll=-2.0)
    check_projection(scene, cam, syn)
    assert cam.data.sensor_fit == "VERTICAL"
    assert abs(cam.data.shift_x) > 0.01 and abs(cam.data.shift_y) > 0.01


@test
def anchor_moves_the_calibrated_frame():
    scene, cam, syn = _calibrated_camera((1600, 1200))
    anchor = Matrix.Translation((4.0, -1.0, 0.5)) @ Matrix.Rotation(math.radians(30.0), 4, "Z")
    s = cam.data.ftc
    s.anchor_matrix = anchor
    s.use_anchor = True
    calibrate.update(bpy.context, cam, apply=True)
    check_projection(scene, cam, syn, anchor)


@test
def rectangle_and_horizon_modes_solve():
    fresh_scene()
    cam = load(write_photo("modes.jpg", (1920, 1080), camera_tiff(focal=35.0, focal35=35)))
    s = cam.data.ftc
    s.mode = "RECT"
    assert s.results.valid, s.results.error
    s.focal_mode = "KNOWN"
    assert s.results.valid, s.results.error
    s.mode = "HORIZON"
    s.camera_height = 1.7
    assert s.results.valid, s.results.error
    assert abs(s.results.height - 1.7) < 1e-6
    s.straighten = True
    assert abs(s.results.roll) < 1e-6


@test
def default_guides_give_camera_above_ground():
    fresh_scene()
    cam = load(write_photo("defaults.jpg", (1920, 1080), camera_tiff(focal=35.0, focal35=35)))
    s = cam.data.ftc
    for mode, count in (("VP", "2"), ("VP", "3"), ("VP", "1"), ("RECT", "2"), ("HORIZON", "2")):
        s.mode, s.vp_count = mode, count
        res = s.results
        assert res.valid, f"{mode} {count}: {res.error}"
        assert res.height > 0.0, f"{mode} {count}: camera below ground ({res.height})"
        assert not res.warnings, f"{mode} {count}: {res.warnings}"


@test
def uncertainty_flags_far_vanishing_points():
    """Real-photo edges: the wall direction vanishes ~22000 px away, so wall +
    verticals is unstable; verticals + one wall line + the EXIF focal is stable."""
    import json

    with open(os.path.join(ROOT, "tests", "data", "elevator_lines.json")) as f:
        data = json.load(f)
    lines = data["lines"]
    size = data["image_size"]
    fresh_scene()
    cam = load(write_photo("square.jpg", tuple(size), camera_tiff(focal=5.9, focal35=25)))
    s = cam.data.ftc

    def norm(p):
        return (p[0] / size[0], p[1] / size[1])

    def place(index, a, b):
        for key, p in zip(calibrate.vp_keys(index), [*lines[a], *lines[b]]):
            calibrate.set_handle(s, key, norm(p))

    with calibrate.suspended():
        s.mode, s.vp_count, s.vp1_axis, s.vp2_axis, s.focal_mode = "VP", "2", "+X", "-Z", "SOLVE"
        place(1, "wall_door_bottom", "wall_threshold")
        place(2, "vertical_left_jamb", "vertical_right_jamb")
    calibrate.refresh(cam.data)
    assert s.results.valid, s.results.error
    assert s.results.focal_error > 0.05, s.results.focal_error
    assert "unstable" in s.results.warnings
    # The default, EXIF focal refined by the guides: the far wall can no longer move it.
    unstable = s.results.angle_error
    s.focal_mode = "AUTO"
    assert s.results.valid, s.results.error
    assert s.results.angle_error < unstable / 3, (s.results.angle_error, unstable)
    assert abs(s.results.focal_shift) < 0.05, s.results.focal_shift
    s.focal_mode = "SOLVE"

    # EXIF 5.9 mm / 25 mm-eq on a square crop of a 4:3 sensor: ~2960 px.
    assert abs(calibrate.known_focal_px(s) - 2964) < 15, calibrate.known_focal_px(s)
    with calibrate.suspended():
        s.vp_count, s.vp1_axis, s.vp2_axis = "1", "-Z", "+X"
        place(1, "vertical_left_jamb", "vertical_right_jamb")
        calibrate.set_handle(s, "hz_a", norm(lines["wall_threshold"][0]))
        calibrate.set_handle(s, "hz_b", norm(lines["wall_threshold"][1]))
    calibrate.refresh(cam.data)
    assert s.results.valid, s.results.error
    assert s.results.angle_error < 1.0, s.results.angle_error
    assert "unstable" not in s.results.warnings
    assert abs(math.degrees(s.results.roll) - 4.0) < 0.5, math.degrees(s.results.roll)
    assert abs(math.degrees(s.results.pitch) + 32.7) < 0.5, math.degrees(s.results.pitch)

    # Two floor directions + one vertical line + the EXIF focal: stable too.
    with calibrate.suspended():
        s.vp_count, s.vp1_axis, s.vp2_axis = "2", "+X", "-Y"
        s.use_third_line, s.focal_mode = True, "KNOWN"
        place(1, "tile_across_c", "tile_across_d")
        place(2, "tile_depth_a", "tile_depth_b")
        calibrate.set_handle(s, "vp3_1a", norm(lines["vertical_right_jamb"][0]))
        calibrate.set_handle(s, "vp3_1b", norm(lines["vertical_right_jamb"][1]))
    calibrate.refresh(cam.data)
    assert s.results.valid, s.results.error
    assert s.results.angle_error < 1.5, s.results.angle_error
    assert s.results.height > 0.0

    s.straighten = True
    assert math.degrees(abs(s.results.removed_roll)) > 1.0
    assert "straighten" in s.results.warnings


@test
def load_image_chooses_the_camera():
    """A new camera named after the photo, the empty camera in view, or the one chosen."""
    scene = fresh_scene()
    ops_load = importlib.import_module(PKG + ".ops_load")
    first = load(write_photo("piazza_nord.jpg", (400, 300)))
    assert first.name == "piazza_nord" and first.data.name == "piazza_nord"

    # The camera in view already has a photo: the next one gets its own camera.
    second = load(write_photo("piazza_sud.jpg", (400, 300)))
    assert second != first and second.name == "piazza_sud"
    assert first.data.ftc.image.name.startswith("piazza_nord")
    assert scene.camera == second

    # Chosen by name: the photo replaces that camera's own.
    assert bpy.ops.ftc.load_image(filepath=write_photo("again.jpg", (400, 300)), camera=first.name) == {"FINISHED"}
    assert first.data.ftc.image.name.startswith("again") and scene.camera == first
    assert len([o for o in scene.objects if o.type == "CAMERA"]) == 2

    # A camera without a photo in view takes it, keeping its name.
    empty = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(empty)
    scene.camera = empty
    bpy.context.view_layer.objects.active = empty
    assert ops_load.default_camera(bpy.context) == "Camera"
    assert load(write_photo("empty.jpg", (400, 300))) == empty and empty.name == "Camera"

    # Without "Name After Photo" the new camera is the generic one.
    path = write_photo("generic.jpg", (400, 300))
    assert bpy.ops.ftc.load_image(filepath=path, camera="NEW", name_after_photo=False) == {"FINISHED"}
    assert scene.camera.name.startswith("FTC Camera")

    # The menu lists every camera; the panel switches between the calibrated ones.
    names = {item[0] for item in ops_load.camera_items(None, bpy.context)}
    assert names == {"NEW"} | {o.name for o in scene.objects if o.type == "CAMERA"}
    assert bpy.ops.ftc.use_camera(camera="piazza_sud") == {"FINISHED"}
    assert scene.camera == second
    photo = {item[0] for item in ops_load.photo_camera_items(None, bpy.context)}
    assert photo == {o.name for o in scene.objects if o.type == "CAMERA" and o.data.ftc.image}


@test
def live_writes_only_in_session_or_apply():
    fresh_scene()
    cam = load(write_photo("live.jpg", (1200, 800)))
    s = cam.data.ftc
    assert s.scale_mode == "REFERENCE"  # a new photo starts with the reference distance
    s.scale_mode = "CUBE"
    assert s.cube_size == "1"
    distance = s.results.distance
    before = cam.matrix_world.copy()
    s.cube_size = "2"  # no session: results only
    assert cam.matrix_world == before
    assert abs(s.results.distance - 2.0 * distance) < 1e-6 * distance
    assert bpy.ops.ftc.apply() == {"FINISHED"}
    assert cam.matrix_world != before
    assert abs(cam.matrix_world.translation.length - 2.0 * distance) < 1e-6 * distance


@test
def scale_cube_sets_the_scale():
    """A 1.5 m cube on the floor of the synthetic scene gives Blender's projection
    back; its top handle is shown on the top of the vertical edge."""
    draw = importlib.import_module(PKG + ".draw")
    scene, cam, syn = _calibrated_camera((1920, 1080))
    s = cam.data.ftc
    w, h = syn.image_size

    def norm(p):
        return (float(p[0] / w), float(p[1] / h))

    calibrate.set_handle(s, "cube_base", norm(syn.project([1.0, 0.5, 0.0])[0]))
    top = norm(syn.project([1.0, 0.5, 1.5])[0])
    calibrate.set_handle(s, "cube_top", top)
    with calibrate.suspended():
        s.scale_mode, s.cube_size, s.cube_custom = "CUBE", "CUSTOM", 1.5
    solution = calibrate.update(bpy.context, cam, apply=True)
    assert solution is not None, s.results.error
    assert {"cube_base", "cube_top"} <= set(calibrate.active_handle_keys(s))
    shown = draw.handle_co(s, solution, "cube_top")
    assert math.dist(shown, top) < 1e-3, (shown, top)
    check_projection(scene, cam, syn)

    # Elsewhere the cube is only a visual check, off by default: its base moves,
    # nothing scales.
    s.mode = "RECT"
    assert not s.show_cube and "cube_base" not in calibrate.active_handle_keys(s)
    s.show_cube = True
    keys = calibrate.active_handle_keys(s)
    assert "cube_base" in keys and "cube_top" not in keys
    s.show_cube = False
    assert "cube_base" not in calibrate.active_handle_keys(s)

    # Cube and reference distance exclude each other: only the chosen one is shown.
    s.show_cube = True
    s.mode = "VP"
    s.scale_mode = "REFERENCE"
    keys = calibrate.active_handle_keys(s)
    assert {"ref_a", "ref_b"} <= set(keys) and not any(k.startswith("cube") for k in keys)
    assert not calibrate.cube_visible(s)
    s.scale_mode = "CUBE"
    keys = calibrate.active_handle_keys(s)
    assert {"cube_base", "cube_top"} <= set(keys) and not any(k.startswith("ref") for k in keys)


@test
def scale_cube_keeps_the_scale_across_changes():
    """Switching to the cube, changing the reference plane to a wall and moving
    the cube's base all keep the scene scale; old files keep their distance."""
    from types import SimpleNamespace

    draw = importlib.import_module(PKG + ".draw")
    ops = importlib.import_module(PKG + ".ops_modal")
    scene, cam, syn = _calibrated_camera((1920, 1080))
    s = cam.data.ftc
    distance = s.results.distance  # from the reference distance
    s.scale_mode = "CUBE"
    assert s.results.valid and abs(s.results.distance - distance) < 1e-6 * distance, s.results.error
    for plane in ("XZ", "YZ", "XY"):
        s.ref_plane = plane
        assert s.results.valid, f"{plane}: {s.results.error}"
        assert abs(s.results.distance - distance) < 1e-6 * distance, (plane, s.results.distance, distance)

    # Drag the base through the modal operator's own code: the top follows.
    view = draw.View(0.0, 0.0, 1920.0, 1080.0, (1920, 1080))
    session = SimpleNamespace(drag_key="cube_base", last_mouse=(0.0, 0.0), pitch_drag=None)

    def changed(ctx, camera, reset_pitch=True, key=None):
        calibrate.settings_changed(camera.data, ctx, reset_pitch=reset_pitch)

    fake = SimpleNamespace(changed=changed)
    s.pitch_offset = 0.01
    distance = s.results.distance
    for _ in range(5):
        ops.FTC_OT_calibrate.drag(fake, bpy.context, session, s, cam, view, SimpleNamespace(shift=False, ctrl=False),
                                  (session.last_mouse[0] + 20.0, session.last_mouse[1] + 6.0))  # fmt: skip
    assert abs(s.results.distance - distance) < 1e-6 * distance, s.results.distance
    assert abs(s.pitch_offset - 0.01) < 1e-7  # scale handles keep the pitch correction

    # A file saved before the cube: the camera keeps its distance from the origin.
    s.cube_size = "2"
    bpy.ops.ftc.apply()
    distance = s.results.distance
    s.handles.remove(s.handles.find("cube_top"))
    calibrate.refresh(cam.data)
    assert "cube_top" in s.handles
    assert abs(s.results.distance - distance) < 1e-4 * distance, (s.results.distance, distance)


@test
def solved_principal_point_solves_the_focal_length():
    _, cam, _ = _calibrated_camera((1920, 1080))
    s = cam.data.ftc
    s.camera_data.focal_35mm = 50.0
    s.vp_count, s.pp_mode, s.focal_mode = "3", "SOLVE", "KNOWN"
    assert calibrate.focal_source(s) == "SOLVE"


@test
def flip_axis_buttons_keep_a_right_handed_world():
    draw = importlib.import_module(PKG + ".draw")
    scene, cam, syn = _calibrated_camera((1920, 1080))
    s = cam.data.ftc
    assert draw.third_axis("+X", "+Y") == "+Z" and draw.third_axis("+Y", "+X") == "-Z"
    assert draw.third_axis("-X", "+Z") == "+Y"
    assert bpy.ops.ftc.flip_axis(index=1) == {"FINISHED"}
    assert (s.vp1_axis, s.vp2_axis) == ("-X", "+Y")
    assert bpy.ops.ftc.flip_axis(index=3) == {"FINISHED"}  # Z flips with axis 2
    assert (s.vp1_axis, s.vp2_axis) == ("-X", "-Y")
    s.vp2_axis = "+Z"
    assert bpy.ops.ftc.flip_axis(index=3) == {"FINISHED"}  # axis 2 is Z: axis 1 flips
    assert (s.vp1_axis, s.vp2_axis) == ("+X", "+Z")

    # The third axis arrow follows the solved camera, not the handle order.
    s.vp1_axis, s.vp2_axis, s.use_third_line = "+X", "+Y", True
    w, h = syn.image_size
    bottom, top = (tuple(syn.project(p)[0] / (w, h)) for p in ([0, 0, 0], [0, 0, 1]))
    calibrate.set_handle(s, "vp3_1a", bottom)
    calibrate.set_handle(s, "vp3_1b", top)
    solution = calibrate.refresh(cam.data)
    assert not draw.runs_backwards(s, solution, "+Z", "vp3_1a", "vp3_1b")
    assert draw.runs_backwards(s, solution, "+Z", "vp3_1b", "vp3_1a")


@test
def ftc_orientation_follows_the_alignment():
    orient = importlib.import_module(PKG + ".ops_orientation")
    scene, cam, syn = _calibrated_camera((1920, 1080))
    assert bpy.context.window is not None, "no window: create_orientation cannot run"
    s = cam.data.ftc
    slot = scene.transform_orientation_slots[0]
    assert orient.find(scene) is None and slot.type == "GLOBAL"
    assert bpy.ops.ftc.apply() == {"FINISHED"}
    o = orient.find(scene)
    assert o is not None and slot.type == "GLOBAL", "Apply creates it without switching to it"
    assert all(abs(o.matrix[i][j] - (i == j)) < 1e-6 for i in range(3) for j in range(3)), "no alignment: Global"

    cursor = scene.cursor
    cursor.location = (2.0, -1.0, 0.5)
    cursor.rotation_mode = "XYZ"
    cursor.rotation_euler = (0.3, -0.2, 0.9)
    for plane in ("XY", "XZ", "YZ"):
        s.ref_plane = plane
        assert bpy.ops.ftc.align_cursor() == {"FINISHED"}
        bpy.ops.ftc.align_rotate()
        bpy.ops.ftc.align_flip()
        m = Matrix(orient.find(scene).matrix)
        align = calibrate.alignment_matrix(s)
        assert abs(m.determinant() - 1.0) < 1e-5
        for k in range(3):
            # Column k: the calibrated axis k in the scene, also seen from the
            # camera: a step along it in the scene is a step along it in the
            # calibrated world.
            axis = Vector([0.0, 0.0, 0.0])
            axis[k] = 1.0
            expected = (align.to_3x3() @ axis).normalized()
            assert (m.col[k] - expected).length < 1e-5, (plane, k)
        # The calibrated axes as seen in the photo: the vanishing direction of the
        # scene axis matches the synthetic camera's world axis.
        rot_cam = cam.matrix_world.to_3x3().normalized()
        for k in range(3):
            in_cam = rot_cam.transposed() @ m.col[k]
            axis = np.zeros(3)
            axis[k] = 1.0
            ref = syn.rotation.T @ axis
            assert np.allclose(np.array(in_cam), ref, atol=1e-4), (plane, k, in_cam, ref)

    # The panel button switches to it and back.
    assert bpy.ops.ftc.use_orientation() == {"FINISHED"} and slot.type == "FTC"
    assert orient.in_use(scene)
    assert bpy.ops.ftc.align_clear() == {"FINISHED"}
    assert slot.type == "FTC", "updating it keeps the slot"
    m = orient.find(scene).matrix
    assert all(abs(m[i][j] - (i == j)) < 1e-6 for i in range(3) for j in range(3))
    assert bpy.ops.ftc.use_orientation() == {"FINISHED"} and slot.type == "GLOBAL"
    # find() leaves a slot on another custom orientation as it was.
    with bpy.context.temp_override(**orient._view3d_override(bpy.context)):
        bpy.ops.transform.create_orientation(name="Mine", use_view=True, use=True)
    assert slot.type == "Mine" and orient.find(scene) is not None and slot.type == "Mine"


@test
def upright_copy_swaps_dimensions():
    scene = fresh_scene()
    cam = load(write_photo("rotated.jpg", (40, 20), camera_tiff(orientation=6)))
    s = cam.data.ftc
    assert s.camera_data.orientation == 6
    source = s.image.pixels[0]
    assert bpy.ops.ftc.upright_image() == {"FINISHED"}
    assert s.image.size[:] == (20, 40)
    assert s.image.packed_file is not None
    assert bytes(s.image.packed_file.data[:2]) == b"\xff\xd8", "packed as JPEG like the source"
    assert abs(s.image.pixels[0] - source) < 0.02, (s.image.pixels[0], source)  # from the packed JPEG
    assert (scene.render.resolution_x, scene.render.resolution_y) == (20, 40)
    assert cam.data.background_images[0].image == s.image


@test
def settings_survive_save_and_reload():
    fresh_scene()
    cam = load(write_photo("persist.jpg", (1000, 750)))
    s = cam.data.ftc
    s.mode = "RECT"
    calibrate.set_handle(s, "rect_0", (0.11, 0.22))
    path = os.path.join(SCRATCH, "persist.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    s = bpy.context.scene.camera.data.ftc
    assert s.mode == "RECT"
    assert tuple(round(c, 4) for c in calibrate.handle(s, "rect_0")) == (0.11, 0.22)
    assert s.camera_data.image_width == 1000


@test
def overlay_draws_in_every_mode():
    import gpu

    try:
        gpu.init()
    except Exception as exc:  # no GPU at all: nothing to check here
        print(f"SKIP  overlay drawing: {exc}")
        return
    draw = importlib.import_module(PKG + ".draw")
    _, cam, _ = _calibrated_camera((1920, 1080))
    settings = cam.data.ftc
    session = SimpleNamespace(active_vp=0, hover="origin", drag_key="vp1_1a")
    width, height = 400, 300
    view = draw.View(20.0, 20.0, 380.0, 222.5, (1920, 1080))
    configs = [
        {"mode": "VP", "vp_count": "2", "scale_mode": "REFERENCE"},
        {"mode": "VP", "vp_count": "3", "scale_mode": "CUBE", "freeze": True},
        {"mode": "VP", "vp_count": "1", "pp_mode": "MANUAL"},
        {"mode": "RECT", "freeze": False},
        {"mode": "HORIZON"},
    ]
    settings.camera_data.focal_35mm = 35.0
    offscreen = gpu.types.GPUOffScreen(width, height)
    try:
        for config in configs:
            for key, value in config.items():
                setattr(settings, key, value)
            solution = calibrate.refresh(cam.data)
            with offscreen.bind():
                fb = gpu.state.active_framebuffer_get()
                fb.clear(color=(0.0, 0.0, 0.0, 0.0))
                with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                    gpu.matrix.load_identity()
                    gpu.matrix.load_projection_matrix(
                        Matrix(((2 / width, 0, 0, -1), (0, 2 / height, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1)))
                    )
                    draw.draw_guides(view, settings, solution, session, "METRIC")
                pixels = np.asarray(fb.read_color(0, 0, width, height, 4, 0, "UBYTE").to_list(), dtype=np.uint8)
            drawn = int((pixels[..., 3] > 0).sum())
            assert drawn > 500, f"{config}: only {drawn} pixels drawn"
    finally:
        offscreen.free()


@test
def magnifier_shows_the_photo_around_the_handle():
    """Shift while dragging: the lens is centred on the handle, 4x larger, and
    hides the system cursor until it closes (never for the pitch diamond)."""
    draw = importlib.import_module(PKG + ".draw")
    ops_modal = importlib.import_module(PKG + ".ops_modal")

    view = draw.View(20.0, 30.0, 380.0, 232.5, (1920, 1080))
    zoomed = draw.lens_view(view, (100.0, 80.0), 4.0, 200)
    assert zoomed.to_region(view.to_norm(100.0, 80.0)) == (100.0, 100.0)
    assert abs((zoomed.x1 - zoomed.x0) - 4.0 * (view.x1 - view.x0)) < 1e-9

    calls = []
    window = SimpleNamespace(
        cursor_modal_set=lambda c: calls.append(c), cursor_modal_restore=lambda: calls.append("restore")
    )
    session = SimpleNamespace(drag_key="pitch", magnify=False, cursor_window=None)
    ops_modal.set_magnifier(session, window, True)
    assert not session.magnify and not calls
    session.drag_key = "vp1_1a"
    ops_modal.set_magnifier(session, window, True)
    ops_modal.set_magnifier(session, window, True)
    assert session.magnify and calls == ["NONE"]
    ops_modal.set_magnifier(session, window, False)
    assert not session.magnify and calls == ["NONE", "restore"]

    import gpu

    try:
        gpu.init()
    except Exception as exc:  # no GPU at all: nothing to draw
        print(f"SKIP  magnifier drawing: {exc}")
        return
    _, cam, _ = _calibrated_camera((1920, 1080))
    settings = cam.data.ftc
    # Gradient photo: red = u, green = v, so every lens pixel tells where it samples.
    w, h = 1920, 1080
    photo = bpy.data.images.new("gradient", w, h)
    u, v = np.meshgrid((np.arange(w) + 0.5) / w, (np.arange(h) + 0.5) / h)
    photo.pixels.foreach_set(np.dstack([u, v, np.zeros_like(u), np.ones_like(u)]).astype(np.float32).ravel())
    photo.update()
    settings.image = photo
    solution = calibrate.refresh(cam.data)
    key = "vp1_1a"
    session = SimpleNamespace(active_vp=0, hover=None, drag_key=key, magnify=True)
    assert draw.magnifying(session)
    centre = view.to_region(draw.handle_co(settings, solution, key))
    width, height = 400, 300
    offscreen = gpu.types.GPUOffScreen(width, height)
    try:
        with offscreen.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 0.0))
            with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                gpu.matrix.load_identity()
                gpu.matrix.load_projection_matrix(
                    Matrix(((2 / width, 0, 0, -1), (0, 2 / height, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1)))
                )
                draw.draw_lens(view, settings, solution, session, "METRIC")
            pixels = np.asarray(fb.read_color(0, 0, width, height, 4, 0, "FLOAT").to_list(), dtype=float)
    finally:
        offscreen.free()
        draw.free_lens()

    def srgb(c):  # the sRGB texture is sampled as linear and stored as such here
        return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0.0, None), 1 / 2.4) - 0.055)

    hits = 0
    for k in range(12):
        a = 2 * math.pi * k / 12
        x, y = centre[0] + 50.0 * math.cos(a), centre[1] + 50.0 * math.sin(a)
        if not (0 <= x < width and 0 <= y < height):
            continue
        expected = np.array(view.to_norm(centre[0] + 50.0 * math.cos(a) / 4.0, centre[1] + 50.0 * math.sin(a) / 4.0))
        got = srgb(pixels[int(y), int(x), :2])
        hits += bool(np.all(np.abs(got - expected) < 0.01))  # guides crossing a sample miss it
    assert hits >= 6, hits


@test
def rectangle_on_a_wall_aligns_to_a_face():
    """A 4-sided wall face seen by a synthetic camera: after "Align to Selection"
    Blender's projection of the face's corners lands on the rectangle handles."""
    import bmesh

    scene = fresh_scene()
    size = (1600, 1200)
    cam = load(write_photo("wall.jpg", size))
    s = cam.data.ftc

    centre = Vector((1.0, 2.0, 1.2))
    x = Vector((math.cos(math.radians(20.0)), math.sin(math.radians(20.0)), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    normal = x.cross(up)
    w, h = 1.8, 1.1
    corners = [centre + a * w / 2 * x + b * h / 2 * up for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    syn = make_camera(pitch=-4.0, yaw=-20.0, roll=1.5, position=tuple(centre + 6.0 * normal + Vector((0.4, 0, 0.3))),
                      image_size=size)  # fmt: skip

    mesh = bpy.data.meshes.new("wall")
    mesh.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new("wall", mesh)
    scene.collection.objects.link(obj)
    for i, c in enumerate(corners):
        p = syn.project(np.array(c))[0]
        calibrate.set_handle(s, f"rect_{i}", (p[0] / size[0], p[1] / size[1]))
    with calibrate.suspended():
        s.mode, s.ref_plane, s.rect_width, s.rect_height = "RECT", "XZ", 1.0, 1.0

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm.faces[0].select = True
    bm.faces.active = bm.faces[0]
    bmesh.update_edit_mesh(mesh)
    assert bpy.ops.ftc.align_selection() == {"FINISHED"}
    bpy.ops.object.mode_set(mode="OBJECT")

    assert abs(s.rect_width - w) < 1e-5 and abs(s.rect_height - h) < 1e-5
    assert abs(s.results.focal_px - syn.focal_px) / syn.focal_px < 0.01
    bpy.context.view_layer.update()
    worst = 0.0
    for i, c in enumerate(corners):
        got = world_to_camera_view(scene, cam, c)
        want = calibrate.handle(s, f"rect_{i}")
        worst = max(worst, abs(got.x - want[0]) * size[0], abs(got.y - want[1]) * size[1])
    assert worst < 0.5, f"corners off by {worst:.2f} px"
    # The camera stays in front of the face, at the synthetic camera's place.
    assert (cam.matrix_world.translation - Vector(syn.position)).length < 1e-3


def _render_to_array(scene, name):
    scene.render.filepath = os.path.join(SCRATCH, name)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(scene.render.filepath + ".png")
    out = np.array(img.pixels[:]).reshape(img.size[1], img.size[0], 4)
    bpy.data.images.remove(img)
    return out


@test
def prepare_render_gives_back_the_photo():
    scene = fresh_scene()
    cam = load(write_photo("render.jpg", (64, 48)))
    s = cam.data.ftc
    user_tree = bpy.data.node_groups.new("Mine", "CompositorNodeTree")
    scene.compositing_node_group = user_tree
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 1.0
    scene.render.resolution_x = 100  # changed by hand: back to the photo size
    assert bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=True) == {"FINISHED"}
    assert scene.render.engine == "CYCLES" and scene.render.film_transparent
    assert scene.view_settings.view_transform == "Standard" and scene.view_settings.look == "None"
    assert scene.view_settings.exposure == 0.0 and scene.display_settings.display_device == "sRGB"
    assert (scene.render.resolution_x, scene.render.resolution_y) == (100, 75)  # the photo's aspect
    scene.render.resolution_x, scene.render.resolution_y = 64, 48
    assert scene.view_layers[0].cycles.use_pass_shadow_catcher
    tree = scene.compositing_node_group
    assert tree is not user_tree and tree.get("ftc_compositing") and user_tree.use_fake_user
    photo = next(n for n in tree.nodes if n.bl_idname == "CompositorNodeImage")
    assert photo.image == s.image
    mix = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeMix")
    assert any(link.from_socket.name == "Shadow Catcher" and link.to_node == mix for link in tree.links)
    out = next(n for n in tree.nodes if n.bl_idname == "NodeGroupOutput")
    assert out.inputs[0].is_linked
    # Again: the same tree is rebuilt, not a new one.
    bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=True)
    assert scene.compositing_node_group == tree
    assert sum(1 for t in bpy.data.node_groups if t.get("ftc_compositing")) == 1

    # Empty scene, render at 50%: the output is the photo, opaque, to the 8-bit level.
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.dither_intensity = 0.0
    scene.render.resolution_percentage = 50
    scene.render.image_settings.color_mode = "RGBA"
    got = _render_to_array(scene, "render_photo")
    assert got.shape == (24, 32, 4), got.shape
    want = s.image.pixels[0]
    assert np.abs(got[..., :3] - want).max() < 1.5 / 255, np.abs(got[..., :3] - want).max()
    assert got[..., 3].min() == 1.0


@test
def prepare_render_transparent_keeps_shadows_in_alpha():
    scene = fresh_scene()
    load(write_photo("render_alpha.jpg", (64, 48)))
    bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=True)
    scene.render.image_settings.file_format = "JPEG"
    assert bpy.ops.ftc.prepare_render(output="ALPHA", use_cycles=True) == {"FINISHED"}
    assert scene.compositing_node_group is None
    assert not any(t.get("ftc_compositing") for t in bpy.data.node_groups)
    assert not scene.view_layers[0].cycles.use_pass_shadow_catcher
    assert scene.render.image_settings.file_format == "PNG" and scene.render.image_settings.color_mode == "RGBA"
    # EEVEE kept: no pass, no Shadow Catcher multiply.
    bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=False)
    scene.render.engine = "BLENDER_EEVEE"
    bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=False)
    tree = scene.compositing_node_group
    assert not any(n.bl_idname == "ShaderNodeMix" for n in tree.nodes)


@test
def object_roles_map_to_render_flags():
    """Two roles, shadow catcher and holdout, that exclude each other; they only
    change the objects' own flags."""
    scene = fresh_scene()
    mesh = bpy.data.meshes.new("m")
    objs = [bpy.data.objects.new(f"o{i}", mesh) for i in range(2)]
    for obj in objs:
        scene.collection.objects.link(obj)
    obj = objs[0]
    assert not obj.ftc_catcher and not obj.ftc_holdout
    obj.ftc_catcher = True
    assert obj.is_shadow_catcher and not obj.is_holdout
    obj.ftc_holdout = True
    assert obj.is_holdout and not obj.is_shadow_catcher and not obj.ftc_catcher
    obj.ftc_holdout = False
    assert not (obj.is_holdout or obj.is_shadow_catcher)
    obj.hide_render = True
    obj.ftc_catcher = True
    assert obj.hide_render  # left alone
    obj.hide_render = False
    for o in objs:
        o.select_set(True)
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    assert bpy.ops.ftc.set_role(role="HOLDOUT") == {"FINISHED"}
    assert all(o.is_holdout and not o.is_shadow_catcher for o in objs)
    assert bpy.ops.ftc.set_role(role="CATCHER") == {"FINISHED"}
    assert all(o.is_shadow_catcher and not o.is_holdout for o in objs)
    assert bpy.ops.ftc.set_role(role="NONE") == {"FINISHED"}
    assert not any(o.is_shadow_catcher or o.is_holdout for o in objs)
    # Nothing is created or copied.
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts
    assert "add_catcher" not in dir(bpy.ops.ftc)
    # Clicking in the list selects the object.
    scene.ftc_role_index = list(scene.objects).index(objs[1])
    assert bpy.context.view_layer.objects.active == objs[1] and not objs[0].select_get()
    # The list shows only renderable objects.
    bpy.ops.object.camera_add()
    ul = importlib.import_module(PKG + ".ops_render").FTC_UL_roles
    mock = SimpleNamespace(filter_name="", bitflag_filter_item=1, use_filter_invert=False, use_filter_sort_alpha=True)
    flags, _order = ul.filter_items(mock, None, scene, "objects")
    assert sum(flags) == 2


@test
def render_setup_edge_cases():
    """Video output, several view layers, Edit Mode, missing Cycles do not break."""
    scene = fresh_scene()
    load(write_photo("render_edge.jpg", (64, 48)))
    image = scene.render.image_settings
    image.media_type = "VIDEO"
    assert bpy.ops.ftc.prepare_render(output="ALPHA", use_cycles=True) == {"FINISHED"}
    assert image.color_mode == "RGBA"
    # Several view layers: the compositor reads the active one.
    second = scene.view_layers.new("Second")
    bpy.context.window.view_layer = second
    bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=True)
    layers = [n.layer for n in scene.compositing_node_group.nodes if n.bl_idname == "CompositorNodeRLayers"]
    assert layers == ["Second"], layers
    bpy.context.window.view_layer = scene.view_layers[0]
    # A click in the roles list while a mesh is in Edit Mode leaves it alone.
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    bpy.ops.mesh.primitive_plane_add()
    other = bpy.context.active_object
    bpy.context.view_layer.objects.active = cube
    bpy.ops.object.mode_set(mode="EDIT")
    scene.ftc_role_index = list(scene.objects).index(other)
    assert bpy.context.view_layer.objects.active == cube
    bpy.ops.object.mode_set(mode="OBJECT")
    assert cube.mode == "OBJECT"


@test
def reference_distance_ignores_the_alignment_plane():
    """The reference distance has its own plane: aligning a wall keeps the scale."""
    scene, cam, syn = _calibrated_camera((1600, 1200))
    s = cam.data.ftc
    w, h = syn.image_size
    a, b = (np.array(syn.project(p)[0]) / (w, h) for p in ([-1.0, -1.3, 0.0], [1.5, -1.3, 0.0]))
    calibrate.set_handle(s, "ref_a", tuple(a))
    calibrate.set_handle(s, "ref_b", tuple(b))
    with calibrate.suspended():
        s.scale_mode, s.ref_axis, s.ref_length, s.ref_measure_plane = "REFERENCE", "X", 2.5, "XY"
    calibrate.update(bpy.context, cam, apply=True)
    check_projection(scene, cam, syn)
    distance = s.results.distance
    for plane in ("XZ", "YZ", "XY"):
        s.ref_plane = plane
        assert abs(s.results.distance - distance) < 1e-6 * distance, (plane, s.results.distance, distance)
    # A reference end close to the horizon keeps a finite uncertainty.
    far = np.array(syn.project([0.0, 3000.0, 0.0])[0]) / (w, h)
    calibrate.set_handle(s, "ref_b", tuple(far))
    solution = calibrate.refresh(cam.data)
    assert solution is not None, s.results.error
    focal, angle = calibrate.uncertainty(s, solution)
    assert math.isfinite(focal) and math.isfinite(angle), (focal, angle)


@test
def second_audit_fixes():
    """Compositor photo follows the camera's, scale kept on mode/plane switches,
    plane change with a target moves the camera, translation context."""
    ops_render = importlib.import_module(PKG + ".ops_render")
    scene, cam, syn = _calibrated_camera((1600, 1200))
    s = cam.data.ftc
    w, h = syn.image_size

    # Cube -> Reference Distance with untouched reference handles keeps the scale.
    calibrate.reset_handles(s)  # reference handles at their defaults
    set_guides_from(s, syn)
    calibrate.set_handle(s, "cube_base", tuple(np.array(syn.project([1.0, 0.5, 0.0])[0]) / (w, h)))
    calibrate.set_handle(s, "cube_top", tuple(np.array(syn.project([1.0, 0.5, 1.0])[0]) / (w, h)))
    with calibrate.suspended():
        s.scale_mode, s.cube_size = "CUBE", "1"
    calibrate.update(bpy.context, cam, apply=True)
    distance = s.results.distance
    s.scale_mode = "REFERENCE"
    assert abs(s.results.distance - distance) < 1e-4 * distance, (s.results.distance, distance)
    s.scale_mode = "CUBE"
    assert abs(s.results.distance - distance) < 1e-4 * distance

    # The cube stays in the image when the plane becomes a wall.
    for plane in ("XZ", "YZ", "XY"):
        s.ref_plane = plane
        for key in ("cube_base", "cube_top"):
            x, y = calibrate.handle(s, key)
            assert -0.06 <= x <= 1.06 and -0.06 <= y <= 1.06, (plane, key, x, y)
        assert abs(s.results.distance - distance) < 1e-4 * distance

    # With a target, changing the plane moves the camera at once.
    s.anchor_matrix = Matrix.Translation((1.0, 2.0, 0.0))
    s.use_anchor = True
    calibrate.update(bpy.context, cam, apply=True)
    before = cam.matrix_world.copy()
    s.ref_plane = "XZ"
    assert (cam.matrix_world.translation - before.translation).length > 1e-3
    s.ref_plane = "XY"
    s.use_anchor = False

    # The compositor shows the scene camera's current photo.
    bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=True)
    tree = scene.compositing_node_group
    tree.use_fake_user = True  # a fake user does not make it "shared"
    bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=True)
    assert scene.compositing_node_group == tree
    second = load(write_photo("second_photo.jpg", (80, 60))).data.ftc
    assert tree.nodes[ops_render.PHOTO_NODE].image == second.image and second.image.name.startswith("second_photo")

    # Generic words are translated only in FTC's own context.
    tr = importlib.import_module(PKG + ".translations")
    assert ("FTC", "Results") in tr.translations_dict["it_IT"]
    assert ("*", "Results") not in tr.translations_dict["it_IT"]


@test
def audit_edge_cases():
    """Session, camera, aspect, keyframes, faces and loading edge cases."""
    ops_modal = importlib.import_module(PKG + ".ops_modal")
    scene, cam, syn = _calibrated_camera((1600, 1200))
    s = cam.data.ftc

    # A local camera that is not a camera is no camera for FTC.
    empty = bpy.data.objects.new("empty", None)
    scene.collection.objects.link(empty)
    space = SimpleNamespace(type="VIEW_3D", use_local_camera=True, camera=empty)
    assert calibrate.space_camera(space, scene) is None
    assert calibrate.space_camera(None, scene) == cam

    # Apply gives the render the image's aspect again, keeping its width.
    size = calibrate.image_size(s)
    scene.render.resolution_x, scene.render.resolution_y = 1000, 1000
    assert not calibrate.aspect_matches(scene, size)
    assert bpy.ops.ftc.apply() == {"FINISHED"}
    assert (scene.render.resolution_x, scene.render.resolution_y) == (1000, 750)
    scene.render.resolution_x, scene.render.resolution_y = 800, 600  # same aspect: kept
    bpy.ops.ftc.apply()
    assert (scene.render.resolution_x, scene.render.resolution_y) == (800, 600)
    scene.render.pixel_aspect_x = 2.0  # stretched pixels change the aspect too
    assert not calibrate.aspect_matches(scene, size)
    scene.render.pixel_aspect_x = 1.0

    # Keyframes, constraints or an animated parent override the calibration.
    assert not calibrate.transform_overridden(cam)
    cam.keyframe_insert("location")
    assert calibrate.transform_overridden(cam)
    cam.animation_data_clear()
    track = cam.constraints.new("TRACK_TO")
    assert calibrate.transform_overridden(cam)
    track.enabled = False
    assert not calibrate.transform_overridden(cam)
    cam.constraints.remove(track)
    cam.data.keyframe_insert("lens")
    assert calibrate.transform_overridden(cam)
    cam.data.animation_data_clear()
    rig = bpy.data.objects.new("rig", None)
    scene.collection.objects.link(rig)
    cam.parent = rig
    rig.keyframe_insert("rotation_euler")
    assert calibrate.transform_overridden(cam)
    cam.parent = None

    # Rotate 90° / Flip act at once during a session (simulated), and Blender's
    # undo re-solves the session camera.
    s.anchor_matrix = Matrix.Translation((1.0, 2.0, 0.0))
    s.use_anchor = True
    calibrate.update(bpy.context, cam, apply=True)
    session = ops_modal.Session(cam, SimpleNamespace(as_pointer=lambda: 0), SimpleNamespace(as_pointer=lambda: 0))
    ops_modal.FTC_OT_calibrate._session = session
    calibrate.session_camera = cam.name
    try:
        before = cam.matrix_world.copy()
        assert bpy.ops.ftc.align_rotate() == {"FINISHED"}
        assert (cam.matrix_world.translation - before.translation).length > 1e-3
        cam.name = "Renamed"
        assert ops_modal.session_camera(session) == cam and calibrate.session_camera == "Renamed"
        ops_modal._on_undo()
        assert not session.stop_requested
        # Apply ends the session, like Enter.
        assert bpy.ops.ftc.apply() == {"FINISHED"}
        assert not ops_modal.FTC_OT_calibrate.running()
    finally:
        ops_modal.end_session()
    assert not ops_modal.FTC_OT_calibrate.running()

    # A face without area is refused.
    mesh = bpy.data.meshes.new("flat")
    mesh.from_pydata([(0, 0, 0)] * 4, [], [(0, 1, 2, 3)])
    flat = bpy.data.objects.new("flat", mesh)
    scene.collection.objects.link(flat)
    bpy.context.view_layer.objects.active = flat
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        before = [tuple(row) for row in s.anchor_matrix]
        try:
            bpy.ops.ftc.align_selection()
            raise AssertionError("a face without area was accepted")
        except RuntimeError as exc:
            assert "no area" in str(exc), exc
        assert [tuple(row) for row in s.anchor_matrix] == before
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")

    # A file that is not an image leaves no empty image behind.
    bad = os.path.join(SCRATCH, "not_an_image.jpg")
    with open(bad, "w") as f:
        f.write("hello")
    count = len(bpy.data.images)
    bpy.context.view_layer.objects.active = cam
    with contextlib.suppress(RuntimeError):  # the operator reports the error
        bpy.ops.ftc.load_image(filepath=bad)
    assert len(bpy.data.images) == count


# Milan, 21 June 2026, 12:30 CEST (10:30 UTC): NREL SPA gives azimuth 148.508°,
# apparent elevation 65.311° (tests/test_sun.py).
SUN_AZIMUTH, SUN_ELEVATION = 148.508, 65.311


def sun_tiff(direction=200.0, ref="T", gps_time=(10, 30, 0), orientation=1):
    gps = [
        (exif.GPS_LAT_REF, ASCII, "N"),
        (exif.GPS_LAT, RATIONAL, [(45, 1), (27, 1), (5112, 100)]),  # 45.4642
        (exif.GPS_LON_REF, ASCII, "E"),
        (exif.GPS_LON, RATIONAL, [(9, 1), (11, 1), (2400, 100)]),  # 9.19
        (exif.GPS_DATE, ASCII, "2026:06:21"),
        (exif.GPS_TIME, RATIONAL, [(v, 1) for v in gps_time]),
    ]
    if direction is not None:
        gps += [(exif.GPS_DIRECTION_REF, ASCII, ref), (exif.GPS_DIRECTION, RATIONAL, [(int(direction * 100), 100)])]
    return build_tiff(
        ifd0=[(exif.TAG_MAKE, ASCII, "SunCam"), (exif.TAG_ORIENTATION, SHORT, orientation)],
        exif_ifd=[
            (exif.TAG_FOCAL_LENGTH, RATIONAL, [(240, 10)]),
            (exif.TAG_FOCAL_35MM, SHORT, 36),
            (exif.TAG_DATETIME_ORIGINAL, ASCII, "2026:06:21 12:30:00"),
        ],
        gps_ifd=gps,
    )


def _sun_camera(tiff):
    fresh_scene()
    cam = load(write_photo("sun.jpg", (1920, 1080), tiff))
    # 36 mm like the EXIF (35 mm equivalent 36): the known focal agrees.
    syn = make_camera(image_size=(1920, 1080), focal_mm=36.0)
    set_guides_from(cam.data.ftc, syn)
    assert calibrate.update(bpy.context, cam, apply=True) is not None, cam.data.ftc.results.error
    return cam


def heading_deg(v):
    return math.degrees(math.atan2(v.x, v.y)) % 360.0


def angle_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def light_dir(light):
    bpy.context.view_layer.update()
    return (light.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()


@test
def sun_from_exif_time_place_and_compass():
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    data = s.camera_data
    assert data.time_state == data.offset_state == data.location_state == "EXIF"
    assert (data.hour, data.minute, data.utc_offset) == (12, 30, 2.0) and data.time_from_gps
    assert s.sun.north_source == "COMPASS"
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    light = s.sun.light
    assert light is not None and light.data.type == "SUN"
    d = light_dir(light)
    assert abs(math.degrees(math.asin(d.z)) - SUN_ELEVATION) < 0.05
    # The camera looks to 200°: the sun is 148.5 - 200 degrees clockwise from its view.
    view = cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    assert angle_diff(heading_deg(d) - heading_deg(view), SUN_AZIMUTH - 200.0) < 0.05

    # Side: the sun comes from the chosen scene axis, at the date's height.
    s.sun.north_source = "SIDE"
    for side, heading in (("+X", 90.0), ("-X", 270.0), ("+Y", 0.0), ("-Y", 180.0)):
        s.sun.sun_side = side
        assert angle_diff(heading_deg(light_dir(light)), heading) < 0.05, side
        assert abs(math.degrees(math.asin(light_dir(light).z)) - SUN_ELEVATION) < 0.05
    # Turn: counter-clockwise seen from above.
    s.sun.sun_side = "-X"
    s.sun.north_correction = math.radians(10.0)
    assert angle_diff(heading_deg(light_dir(light)), 260.0) < 0.05
    s.sun.north_correction = 0.0
    # Raise: the height only, kept above the horizon.
    s.sun.elevation_correction = math.radians(-3.0)
    assert abs(math.degrees(math.asin(light_dir(light).z)) - (SUN_ELEVATION - 3.0)) < 0.05
    assert angle_diff(heading_deg(light_dir(light)), 270.0) < 0.05
    s.sun.elevation_correction = math.radians(-120.0)
    assert abs(math.degrees(math.asin(light_dir(light).z)) - 0.5) < 1e-3, "kept just above the horizon"
    s.sun.elevation_correction = 0.0

    # The north correction turns the sun about Z; the light stays where it is.
    light.location = (1.0, 2.0, 3.0)
    before = heading_deg(light_dir(light))
    s.sun.north_correction = math.radians(10.0)
    assert angle_diff(heading_deg(light_dir(light)), before - 10.0) < 1e-3
    assert (light.matrix_world.translation - Vector((1.0, 2.0, 3.0))).length < 1e-6
    assert abs(math.degrees(math.asin(light_dir(light).z)) - SUN_ELEVATION) < 0.05

    # A rotated parent: the light still points at the sun.
    target = light_dir(light).copy()
    parent = bpy.data.objects.new("rig", None)
    bpy.context.collection.objects.link(parent)
    parent.rotation_euler = (0.4, -0.3, 1.1)
    bpy.context.view_layer.update()
    light.parent = parent
    assert math.degrees(light_dir(light).angle(target)) > 10.0
    s.sun.north_correction = math.radians(10.0001)
    assert math.degrees(light_dir(light).angle(target)) < 1e-2


@test
def calibrate_shadow_leaves_the_camera_alone():
    """Calibrate Shadow: only the shadow handles are shown and picked, the
    calibration shortcuts are off and the camera is never written."""
    import gpu

    draw = importlib.import_module(PKG + ".draw")
    ops_modal = importlib.import_module(PKG + ".ops_modal")
    ops_sun = importlib.import_module(PKG + ".ops_sun")
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    s.sun.source = "SHADOW"
    s.live = True
    fake = SimpleNamespace(as_pointer=lambda: 0)
    session = ops_modal.Session(cam, fake, fake, shadow_only=True)
    ops_modal.FTC_OT_calibrate._session = session
    try:
        assert ops_modal.FTC_OT_calibrate.running(shadow=True) and not ops_modal.FTC_OT_calibrate.running(shadow=False)
        # The modal of a session replaced by another (Calibrate <-> Calibrate Shadow) stops without ending it.
        assert ops_modal.FTC_OT_calibrate.owns_session(SimpleNamespace(_own=session))
        assert not ops_modal.FTC_OT_calibrate.owns_session(SimpleNamespace(_own=object()))
        assert draw.session_keys(s, session) == list(ops_sun.SHADOW_KEYS)
        assert ops_modal.session_camera(session) == cam and calibrate.session_camera is None
        view = draw.View(0.0, 0.0, 1920.0, 1080.0, (1920, 1080))
        solution = calibrate.cached_solution(cam.data)
        at = view.to_region(draw.handle_co(s, solution, "vp1_1a"))
        assert ops_modal.FTC_OT_calibrate.pick(None, s, view, at) is None, "guides are not picked"
        at = view.to_region(draw.handle_co(s, solution, "shadow_tip"))
        assert ops_modal.FTC_OT_calibrate.pick(None, s, view, at) == "shadow_tip"

        # A guide moved meanwhile (from the panel or a script): Enter does not write the camera.
        before = cam.matrix_world.copy()
        with calibrate.suspended():
            co = calibrate.handle(s, "vp1_1a")
            calibrate.set_handle(s, "vp1_1a", (co[0] + 0.05, co[1]))
        ops_modal.FTC_OT_calibrate.changed(None, bpy.context, cam, key=None)
        report = SimpleNamespace(report=lambda *args: None)
        ops_modal.FTC_OT_calibrate.finish(report, bpy.context, apply=True)
        assert not ops_modal.FTC_OT_calibrate.running()
        assert all(abs(a - b) < 1e-9 for ra, rb in zip(cam.matrix_world, before) for a, b in zip(ra, rb))
    finally:
        ops_modal.end_session()

    # The overlay draws the shadow alone.
    try:
        gpu.init()
    except Exception as exc:
        print(f"SKIP  shadow overlay drawing: {exc}")
        return
    session = SimpleNamespace(active_vp=0, hover=None, drag_key=None, shadow_only=True)
    width, height = 400, 300
    view = draw.View(20.0, 20.0, 380.0, 222.5, (1920, 1080))
    offscreen = gpu.types.GPUOffScreen(width, height)
    try:
        with offscreen.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 0.0))
            with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                gpu.matrix.load_identity()
                gpu.matrix.load_projection_matrix(
                    Matrix(((2 / width, 0, 0, -1), (0, 2 / height, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1)))
                )
                draw.draw_guides(view, s, calibrate.refresh(cam.data), session, "METRIC")
            pixels = np.asarray(fb.read_color(0, 0, width, height, 4, 0, "UBYTE").to_list(), dtype=np.uint8)
        assert int((pixels[..., 3] > 0).sum()) > 100
    finally:
        offscreen.free()


@test
def sun_needs_time_zone_and_place_and_daylight():
    ops_sun = importlib.import_module(PKG + ".ops_sun")
    fresh_scene()
    cam = load(write_photo("nosun.jpg", (1200, 800), camera_tiff()))
    s = cam.data.ftc
    data = s.camera_data
    assert s.sun.north_source == "SIDE" and s.sun.sun_side == "-Y", "no compass: the sun's side, by default -Y"
    assert "Date and time" in ops_sun.evaluate(s).error
    data.hour = 12
    assert data.time_state == "MANUAL"
    data.year, data.month, data.day = 2026, 6, 21
    assert "Time zone" in ops_sun.evaluate(s).error
    data.utc_offset = 2.0
    assert data.offset_state == "MANUAL"
    assert "Place" in ops_sun.evaluate(s).error
    data.gps_latitude, data.gps_longitude = 45.4642, 9.19
    assert data.location_state == "MANUAL"
    data.minute = 30
    state = ops_sun.evaluate(s)
    assert not state.error, state.error
    assert abs(state.sun.azimuth - SUN_AZIMUTH) < 0.05 and abs(state.sun.elevation - SUN_ELEVATION) < 0.05
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    light = s.sun.light
    before = light.matrix_basis.copy()
    data.hour = 23
    assert "below the horizon" in ops_sun.evaluate(s).error
    assert light.matrix_basis == before, "a night time leaves the light alone"
    data.day = 31
    data.month = 6
    assert ops_sun.evaluate(s).error == "Invalid date"


@test
def sun_time_read_again_and_stale_gps():
    ops_sun = importlib.import_module(PKG + ".ops_sun")
    fresh_scene()
    # GPS fix 2 h 13 min older than the camera clock: not a time zone.
    cam = load(write_photo("stale.jpg", (1200, 800), sun_tiff(direction=None, gps_time=(10, 17, 0))))
    s = cam.data.ftc
    data = s.camera_data
    assert data.clock_mismatch and data.offset_state == "EXIF" and data.utc_offset == 0.0
    assert (data.hour, data.minute) == (10, 17), "the GPS time, shown as UTC"
    assert any("GPS time" in w for w in ops_sun.evaluate(s).warnings)
    data.hour = 8
    assert data.time_state == "MANUAL"
    assert bpy.ops.ftc.read_photo_time() == {"FINISHED"}
    assert data.time_state == "EXIF" and data.hour == 10
    # 1.0 files: GPS read, no location state yet.
    data.location_state = "MISSING"
    assert ops_sun.location_state(data) == "EXIF"


def shine(light):
    """Direction the light shines along (its world -Z)."""
    bpy.context.view_layer.update()
    return (light.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


@test
def sun_light_mirrored_parented_or_gone():
    ops_sun = importlib.import_module(PKG + ".ops_sun")
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    light = s.sun.light
    sun = ops_sun.evaluate(s).direction
    for scale in ((-1.0, 1.0, 1.0), (1.0, 1.0, -2.0), (-1.0, -1.0, -1.0), (2.0, 3.0, 0.5)):
        light.scale = scale
        ops_sun.orient(s)
        assert shine(light).dot(sun) < -0.9999, scale
    light.scale = (1.0, 1.0, 1.0)
    parent = bpy.data.objects.new("mirror", None)
    bpy.context.collection.objects.link(parent)
    parent.scale = (1.0, -1.0, 3.0)
    parent.rotation_euler = (0.3, 0.2, -0.7)
    bpy.context.view_layer.update()
    light.parent = parent
    ops_sun.orient(s)
    assert shine(light).dot(sun) < -0.9999, "mirrored, non-uniform parent"
    light.parent = None

    # A Track To constraint overrides the rotation: say so.
    light.constraints.new("TRACK_TO")
    assert "override" in ops_sun.light_problem(light)
    light.constraints.remove(light.constraints[0])
    assert ops_sun.light_problem(light) == ""

    # Deleted (still referenced by FTC): left alone and reported.
    for coll in list(light.users_collection):
        coll.objects.unlink(light)
    before = light.matrix_basis.copy()
    s.sun.north_correction = math.radians(20.0)
    assert light.matrix_basis == before
    assert "no scene" in ops_sun.light_problem(light)


@test
def sun_side_without_compass_and_handles():
    ops_sun = importlib.import_module(PKG + ".ops_sun")
    cam = _sun_camera(sun_tiff(direction=None))
    s = cam.data.ftc
    assert s.sun.north_source == "SIDE"
    state = ops_sun.evaluate(s)
    assert not state.error and angle_diff(heading_deg(state.direction), 180.0) < 0.05, "from -Y"
    assert "shadow_foot" not in calibrate.active_handle_keys(s), "Side needs no handles"
    # 1.1 development files: Map and Landmark read as Side.
    s.sun.north_source = "MAP"
    assert ops_sun.north_source(s) == "SIDE" and ops_sun.evaluate(s).direction is not None
    # A new photo without compass keeps the north chosen by hand.
    s.sun.north_source = "SHADOW"
    load_op = bpy.ops.ftc.load_image(filepath=write_photo("again.jpg", (1200, 800), camera_tiff()), camera=cam.name)
    assert load_op == {"FINISHED"}
    assert s.sun.north_source == "SHADOW"


@test
def sun_after_reopening_and_upright_copy():
    ops_sun = importlib.import_module(PKG + ".ops_sun")
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    assert not ops_sun.evaluate(s).error
    path = os.path.join(SCRATCH, "sun_reopen.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    s = bpy.context.scene.camera.data.ftc
    state = ops_sun.evaluate(s)
    assert not state.error and state.direction is not None, state.error

    # Upright copy (packed, no EXIF): Read from Photo uses the original file.
    fresh_scene()
    cam = load(write_photo("sun_portrait.jpg", (40, 20), sun_tiff(orientation=6)))
    s = cam.data.ftc
    assert bpy.ops.ftc.upright_image() == {"FINISHED"}
    s.camera_data.hour = 3
    assert bpy.ops.ftc.read_photo_time() == {"FINISHED"}
    assert s.camera_data.time_state == "EXIF" and s.camera_data.hour == 12
    # Original gone and the copy without EXIF: nothing is wiped.
    s.source_path = os.path.join(SCRATCH, "missing.jpg")
    s.camera_data.hour = 3
    assert bpy.ops.ftc.read_photo_time() == {"CANCELLED"}
    assert s.camera_data.hour == 3 and s.camera_data.time_state == "MANUAL"


def set_shadow(settings, sun, foot=(1.0, 2.0, 0.0), height=1.5):
    """Put the shadow handles on a pole lit by ``sun``, seen by the solved camera
    (scene = solved world, no alignment)."""
    sol = calibrate.cached_solution(settings.id_data)
    foot = np.asarray(foot, float)
    top = foot + [0.0, 0.0, height]
    tip = top - top[2] / sun[2] * np.asarray(sun, float)
    w, h = sol.image_size
    for key, point in zip(("shadow_foot", "shadow_top", "shadow_tip"), (foot, top, tip)):
        c = (point - sol.position) @ sol.rotation
        px = sol.principal_point + sol.focal_px * c[:2] / -c[2]
        calibrate.set_handle(settings, key, (float(px[0] / w), float(px[1] / h)))


@test
def sun_from_a_shadow_alone():
    from solver.sun import direction_enu

    ops_sun = importlib.import_module(PKG + ".ops_sun")
    scene, cam, syn = _calibrated_camera((1920, 1080))
    s = cam.data.ftc
    assert "shadow_foot" not in calibrate.active_handle_keys(s)
    s.sun.source = "SHADOW"
    assert {"shadow_foot", "shadow_top", "shadow_tip"} <= set(calibrate.active_handle_keys(s))
    assert "shadow_tip" not in calibrate.calibrate_keys(s)
    assert any("shadow handles" in w for w in ops_sun.evaluate(s).warnings), "untouched handles"
    sun = direction_enu(250.0, 30.0)
    set_shadow(s, sun)
    state = ops_sun.evaluate(s)
    assert not state.error and not state.warnings, (state.error, state.warnings)
    assert math.degrees(state.direction.angle(Vector(sun))) < 0.01
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    assert shine(s.sun.light).dot(Vector(sun)) < -0.9999
    # Reset Guides keeps the shadow.
    before = calibrate.handle(s, "shadow_tip")
    assert bpy.ops.ftc.reset() == {"FINISHED"}
    assert max(abs(a - b) for a, b in zip(calibrate.handle(s, "shadow_tip"), before)) < 1e-6
    # A tip "behind" the light: an error, the light stays.
    calibrate.set_handle(s, "shadow_foot", (0.5, 0.99))
    state = ops_sun.evaluate(s)
    assert state.error and state.direction is None


@test
def shadow_checks_the_date_and_gives_the_north():
    from solver.sun import direction_enu

    ops_sun = importlib.import_module(PKG + ".ops_sun")
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    assert s.sun.north_source == "COMPASS"
    s.sun.use_shadow = True
    assert "shadow_foot" in calibrate.active_handle_keys(s), "checking the compass"
    # The shadow of the true sun (east-north-up scene). A high sun (65°) casts
    # short shadows: a tall pole keeps the measure sharp.
    set_shadow(s, direction_enu(SUN_AZIMUTH, SUN_ELEVATION), foot=(0.0, 1.0, 0.0), height=4.0)
    state = ops_sun.evaluate(s)
    assert state.shadow_spread < 2.0, state.shadow_spread
    assert abs(state.shadow_elevation_offset) < 0.02, state
    first = state.shadow_north_offset
    # Turning the compass north by 10° shows in Shadow vs Compass.
    s.sun.north_correction = math.radians(10.0)
    assert angle_diff(ops_sun.evaluate(s).shadow_north_offset, first - 10.0) < 0.02
    # Side + Check with a Shadow: Shadow vs Turn is the Turn to add, and the
    # elevation offset the Raise that matches.
    s.sun.north_source = "SIDE"
    assert "shadow_foot" in calibrate.active_handle_keys(s)
    s.sun.north_correction = 0.0
    need = ops_sun.evaluate(s).shadow_north_offset
    s.sun.north_correction = math.radians(need)
    assert abs(ops_sun.evaluate(s).shadow_north_offset) < 0.02
    s.sun.elevation_correction = math.radians(-3.0)
    assert abs(ops_sun.evaluate(s).shadow_elevation_offset) < 0.02, "against the date, not the raised sun"
    s.sun.elevation_correction = 0.0
    s.sun.use_shadow = False
    assert "shadow_foot" not in calibrate.active_handle_keys(s)
    s.sun.use_shadow = True
    s.sun.north_source = "COMPASS"
    # North from the shadow: the light follows the shadow, the turn is ignored.
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    s.sun.north_source = "SHADOW"
    d = light_dir(s.sun.light)
    assert angle_diff(heading_deg(d), SUN_AZIMUTH) < 0.05
    assert abs(math.degrees(math.asin(d.z)) - SUN_ELEVATION) < 0.05


def synthetic_hdri(u0, v0, size=(512, 256), radius_deg=3.0):
    """Float equirectangular image: a dim sky and a bright disc (the sun) at (u0, v0)."""
    from solver.hdri import direction

    w, h = size
    rows, cols = np.mgrid[0:h, 0:w]
    u, v = (cols + 0.5) / w, (rows + 0.5) / h
    phi, theta = (0.5 - u) * 2 * math.pi, (v - 0.5) * math.pi
    dirs = np.stack([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), np.sin(theta)], -1)
    px = np.full((h, w, 4), 0.02, dtype=np.float32)
    px[..., 3] = 1.0
    px[dirs @ direction(u0, v0) > math.cos(math.radians(radius_deg)), :3] = 50.0
    img = bpy.data.images.new("synthetic_hdri", w, h, float_buffer=True)
    img.pixels.foreach_set(px.ravel())
    img.update()
    return img


def world_with(image):
    world = bpy.data.worlds.new("hdri world")
    if world.node_tree is None:
        world.use_nodes = True
    tree = world.node_tree
    env = tree.nodes.new("ShaderNodeTexEnvironment")
    env.image = image
    tree.links.new(env.outputs["Color"], tree.nodes["Background"].inputs["Color"])
    bpy.context.scene.world = world
    return world, env


def center_brightness(scene, direction, name):
    """Render a narrow view along ``direction`` (world) and return the centre pixel."""
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens, cam_data.sensor_width = 400.0, 36.0  # about 5° wide
    probe = bpy.data.objects.new(name, cam_data)
    scene.collection.objects.link(probe)
    probe.rotation_mode = "QUATERNION"
    probe.rotation_quaternion = Vector(direction).to_track_quat("-Z", "Y")
    previous = scene.camera
    scene.camera = probe
    scene.render.engine = "CYCLES"
    scene.cycles.samples, scene.cycles.use_denoising = 1, False
    scene.render.resolution_x = scene.render.resolution_y = 9
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    try:
        px = _render_to_array(scene, name)
    finally:
        scene.camera = previous
    return float(px[4, 4, :3].mean())


@test
def fit_hdri_renders_the_sun_where_computed():
    """Cycles' equirectangular convention and the Mapping sign, checked by a render."""
    from solver.hdri import image_point

    ops_sun = importlib.import_module(PKG + ".ops_sun")
    cam = _sun_camera(sun_tiff())
    scene = bpy.context.scene
    s = cam.data.ftc
    sun = ops_sun.evaluate(s).direction
    # The HDRI's sun a quarter turn from the photo's: the right turn is 90°,
    # the opposite one misses by 180°.
    u0 = (0.5 - (math.atan2(sun.y, sun.x) + math.pi / 2) / (2 * math.pi)) % 1.0
    v0 = image_point(sun)[1]
    world, env = world_with(synthetic_hdri(u0, v0))
    assert bpy.ops.ftc.fit_hdri(point=(u0, v0)) == {"FINISHED"}
    mapping = env.inputs["Vector"].links[0].from_node
    assert mapping.type == "MAPPING" and mapping.get("ftc_hdri")
    assert s.sun.hdri_fitted and s.sun.hdri_image == env.image.name
    assert center_brightness(scene, sun, "hdri_on_sun") > 0.9, "the HDRI's sun is where the photo's is"
    z = mapping.inputs["Rotation"].default_value[2]
    mapping.inputs["Rotation"].default_value[2] = -z
    assert center_brightness(scene, sun, "hdri_wrong_sign") < 0.2, "the opposite turn misses it"

    # FTC finds the sun on its own (thumbnail, brightest point), in memory...
    assert bpy.ops.ftc.fit_hdri() == {"FINISHED"}
    assert abs(mapping.inputs["Rotation"].default_value[2] - z) < math.radians(1.0)
    # ...and from a file larger than the thumbnail (reduced by Blender).
    path = os.path.join(SCRATCH, "big_hdri.exr")
    big = synthetic_hdri(u0, v0, size=(2400, 1200), radius_deg=0.6)
    big.filepath_raw, big.file_format = path, "OPEN_EXR"
    big.save()
    env.image = bpy.data.images.load(path)
    s.sun.hdri_fitted = False
    mapping.inputs["Rotation"].default_value[2] = 0.0
    assert bpy.ops.ftc.fit_hdri() == {"FINISHED"}
    assert abs(mapping.inputs["Rotation"].default_value[2] - z) < math.radians(1.0)
    # A second fit reuses the same Mapping node.
    assert sum(n.type == "MAPPING" for n in world.node_tree.nodes) == 1

    # The fitted HDRI follows the sun.
    s.sun.north_correction = math.radians(25.0)
    moved = ops_sun.evaluate(s).direction
    assert center_brightness(scene, moved, "hdri_follows") > 0.9


@test
def fit_hdri_inside_a_node_group():
    """HDRI add-ons wrap the World in a node group: the Mapping goes inside it."""
    from solver.hdri import image_point

    ops_sun = importlib.import_module(PKG + ".ops_sun")
    ops_hdri = importlib.import_module(PKG + ".ops_hdri")
    cam = _sun_camera(sun_tiff())
    scene = bpy.context.scene
    s = cam.data.ftc
    sun = ops_sun.evaluate(s).direction
    u0, v0 = 0.7, image_point(sun)[1]
    group = bpy.data.node_groups.new("HDRI Setup", "ShaderNodeTree")
    group.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    env = group.nodes.new("ShaderNodeTexEnvironment")
    env.image = synthetic_hdri(u0, v0)
    background = group.nodes.new("ShaderNodeBackground")
    out = group.nodes.new("NodeGroupOutput")
    group.links.new(env.outputs["Color"], background.inputs["Color"])
    group.links.new(background.outputs["Background"], out.inputs[0])
    world = bpy.data.worlds.new("grouped")
    if world.node_tree is None:
        world.use_nodes = True
    node = world.node_tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    world_out = next(n for n in world.node_tree.nodes if n.type == "OUTPUT_WORLD")
    world.node_tree.links.new(node.outputs[0], world_out.inputs["Surface"])
    scene.world = world
    found, problem = ops_hdri.environment(world)
    assert found == env and not problem, problem
    assert bpy.ops.ftc.fit_hdri(point=(u0, v0)) == {"FINISHED"}
    mapping = ops_hdri.mapping_of(env)
    assert mapping is not None and mapping.id_data == group
    assert center_brightness(scene, sun, "hdri_group") > 0.9


@test
def fit_hdri_needs_an_equirectangular_world():
    ops_hdri = importlib.import_module(PKG + ".ops_hdri")
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new("plain")
    assert ops_hdri.environment(scene.world)[0] is None
    with contextlib.redirect_stderr(None) if False else contextlib.nullcontext():
        try:
            result = bpy.ops.ftc.fit_hdri()
        except RuntimeError:
            result = {"CANCELLED"}
    assert result == {"CANCELLED"}
    _world, env = world_with(synthetic_hdri(0.3, 0.6, size=(64, 32)))
    env.projection = "MIRROR_BALL"
    node, problem = ops_hdri.environment(scene.world)
    assert node is None and "equirectangular" in problem
    env.projection = "EQUIRECTANGULAR"
    # A user's own Mapping (Texture type, with a location) is reused: only Z changes.
    tree = scene.world.node_tree
    mine = tree.nodes.new("ShaderNodeMapping")
    mine.vector_type = "TEXTURE"
    mine.inputs["Location"].default_value = (1.0, 2.0, 3.0)
    tree.links.new(mine.outputs["Vector"], env.inputs["Vector"])
    reroute = tree.nodes.new("NodeReroute")
    tree.links.new(mine.outputs["Vector"], reroute.inputs[0])
    tree.links.new(reroute.outputs[0], env.inputs["Vector"])
    assert bpy.ops.ftc.fit_hdri(point=(0.3, 0.6)) == {"FINISHED"}
    assert ops_hdri.mapping_of(env) == mine and tuple(mine.inputs["Location"].default_value) == (1.0, 2.0, 3.0)
    assert sum(n.type == "MAPPING" for n in tree.nodes) == 1, "found behind the reroute"
    assert s.sun.hdri_fitted

    # Turned by hand: FTC stops following; switched on again, it takes over.
    mine.inputs["Rotation"].default_value[2] += 0.5
    s.sun.north_correction = math.radians(5.0)
    assert not s.sun.hdri_fitted
    s.sun.hdri_fitted = True
    assert abs(ops_hdri.get_z(mine) - s.sun.hdri_angle) < 1e-5

    # A second Environment Texture with the same image (camera background) turns too.
    twin = tree.nodes.new("ShaderNodeTexEnvironment")
    twin.image = env.image
    assert bpy.ops.ftc.fit_hdri(point=(0.35, 0.6)) == {"FINISHED"}
    assert abs(ops_hdri.get_z(ops_hdri.mapping_of(twin)) - ops_hdri.get_z(mine)) < 1e-6

    # A rotation from nodes that cannot be followed back (a sine): refused, nothing changed.
    combine = tree.nodes.new("ShaderNodeCombineXYZ")
    sine = tree.nodes.new("ShaderNodeMath")
    sine.operation = "SINE"
    tree.links.new(sine.outputs[0], combine.inputs["Z"])
    tree.links.new(combine.outputs[0], mine.inputs["Rotation"])
    assert "cannot follow" in ops_hdri.vector_problem(env, scene.world)
    before = sine.inputs[0].default_value
    try:
        result = bpy.ops.ftc.fit_hdri(point=(0.5, 0.6))
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and sine.inputs[0].default_value == before
    # Keyframed: refused too.
    tree.links.remove(sine.outputs[0].links[0])
    assert not ops_hdri.vector_problem(env, scene.world)
    combine.inputs["Z"].keyframe_insert("default_value")
    assert "keyframed" in ops_hdri.vector_problem(env, scene.world)


@test
def fit_hdri_turns_a_group_rotation_input():
    """Poly Haven's World: the group's Rotation input (degrees) -> Multiply
    (to radians) -> Combine XYZ Z -> the Mapping's Rotation. FTC writes the
    group's input, within its limits."""
    from solver.hdri import image_point

    ops_sun = importlib.import_module(PKG + ".ops_sun")
    ops_hdri = importlib.import_module(PKG + ".ops_hdri")
    cam = _sun_camera(sun_tiff())
    scene = bpy.context.scene
    s = cam.data.ftc
    sun = ops_sun.evaluate(s).direction
    u0, v0 = 0.7, image_point(sun)[1]
    group = bpy.data.node_groups.new("Poly Haven HDRI", "ShaderNodeTree")
    rotation = group.interface.new_socket("Rotation", in_out="INPUT", socket_type="NodeSocketFloat")
    rotation.min_value, rotation.max_value = 0.0, 360.0
    group.interface.new_socket("Background", in_out="OUTPUT", socket_type="NodeSocketShader")
    nodes, links = group.nodes, group.links
    inputs, out = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")
    coords, mapping = nodes.new("ShaderNodeTexCoord"), nodes.new("ShaderNodeMapping")
    env, background = nodes.new("ShaderNodeTexEnvironment"), nodes.new("ShaderNodeBackground")
    multiply, combine = nodes.new("ShaderNodeMath"), nodes.new("ShaderNodeCombineXYZ")
    multiply.operation = "MULTIPLY"
    multiply.inputs[1].default_value = 0.0174533
    env.image = synthetic_hdri(u0, v0)
    links.new(inputs.outputs["Rotation"], multiply.inputs[0])
    links.new(multiply.outputs[0], combine.inputs["Z"])
    links.new(combine.outputs[0], mapping.inputs["Rotation"])
    links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs[0], out.inputs[0])
    world = bpy.data.worlds.new("poly haven")
    if world.node_tree is None:
        world.use_nodes = True
    node = world.node_tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    world_out = next(n for n in world.node_tree.nodes if n.type == "OUTPUT_WORLD")
    world.node_tree.links.new(node.outputs[0], world_out.inputs["Surface"])
    scene.world = world

    assert not ops_hdri.vector_problem(env, world)
    assert bpy.ops.ftc.fit_hdri(point=(u0, v0)) == {"FINISHED"}
    assert sum(n.type == "MAPPING" for n in nodes) == 1, "no Mapping added"
    degrees = node.inputs["Rotation"].default_value
    assert 0.0 <= degrees <= 360.0 and abs(degrees) > 1.0, degrees
    assert abs(ops_hdri._wrap(degrees * 0.0174533 - s.sun.hdri_angle)) < 1e-4
    assert center_brightness(scene, sun, "hdri_poly_haven") > 0.9

    # It follows the sun through the group input; turned by hand there, it stops.
    s.sun.north_correction = math.radians(25.0)
    moved = ops_sun.evaluate(s).direction
    assert node.inputs["Rotation"].default_value != degrees
    assert center_brightness(scene, moved, "hdri_poly_haven_follows") > 0.9
    node.inputs["Rotation"].default_value += 10.0
    s.sun.north_correction = math.radians(20.0)
    assert not s.sun.hdri_fitted

    # Limits too narrow for the angle: refused, the World as it was.
    rotation.min_value, rotation.max_value = 0.0, 1.0
    node.inputs["Rotation"].default_value = 0.5
    count = len(nodes)
    try:
        result = bpy.ops.ftc.fit_hdri(point=(u0, v0))
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and node.inputs["Rotation"].default_value == 0.5 and len(nodes) == count
    rotation.min_value, rotation.max_value = 0.0, 360.0

    # A muted Multiply passes its input through: not followed. A muted Mapping: refused.
    multiply.mute = True
    assert "cannot follow" in ops_hdri.vector_problem(env, world)
    multiply.mute = False
    mapping.mute = True
    assert "muted" in ops_hdri.vector_problem(env, world)
    mapping.mute = False
    # A keyframed constant: the fit would hold on one frame only.
    multiply.inputs[1].keyframe_insert("default_value")
    assert "keyframed" in ops_hdri.vector_problem(env, world)


@test
def extra_guide_lines():
    scene, cam, syn = _calibrated_camera((1920, 1080))
    s = cam.data.ftc
    assert s.vp1_lines == 2 and "vp1_3a" not in calibrate.active_handle_keys(s)
    assert bpy.ops.ftc.vp_line(index=1) == {"FINISHED"} and s.vp1_lines == 3
    keys = calibrate.active_handle_keys(s)
    assert "vp1_3a" in keys and "vp1_3b" in keys and "vp1_4a" not in keys
    a1, a2 = calibrate.handle(s, "vp1_1a"), calibrate.handle(s, "vp1_2a")
    middle = ((a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2)
    assert math.dist(calibrate.handle(s, "vp1_3a"), middle) < 1e-6, "between the first two lines"
    # On a real X edge the third line keeps the calibration exact.
    w, h = syn.image_size
    a, b = syn.segment((-2, 0, 1.5), (2, 0, 1.5))
    calibrate.set_handle(s, "vp1_3a", (float(a[0] / w), float(a[1] / h)))
    calibrate.set_handle(s, "vp1_3b", (float(b[0] / w), float(b[1] / h)))
    assert calibrate.update(bpy.context, cam, apply=True) is not None, s.results.error
    check_projection(scene, cam, syn)
    for _ in range(5):
        bpy.ops.ftc.vp_line(index=1)
    assert s.vp1_lines == calibrate.MAX_LINES
    for _ in range(6):
        bpy.ops.ftc.vp_line(index=1, remove=True)
    assert s.vp1_lines == 2 and "vp1_3a" not in calibrate.active_handle_keys(s)
    assert len(s.handles) == len(calibrate.HANDLE_DEFAULTS)

    # Line 2 drawn the other way and shorter: the new line still aims at the
    # meeting point of the first two.
    calibrate.set_handle(s, "vp2_2a", (0.15, 0.62))
    calibrate.set_handle(s, "vp2_2b", (0.40, 0.69))
    assert bpy.ops.ftc.vp_line(index=2) == {"FINISHED"}
    pts = [np.array([*calibrate.handle(s, k), 1.0]) for k in ("vp2_1a", "vp2_1b", "vp2_2a", "vp2_2b")]
    meet = np.cross(np.cross(pts[0], pts[1]), np.cross(pts[2], pts[3]))
    meet = meet[:2] / meet[2]
    a, b = (np.array(calibrate.handle(s, k)) for k in ("vp2_3a", "vp2_3b"))
    off = abs((b - a)[0] * (meet - a)[1] - (b - a)[1] * (meet - a)[0]) / np.linalg.norm(b - a)
    assert off < 1e-5, off

    # Session undo brings the number of lines back with the handles.
    ops = importlib.import_module(PKG + ".ops_modal")
    snap = ops.snapshot(s)
    bpy.ops.ftc.vp_line(index=2)
    assert s.vp2_lines == 4
    ops.restore(s, snap)
    assert s.vp2_lines == 3


@test
def export_report_json_and_markdown():
    import json

    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    # GPS in the EXIF but Fit Sun not used: the place is not written.
    path = os.path.join(SCRATCH, "private.md")  # .md asked, JSON chosen: report.json, not .md.json
    assert bpy.ops.ftc.export_report(filepath=path, format="JSON") == {"FINISHED"}
    with open(os.path.join(SCRATCH, "private.json"), encoding="utf-8") as f:
        assert "sun" not in json.load(f)
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    path = os.path.join(SCRATCH, "report.json")
    assert bpy.ops.ftc.export_report(filepath=path, format="JSON") == {"FINISHED"}
    with open(path, encoding="utf-8") as f:
        report = json.load(f)
    assert report["camera"] == cam.name and report["ftc_version"].startswith("1.1")
    assert report["camera_data"]["focal_35mm"] == {"value": 36.0, "source": "EXIF"}
    res = report["results"]
    assert res["valid"] and abs(res["focal_px"] - s.results.focal_px) < 1e-2
    assert res["location"] == [round(v, 6) for v in cam.matrix_world.translation] and res["applied_to_camera"]
    assert report["calibration"]["lines_per_vanishing_point"] == [2, 2]
    sun = report["sun"]
    assert abs(sun["azimuth_deg"] - SUN_AZIMUTH) < 0.05 and sun["light"] == s.sun.light.name
    assert sun["light_elevation_deg"] == sun["elevation_deg"] and sun["north_from"] == "COMPASS"
    assert sun["utc"].startswith("2026-06-21T10:30:00") and sun["latitude"]["source"] == "EXIF"

    cam.name = "cam|one"
    path = os.path.join(SCRATCH, "report")
    assert bpy.ops.ftc.export_report(filepath=path, format="MARKDOWN") == {"FINISHED"}
    with open(path + ".md", encoding="utf-8") as f:
        text = f.read()
    assert text.startswith("# FTC calibration report: cam\\|one") and "## Sun" in text and "| focal px |" in text

    # A failed calibration still gives a report, with the error.
    fresh_scene()
    cam = load(write_photo("plain_report.jpg", (800, 600)))
    calibrate.set_handle(cam.data.ftc, "vp1_1b", calibrate.handle(cam.data.ftc, "vp1_1a"))
    calibrate.refresh(cam.data)
    path = os.path.join(SCRATCH, "failed.json")
    assert bpy.ops.ftc.export_report(filepath=path, format="JSON") == {"FINISHED"}
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["results"]["valid"] is False


@test
def every_button_has_a_tooltip():
    """Operators and the settings drawn as buttons all carry a description."""
    internal = {"loading", "active_vp", "handles", "anchor_matrix", "camera_data", "results", "image", "rna_type"}
    internal |= {"sun"}
    internal |= {"name", "make", "model", "lens", "image_width", "image_height", "has_gps", "direction_ref"}
    internal |= {"gps_altitude"}
    missing = []
    for op in (
        "load_image",
        "use_camera",
        "upright_image",
        "calibrate",
        "apply",
        "reset",
        "align_cursor",
        "align_selection",
        "align_clear",
        "align_rotate",
        "align_flip",
        "flip_axis",
        "use_orientation",
        "prepare_render",
        "set_role",
        "new_sun",
        "read_photo_time",
        "fit_hdri",
        "vp_line",
        "export_report",
    ):
        description = getattr(bpy.ops.ftc, op).get_rna_type().description
        if not description.strip() or "\n" in description:
            missing.append("ftc." + op)  # (a line break would miss the translation)
    settings = bpy.data.cameras.new("tooltips").ftc
    for rna in (settings.bl_rna, settings.camera_data.bl_rna, settings.sun.bl_rna):
        for prop in rna.properties:
            if prop.identifier in internal or prop.identifier.endswith("_state"):
                continue
            if not prop.description.strip():
                missing.append(f"{rna.identifier}.{prop.identifier}")
    for prop in ("ftc_catcher", "ftc_holdout"):
        if not bpy.types.Object.bl_rna.properties[prop].description.strip():
            missing.append("Object." + prop)
    assert not missing, missing


@test
def third_audit_fixes():
    """1.1.1: upright copy of a 16-bit photo, Read from Photo, report privacy,
    Align to Scene checkbox, tilted alignment and the sun, session undo."""
    ops_modal = importlib.import_module(PKG + ".ops_modal")
    ops_sun = importlib.import_module(PKG + ".ops_sun")
    report = importlib.import_module(PKG + ".report")

    # A 16-bit photo turned upright keeps its brightness after save and reopen.
    scene = fresh_scene()
    img = bpy.data.images.new("flat16", 6, 4, float_buffer=True)
    px = np.zeros((4, 6, 4), np.float32)
    px[..., 3], px[..., :3] = 1.0, 0.2
    img.pixels.foreach_set(px.ravel())
    img.update()
    path = os.path.join(SCRATCH, "flat16.png")
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "16"
    img.save_render(path, scene=scene)
    bpy.data.images.remove(img)
    cam = load(path)
    s = cam.data.ftc
    s.camera_data.orientation = 3
    assert bpy.ops.ftc.upright_image() == {"FINISHED"}
    blend = os.path.join(SCRATCH, "upright16.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    bpy.ops.wm.open_mainfile(filepath=blend)
    image = bpy.context.scene.camera.data.ftc.image
    assert abs(image.pixels[0] - 0.2) < 0.01, image.pixels[0]

    # Make Upright Copy of a photo whose file is gone: a message, no traceback.
    fresh_scene()
    path = write_photo("gone.jpg", (40, 30))
    cam = load(path)
    s = cam.data.ftc
    s.camera_data.orientation = 6
    os.remove(path)
    s.image.reload()
    try:
        result = bpy.ops.ftc.upright_image()
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and s.image.name == "gone.jpg"

    # Read from Photo keeps a place typed by hand when the photo has none.
    fresh_scene()
    tiff = build_tiff(
        ifd0=[(exif.TAG_MAKE, ASCII, "NoGps")],
        exif_ifd=[
            (exif.TAG_DATETIME_ORIGINAL, ASCII, "2026:06:21 12:30:00"),
            (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, "+02:00"),
        ],
    )
    cam = load(write_photo("nogps.jpg", (800, 600), tiff))
    data = cam.data.ftc.camera_data
    assert data.location_state == "MISSING" and data.time_state == "EXIF"
    data.gps_latitude, data.gps_longitude = 45.46, 9.19
    data.hour = 9
    assert data.location_state == "MANUAL" and data.time_state == "MANUAL"
    assert bpy.ops.ftc.read_photo_time() == {"FINISHED"}
    assert data.hour == 12 and data.time_state == "EXIF"
    assert data.location_state == "MANUAL" and abs(data.gps_latitude - 45.46) < 1e-4

    # The report leaves out the place once the Fit Sun light is deleted
    # (the pointer still holds it, in no scene).
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    assert report.sun_report(s, bpy.context.scene) is not None
    light = s.sun.light
    for collection in light.users_collection:
        collection.objects.unlink(light)
    assert s.sun.light is not None and not s.sun.light.users_scene
    assert report.sun_report(s, bpy.context.scene) is None

    # A tilted alignment tilts the sky with it: the date's sun keeps its height
    # above the photo's ground (the plane's normal in the scene).
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    assert bpy.ops.ftc.new_sun() == {"FINISHED"}
    for north in ("COMPASS", "SIDE"):
        s.sun.north_source = north
        s.use_anchor = False
        level = light_dir(s.sun.light).copy()
        tilt = Matrix.Rotation(math.radians(20.0), 4, "X")
        s.anchor_matrix = tilt
        s.use_anchor = True
        tilted = light_dir(s.sun.light)
        assert math.degrees(tilted.angle(tilt.to_3x3() @ level)) < 0.05, north
    # The Align to Scene checkbox moves the camera at once, like Rotate 90°.
    s.sun.north_source = "COMPASS"
    before = cam.matrix_world.copy()
    s.use_anchor = False
    assert (cam.matrix_world.translation - before.translation).length > 1e-3
    s.use_anchor = True
    assert (cam.matrix_world.translation - before.translation).length < 1e-6

    # The session's undo brings back the settings changed in the panel too.
    snap = ops_modal.snapshot(s)
    s.vp_count = "3"
    s.cube_size = "5"
    calibrate.set_handle(s, "vp1_1a", (0.1, 0.1))
    ops_modal.restore(s, snap)
    assert s.vp_count == "2" and s.cube_size != "5" and ops_modal.snapshot(s) == snap

    assert ops_sun.scene_y_bearing(s, ops_sun.evaluate(s)) is not None


@test
def fit_hdri_edge_cases():
    """1.1.1: a Mapping with a Location warns, other Texture Coordinate outputs
    and muted links are not taken for the world direction, a fake user does
    not make a group "shared", a vanished file gives a message."""
    ops_hdri = importlib.import_module(PKG + ".ops_hdri")
    cam = _sun_camera(sun_tiff())
    s = cam.data.ftc
    scene = bpy.context.scene
    world, env = world_with(synthetic_hdri(0.3, 0.6, size=(64, 32)))
    tree = world.node_tree

    mapping = tree.nodes.new("ShaderNodeMapping")
    tree.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    assert ops_hdri.fit(s, scene, (0.3, 0.6))[2] == ""
    mapping.inputs["Location"].default_value = (0.0, 0.0, 1.0)
    assert ops_hdri.fit(s, scene, (0.3, 0.6))[2] == ops_hdri.TILTED
    mapping.vector_type = "VECTOR"  # (no location for directions)
    assert ops_hdri.fit(s, scene, (0.3, 0.6))[2] == ""

    coords = tree.nodes.new("ShaderNodeTexCoord")
    tree.nodes.remove(mapping)
    tree.links.new(coords.outputs["Object"], env.inputs["Vector"])
    assert ops_hdri.vector_problem(env) == ops_hdri.COORDINATES
    tree.links.new(coords.outputs["Generated"], env.inputs["Vector"])
    assert ops_hdri.vector_problem(env) == ""

    # A muted link from an old Mapping: the new Mapping starts from Generated.
    old = tree.nodes.new("ShaderNodeMapping")
    old.inputs["Rotation"].default_value[2] = 1.0
    link = tree.links.new(old.outputs["Vector"], env.inputs["Vector"])
    link.is_muted = True
    fitted = ops_hdri.ensure_mapping(tree, env)
    assert fitted != old and not old.outputs["Vector"].links
    source = fitted.inputs["Vector"].links[0].from_socket
    assert source.node.type == "TEX_COORD" and source.identifier == "Generated"

    # A group with a fake user, used once, is not "shared".
    group = bpy.data.node_groups.new("one use", "ShaderNodeTree")
    group.use_fake_user = True
    assert ops_hdri.real_users(group) == 0

    # The HDRI file vanished while its pixels are in memory.
    big = bpy.data.images.new("big", 2400, 1200, float_buffer=True)
    path = os.path.join(SCRATCH, "big.exr")
    big.filepath_raw = path
    big.file_format = "OPEN_EXR"
    big.save()
    bpy.data.images.remove(big)
    big = bpy.data.images.load(path)
    assert tuple(big.size) == (2400, 1200)
    os.remove(path)
    try:
        ops_hdri.thumbnail(big)
    except ValueError as exc:
        assert "file" in str(exc)
    else:
        raise AssertionError("no error for a vanished HDRI file")


# The same in Italian: names, units, axes.
SAME_IN_ITALIAN = {"FTC", "Fit The Camera", "Fit Sun", "Fit HDRI", "GPS", "UTC", "Render", "Camera", "Catcher"}
SAME_IN_ITALIAN |= {
    "Camera: {}",
    "max {:.2f}°",
    "XY",
    "XZ",
    "YZ",
    "10 cm",
    "20 cm",
    "50 cm",
    "1 m",
    "2 m",
    "5 m",
    "10 m",
}
SAME_IN_ITALIAN |= {s + a for s in ("", "+", "-") for a in "XYZ"}
TRANSLATORS = ("iface_", "tip_", "rpt_", "pgettext_iface", "pgettext_tip", "pgettext_rpt", "message")


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _literal(node.left), _literal(node.right)
        if a is not None and b is not None:
            return a + b
    return None


def _source_strings():
    """(where, kind, context, text) of the messages written in the source: the
    translated calls, reports, labels, solver errors, warnings and message
    constants. Kind "fstring": a formatted message no translation can match."""
    folder = os.path.join(ROOT, "fit_the_camera")
    paths = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".py")]
    paths += [os.path.join(folder, "solver", f) for f in sorted(os.listdir(os.path.join(folder, "solver")))]
    found = []

    def add(where, node, kind, value, ctxt="*"):
        text = _literal(value)
        if text is not None:
            found.append((f"{where}:{node.lineno}", kind, ctxt, text))
        elif isinstance(value, ast.JoinedStr):
            found.append((f"{where}:{node.lineno}", "fstring", ctxt, ast.unparse(value)))

    for path in paths:
        if not path.endswith(".py") or path.endswith("translations.py"):
            continue
        where = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                kw = {k.arg: k.value for k in node.keywords}
                if name in TRANSLATORS and node.args:
                    ctxt = _literal(node.args[1]) if len(node.args) > 1 else None
                    add(where, node, "tip" if "tip" in name else "iface", node.args[0], ctxt or "*")
                elif name == "report" and len(node.args) > 1:
                    add(where, node, "report", node.args[1])
                elif (name == "SolverError" or name == "ValueError" and "ops_" in path) and node.args:
                    add(where, node, "message", node.args[0])  # (other ValueErrors: parsing, never shown)
                elif name in ("append", "insert") and "warning" in ast.unparse(fn) and node.args:
                    add(where, node, "message", node.args[-1])
                elif name == "format" and isinstance(fn, ast.Attribute):
                    text = _literal(fn.value)
                    if text is not None and "{" in text:
                        found.append((f"{where}:{node.lineno}", "message", "*", text))
                translate = kw.get("translate")
                if "text" in kw and not (isinstance(translate, ast.Constant) and translate.value is False):
                    add(where, node, "iface", kw["text"], _literal(kw["text_ctxt"]) if "text_ctxt" in kw else "*")
                if "heading" in kw:
                    add(where, node, "iface", kw["heading"])
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Attribute) and target.attr in ("error", "shadow_error"):
                    add(where, node, "message", node.value)
                if isinstance(target, ast.Name) and target.id.isupper():
                    for value in node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]:
                        text = _literal(value)
                        if text is not None and len(text.split()) > 3:
                            found.append((f"{where}:{node.lineno}", "message", "*", text))
    return found


def _rna_strings():
    """(where, kind, context, text) of the registered names, tooltips and enum items."""
    found = []
    inherited = {
        p.identifier
        for base in (bpy.types.Operator, bpy.types.Panel, bpy.types.UIList, bpy.types.PropertyGroup)
        for p in base.bl_rna.properties
    }

    def props(owner, rna):
        for prop in rna.properties:
            if prop.identifier in inherited or prop.name == prop.identifier:
                continue  # unnamed: internal, never drawn
            ctxt = prop.translation_context or "*"
            where = f"{owner}.{prop.identifier}"
            found.append((where, "iface", ctxt, prop.name))
            if prop.description:
                found.append((where, "tip", "*", prop.description))
            if prop.type == "ENUM":
                for item in prop.enum_items:
                    found.append((f"{where}:{item.identifier}", "iface", ctxt, item.name))
                    if item.description:
                        found.append((f"{where}:{item.identifier}", "tip", "*", item.description))

    for name in dir(bpy.types):
        if not name.startswith("FTC_"):
            continue
        cls = getattr(bpy.types, name)
        if "_OT_" in name or "_PT_" in name:
            ctxt = getattr(cls, "bl_translation_context", None) or ("Operator" if "_OT_" in name else "*")
            found.append((name, "iface", ctxt, cls.bl_label))
            if "_OT_" in name:
                found.append((name, "tip", "*", cls.bl_rna.description))
        props(name, cls.bl_rna)
    # Property groups are not in bpy.types: walked from the Camera's pointer.
    seen = set()

    def walk(struct):
        if struct.identifier not in seen:
            seen.add(struct.identifier)
            props(struct.identifier, struct)
            for prop in struct.properties:
                if prop.type in {"POINTER", "COLLECTION"} and prop.fixed_type.identifier.startswith("FTC_"):
                    walk(prop.fixed_type)

    walk(bpy.types.Camera.bl_rna.properties["ftc"].fixed_type)
    for owner in (bpy.types.Object, bpy.types.Scene):
        props(
            owner.__name__,
            SimpleNamespace(properties=[p for p in owner.bl_rna.properties if p.identifier.startswith("ftc")]),
        )
    return found


@test
def every_string_is_translated():
    """Every name, tooltip, enum item, label, report and message of the
    interface has its Italian translation (formatted messages are templates:
    ``translations.message``)."""
    view = bpy.context.preferences.view
    previous = (view.language, view.use_translate_interface, view.use_translate_tooltips, view.use_translate_reports)
    view.language = "it_IT"
    view.use_translate_interface = view.use_translate_tooltips = view.use_translate_reports = True
    try:
        from bpy.app.translations import pgettext_iface, pgettext_tip

        missing, formatted = set(), []
        for where, kind, ctxt, text in _rna_strings() + _source_strings():
            if kind == "fstring":
                formatted.append(f"{where}: {text}")
                continue
            if not any(c.isalpha() for c in text) or text in SAME_IN_ITALIAN:
                continue
            if kind == "iface":
                done = pgettext_iface(text, ctxt) if ctxt != "*" else pgettext_iface(text)
            else:
                done = pgettext_tip(text)
            if done == text:
                missing.add(f"{where} [{ctxt}] {text!r}")
        message = importlib.import_module(PKG + ".translations").message
        assert message(
            "unstable calibration (focal ±12%, angles ±3.4°): use longer guides further apart, add a "
            "third axis line or a third vanishing point, or use the known focal length"
        ).startswith("calibrazione instabile (focale ±12%, angoli ±3.4°)")
        assert message("Camera not updated: the rectangle needs four corners") == (
            "Camera non aggiornata: il rettangolo richiede quattro angoli"
        )
        assert message("Plane (face)") == "Plane (faccia)"  # a name stays
    finally:
        view.language = previous[0]
        view.use_translate_interface, view.use_translate_tooltips, view.use_translate_reports = previous[1:]
    assert not formatted, "formatted messages cannot be translated: use a template\n" + "\n".join(formatted)
    assert not missing, "no Italian translation:\n" + "\n".join(sorted(missing))


def _animatable_ftc_props():
    found, seen = [], set()

    def walk(struct):
        if struct.identifier in seen:
            return
        seen.add(struct.identifier)
        for prop in struct.properties:
            if prop.identifier == "rna_type":
                continue
            if prop.is_animatable:
                found.append(f"{struct.identifier}.{prop.identifier}")
            if prop.type in {"POINTER", "COLLECTION"} and prop.fixed_type.identifier.startswith("FTC_"):
                walk(prop.fixed_type)

    walk(bpy.types.Camera.bl_rna.properties["ftc"].fixed_type)
    for owner in (bpy.types.Camera, bpy.types.Object, bpy.types.Scene):
        found += [
            f"{owner.__name__}.{p.identifier}"
            for p in owner.bl_rna.properties
            if p.identifier.startswith("ftc") and p.is_animatable
        ]
    return found


@test
def settings_cannot_be_keyframed():
    """I over a panel field must not key FTC settings: the keys would put the
    calibration back at every frame change."""
    fresh_scene()
    cam = bpy.data.cameras.new("Cam")
    assert not _animatable_ftc_props(), _animatable_ftc_props()
    for path in ("ftc.vp_count", "ftc.camera_data.focal_mm", "ftc.sun.north_correction"):
        with contextlib.suppress(TypeError, RuntimeError):
            cam.keyframe_insert(path)
    assert cam.animation_data is None or not cam.animation_data.action, "a key was inserted"
    assert cam.keyframe_insert("lens"), "the camera's own lens stays animatable"


@test
def disable_and_enable():
    bpy.ops.preferences.addon_disable(module=PKG)
    assert not hasattr(bpy.types.Camera, "ftc")
    bpy.ops.preferences.addon_enable(module=PKG)
    assert hasattr(bpy.types.Camera, "ftc")
    assert not _animatable_ftc_props(), "re-registered properties are animatable again"


def main():
    failures = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures} passed, {failures} failed")
    if failures:
        sys.exit(1)


main()
