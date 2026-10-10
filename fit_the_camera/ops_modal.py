# SPDX-License-Identifier: GPL-3.0-or-later
"""Interactive calibration in the camera view, plus the panel's helper operators."""

from __future__ import annotations

import math

import bpy
from bpy.types import Operator

from . import calibrate, draw

FINE_FACTOR = 0.2
UNDO_LIMIT = 100

# Events left to the viewport so that pan and zoom keep working.
NAVIGATION_EVENTS = {
    "MIDDLEMOUSE",
    "WHEELUPMOUSE",
    "WHEELDOWNMOUSE",
    "WHEELINMOUSE",
    "WHEELOUTMOUSE",
    "TRACKPADPAN",
    "TRACKPADZOOM",
    "MOUSEROTATE",
    "MOUSESMARTZOOM",
    "NUMPAD_PLUS",
    "NUMPAD_MINUS",
    "NUMPAD_0",
    "HOME",
}

AXIS_KEYS = {"ONE": "X", "TWO": "Y", "THREE": "Z", "NUMPAD_1": "X", "NUMPAD_2": "Y", "NUMPAD_3": "Z"}
# Keys that also work with the mouse over the sidebar or header of the 3D view.
SHORTCUT_KEYS = {"F", "H", *AXIS_KEYS}

MODE_NAMES = {"VP": "Vanishing Points", "RECT": "Known Rectangle", "HORIZON": "Horizon"}


class Session:
    """State of the running calibration, shared with the draw callback."""

    def __init__(self, camera_name, area, region):
        self.camera_name = camera_name
        self.area_ptr = area.as_pointer()
        self.region_ptr = region.as_pointer()
        self.view: draw.View | None = None
        self.hover: str | None = None
        self.drag_key: str | None = None
        self.active_vp = 0
        self.undo: list[dict] = []
        self.redo: list[dict] = []
        self.drag_start: dict | None = None
        self.last_mouse = (0.0, 0.0)
        self.pitch_drag: tuple[float, float] | None = None
        self.stop_requested = False
        self.handler = None


def snapshot(settings) -> dict:
    return {
        "handles": {h.name: tuple(h.co) for h in settings.handles},
        "pitch_offset": settings.pitch_offset,
        "axes": (settings.vp1_axis, settings.vp2_axis, settings.vp3_axis),
        "straighten": settings.straighten,
    }


def restore(settings, snap: dict) -> None:
    with calibrate.suspended():
        for key, co in snap["handles"].items():
            calibrate.set_handle(settings, key, co)
        settings.pitch_offset = snap["pitch_offset"]
        settings.vp1_axis, settings.vp2_axis, settings.vp3_axis = snap["axes"]
        settings.straighten = snap["straighten"]


def find_region(window, area_ptr, region_ptr):
    for area in window.screen.areas:
        if area.as_pointer() == area_ptr:
            for region in area.regions:
                if region.as_pointer() == region_ptr:
                    return area, region
    return None, None


def main_region(area):
    """The 3D view WINDOW region showing the area's main view."""
    space = area.spaces.active
    windows = [r for r in area.regions if r.type == "WINDOW"]
    for region in windows:
        if region.data == space.region_3d:
            return region
    return windows[-1] if windows else None


def mouse_in_region(area, region, event) -> tuple[float, float] | None:
    """Mouse position in region pixels, or ``None`` when over another region."""
    x, y = event.mouse_x, event.mouse_y
    if not (region.x <= x < region.x + region.width and region.y <= y < region.y + region.height):
        return None
    for other in area.regions:
        if other.type == "WINDOW" or other.width <= 1 or other.height <= 1:
            continue
        if other.x <= x < other.x + other.width and other.y <= y < other.y + other.height:
            return None
    return x - region.x, y - region.y


def flip(axis: str) -> str:
    return ("-" if axis.startswith("+") else "+") + axis[1:]


