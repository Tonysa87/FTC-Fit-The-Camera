"""Magnifier snapshot: the calibrated elevator photo (or a synthetic one) with the
lens open on a guide handle. Writes lens.png into the output dir."""

import importlib
import json
import os
import sys
from types import SimpleNamespace

ROOT, OUT = sys.argv[-2:]
sys.argv = sys.argv[:-2] + [ROOT, OUT]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "lens"}
exec(compile(src, "test_addon", "exec"), g)
import bpy  # noqa: E402
import gpu  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix  # noqa: E402

gpu.init()
draw = importlib.import_module(g["PKG"] + ".draw")
calibrate = g["calibrate"]
photo_path = os.path.join(ROOT, "samples", "elevator.jpg")
lines_path = os.path.join(ROOT, "tests", "data", "elevator_lines.json")
if os.path.exists(photo_path):
    g["fresh_scene"]()
    cam = g["load"](photo_path)
    s = cam.data.ftc
    if s.camera_data.orientation > 1:
        bpy.ops.ftc.upright_image()
        cam = bpy.context.scene.camera
        s = cam.data.ftc
    size = calibrate.image_size(s)
    lines = json.load(open(lines_path))["lines"]
    w, h = size

    def put(key, p):
        calibrate.set_handle(s, key, (p[0] / w, p[1] / h))

    for key, name in (("vp1_1", "wall_door_bottom"), ("vp1_2", "wall_right_skirting")):
        put(key + "a", lines[name][0])
        put(key + "b", lines[name][1])
    for key, name in (("vp2_1", "vertical_left_jamb"), ("vp2_2", "vertical_right_jamb")):
        put(key + "a", lines[name][0])
        put(key + "b", lines[name][1])
    s.vp1_axis, s.vp2_axis = "+X", "+Z"
else:
    _, cam, _ = g["_calibrated_camera"]((1920, 1080))
    s = cam.data.ftc
    size = calibrate.image_size(s)
sol = calibrate.refresh(cam.data)
print("solve:", s.results.error or "ok")
W, H = 1000, 1000
scale = 940 / max(size)
fw, fh = size[0] * scale, size[1] * scale
view = draw.View((W - fw) / 2, (H - fh) / 2, (W + fw) / 2, (H + fh) / 2, size)
session = SimpleNamespace(active_vp=0, hover=None, drag_key="vp1_1a", magnify=True)
off = gpu.types.GPUOffScreen(W, H)
with off.bind():
    fb = gpu.state.active_framebuffer_get()
    fb.clear(color=(0.22, 0.22, 0.22, 1.0))
    with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
        gpu.matrix.load_identity()
        gpu.matrix.load_projection_matrix(Matrix(((2 / W, 0, 0, -1), (0, 2 / H, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1))))
        gpu.state.blend_set("ALPHA")
        draw._photo(view, s.image)
        draw.draw_guides(view, s, sol, session, "METRIC")
        before = np.asarray(fb.read_color(0, 0, W, H, 4, 0, "UBYTE").to_list(), dtype=np.uint8)
        draw.draw_lens(view, s, sol, session, "METRIC")
    pixels = np.asarray(fb.read_color(0, 0, W, H, 4, 0, "UBYTE").to_list(), dtype=np.uint8)
off.free()
print("pixels changed by the lens:", int((before != pixels).any(axis=2).sum()))
lens = draw._lens_buffer.get("texture")
if lens is not None:
    data = np.asarray(lens.read().to_list(), dtype=float)
    print("lens buffer mean", data.reshape(-1, 4).mean(axis=0))
img = bpy.data.images.new("lens_snap", W, H, alpha=True)
img.pixels.foreach_set((pixels.astype(np.float32) / 255.0).ravel())
img.update()
img.filepath_raw = os.path.join(OUT, "lens.png")
img.file_format = "PNG"
img.save()
print("saved", img.filepath_raw)
