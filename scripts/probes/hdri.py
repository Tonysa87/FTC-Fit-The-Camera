"""The Fit HDRI viewer drawn offscreen over a synthetic sky.

Writes dist/probes/hdri_viewer.png: thumbnail, horizon, proposal ring, pick
ring with its elevation, and the cross where the photo's sun lands.
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
ops_hdri = importlib.import_module(g["PKG"] + ".ops_hdri")
from solver.hdri import brightest_point, luminance  # noqa: E402

image = g["synthetic_hdri"](0.31, 0.62, size=(1024, 512), radius_deg=1.5)
rgb = ops_hdri.thumbnail(image)
# A sky gradient under the sun, to see the tone mapping.
rows = np.linspace(0.0, 1.0, rgb.shape[0])[:, None, None]
rgb = np.maximum(rgb, 0.05 + 0.6 * rows * np.array([0.5, 0.7, 1.0]))
proposal = brightest_point(luminance(rgb))
W, H = 1200, 700
fake = SimpleNamespace(as_pointer=lambda: 1, width=W, height=H)
viewer = ops_hdri.Viewer(fake, fake, rgb, proposal, sun_elevation=35.0)
viewer.pick = (proposal[0] + 0.01, proposal[1])
print("proposal", proposal)
off = gpu.types.GPUOffScreen(W, H)
with off.bind():
    fb = gpu.state.active_framebuffer_get()
    fb.clear(color=(0.12, 0.12, 0.12, 1.0))
    with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
        gpu.matrix.load_identity()
        gpu.matrix.load_projection_matrix(Matrix(((2 / W, 0, 0, -1), (0, 2 / H, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1))))
        ops_hdri.paint(viewer, fake)
    px = np.asarray(fb.read_color(0, 0, W, H, 4, 0, "FLOAT").to_list(), dtype=np.float32)
off.free()
img = bpy.data.images.new("hdri_viewer", W, H)
img.pixels.foreach_set(px.ravel())
img.filepath_raw = os.path.join(OUT, "hdri_viewer.png")
img.file_format = "PNG"
img.save()
print("elevation of the pick", (viewer.pick[1] - 0.5) * 180.0, "computed sun", 35.0, math.pi)
