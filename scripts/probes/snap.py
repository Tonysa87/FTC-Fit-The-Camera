import importlib
import os
import sys
from types import SimpleNamespace

ROOT, OUT = sys.argv[-2:]
sys.argv = sys.argv[:-2] + [ROOT, OUT]
# reuse the test helpers without running main()
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "snap"}
exec(compile(src, "test_addon", "exec"), g)
import bpy
import gpu
import numpy as np
from mathutils import Matrix

gpu.init()
draw = importlib.import_module(g["PKG"] + ".draw")
calibrate = g["calibrate"]
_, cam, syn = g["_calibrated_camera"]((1920, 1080))
s = cam.data.ftc
w, h = syn.image_size
calibrate.set_handle(s, "cube_base", tuple(syn.project([1.0, 0.5, 0.0])[0] / (w, h)))
calibrate.set_handle(s, "cube_top", tuple(syn.project([1.0, 0.5, 1.0])[0] / (w, h)))
calibrate.set_handle(s, "vp3_1a", tuple(syn.project([2, -2, 3])[0] / (w, h)))
calibrate.set_handle(s, "vp3_1b", tuple(syn.project([2, -2, 0])[0] / (w, h)))
s.scale_mode, s.use_third_line = "CUBE", True
s.vp1_lines = 4  # extra guides (1.1), at their default places between lines 1 and 2
W, H = 1200, 700
view = draw.View(20.0, 20.0, 1180.0, 20.0 + 1160 * 1080 / 1920, (1920, 1080))
session = SimpleNamespace(active_vp=0, hover=None, drag_key=None)
for name, cfg in (("vp", {}), ("rect", {"mode": "RECT"})):
    for k, v in cfg.items():
        setattr(s, k, v)
    sol = calibrate.refresh(cam.data)
    print(name, s.results.error, s.results.warnings)
    off = gpu.types.GPUOffScreen(W, H)
    with off.bind():
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.12, 0.12, 0.12, 1.0))
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(
                Matrix(((2 / W, 0, 0, -1), (0, 2 / H, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1)))
            )
            draw.draw_guides(view, s, sol, session, "METRIC")
        px = np.asarray(fb.read_color(0, 0, W, H, 4, 0, "FLOAT").to_list(), dtype=np.float32)
    off.free()
    img = bpy.data.images.new(name, W, H)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, name + ".png")
    img.file_format = "PNG"
    img.save()
