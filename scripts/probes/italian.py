"""Every text the panel and the overlay show, collected in Italian: lists the
ones still in English and the ones translated twice (an Italian word that is
also an English msgid). Run: bash scripts/probe.sh italian"""

import importlib
import itertools
import os
import re
import sys
from types import SimpleNamespace

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "snap"}
exec(compile(src, "test_addon", "exec"), g)
import bpy  # noqa: E402
import gpu  # noqa: E402
from bpy.app.translations import pgettext_iface  # noqa: E402
from mathutils import Matrix  # noqa: E402

view_prefs = bpy.context.preferences.view
view_prefs.language = "it_IT"
view_prefs.use_translate_interface = view_prefs.use_translate_tooltips = view_prefs.use_translate_reports = True
view_prefs.use_translate_new_dataname = False

PKG = g["PKG"]
calibrate = g["calibrate"]
ui = importlib.import_module(PKG + ".ui")
draw = importlib.import_module(PKG + ".draw")
shown = {}  # displayed text -> where
ITALIAN = set(importlib.import_module(PKG + ".translations").translations_dict["it_IT"].values())


def show(text, where, translate=True, ctxt=None):
    if not text:
        return
    final = text
    if translate:
        final = pgettext_iface(text, ctxt) if ctxt else pgettext_iface(text)
        if text in ITALIAN and final != text:
            # Already translated by the code, translated again by Blender.
            shown.setdefault(f"DOUBLE {text!r} -> {final!r}", where)
    shown.setdefault(final, where)


class Mock:
    def __init__(self, where="panel"):
        object.__setattr__(self, "where", where)

    def __getattr__(self, name):
        if name in ("row", "column", "box", "split", "grid_flow", "column_flow"):
            return lambda *a, **k: (show(k.get("heading"), self.where), Mock(self.where))[1]
        if name == "panel":
            return lambda *a, **k: (Mock(self.where), Mock(self.where))
        if name in ("prop", "prop_enum", "operator", "operator_menu_enum", "label", "menu"):

            def item(*a, **k):
                if "text" in k:
                    show(k["text"], f"{self.where}.{name}", k.get("translate", True), k.get("text_ctxt"))
                return Mock(self.where)

            return item
        return Mock(self.where)

    def __setattr__(self, k, v):
        pass

    def __call__(self, *a, **k):
        return Mock(self.where)

    def __iter__(self):
        return iter((Mock(self.where), Mock(self.where)))


_, cam, syn = g["_calibrated_camera"]((1920, 1080))
s = cam.data.ftc
bpy.context.view_layer.objects.active = cam
ctx = SimpleNamespace(
    region=SimpleNamespace(width=300),
    preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1.0)),
    scene=bpy.context.scene,
    active_object=cam,
    space_data=None,
    area=None,
)
panel = SimpleNamespace(layout=Mock())
for name in ("draw_alignment", "draw_shadow", "draw_hdri", "draw_camera_data", "draw_calibration"):
    setattr(panel, name, (lambda fn: lambda *a: fn(panel, *a))(getattr(ui.FTC_PT_main, name)))
for mode, vp, scale, focal, cube, pp, anchor in itertools.product(
    ("VP", "RECT", "HORIZON"),
    ("1", "2", "3"),
    ("CUBE", "REFERENCE"),
    ("AUTO", "SOLVE", "KNOWN"),
    (True, False),
    ("CENTER", "SOLVE"),
    (True, False),
):
    with calibrate.suspended():
        s.mode, s.vp_count, s.scale_mode, s.focal_mode, s.show_cube, s.pp_mode = mode, vp, scale, focal, cube, pp
        s.use_anchor = anchor
        s.align_source = "3D Cursor"
        s.anchor_matrix[0][0] = 1.0
    calibrate.refresh(cam.data)
    for fn in (
        ui.FTC_PT_main.draw_camera_data,
        ui.FTC_PT_main.draw_calibration,
        ui.FTC_PT_main.draw_display,
        ui.FTC_PT_main.draw_results,
        ui.FTC_PT_main.draw_render,
        ui.FTC_PT_main.draw_tools,
    ):
        try:
            if fn.__name__ == "draw_display":
                fn(panel, ctx, Mock(fn.__name__), cam, s)
            elif fn.__name__ == "draw_tools":
                fn(panel, ctx, Mock(fn.__name__))
            else:
                fn(panel, ctx, Mock(fn.__name__), s)
        except Exception as exc:
            import traceback

            show(f"ERROR {fn.__name__}: {exc} {traceback.format_exc().splitlines()[-3]}", "probe", False)
