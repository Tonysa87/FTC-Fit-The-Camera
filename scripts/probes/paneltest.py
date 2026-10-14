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
        if name == "operator_menu_enum":

            def operator_menu_enum(idname, prop, *a, **k):
                mod, op = idname.split(".")
                try:
                    rna = getattr(getattr(bpy.ops, mod), op).get_rna_type()
                    if prop not in rna.properties:
                        problems.add(f"missing operator prop {idname}.{prop}")
                except Exception:
                    problems.add(f"missing operator {idname}")

            return operator_menu_enum
        if name == "template_list":

            def template_list(list_id, _list, data, prop, active_data, active_prop, *a, **k):
                if not hasattr(bpy.types, list_id):
                    problems.add(f"missing UIList {list_id}")
                for d, p in ((data, prop), (active_data, active_prop)):
                    if p not in d.bl_rna.properties:
                        problems.add(f"missing prop {d.bl_rna.identifier}.{p}")

            return template_list
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
panel.draw_shadow = lambda *a: ui.FTC_PT_main.draw_shadow(panel, *a)
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
    sections = (
        ui.FTC_PT_main.draw_calibration,
        ui.FTC_PT_main.draw_display,
        ui.FTC_PT_main.draw_results,
        ui.FTC_PT_main.draw_render,
    )
    for fn in sections:
        try:
            if fn.__name__ == "draw_display":
                fn(panel, ctx, Mock(), cam, s)
            else:
                fn(panel, ctx, Mock(), s)
        except Exception as exc:
            problems.add(f"{fn.__name__} {mode} {vp} {scale} {focal}: {type(exc).__name__}: {exc}")
    count += 1
light = bpy.data.objects.new("probe sun", bpy.data.lights.new("probe sun", "SUN"))
bpy.context.collection.objects.link(light)
data = s.camera_data
for sun_from, use_shadow, source, ref, has_light, time_state, offset_state, place, direction in itertools.product(
    ("TIME", "SHADOW"),
    (False, True),
    ("COMPASS", "MAP", "LANDMARK", "SHADOW"),
    ("", "T", "M"),
    (True, False),
    ("MISSING", "EXIF", "MANUAL"),
    ("MISSING", "EXIF"),
    ("MISSING", "EXIF"),
    ("MISSING", "EXIF"),
):
    with calibrate.suspended():
        s.mode = "VP"
        s.sun.north_source = source
        s.sun.source = sun_from
        s.sun.use_shadow = use_shadow
        s.sun.light = light if has_light else None
        data.loading = True
        data.direction_ref = ref
        data.time_state, data.offset_state, data.location_state = time_state, offset_state, place
        data.direction_state = direction
        data.year, data.month, data.day, data.hour = 2026, 6, 21, 12
        data.gps_latitude, data.gps_longitude = 45.0, 9.0
        data.loading = False
    calibrate.refresh(cam.data)
    try:
        ui.FTC_PT_main.draw_sun(panel, ctx, Mock(), s)
    except Exception as exc:
        problems.add(f"draw_sun {sun_from} {use_shadow} {source} {ref} {time_state}: {type(exc).__name__}: {exc}")
    count += 1
print("configs", count, "problems:", *sorted(problems), sep="\n  ")
