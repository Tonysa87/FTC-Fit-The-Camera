# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the test photo for test_gui.py (run headless, before the GUI session).

Usage: blender --background --python tests_blender/make_photo.py -- <project root> <output .jpg>
"""

import os
import struct
import sys

import bpy
import numpy as np

ROOT, OUT = sys.argv[-2:]
sys.path += [os.path.join(ROOT, "tests"), os.path.join(ROOT, "fit_the_camera")]

import exif  # noqa: E402
from exif_builder import ASCII, RATIONAL, SHORT, build_tiff  # noqa: E402

W, H = 1600, 900
img = bpy.data.images.new("photo", W, H)
yy, xx = np.mgrid[0:H, 0:W]
px = np.ones((H, W, 4), dtype=np.float32)
px[..., :3] = (0.25 + 0.1 * (((xx // 80) + (yy // 80)) % 2))[..., None]
img.pixels.foreach_set(px.ravel())
img.filepath_raw = OUT
img.file_format = "JPEG"
img.save()

tiff = build_tiff(
    ifd0=[(exif.TAG_MAKE, ASCII, "Sim"), (exif.TAG_MODEL, ASCII, "Cam"), (exif.TAG_ORIENTATION, SHORT, 1)],
    exif_ifd=[(exif.TAG_FOCAL_LENGTH, RATIONAL, [(350, 10)]), (exif.TAG_FOCAL_35MM, SHORT, 35)],
)
with open(OUT, "rb") as f:
    raw = f.read()
app1 = b"Exif\0\0" + tiff
with open(OUT, "wb") as f:
    f.write(raw[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + raw[2:])
