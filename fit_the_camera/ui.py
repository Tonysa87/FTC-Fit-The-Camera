# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel (tab "FTC") in the 3D view."""

import math

import bpy
from bpy.app.translations import pgettext_iface as iface_
from bpy.types import Panel

from . import calibrate
from .draw import remaining_axis
from .exif import is_native_aspect
from .ops_load import background_for
from .ops_modal import FTC_OT_calibrate

STATE_ICONS = {"EXIF": "CHECKMARK", "MISSING": "ERROR", "MANUAL": "GREASEPENCIL"}


def field(layout, data, prop, state):
    row = layout.row(align=True)
    row.alert = state == "MISSING"
    row.prop(data, prop)
    sub = row.row(align=True)
    sub.alert = False
    sub.label(text="", icon=STATE_ICONS[state])
    return row


def info_row(layout, label, value, alert=False):
    split = layout.split(factor=0.4)
    split.alert = alert
    split.label(text=label)
    split.label(text=value)


class FTC_PT_main(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FTC"
    bl_label = "Fit The Camera"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        cam_obj = calibrate.view_camera(context)
        active = context.active_object
        if active is not None and active.type == "CAMERA" and active != cam_obj:
            box = layout.box()
            box.label(text=iface_("Active camera '{}' is not the view camera").format(active.name), icon="INFO")

        layout.operator("ftc.load_image", icon="FILE_IMAGE")
        if cam_obj is None:
            layout.label(text="No scene camera: load an image to create one", icon="INFO")
            return
        settings = cam_obj.data.ftc
        if settings.image is None:
            layout.label(text=iface_("Camera: {}").format(cam_obj.name), icon="CAMERA_DATA")
            return

        col = layout.column(align=True)
        col.label(text=f"{cam_obj.name}  ·  {settings.image.name}", icon="CAMERA_DATA")
        data = settings.camera_data
        if data.orientation > 1:
            box = layout.box()
            box.alert = True
            box.label(text=iface_("Image stored rotated (EXIF orientation {})").format(data.orientation), icon="ERROR")
            box.operator("ftc.upright_image", icon="FILE_REFRESH")

        self.draw_camera_data(context, layout, settings)
        self.draw_calibration(context, layout, settings)
        self.draw_display(context, layout, cam_obj, settings)
        self.draw_results(context, layout, settings)
        self.draw_tools(context, layout)

    # ------------------------------------------------------------------

    def draw_camera_data(self, context, layout, settings):
        header, body = layout.panel("ftc_camera_data", default_closed=False)
        header.label(text="Camera Data")
        if body is None:
            return
        data = settings.camera_data
        info_row(body, iface_("Camera"), " ".join(p for p in (data.make, data.model) if p) or iface_("Unknown"))
        if data.lens:
            info_row(body, iface_("Lens"), data.lens)
        info_row(body, iface_("Image"), f"{data.image_width} × {data.image_height} px")
        field(body, data, "focal_mm", data.focal_mm_state)
        field(body, data, "focal_35mm", data.focal_35mm_state)
        field(body, data, "sensor_mm", data.sensor_mm_state)
        if data.has_gps:
            info_row(body, iface_("GPS"), f"{data.gps_latitude:.6f}, {data.gps_longitude:.6f}")
        row = field(body, data, "direction", data.direction_state)
        if data.direction_ref:
            row.label(text=data.direction_ref)

        if data.focal_35mm_state != "MISSING" and not is_native_aspect((data.image_width, data.image_height)):
            body.label(text="Cropped image: 35 mm equivalent taken on the uncropped 4:3 sensor", icon="INFO")
        missing_focal = data.focal_mm_state == "MISSING" and data.focal_35mm_state == "MISSING"
        missing_sensor = data.sensor_mm_state == "MISSING" and data.focal_35mm_state == "MISSING"
        if missing_focal or missing_sensor:
            box = body.box()
            col = box.column(align=True)
            col.alert = True
            what = iface_("Focal length") if missing_focal else iface_("Sensor size")
            col.label(text=iface_("{} not in the image metadata").format(what), icon="ERROR")
            camera = " ".join(p for p in (data.make, data.model) if p)
            if camera:
                col.label(text=iface_("Look up the specifications of: {}").format(camera), icon="VIEWZOOM")
            col.alert = False
            col.label(text="Enter focal length + sensor width, or the 35 mm equivalent")

    def draw_calibration(self, context, layout, settings):
        header, body = layout.panel("ftc_calibration", default_closed=False)
        header.label(text="Calibration")
        if body is None:
            return
        has_focal = calibrate.known_focal_px(settings) is not None

        row = body.row(align=True)
        row.use_property_split = False
        row.prop_enum(settings, "mode", "VP")
        row.prop_enum(settings, "mode", "RECT")
        sub = row.row(align=True)
        sub.enabled = has_focal
        sub.prop_enum(settings, "mode", "HORIZON")

        col = body.column()
        if settings.mode == "VP":
            row = col.row(align=True)
            row.label(text="Vanishing Points")
            sub = row.row(align=True)
            sub.enabled = has_focal
            sub.prop_enum(settings, "vp_count", "1")
            row.prop_enum(settings, "vp_count", "2")
            row.prop_enum(settings, "vp_count", "3")
            count = int(settings.vp_count)
            col.prop(settings, "vp1_axis", text=iface_("Axis 1"))
            col.prop(settings, "vp2_axis", text=iface_("Axis 2 Line") if count == 1 else iface_("Axis 2"))
            if count == 3:
                info_row(col, iface_("Axis 3"), remaining_axis(settings.vp1_axis, settings.vp2_axis))
            col.separator()
            col.prop(settings, "scale_mode")
            if settings.scale_mode == "DISTANCE":
                col.prop(settings, "camera_distance")
            else:
                col.prop(settings, "ref_axis")
                col.prop(settings, "ref_length")
            if count != 3:
                col.prop(settings, "pp_mode")
            if count == 1 and not has_focal:
                col.label(text="Needs the focal length (Camera Data)", icon="ERROR")
        elif settings.mode == "RECT":
            col.prop(settings, "rect_width")
            col.prop(settings, "rect_height")
            sub = col.row()
            sub.enabled = has_focal
            sub.prop(settings, "rect_use_focal")
            col.prop(settings, "pp_mode")
        else:
            col.prop(settings, "camera_height")
            data = settings.camera_data
            row = col.row()
            row.enabled = data.direction_state != "MISSING"
            row.prop(settings, "yaw_source")
            if settings.yaw_source == "MANUAL" or data.direction_state == "MISSING":
                col.prop(settings, "yaw")
            col.prop(settings, "pp_mode")
            if not has_focal:
                col.label(text="Needs the focal length (Camera Data)", icon="ERROR")

        body.separator()
        running = FTC_OT_calibrate.running()
        row = body.row(align=True)
        row.scale_y = 1.4
        row.operator(
            "ftc.calibrate",
            text=iface_("Stop Calibrating") if running else iface_("Calibrate"),
            icon="PAUSE" if running else "PLAY",
            depress=running,
        )
        row = body.row(align=True)
        row.operator("ftc.apply", icon="CHECKMARK")
        row.operator("ftc.reset", icon="LOOP_BACK")

        col = body.column(heading="Options")
        col.prop(settings, "live")
        col.prop(settings, "freeze")
        col.prop(settings, "straighten")
        if settings.pitch_offset != 0.0:
            col.prop(settings, "pitch_offset")

        row = body.row(align=True)
        row.operator("ftc.anchor_cursor", icon="PIVOT_CURSOR")
        sub = row.row(align=True)
        sub.enabled = any(settings.anchor_matrix[i][i] != 0.0 for i in range(4))
        sub.prop(settings, "use_anchor", text="", icon="LINKED" if settings.use_anchor else "UNLINKED")

    def draw_display(self, context, layout, cam_obj, settings):
        header, body = layout.panel("ftc_display", default_closed=False)
        header.label(text="Opacity")
        if body is None:
            return
        bg = background_for(cam_obj.data, settings.image)
        if bg is not None:
            body.prop(bg, "alpha", text=iface_("Image"), slider=True)
        row = body.row(heading="Grid")
        row.prop(settings, "show_grid", text="")
        sub = row.row()
        sub.active = settings.show_grid
        sub.prop(settings, "grid_opacity", text="", slider=True)

    def draw_results(self, context, layout, settings):
        header, body = layout.panel("ftc_results", default_closed=False)
        header.label(text="Results")
        if body is None:
            return
        res = settings.results
        if not res.valid:
            box = body.box()
            box.alert = True
            box.label(text=res.error or iface_("Not solved"), icon="ERROR")
            return
        for line in res.warnings.splitlines():
            box = body.box()
            box.label(text=line, icon="ERROR")
        col = body.column(align=True)
        focal = f"{res.lens:.2f} mm  ({res.focal_px:.0f} px)"
        if res.focal_solved:
            focal += f"  ±{100 * res.focal_error:.1f}%"
        info_row(col, iface_("Focal Length"), focal, alert=res.focal_solved and res.focal_error > 0.05)
        info_row(col, iface_("Orientation"), f"±{res.angle_error:.2f}°", alert=res.angle_error > 1.0)
        info_row(col, iface_("Sensor"), f"{res.sensor:.2f} mm")
        info_row(col, iface_("Field of View"), f"{math.degrees(res.fov_h):.2f}° × {math.degrees(res.fov_v):.2f}°")
        unit = context.scene.unit_settings.system
        info_row(col, iface_("Camera Height"), bpy.utils.units.to_string(unit, "LENGTH", res.height, precision=3))
        info_row(col, iface_("Distance"), bpy.utils.units.to_string(unit, "LENGTH", res.distance, precision=3))
        info_row(col, iface_("Pitch"), f"{math.degrees(res.pitch):.2f}°")
        info_row(col, iface_("Roll"), f"{math.degrees(res.roll):.2f}°")
        info_row(col, iface_("Yaw"), f"{math.degrees(res.yaw):.2f}°")
        if settings.straighten:
            info_row(col, iface_("Removed Roll"), f"{math.degrees(res.removed_roll):+.2f}°", alert=True)

    def draw_tools(self, context, layout):
        header, body = layout.panel("ftc_tools", default_closed=True)
        header.label(text="Tools")
        if body is None:
            return
        body.operator("ftc.move_along_view", icon="EMPTY_SINGLE_ARROW")


classes = (FTC_PT_main,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