class FTC_OT_calibrate(Operator):
    """Edit the calibration guides in the camera view"""

    bl_idname = "ftc.calibrate"
    bl_label = "Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    _session: Session | None = None

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != "VIEW_3D":
            return False
        cam = calibrate.view_camera(context)
        return cam is not None and cam.data.ftc.image is not None

    @classmethod
    def running(cls) -> bool:
        return cls._session is not None

    def invoke(self, context, event):
        if FTC_OT_calibrate._session is not None:
            # A second click on Calibrate ends the running session.
            FTC_OT_calibrate._session.stop_requested = True
            return {"CANCELLED"}
        cam_obj = calibrate.view_camera(context)
        area = context.area
        region = main_region(area)
        if region is None:
            return {"CANCELLED"}
        space = area.spaces.active
        if space.region_3d.view_perspective != "CAMERA":
            space.region_3d.view_perspective = "CAMERA"

        settings = cam_obj.data.ftc
        calibrate.ensure_handles(settings)
        session = Session(cam_obj.name, area, region)
        session.handler = bpy.types.SpaceView3D.draw_handler_add(draw.draw_overlay, (session,), "WINDOW", "POST_PIXEL")
        FTC_OT_calibrate._session = session
        calibrate.session_camera = cam_obj.name
        calibrate.update(context, cam_obj, apply=settings.live)
        context.window_manager.modal_handler_add(self)
        self.update_status(context, area)
        area.tag_redraw()
        return {"RUNNING_MODAL"}

    # ------------------------------------------------------------------
    # Helpers

    def update_status(self, context, area) -> None:
        session = FTC_OT_calibrate._session
        cam_obj = bpy.data.objects.get(session.camera_name)
        settings = cam_obj.data.ftc
        mode = MODE_NAMES[settings.mode]
        if settings.mode == "VP":
            mode += f" ({settings.vp_count})"
        if settings.freeze:
            mode += " [frozen]"
        area.header_text_set(
            f"FTC  {mode}  |  LMB drag: move  Shift: fine  Ctrl: snap  1/2/3: axis  F: flip  "
            "H: straighten  Ctrl+Z / Ctrl+Shift+Z: undo/redo  Enter: apply  Esc/RMB: exit"
        )

    def finish(self, context, *, apply: bool):
        session = FTC_OT_calibrate._session
        cam_obj = bpy.data.objects.get(session.camera_name) if session else None
        if apply and cam_obj is not None:
            calibrate.update(context, cam_obj, apply=True)
        if session is not None and session.handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(session.handler, "WINDOW")
        FTC_OT_calibrate._session = None
        calibrate.session_camera = None
        area, _ = find_region(context.window, session.area_ptr, session.region_ptr) if session else (None, None)
        if area is not None:
            area.header_text_set(None)
        calibrate.tag_redraw(context)
        return {"FINISHED"}

    def pick(self, settings, view, mouse) -> str | None:
        radius = draw.PICK_RADIUS * draw.ui_scale()
        best, best_d = None, radius
        if not settings.freeze:
            for key in calibrate.active_handle_keys(settings):
                d = math.dist(view.to_region(calibrate.handle(settings, key)), mouse)
                if d < best_d:
                    best, best_d = key, d
        solution = calibrate.cached_solution(bpy.data.objects[FTC_OT_calibrate._session.camera_name].data)
        if solution is not None and best is None:
            ph = draw.pitch_handle_px(solution)
            if ph is not None and math.dist(view.px_to_region(ph), mouse) < radius * 1.2:
                best = "pitch"
        return best

    def snap_target(self, settings, view, key, pos):
        radius = draw.PICK_RADIUS * draw.ui_scale() * 1.5
        best, best_d = None, radius
        for other in calibrate.active_handle_keys(settings):
            if other == key:
                continue
            p = view.to_region(calibrate.handle(settings, other))
            d = math.dist(p, pos)
            if d < best_d:
                best, best_d = p, d
        return best

    def push_undo(self, session, snap) -> None:
        session.undo.append(snap)
        del session.undo[:-UNDO_LIMIT]
        session.redo.clear()

    def changed(self, context, cam_obj, *, reset_pitch=True):
        calibrate.settings_changed(cam_obj.data, context, reset_pitch=reset_pitch)

    # ------------------------------------------------------------------
    # Event loop

    def modal(self, context, event):
        session = FTC_OT_calibrate._session
        if session is None:
            return {"CANCELLED"}
        cam_obj = bpy.data.objects.get(session.camera_name)
        area, region = find_region(context.window, session.area_ptr, session.region_ptr)
        if session.stop_requested or cam_obj is None or cam_obj.type != "CAMERA" or area is None:
            return self.finish(context, apply=False)
        settings = cam_obj.data.ftc
        rv3d = area.spaces.active.region_3d
        view = session.view
        if view is None or rv3d.view_perspective != "CAMERA":
            view = None
        mouse = mouse_in_region(area, region, event)

        if event.type in NAVIGATION_EVENTS:
            return {"PASS_THROUGH"}

        # Dragging -------------------------------------------------------
        if session.drag_key is not None:
            if event.type == "MOUSEMOVE" and view is not None:
                raw = (event.mouse_x - region.x, event.mouse_y - region.y)
                self.drag(context, session, settings, cam_obj, view, event, raw)
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                if snapshot(settings) != session.drag_start:
                    self.push_undo(session, session.drag_start)
                session.drag_key = None
                session.pitch_drag = None
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
                restore(settings, session.drag_start)
                session.drag_key = None
                self.changed(context, cam_obj, reset_pitch=False)
                return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"}

        if event.type == "Z" and (event.ctrl or event.oskey):
            # Always handled here: Blender's global undo must not run mid-session.
            if event.value == "PRESS":
                self.undo_redo(context, session, settings, cam_obj, redo=event.shift)
            return {"RUNNING_MODAL"}

        if mouse is None:
            # Over the sidebar, header or another area: let Blender handle it,
            # except the calibration shortcuts while the mouse is in this area.
            if session.hover is not None:
                session.hover = None
                area.tag_redraw()
            in_area = area.x <= event.mouse_x < area.x + area.width and area.y <= event.mouse_y < area.y + area.height
            if not (in_area and event.value == "PRESS" and event.type in SHORTCUT_KEYS):
                return {"PASS_THROUGH"}

        if event.type == "MOUSEMOVE":
            hover = self.pick(settings, view, mouse) if view is not None else None
            if hover != session.hover:
                session.hover = hover
                area.tag_redraw()
            return {"PASS_THROUGH"}

        if event.value != "PRESS":
            return {"RUNNING_MODAL"} if event.type == "LEFTMOUSE" else {"PASS_THROUGH"}

        if event.type == "LEFTMOUSE":
            key = self.pick(settings, view, mouse) if view is not None else None
            if key is not None:
                session.drag_key = key
                session.drag_start = snapshot(settings)
                session.last_mouse = mouse
                if key == "pitch":
                    session.pitch_drag = (settings.pitch_offset, view.region_to_px(*mouse)[1])
                elif key.startswith("vp"):
                    session.active_vp = int(key[2]) - 1
                elif key.startswith("hz") and settings.mode == "VP":
                    session.active_vp = 1
                area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type in {"RET", "NUMPAD_ENTER"}:
            return self.finish(context, apply=True)
        if event.type in {"ESC", "RIGHTMOUSE"}:
            return self.finish(context, apply=False)

        if event.type == "H":
            self.push_undo(session, snapshot(settings))
            settings.straighten = not settings.straighten
            return {"RUNNING_MODAL"}

        if event.type in AXIS_KEYS and settings.mode == "VP" and not event.ctrl:
            self.set_axis(session, settings, AXIS_KEYS[event.type])
            self.changed(context, cam_obj)
            return {"RUNNING_MODAL"}

        if event.type == "F" and not event.ctrl:
            self.push_undo(session, snapshot(settings))
            if settings.mode == "VP":
                attr = f"vp{session.active_vp + 1}_axis"
                with calibrate.suspended():
                    setattr(settings, attr, flip(getattr(settings, attr)))
            elif settings.mode == "RECT":
                # Move the first corner to the next vertex.
                cos = [calibrate.handle(settings, f"rect_{i}") for i in range(4)]
                with calibrate.suspended():
                    for i in range(4):
                        calibrate.set_handle(settings, f"rect_{i}", cos[(i + 1) % 4])
            self.changed(context, cam_obj)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" or event.type in {"A", "B", "C", "X", "DEL", "G", "R", "S", "TAB"}:
            # Keep the scene safe from accidental edits while calibrating.
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def undo_redo(self, context, session, settings, cam_obj, *, redo: bool):
        source, target = (session.redo, session.undo) if redo else (session.undo, session.redo)
        if source:
            target.append(snapshot(settings))
            restore(settings, source.pop())
            self.changed(context, cam_obj, reset_pitch=False)

    def set_axis(self, session, settings, letter):
        """Assign ``letter`` to the active vanishing point, swapping with the one that had it."""
        self.push_undo(session, snapshot(settings))
        count = 2 if settings.vp_count != "3" else 3
        attrs = [f"vp{i}_axis" for i in range(1, count + 1)]
        active = attrs[min(session.active_vp, count - 1)]
        old = getattr(settings, active)
        with calibrate.suspended():
            for attr in attrs:
                other = getattr(settings, attr)
                if attr != active and other[1] == letter:
                    setattr(settings, attr, other[0] + old[1])
            setattr(settings, active, old[0] + letter)

    def drag(self, context, session, settings, cam_obj, view, event, mouse):
        if session.drag_key == "pitch":
            solution = calibrate.cached_solution(cam_obj.data)
            if solution is None:
                return
            base, y0 = session.pitch_drag
            y = view.region_to_px(*mouse)[1]
            py, f = solution.principal_point[1], solution.focal_px
            # Moving the horizon up means tilting the camera down.
            delta = math.atan((y - py) / f) - math.atan((y0 - py) / f)
            settings.pitch_offset = base - delta
            return
        dx, dy = mouse[0] - session.last_mouse[0], mouse[1] - session.last_mouse[1]
        session.last_mouse = mouse
        if event.shift:
            dx, dy = dx * FINE_FACTOR, dy * FINE_FACTOR
        pos = view.to_region(calibrate.handle(settings, session.drag_key))
        pos = (pos[0] + dx, pos[1] + dy)
        if event.ctrl:
            target = self.snap_target(settings, view, session.drag_key, mouse)
            if target is not None:
                pos = target
        calibrate.set_handle(settings, session.drag_key, view.to_norm(*pos))
        self.changed(context, cam_obj, reset_pitch=True)


