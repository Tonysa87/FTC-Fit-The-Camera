# SPDX-License-Identifier: GPL-3.0-or-later
"""In-Blender tests, run headless by scripts/blender_tests.sh.

Usage: blender --background --python tests_blender/test_addon.py -- <project root> <scratch dir>
"""

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
    d = syn.rotation.T @ {"X": np.array([1.0, 0, 0]), "Y": np.array([0, 1.0, 0])}[axis]
    return ("+" if d[2] < 0 else "-") + axis


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
    s.rect_use_focal = True
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
        s.mode, s.vp_count, s.vp1_axis, s.vp2_axis = "VP", "2", "+X", "-Z"
        place(1, "wall_door_bottom", "wall_threshold")
        place(2, "vertical_left_jamb", "vertical_right_jamb")
    calibrate.refresh(cam.data)
    assert s.results.valid, s.results.error
    assert s.results.focal_error > 0.05, s.results.focal_error
    assert "unstable" in s.results.warnings

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

    s.straighten = True
    assert math.degrees(abs(s.results.removed_roll)) > 1.0
    assert "straighten" in s.results.warnings


@test
def live_writes_only_in_session_or_apply():
    fresh_scene()
    cam = load(write_photo("live.jpg", (1200, 800)))
    before = cam.matrix_world.copy()
    cam.data.ftc.camera_distance = 25.0  # no session: results only
    assert cam.matrix_world == before
    assert bpy.ops.ftc.apply() == {"FINISHED"}
    assert cam.matrix_world != before
    assert abs(cam.matrix_world.translation.length - 25.0) < 1e-3


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
def upright_copy_swaps_dimensions():
    scene = fresh_scene()
    cam = load(write_photo("rotated.jpg", (40, 20), camera_tiff(orientation=6)))
    s = cam.data.ftc
    assert s.camera_data.orientation == 6
    assert bpy.ops.ftc.upright_image() == {"FINISHED"}
    assert s.image.size[:] == (20, 40)
    assert s.image.packed_file is not None
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
        {"mode": "VP", "vp_count": "3", "scale_mode": "DISTANCE", "freeze": True},
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
        "move_along_view",
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
