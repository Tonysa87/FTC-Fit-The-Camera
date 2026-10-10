# SPDX-License-Identifier: GPL-3.0-or-later
"""In-Blender tests, run headless by scripts/blender_tests.sh.

Usage: blender --background --python tests_blender/test_addon.py -- <project root> <scratch dir>
"""

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
    assert abs(cam.data.lens - 35.0) < 0.05  # 36 mm sensor fallback: 35 mm equivalent


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
def live_writes_only_in_session_or_apply():
    fresh_scene()
    cam = load(write_photo("live.jpg", (1200, 800)))
    s = cam.data.ftc
    assert s.scale_mode == "CUBE" and s.cube_size == "1"
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

    # Elsewhere the cube is only a visual check: its base moves, nothing scales.
    s.mode = "RECT"
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

    def changed(ctx, camera, reset_pitch=True):
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
def move_along_view_keeps_image_position():
    scene, cam, syn = _calibrated_camera((1920, 1080))
    mesh = bpy.data.meshes.new("cube")
    obj = bpy.data.objects.new("cube", mesh)
    scene.collection.objects.link(obj)
    obj.location = (1.0, 2.0, 0.5)
    bpy.context.view_layer.update()
    for o in scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    before = world_to_camera_view(scene, cam, obj.matrix_world.translation)
    c = cam.matrix_world.translation
    expected = c + (obj.matrix_world.translation - c) * 2.0
    assert bpy.ops.ftc.move_along_view(factor=2.0, scale_objects=True) == {"FINISHED"}
    bpy.context.view_layer.update()
    assert (obj.matrix_world.translation - expected).length < 1e-5
    assert abs(obj.scale.x - 2.0) < 1e-6
    after = world_to_camera_view(scene, cam, obj.matrix_world.translation)
    assert (after.to_2d() - before.to_2d()).length < 1e-6


@test
def move_along_view_edit_mode_vertices():
    scene, cam, syn = _calibrated_camera((1920, 1080))
    mesh = bpy.data.meshes.new("plane")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("plane", mesh)
    scene.collection.objects.link(obj)
    obj.location = (-1.0, 1.0, 0.0)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    assert bpy.ops.ftc.move_along_view(factor=0.5) == {"FINISHED"}
    bpy.ops.object.mode_set(mode="OBJECT")
    c = cam.matrix_world.translation
    for v, orig in zip(mesh.vertices, [(0, 0, 0), (1, 0, 0), (1, 1, 0)]):
        world = obj.matrix_world @ v.co
        expected = c + (obj.matrix_world @ Vector(orig) - c) * 0.5
        assert (world - expected).length < 1e-5


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
def ray_gizmo_moves_along_the_camera_rays():
    mv = importlib.import_module(PKG + ".ops_move_view")
    scene, cam, syn = _calibrated_camera((1920, 1080))
    assert all("bl_rna" in cls.__dict__ for cls in (mv.FTC_GGT_move_along_rays, mv.FTC_GT_ray_handle))
    c = cam.matrix_world.translation
    centre = Vector((0.7, 1.3, 0.4))
    right = cam.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))
    frame = mv.ray_frame(centre, c, right)
    r = frame.to_3x3()
    assert abs(r.determinant() - 1.0) < 1e-6 and (frame.translation - centre).length < 1e-9
    assert (r.col[2] - (c - centre).normalized()).length < 1e-9, "z towards the camera"
    assert r.col[0].dot(right) > 0.99
    # The arrow is seen end-on: any point on it stays on the selection's pixel.
    p0 = world_to_camera_view(scene, cam, centre).to_2d()
    for t in (-3.0, 0.5, 1.5):
        assert (world_to_camera_view(scene, cam, centre + r.col[2] * t).to_2d() - p0).length < 1e-6
    assert mv.ray_frame(c, c, right) is None
    assert len(mv.gizmo_shape()) % 3 == 0 and len(mv.gizmo_shape(1.0)) == len(mv.gizmo_shape())

    # The handle sits on what the operator moves: the median of the selection.
    objs = []
    for i, loc in enumerate([(1, 0, 0), (0, 2, 0), (0, 0, 3)]):
        obj = bpy.data.objects.new(f"o{i}", None)
        scene.collection.objects.link(obj)
        obj.location = loc
        objs.append(obj)
    objs[2].parent = objs[0]  # moves with its parent: not counted twice
    bpy.context.view_layer.update()
    for o in scene.objects:
        o.select_set(o in objs)
    cam.select_set(True)
    got = mv.selection_centre(bpy.context, cam)
    assert (got - Vector((0.5, 1.0, 0.0))).length < 1e-6, got

    mesh = bpy.data.meshes.new("tri")
    mesh.from_pydata([(0, 0, 0), (2, 0, 0), (0, 2, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("tri", mesh)
    scene.collection.objects.link(obj)
    obj.location = (1.0, 1.0, 1.0)
    for o in scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    assert mv.selection_centre(bpy.context, cam) is None
    bpy.ops.mesh.select_all(action="SELECT")
    got = mv.selection_centre(bpy.context, cam)
    assert (got - Vector((1.0 + 2 / 3, 1.0 + 2 / 3, 1.0))).length < 1e-6, got
    bpy.ops.object.mode_set(mode="OBJECT")
    # Gizmo hidden outside the camera view, with the toggle off, during a session.
    assert not mv.gizmo_wanted(bpy.context)
    rna = bpy.ops.ftc.move_along_view.get_rna_type()
    assert rna.properties["release_confirm"].is_skip_save and rna.properties["scale_objects"].is_skip_save


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
    load(write_photo("second_photo.jpg", (80, 60)))
    assert tree.nodes[ops_render.PHOTO_NODE].image == s.image and s.image.name.startswith("second_photo")

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


@test
def every_button_has_a_tooltip():
    """Operators and the settings drawn as buttons all carry a description."""
    internal = {"loading", "active_vp", "handles", "anchor_matrix", "camera_data", "results", "image", "rna_type"}
    internal |= {"name", "make", "model", "lens", "image_width", "image_height", "has_gps", "direction_ref"}
    internal |= {p for p in ("gps_latitude", "gps_longitude", "gps_altitude")}
    missing = []
    for op in (
        "load_image",
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
        "move_along_view",
        "use_orientation",
        "prepare_render",
        "set_role",
    ):
        if not getattr(bpy.ops.ftc, op).get_rna_type().description.strip():
            missing.append("ftc." + op)
    settings = bpy.data.cameras.new("tooltips").ftc
    for rna in (settings.bl_rna, settings.camera_data.bl_rna):
        for prop in rna.properties:
            if prop.identifier in internal or prop.identifier.endswith("_state"):
                continue
            if not prop.description.strip():
                missing.append(f"{rna.identifier}.{prop.identifier}")
    for prop in ("ftc_catcher", "ftc_holdout"):
        if not bpy.types.Object.bl_rna.properties[prop].description.strip():
            missing.append("Object." + prop)
    for prop in ("ftc_ray_gizmo", "ftc_ray_scale"):
        if not bpy.types.Scene.bl_rna.properties[prop].description.strip():
            missing.append("Scene." + prop)
    assert not missing, missing


@test
def disable_and_enable():
    bpy.ops.preferences.addon_disable(module=PKG)
    assert not hasattr(bpy.types.Camera, "ftc")
    bpy.ops.preferences.addon_enable(module=PKG)
    assert hasattr(bpy.types.Camera, "ftc")


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
