"""Overlay with the north arrow, the sun direction, the landmark handle and a shadow.

Writes dist/probes/sun_map.png (north from a map), sun_landmark.png and
sun_shadow.png (shadow handles, the cross = the tip for the date's sun).
"""

import importlib
import math
import os
import sys
from types import SimpleNamespace

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "probe"}
exec(compile(src, "test_addon", "exec"), g)
import bpy  # noqa: E402
import gpu  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix  # noqa: E402

gpu.init()
draw = importlib.import_module(g["PKG"] + ".draw")
ops_sun = importlib.import_module(g["PKG"] + ".ops_sun")
calibrate = g["calibrate"]
cam = g["_sun_camera"](g["sun_tiff"]())
s = cam.data.ftc
W, H = 1200, 700
view = draw.View(20.0, 20.0, 1180.0, 20.0 + 1160 * 1080 / 1920, (1920, 1080))
session = SimpleNamespace(active_vp=0, hover=None, drag_key=None)
from solver.sun import direction_enu  # noqa: E402

for name, source in (("sun_map", "MAP"), ("sun_landmark", "LANDMARK"), ("sun_shadow", "MAP")):
    s.sun.north_source = source
    s.sun.use_shadow = name == "sun_shadow"
    if s.sun.use_shadow:
        calibrate.refresh(cam.data)
        # Shadow of the sun 8° off the date's: the cross shows where it should be.
        g["set_shadow"](s, direction_enu(g["SUN_AZIMUTH"] + 8.0, g["SUN_ELEVATION"]), (0.0, 1.0, 0.0), 4.0)
    s.sun.map_axis, s.sun.map_bearing = "+X", math.radians(90.0)
    s.sun.landmark_bearing = math.radians(200.0)
    calibrate.set_handle(s, "landmark", (0.7, 0.62))
    sol = calibrate.refresh(cam.data)
    state = ops_sun.evaluate(s, sol)
    print(name, "error:", state.error or "-", "y bearing:", state.y_bearing)
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
