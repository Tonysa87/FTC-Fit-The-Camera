import importlib
import itertools
import os
import sys
from types import SimpleNamespace

ROOT, OUT = sys.argv[-2:]
src = open(os.path.join(ROOT, "tests_blender/test_addon.py")).read().replace("\nmain()\n", "\n")
g = {"__name__": "snap"}
exec(compile(src, "test_addon", "exec"), g)
import bpy

PKG = g["PKG"]
calibrate = g["calibrate"]
ui = importlib.import_module(PKG + ".ui")
problems = set()


class Mock:
    def __init__(self):
        pass

    def __getattr__(self, name):
        if name in ("row", "column", "box", "split", "grid_flow", "column_flow"):
            return lambda *a, **k: Mock()
        if name == "panel":
            return lambda *a, **k: (Mock(), Mock())
        if name == "prop":

            def prop(data, prop, *a, **k):
                if prop not in data.bl_rna.properties:
                    problems.add(f"missing prop {data.bl_rna.identifier}.{prop}")
                return Mock()

            return prop
        if name == "prop_enum":

            def prop_enum(data, prop, value, *a, **k):
                items = [i.identifier for i in data.bl_rna.properties[prop].enum_items]
                if value not in items:
                    problems.add(f"bad enum {prop}={value}")

            return prop_enum
        if name == "operator":

            def operator(idname, *a, **k):
                mod, op = idname.split(".")
                try:
                    getattr(getattr(bpy.ops, mod), op).get_rna_type()
                except Exception:
                    problems.add(f"missing operator {idname}")
                return SimpleNamespace()

            return operator
        if name in ("label", "separator", "template_ID", "context_pointer_set"):
            return lambda *a, **k: None
        return Mock()

    def __setattr__(self, k, v):
        pass


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
panel.draw_alignment = lambda *a: ui.FTC_PT_main.draw_alignment(panel, *a)
for meth in ("draw_camera_data", "draw_calibration", "draw_display", "draw_results", "draw_tools"):
    pass
count = 0
for mode, vp, scale, focal, cube, size, pp in itertools.product(
    ("VP", "RECT", "HORIZON"),
    ("1", "2", "3"),
    ("CUBE", "REFERENCE"),
    ("AUTO", "SOLVE", "KNOWN"),
    (True, False),
    ("1", "CUSTOM"),
    ("CENTER", "SOLVE"),
):
    with calibrate.suspended():
        s.mode, s.vp_count, s.scale_mode, s.focal_mode, s.show_cube, s.cube_size, s.pp_mode = (
            mode,
            vp,
            scale,
            focal,
            cube,
            size,
            pp,
        )
    calibrate.refresh(cam.data)
    for fn in (ui.FTC_PT_main.draw_calibration, ui.FTC_PT_main.draw_display, ui.FTC_PT_main.draw_results):
        try:
            if fn.__name__ == "draw_display":
                fn(panel, ctx, Mock(), cam, s)
            else:
                fn(panel, ctx, Mock(), s)
        except Exception as exc:
            problems.add(f"{fn.__name__} {mode} {vp} {scale} {focal}: {type(exc).__name__}: {exc}")
    count += 1
print("configs", count, "problems:", *sorted(problems), sep="\n  ")
