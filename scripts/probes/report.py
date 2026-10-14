"""A sample calibration report (Milan test photo, north from its compass).

Writes dist/probes/report.md and report.json.
"""

import os
import sys

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "probe"}
exec(compile(src, "test_addon", "exec"), g)
import bpy  # noqa: E402

cam = g["_sun_camera"](g["sun_tiff"]())
s = cam.data.ftc
bpy.ops.ftc.new_sun()
for fmt, name in (("MARKDOWN", "report.md"), ("JSON", "report.json")):
    print(bpy.ops.ftc.export_report(filepath=os.path.join(OUT, name), format=fmt))
