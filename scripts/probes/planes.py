import os
import sys

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "snap"}
exec(compile(src, "test_addon", "exec"), g)
calibrate = g["calibrate"]
for exif in (True, False):
    g["fresh_scene"]()
    cam = g["load"](g["write_photo"]("p.jpg", (4000, 3000), g["camera_tiff"](focal=5.9, focal35=25) if exif else None))
    s = cam.data.ftc
    for vp in ("2", "3"):
        for plane in ("XY", "XZ", "YZ"):
            s.vp_count, s.ref_plane = vp, plane
            print(
                "exif" if exif else "noexif",
                vp,
                plane,
                s.results.valid,
                s.results.error[:70],
                "|",
                s.results.warnings[:60],
            )
