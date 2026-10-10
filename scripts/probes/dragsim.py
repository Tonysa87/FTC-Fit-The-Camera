import importlib
import math
import os
import sys
from types import SimpleNamespace

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "snap"}
exec(compile(src, "test_addon", "exec"), g)
import bpy

calibrate = g["calibrate"]
PKG = g["PKG"]
draw = importlib.import_module(PKG + ".draw")
ops = importlib.import_module(PKG + ".ops_modal")
_, cam, syn = g["_calibrated_camera"]((1920, 1080))
s = cam.data.ftc
w, h = syn.image_size
calibrate.set_handle(s, "cube_base", tuple(syn.project([1.0, 0.5, 0.0])[0] / (w, h)))
calibrate.set_handle(s, "cube_top", tuple(syn.project([1.0, 0.5, 1.0])[0] / (w, h)))
s.scale_mode = "CUBE"
view = draw.View(0.0, 0.0, 1920.0, 1080.0, (1920, 1080))
op = ops.FTC_OT_calibrate
fake = SimpleNamespace(
    changed=lambda ctx, c, reset_pitch=True: calibrate.settings_changed(c.data, ctx, reset_pitch=reset_pitch)
)
fake.snap_target = lambda *a: op.snap_target(fake, *a)
session = SimpleNamespace(drag_key="cube_top", last_mouse=None, pitch_drag=None)


def shown(key):
    return view.to_region(draw.handle_co(s, calibrate.cached_solution(cam.data), key))


calibrate.refresh(cam.data)


def drag(key, moves, ctrl=False, shift=False):
    session.drag_key = key
    m = shown(key)
    session.last_mouse = m
    out = []
    for dx, dy in moves:
        m = (m[0] + dx, m[1] + dy)
        ev = SimpleNamespace(shift=shift, ctrl=ctrl)
        op.drag(fake, bpy.context, session, s, cam, view, ev, m)
        out.append((m, shown(key), s.results.distance, s.results.error))
    return out


print("start distance", round(s.results.distance, 3), "shown top", [round(v, 1) for v in shown("cube_top")])
for label, moves in (
    ("up", [(0, 10)] * 10),
    ("down", [(0, -10)] * 15),
    ("sideways", [(10, 0)] * 10),
    ("back", [(-10, 0)] * 10),
):
    res = drag("cube_top", moves)
    print(
        label,
        [(round(r[2], 3)) for r in res][::2],
        "gap mouse-shown at end %.1f px" % math.dist(res[-1][0], res[-1][1]),
        res[-1][3],
    )
# drag below the base: error then recover
res = drag("cube_top", [(0, -40)] * 8 + [(0, 40)] * 8)
print("through base:", [(round(r[2], 2), r[3][:30]) for r in res])
res = drag("cube_base", [(15, 5)] * 6)
print("base move: distance", [round(r[2], 3) for r in res], "top shown", [round(v, 1) for v in shown("cube_top")])
# base beyond horizon
res = drag("cube_base", [(0, 120)] * 6 + [(0, -120)] * 6)
print("base to horizon:", [(round(r[2], 2), r[3][:40]) for r in res])
print(
    "final top shown",
    [round(v, 1) for v in shown("cube_top")],
    "stored",
    [round(c * d, 1) for c, d in zip(calibrate.handle(s, "cube_top"), (w, h))],
)
# ctrl snap of cube_top onto cube_base
res = drag("cube_top", [(0, -3)], ctrl=True)
print(
    "ctrl snap:",
    res[-1][2:],
)