# ----------------------------------------------------------------------------
# Panel helpers


def _panel_camera(context):
    cam = calibrate.view_camera(context)
    return cam if cam is not None and cam.data.ftc.image is not None else None


class FTC_OT_apply(Operator):
    """Solve the calibration and write it into the camera"""

    bl_idname = "ftc.apply"
    bl_label = "Apply"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _panel_camera(context) is not None

    def execute(self, context):
        cam_obj = _panel_camera(context)
        solution = calibrate.update(context, cam_obj, apply=True)
        if solution is None:
            self.report({"ERROR"}, cam_obj.data.ftc.results.error or "The calibration cannot be solved")
            return {"CANCELLED"}
        return {"FINISHED"}


class FTC_OT_reset(Operator):
    """Reset the guides to their default layout"""

    bl_idname = "ftc.reset"
    bl_label = "Reset Guides"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _panel_camera(context) is not None

    def execute(self, context):
        cam_obj = _panel_camera(context)
        settings = cam_obj.data.ftc
        session = FTC_OT_calibrate._session
        if session is not None and session.camera_name == cam_obj.name:
            session.undo.append(snapshot(settings))
        with calibrate.suspended():
            calibrate.reset_handles(settings)
            settings.pitch_offset = 0.0
        calibrate.settings_changed(cam_obj.data, context, reset_pitch=True)
        return {"FINISHED"}


class FTC_OT_anchor_cursor(Operator):
    """Place the calibrated origin at the current 3D cursor location and rotation (stored)"""

    bl_idname = "ftc.anchor_cursor"
    bl_label = "Anchor to 3D Cursor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _panel_camera(context) is not None

    def execute(self, context):
        cam_obj = _panel_camera(context)
        settings = cam_obj.data.ftc
        loc, rot, _ = context.scene.cursor.matrix.decompose()
        matrix = rot.to_matrix().to_4x4()
        matrix.translation = loc
        with calibrate.suspended():
            settings.anchor_matrix = matrix
        settings.use_anchor = True
        if FTC_OT_calibrate._session is None:
            calibrate.update(context, cam_obj, apply=True)
        return {"FINISHED"}


classes = (FTC_OT_calibrate, FTC_OT_apply, FTC_OT_reset, FTC_OT_anchor_cursor)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    session = FTC_OT_calibrate._session
    if session is not None and session.handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(session.handler, "WINDOW")
    FTC_OT_calibrate._session = None
    calibrate.session_camera = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
