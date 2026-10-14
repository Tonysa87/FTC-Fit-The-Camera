# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel (tab "FTC") in the 3D view."""

import math
import textwrap

import bpy
from bpy.app.translations import pgettext_iface as iface_
from bpy.types import Panel

from . import calibrate, ops_orientation, ops_render, ops_sun
from .draw import plane_axes, remaining_axis, third_axis
from .exif import is_native_aspect
from .ops_load import background_for
from .ops_modal import FTC_OT_calibrate

OVERRIDDEN = "Keyframes, drivers or constraints on the camera (or its parent) override the calibration"
STATE_ICONS = {"EXIF": "CHECKMARK", "MISSING": "ERROR", "MANUAL": "GREASEPENCIL"}


def field(layout, data, prop, state):
    row = layout.row(align=True)
    row.alert = state == "MISSING"
    row.prop(data, prop)
    sub = row.row(align=True)
    sub.alert = False
    sub.label(text="", icon=STATE_ICONS[state])
    return row


def wrapped(layout, context, text, icon="NONE"):
    """Label split over several lines to fit the sidebar width."""
    width = context.region.width if context.region else 300
    chars = max(20, int(width / (6.5 * context.preferences.system.ui_scale)))
    col = layout.column(align=True)
    for i, line in enumerate(textwrap.wrap(text, chars)):
        col.label(text=line, icon=icon if i == 0 else "BLANK1")


def info_row(layout, label, value, alert=False):
    split = layout.split(factor=0.4)
    split.alert = alert
    split.label(text=label)
    split.label(text=value)


def time_row(layout, label, data, props, state):
    """Label, then several small fields on one line (date or time)."""
    split = layout.split(factor=0.4, align=True)
    split.alert = state == "MISSING"
    sub = split.row()
    sub.alignment = "RIGHT"
    sub.label(text=label, text_ctxt="FTC")
    row = split.row(align=True)
    for prop in props:
        row.prop(data, prop, text="")
    icon = row.row(align=True)
    icon.alert = False
    icon.label(text="", icon=STATE_ICONS[state])


def draw_cube_size(layout, settings):
    layout.prop(settings, "cube_size")
    if settings.cube_size == "CUSTOM":
        layout.prop(settings, "cube_custom")


def axis_row(layout, settings, index, label):
    """Axis of a guide group with its flip button; the third axis is derived."""
    row = layout.row(align=True)
    if index == 3:
        split = row.split(factor=0.4)
        sub = split.row()
        sub.alignment = "RIGHT"
        sub.label(text=label)
        split.label(text=third_axis(settings.vp1_axis, settings.vp2_axis))
    else:
        row.prop(settings, f"vp{index}_axis", text=label)
    row.operator("ftc.flip_axis", text="", icon="ARROW_LEFTRIGHT").index = index


