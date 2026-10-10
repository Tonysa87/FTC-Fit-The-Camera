import importlib
import itertools
import os
import sys
from types import SimpleNamespace

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "snap"}
exec(compile(src, "test_addon", "exec"), g)
import gpu
from mathutils import Matrix

gpu.init()
PKG = g["PKG"]
calibrate = g["calibrate"]
draw = importlib.import_module(PKG + ".draw")
_, cam, syn = g["_calibrated_camera"]((1920, 1080))
s = cam.data.ftc
s.camera_data.focal_35mm = 35.0
view = draw.View(20.0, 20.0, 380.0, 222.5, (1920, 1080))
off = gpu.types.GPUOffScreen(400, 300)
problems = set()
n = 0
for mode, vp, scale, cube, plane, third, hover, broken in itertools.product(
    ("VP", "RECT", "HORIZON"),
    ("1", "2", "3"),
    ("CUBE", "REFERENCE"),
    (True, False),
    ("XY", "XZ", "YZ"),
    (True, False),
    ("cube_top", "cube_base"),
    (False, True),
):
    with calibrate.suspended():
        s.mode, s.vp_count, s.scale_mode, s.show_cube, s.ref_plane, s.use_third_line = (
            mode,
            vp,
            scale,
            cube,
            plane,
            third,
        )
        calibrate.set_handle(s, "cube_base", (0.6, 1.5 if broken else 0.2))
    sol = calibrate.refresh(cam.data)
    session = SimpleNamespace(active_vp=2, hover=hover, drag_key=hover)
    try:
        with off.bind():
            with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                gpu.matrix.load_identity()
                gpu.matrix.load_projection_matrix(
                    Matrix(((2 / 400, 0, 0, -1), (0, 2 / 300, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1)))
                )
                draw.draw_guides(view, s, sol, session, "IMPERIAL")
        for key in calibrate.active_handle_keys(s):
            draw.handle_co(s, sol, key)
    except Exception as exc:
        problems.add(f"{mode} {vp} {scale} {plane}: {type(exc).__name__}: {exc}")
    n += 1
off.free()
print("configs", n, "problems", *sorted(problems), sep="\n ")
