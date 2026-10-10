"""Render a CG cube over a calibrated photo through Prepare Render (render.png)."""

import os
import sys

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "render_probe"}
exec(compile(src, "test_addon", "exec"), g)
import bpy  # noqa: E402
import numpy as np  # noqa: E402

scene, cam, syn = g["_calibrated_camera"]((640, 480))
# A gradient photo instead of the flat grey one, to see the background.
img = cam.data.ftc.image
yy, xx = np.mgrid[0:480, 0:640]
px = np.ones((480, 640, 4), np.float32)
px[..., 0], px[..., 1], px[..., 2] = xx / 640, yy / 480, 0.6
img.pixels.foreach_set(px.ravel())
img.update()
img.pack()

size = cam.data.ftc.results.distance / 6
bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, size / 2))
bpy.ops.object.light_add(type="SUN", rotation=(0.6, 0.4, 0.0))
bpy.context.active_object.data.energy = 4.0
bpy.ops.mesh.primitive_plane_add(size=cam.data.ftc.results.distance * 10)
bpy.context.active_object.ftc_catcher = True
bpy.ops.ftc.prepare_render(output="PHOTO", use_cycles=True)
scene.cycles.samples = 32
scene.cycles.use_denoising = False
for output in ("PHOTO", "ALPHA"):
    bpy.ops.ftc.prepare_render(output=output, use_cycles=True)
    scene.render.filepath = os.path.join(OUT, f"render_{output.lower()}")
    bpy.ops.render.render(write_still=True)
    print("wrote", scene.render.filepath)