# Warnings: break the guides so the solver warns / fails.
for key in ("vp1_a", "vp1_b"):
    if key in [p.identifier for p in s.bl_rna.properties]:
        pass

# Sun panel
g["world_with"](g["synthetic_hdri"](0.3, 0.6, size=(64, 32)))
s.sun.hdri_fitted, s.sun.hdri_image, s.sun.hdri_point = True, "synthetic_hdri", (0.3, 0.6)
light = bpy.data.objects.new("probe sun", bpy.data.lights.new("probe sun", "SUN"))
bpy.context.collection.objects.link(light)
data = s.camera_data
for sun_from, use_shadow, source, has_light, time_state, place, direction in itertools.product(
    ("TIME", "SHADOW"),
    (False, True),
    ("COMPASS", "SIDE", "SHADOW"),
    (True, False),
    ("MISSING", "EXIF", "MANUAL"),
    ("MISSING", "EXIF"),
    ("MISSING", "EXIF"),
):
    with calibrate.suspended():
        s.mode = "VP"
        s.sun.north_source, s.sun.source, s.sun.use_shadow = source, sun_from, use_shadow
        s.sun.light = light if has_light else None
        data.loading = True
        data.time_state, data.location_state, data.direction_state = time_state, place, direction
        data.year, data.month, data.day, data.hour = 2026, 6, 21, 12
        data.gps_latitude, data.gps_longitude = 45.0, 9.0
        data.loading = False
    calibrate.refresh(cam.data)
    try:
        ui.FTC_PT_main.draw_sun(panel, ctx, Mock("draw_sun"), s)
    except Exception as exc:
        show(f"ERROR draw_sun: {exc}", "probe", False)

# Overlay texts (blf: never translated by Blender).
gpu.init()
original_text = draw.text
draw.text = lambda pos, string, *a, **k: show(string, "overlay", False)
view = draw.View(20.0, 20.0, 380.0, 222.5, (1920, 1080))
off = gpu.types.GPUOffScreen(400, 300)
for mode, vp, scale, cube, plane, unit in itertools.product(
    ("VP", "RECT", "HORIZON"), ("1", "2", "3"), ("CUBE", "REFERENCE"), (True, False), ("XY", "XZ"), ("METRIC", "IMPERIAL")
):
    with calibrate.suspended():
        s.mode, s.vp_count, s.scale_mode, s.show_cube, s.ref_plane = mode, vp, scale, cube, plane
    sol = calibrate.refresh(cam.data)
    session = SimpleNamespace(active_vp=0, hover=None, drag_key=None)
    try:
        with off.bind(), gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(Matrix(((2 / 400, 0, 0, -1), (0, 2 / 300, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1))))
            draw.draw_guides(view, s, sol, session, unit)
    except Exception as exc:
        show(f"ERROR overlay: {exc}", "probe", False)
off.free()

ENGLISH = re.compile(r"\b(the|and|of|is|not|to|with|from|on|for|no|use|cannot|needs?|set|guides?|camera|image|photo|focal|length)\b", re.I)
SAME = {"FTC", "Fit Sun", "Fit HDRI", "Roll", "Pitch", "Yaw", "OK", "HDRI"}
print("texts:", len(shown))
for text, where in sorted(shown.items(), key=lambda t: t[1]):
    flag = "DOUBLE" in text or "ERROR" in text or (ENGLISH.search(text) and text not in SAME)
    if flag:
        print(f"  ?? [{where}] {text}")
with open(os.path.join(OUT, "italian.txt"), "w") as f:
    for text, where in sorted(shown.items(), key=lambda t: t[1]):
        f.write(f"[{where}] {text}\n")
