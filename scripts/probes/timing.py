import os
import sys
import time

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "snap"}
exec(compile(src, "test_addon", "exec"), g)
calibrate = g["calibrate"]
g["fresh_scene"]()
cam = g["load"](g["write_photo"]("t.jpg", (4000, 3000), g["camera_tiff"](focal=5.9, focal35=25)))
s = cam.data.ftc


def t(label, n=5):
    t0 = time.perf_counter()
    for _ in range(n):
        calibrate.refresh(cam.data)
    dt = (time.perf_counter() - t0) / n
    calibrate.defer_uncertainty = True
    t0 = time.perf_counter()
    for _ in range(n):
        calibrate.refresh(cam.data)
    dd = (time.perf_counter() - t0) / n
    calibrate.defer_uncertainty = False
    print(
        f"{label:28s} full {1000 * dt:7.1f} ms   drag {1000 * dd:6.2f} ms  valid={s.results.valid} {s.results.error} | {s.results.warnings[:90]}"
    )


for fm in ("SOLVE", "AUTO", "KNOWN"):
    s.focal_mode = fm
    for mode, count in (("VP", "2"), ("VP", "3"), ("RECT", "2")):
        s.mode, s.vp_count = mode, count
        t(f"{fm} {mode} {count}")
    s.mode, s.vp_count, s.use_third_line = "VP", "2", True
    t(f"{fm} VP 2 + third line")
    s.use_third_line = False