def draw_focal_mode(layout, settings, has_focal):
    row = layout.row()
    row.enabled = not calibrate.pp_solved(settings)
    row.prop(settings, "focal_mode")
    if not row.enabled:
        layout.label(text="Solved principal point: the focal length comes from the guides", icon="INFO")
    elif not has_focal and settings.focal_mode == "AUTO":
        layout.label(text="Focal length unknown: solved from the guides", icon="INFO")
    elif not has_focal and settings.focal_mode == "KNOWN":
        layout.label(text="Needs the focal length (Camera Data)", icon="ERROR")


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
        label = f"{cam_obj.name}  ·  {settings.image.name}"
        if sum(1 for o in context.scene.objects if o.type == "CAMERA" and o.data.ftc.image is not None) > 1:
            # Several calibrated cameras: the label is a menu to switch between them.
            col.operator_menu_enum("ftc.use_camera", "camera", text=label, icon="CAMERA_DATA")
        else:
            col.label(text=label, icon="CAMERA_DATA")
        data = settings.camera_data
        if data.orientation > 1:
            box = layout.box()
            box.alert = True
            box.label(text=iface_("Image stored rotated (EXIF orientation {})").format(data.orientation), icon="ERROR")
            box.operator("ftc.upright_image", icon="FILE_REFRESH")

        if not calibrate.aspect_matches(context.scene, calibrate.image_size(settings)):
            box = layout.box()
            box.alert = True
            box.label(text="Render size has another aspect than the image: Apply or Calibrate fixes it", icon="ERROR")
        if calibrate.transform_overridden(cam_obj):
            box = layout.box()
            box.alert = True
            wrapped(box, context, iface_(OVERRIDDEN), icon="ERROR")
        self.draw_camera_data(context, layout, settings)
        self.draw_calibration(context, layout, settings)
        self.draw_display(context, layout, cam_obj, settings)
        self.draw_results(context, layout, settings)
        self.draw_render(context, layout, settings)
        self.draw_sun(context, layout, settings)
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
            axis_row(col, settings, 1, iface_("Axis 1"))
            axis_row(col, settings, 2, iface_("Axis 2 Line") if count == 1 else iface_("Axis 2"))
            if count >= 2:
                axis_row(col, settings, 3, iface_("Axis 3"))
            if count == 2:
                third = remaining_axis(settings.vp1_axis, settings.vp2_axis)
                col.prop(settings, "use_third_line", text=iface_("Third Axis Line") + f" ({third})")
            if count >= 2:
                draw_focal_mode(col, settings, has_focal)
            col.separator()
            col.prop(settings, "scale_mode")
            if settings.scale_mode == "CUBE":
                draw_cube_size(col, settings)
            else:
                col.prop(settings, "ref_measure_plane")
                col.prop(settings, "ref_axis")
                col.prop(settings, "ref_length")
            col.prop(settings, "pp_mode")
            if settings.pp_mode == "SOLVE" and count != 3:
                col.label(text="Solve needs three vanishing points: using the centre", icon="INFO")
            if count == 1 and not has_focal:
                col.label(text="Needs the focal length (Camera Data)", icon="ERROR")
        elif settings.mode == "RECT":
            # The rectangle lies on the reference plane: its sides run along the
            # plane's two axes (never "height" unless the plane is a wall).
            col.row(align=True).prop(settings, "ref_plane", expand=True)
            first, second = plane_axes(settings.ref_plane)[:2]
            col.prop(settings, "rect_width", text=iface_("Side {}").format(first))
            col.prop(settings, "rect_height", text=iface_("Side {}").format(second))
            draw_focal_mode(col, settings, has_focal)
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

        self.draw_alignment(context, body, settings)

    def draw_alignment(self, context, layout, settings):
        header, body = layout.panel("ftc_align", default_closed=False)
        header.label(text="Align to Scene")
        if body is None:
            return
        if settings.mode == "VP":
            # (RECT shows the plane with the rectangle, HORIZON is always the ground.)
            row = body.row(align=True)
            row.prop(settings, "ref_plane", expand=True)
        row = body.row(align=True)
        row.operator("ftc.align_cursor", icon="PIVOT_CURSOR")
        row.operator("ftc.align_selection", icon="RESTRICT_SELECT_OFF")
        row.operator("ftc.align_clear", icon="WORLD")
        if settings.use_anchor:
            info_row(body, iface_("Aligned To"), settings.align_source or "—")
            row = body.row(align=True)
            row.operator("ftc.align_rotate", icon="FILE_REFRESH")
            row.operator("ftc.align_flip", icon="ARROW_LEFTRIGHT", depress=settings.align_flip)
        elif any(settings.anchor_matrix[i][i] != 0.0 for i in range(4)):
            # A target is stored but switched off: offer to switch it back on.
            body.prop(settings, "use_anchor", text=iface_("Use Stored Target") + f" ({settings.align_source})")

    def draw_display(self, context, layout, cam_obj, settings):
        header, body = layout.panel("ftc_display", default_closed=False)
        header.label(text="Display", text_ctxt="FTC")
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
        if not calibrate.cube_scales(settings) and not calibrate.reference_scales(settings):
            # When the cube sets the scale it is always shown, with its size above;
            # with the reference distance it is hidden.
            row = body.row(heading="Scale Cube")
            row.prop(settings, "show_cube", text="")
            sub = row.row(align=True)
            sub.active = settings.show_cube
            sub.prop(settings, "cube_size", text="")
            if settings.cube_size == "CUSTOM":
                sub.prop(settings, "cube_custom", text="")
        body.prop(settings.sun, "show_north")

    def draw_results(self, context, layout, settings):
        header, body = layout.panel("ftc_results", default_closed=False)
        header.label(text="Results", text_ctxt="FTC")
        if body is None:
            return
        res = settings.results
        if not res.valid:
            box = body.box()
            box.alert = True
            wrapped(box, context, res.error or iface_("Not solved"), icon="ERROR")
            return
        for line in res.warnings.splitlines():
            wrapped(body.box(), context, line, icon="ERROR")
        col = body.column(align=True)
        focal = f"{res.lens:.2f} mm  ({res.focal_px:.0f} px)"
        if res.focal_solved:
            focal += f"  ±{100 * res.focal_error:.1f}%"
        info_row(col, iface_("Focal Length"), focal, alert=res.focal_solved and res.focal_error > 0.05)
        if calibrate.focal_source(settings) == "AUTO":
            info_row(col, iface_("vs Known"), f"{100 * res.focal_shift:+.1f}%", alert=abs(res.focal_shift) > 0.15)
        info_row(col, iface_("Orientation"), f"±{res.angle_error:.2f}°", alert=res.angle_error > 1.0)
        if settings.mode == "VP":
            misfit = math.degrees(res.guide_misfit)
            info_row(col, iface_("Guide Fit"), iface_("max {:.2f}°").format(misfit), alert=misfit > 1.0)
        info_row(col, iface_("Sensor"), f"{res.sensor:.2f} mm")
        info_row(col, iface_("Field of View"), f"{math.degrees(res.fov_h):.2f}° × {math.degrees(res.fov_v):.2f}°")
        unit = context.scene.unit_settings.system
        info_row(col, iface_("Camera Height"), bpy.utils.units.to_string(unit, "LENGTH", res.height, precision=3))
        info_row(col, iface_("Distance"), bpy.utils.units.to_string(unit, "LENGTH", res.distance, precision=3))
        info_row(col, iface_("Pitch"), f"{math.degrees(res.pitch):.2f}°")
        info_row(col, iface_("Roll"), f"{math.degrees(res.roll):.2f}°")
        info_row(col, iface_("Yaw", "FTC"), f"{math.degrees(res.yaw):.2f}°")
        if settings.straighten:
            info_row(col, iface_("Removed Roll"), f"{math.degrees(res.removed_roll):+.2f}°", alert=True)

    def draw_render(self, context, layout, settings):
        header, body = layout.panel("ftc_render", default_closed=True)
        header.label(text="Render")
        if body is None:
            return
        scene = context.scene
        row = body.row()
        row.scale_y = 1.4
        row.operator("ftc.prepare_render", icon="SCENE")
        if not ops_render.color_ready(scene):
            body.label(text="Scene not set up for the photo: use Prepare Render", icon="INFO")
        if scene.render.engine != "CYCLES" and ops_render.has_catchers(scene):
            wrapped(body, context, iface_(ops_render.CATCHER_EEVEE), icon="ERROR")
        tree = scene.compositing_node_group
        if tree is not None and tree.get(ops_render.TREE_TAG) and sum(v.use for v in scene.view_layers) > 1:
            wrapped(body, context, iface_("Only the active view layer is composited over the photo"), icon="INFO")

        body.label(text="Object Roles")
        body.template_list("FTC_UL_roles", "", scene, "objects", scene, "ftc_role_index", rows=4)
        body.operator_menu_enum("ftc.set_role", "role", icon="RESTRICT_SELECT_OFF")

    def draw_sun(self, context, layout, settings):
        header, body = layout.panel("ftc_sun", default_closed=True)
        header.label(text="Fit Sun")
        if body is None:
            return
        data = settings.camera_data
        sun = settings.sun
        state = ops_sun.evaluate(settings)

        row = body.row(align=True)
        row.use_property_split = False
        row.prop(sun, "source", expand=True)

        if sun.source == "TIME":
            col = body.column(align=True)
            time_row(col, "Date", data, ("day", "month", "year"), data.time_state)
            time_row(col, "Time", data, ("hour", "minute", "second"), data.time_state)
            row = field(body, data, "utc_offset", data.offset_state)
            if data.time_from_gps and data.offset_state == "EXIF" and data.utc_offset == 0.0:
                row.label(text="UTC")
            col = body.column(align=True)
            place = ops_sun.location_state(data)
            field(col, data, "gps_latitude", place)
            field(col, data, "gps_longitude", place)
            body.operator("ftc.read_photo_time", icon="FILE_REFRESH")

            body.separator()
            row = body.row(align=True)
            row.use_property_split = False
            row.prop(sun, "north_source", expand=True)
            col = body.column()
            if sun.north_source == "COMPASS":
                # Without a compass the error box below says what to do.
                if data.direction_state != "MISSING":
                    row = field(col, data, "direction", data.direction_state)
                    if data.direction_ref:
                        row.label(text=data.direction_ref)
                    if data.direction_ref.upper().startswith("M"):
                        col.prop(sun, "declination")
            elif sun.north_source == "MAP":
                col.prop(sun, "map_axis")
                col.prop(sun, "map_bearing")
            elif sun.north_source == "LANDMARK":
                col.prop(sun, "landmark_bearing")
                wrapped(
                    col, context, iface_("Drag the Landmark handle (Calibrate) onto a distant feature"), icon="INFO"
                )
            col.prop(sun, "north_correction")
            if state.sun is not None:
                col = body.column(align=True)
                info_row(col, iface_("Sun Azimuth"), f"{state.sun.azimuth:.1f}°")
                info_row(col, iface_("Sun Elevation"), f"{state.sun.elevation:.1f}°", alert=state.sun.elevation <= 0)

        self.draw_shadow(context, body, sun, state)

        if state.error:
            box = body.box()
            box.alert = True
            wrapped(box, context, iface_(state.error), icon="ERROR")
        for line in state.warnings:
            wrapped(body.box(), context, iface_(line), icon="ERROR")

        body.separator()
        row = body.row(align=True)
        row.prop(sun, "light")
        row.operator("ftc.new_sun", text="", icon="LIGHT_SUN")
        if sun.light is None:
            body.label(text="Pick a Sun light or add one: FTC turns it towards the sun", icon="INFO")
        elif problem := ops_sun.light_problem(sun.light):
            box = body.box()
            box.alert = True
            wrapped(box, context, iface_(problem), icon="ERROR")

    def draw_shadow(self, context, body, sun, state):
        """Shadow handles: the sun itself (Shadow), or a check of the date and place."""
        body.separator()
        needed = sun.source == "SHADOW" or sun.north_source == "SHADOW"
        if not needed:
            body.prop(sun, "use_shadow")
        if not (needed or sun.use_shadow):
            return
        row = body.row(align=True)
        row.use_property_split = False
        row.prop(sun, "shadow_plane", expand=True)
        wrapped(
            body,
            context,
            iface_(
                "Calibrate: orange handles on the foot and the top of something vertical, and on the tip of its shadow"
            ),
            icon="INFO",
        )
        col = body.column(align=True)
        if state.shadow is not None:
            spread = f"  ±{state.shadow_spread:.1f}°" if math.isfinite(state.shadow_spread) else ""
            info_row(col, iface_("Shadow Elevation"), f"{ops_sun.elevation_of(state.shadow):.1f}°{spread}")
        elif state.shadow_error and state.error != state.shadow_error:
            box = body.box()
            box.alert = True
            wrapped(box, context, iface_(state.shadow_error), icon="ERROR")
        if state.shadow_elevation_offset is not None:
            off = state.shadow_elevation_offset
            info_row(
                col,
                iface_("Shadow vs Date"),
                iface_("{:+.1f}° elevation").format(off),
                alert=abs(off) > ops_sun.SHADOW_ELEVATION_ALERT,
            )
        if state.shadow_north_offset is not None:
            off = state.shadow_north_offset
            info_row(
                col,
                iface_("Shadow vs North"),
                f"{off:+.1f}°",
                alert=abs(off) > ops_sun.SHADOW_NORTH_ALERT,
            )
            row = body.row()
            row.prop_enum(sun, "north_source", "SHADOW", text="Use Shadow North")

    def draw_tools(self, context, layout):
        header, body = layout.panel("ftc_tools", default_closed=False)
        header.label(text="Tools")
        if body is None:
            return
        in_use = ops_orientation.in_use(context.scene)
        body.operator("ftc.use_orientation", icon="ORIENTATION_GLOBAL", depress=in_use)


classes = (FTC_PT_main,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
