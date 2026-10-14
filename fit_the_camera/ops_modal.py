# SPDX-License-Identifier: GPL-3.0-or-later
"""Interactive calibration in the camera view, plus the panel's helper operators."""

from __future__ import annotations

import contextlib
import math

import bpy
from bpy.app.handlers import persistent
from bpy.app.translations import pgettext_iface as iface_
from bpy.app.translations import pgettext_tip as tip_
from bpy.props import BoolProperty, IntProperty
from bpy.types import Operator

from . import calibrate, draw, ops_orientation, ops_sun
from .ops_load import match_image_aspect
from .solver import cube_top_px

FINE_FACTOR = 0.2
# Handles that only place or scale the scene, not its orientation.
SCALE_KEYS = {"origin", "ref_a", "ref_b", "cube_base", "cube_top", *ops_sun.SUN_KEYS}
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
STATUS_KEYS = (
    "LMB drag: move  Shift: fine + magnifier  Ctrl: snap  1/2/3: axis  F: flip  H: straighten  "
    "Ctrl+Z / Ctrl+Shift+Z: undo/redo  Enter: apply  Esc/RMB: exit"
)
SHADOW_STATUS_KEYS = (
    "Foot, top, shadow tip  |  LMB drag: move  Shift: fine + magnifier  Ctrl: snap  "
    "Ctrl+Z / Ctrl+Shift+Z: undo/redo  Enter/Esc/RMB: done"
)


class Session:
    """State of the running calibration, shared with the draw callback."""

    def __init__(self, camera, area, region, shadow_only=False):
        # Calibrate Shadow: only the shadow handles, the camera left alone.
        self.shadow_only = shadow_only
        self.camera_name = camera.name
        self.camera_ptr = camera.as_pointer()
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
        self.status = ""
        self.handler = None
        # Magnifier on the dragged handle (Shift); the system cursor is hidden
        # meanwhile: with fine dragging it drifts away from the handle.
        self.magnify = False
        self.cursor_window = None


def snapshot(settings) -> dict:
    return {
        "handles": {h.name: tuple(h.co) for h in settings.handles},
        "pitch_offset": settings.pitch_offset,
        "axes": (settings.vp1_axis, settings.vp2_axis, settings.vp3_axis),
        "straighten": settings.straighten,
        "lines": (settings.vp1_lines, settings.vp2_lines, settings.vp3_lines),
    }


def restore(settings, snap: dict) -> None:
    with calibrate.suspended():
        for key, co in snap["handles"].items():
            calibrate.set_handle(settings, key, co)
        settings.pitch_offset = snap["pitch_offset"]
        settings.vp1_axis, settings.vp2_axis, settings.vp3_axis = snap["axes"]
        settings.straighten = snap["straighten"]
        if "lines" in snap:
            settings.vp1_lines, settings.vp2_lines, settings.vp3_lines = snap["lines"]


def session_camera(session):
    """The session's camera object, followed through a rename; ``None`` if gone."""
    obj = draw.session_camera(session)
    if obj is not None and not session.shadow_only:
        calibrate.session_camera = obj.name
    return obj


def clear_header(session) -> None:
    """Remove the session's header text, wherever its area is now."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.as_pointer() == session.area_ptr:
                area.header_text_set(None)
                return


def area_exists(session) -> bool:
    return any(a.as_pointer() == session.area_ptr for s in bpy.data.screens for a in s.areas)


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


MIN_CUBE_PX = 4.0


def above_base(base, top, pos):
    """Keep the dragged cube top ``pos`` at least ``MIN_CUBE_PX`` above the base
    along the edge (``base`` -> ``top``): past the base the cube would flip."""
    axis = (top[0] - base[0], top[1] - base[1])
    length = math.hypot(*axis)
    if length < 1e-6:
        return pos
    u = (axis[0] / length, axis[1] / length)
    lift = MIN_CUBE_PX - ((pos[0] - base[0]) * u[0] + (pos[1] - base[1]) * u[1])
    return (pos[0] + lift * u[0], pos[1] + lift * u[1]) if lift > 0.0 else pos


def set_magnifier(session, window, on: bool) -> None:
    """Show or hide the lens, hiding the system cursor while it is shown."""
    on = on and session.drag_key not in (None, "pitch")
    if on == session.magnify:
        return
    session.magnify = on
    if on and window is not None:
        window.cursor_modal_set("NONE")
        session.cursor_window = window
    elif not on:
        restore_cursor(session)


def restore_cursor(session) -> None:
    window, session.cursor_window = session.cursor_window, None
    if window is not None:
        with contextlib.suppress(ReferenceError):  # the window was closed
            window.cursor_modal_restore()


def push_undo(session, snap) -> None:
    session.undo.append(snap)
    del session.undo[:-UNDO_LIMIT]
    session.redo.clear()


def flip(axis: str) -> str:
    return ("-" if axis.startswith("+") else "+") + axis[1:]


def flip_axis(settings, index: int) -> None:
    """Flip axis ``index`` (1-3) of the vanishing point guides.

    The world is right-handed, so the third axis follows from the first two:
    flipping it flips axis 2, or axis 1 when axis 2 is Z, keeping Z where it is.
    """
    if index == 3:
        index = 1 if settings.vp2_axis[1] == "Z" else 2
    attr = f"vp{index}_axis"
    with calibrate.suspended():
        setattr(settings, attr, flip(getattr(settings, attr)))


class FTC_OT_calibrate(Operator):
    """Edit the calibration guides in the camera view"""

    bl_idname = "ftc.calibrate"
    bl_label = "Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    shadow: BoolProperty(
        name="Shadow Only",
        description="Only the shadow handles of Fit Sun: the guides are hidden and the camera is not changed",
        options={"SKIP_SAVE", "HIDDEN"},
    )

    _session: Session | None = None

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != "VIEW_3D":
            return False
        cam = calibrate.view_camera(context)
        return cam is not None and cam.data.ftc.image is not None

    @classmethod
    def running(cls, shadow: bool | None = None) -> bool:
        """A session runs (of that kind, when ``shadow`` is given)."""
        session = cls._session
        return session is not None and (shadow is None or session.shadow_only == shadow)

    @classmethod
    def description(cls, context, properties):
        if properties.shadow:
            if cls.running(shadow=True):
                return tip_("End placing the shadow handles")
            return tip_(
                "Place the shadow handles in the camera view: the foot and the top of something vertical, the tip "
                "of its shadow. The calibration guides are hidden and the camera is not changed"
            )
        if cls.running(shadow=False):
            return tip_("End the calibration session, keeping the guides")
        return tip_(
            "Edit the calibration guides in the camera view: drag the handles onto lines of the image. "
            "Shortcuts are listed in the header"
        )

    def invoke(self, context, event):
        session = FTC_OT_calibrate._session
        if session is not None and not area_exists(session):
            # Left over by a modal handler Blender dropped (window closed).
            end_session()
        elif session is not None and session.shadow_only == self.shadow:
            # A second click on Calibrate ends the running session.
            session.stop_requested = True
            return {"CANCELLED"}
        elif session is not None:
            # The other kind of session: switch (its modal handler sees no
            # session at its next event and stops).
            end_session()
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
        if match_image_aspect(context.scene, calibrate.image_size(settings)):
            self.report({"INFO"}, "Render height changed to the image's aspect ratio")
        session = Session(cam_obj, area, region, shadow_only=self.shadow)
        session.handler = bpy.types.SpaceView3D.draw_handler_add(draw.draw_overlay, (session,), "WINDOW", "POST_PIXEL")
        FTC_OT_calibrate._session = session
        if self.shadow:
            # Not a calibration session: the camera is not written.
            if calibrate.cached_solution(cam_obj.data) is None:
                calibrate.refresh(cam_obj.data)
        else:
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
        settings = session_camera(session).data.ftc
        if session.shadow_only:
            text = "FTC  " + iface_("Shadow", "FTC") + "  |  " + iface_(SHADOW_STATUS_KEYS)
            if text != session.status:
                session.status = text
                area.header_text_set(text)
            return
        mode = iface_(MODE_NAMES[settings.mode])
        if settings.mode == "VP":
            mode += f" ({settings.vp_count})"
        if settings.freeze:
            mode += "  [" + iface_("Freeze Guides") + "]"
        if settings.straighten:
            mode += "  [" + iface_("Straighten Horizon") + "]"
        text = f"FTC  {mode}  |  " + iface_(STATUS_KEYS)
        if text != session.status:
            session.status = text
            area.header_text_set(text)

    def finish(self, context, *, apply: bool):
        session = FTC_OT_calibrate._session
        cam_obj = session_camera(session) if session else None
        if apply and cam_obj is not None and not session.shadow_only:
            if calibrate.update(context, cam_obj, apply=True) is None:
                error = cam_obj.data.ftc.results.error or "the calibration cannot be solved"
                self.report({"WARNING"}, iface_("Camera not updated: {}").format(error))
            else:
                ops_orientation.sync(context, cam_obj)
        end_session()
        calibrate.tag_redraw(context)
        return {"FINISHED"}

    def cancel(self, context):
        # Blender dropped the modal handler (window closed, file loaded...).
        end_session()

    def pick(self, settings, view, mouse) -> str | None:
        radius = draw.PICK_RADIUS * draw.ui_scale()
        best, best_d = None, radius
        solution = calibrate.cached_solution(settings.id_data)
        if FTC_OT_calibrate._session.shadow_only:
            for key in draw.session_keys(settings, FTC_OT_calibrate._session):
                d = math.dist(view.to_region(draw.handle_co(settings, solution, key)), mouse)
                if d < best_d:
                    best, best_d = key, d
            return best
        if not settings.freeze:
            for key in calibrate.active_handle_keys(settings):
                d = math.dist(view.to_region(draw.handle_co(settings, solution, key)), mouse)
                if d < best_d:
                    best, best_d = key, d
        if solution is not None and best is None and not settings.freeze:
            ph = draw.pitch_handle_px(solution)
            if ph is not None and math.dist(view.px_to_region(ph), mouse) < radius * 1.2:
                best = "pitch"
        return best

    def snap_target(self, settings, view, key, pos):
        radius = draw.PICK_RADIUS * draw.ui_scale() * 1.5
        best, best_d = None, radius
        for other in draw.session_keys(settings, FTC_OT_calibrate._session):
            if other == key:
                continue
            p = view.to_region(draw.handle_co(settings, calibrate.cached_solution(settings.id_data), other))
            d = math.dist(p, pos)
            if d < best_d:
                best, best_d = p, d
        return best

    def push_undo(self, session, snap) -> None:
        push_undo(session, snap)

    def changed(self, context, cam_obj, *, reset_pitch=True, key=None):
        session = FTC_OT_calibrate._session
        if key in ops_sun.SUN_KEYS or (session is not None and session.shadow_only):
            # Not a calibration input: no solve (nor uncertainty), only the sun.
            ops_sun.orient(cam_obj.data.ftc)
            calibrate.tag_redraw(context)
            return
        calibrate.settings_changed(cam_obj.data, context, reset_pitch=reset_pitch)

    # ------------------------------------------------------------------
    # Event loop

    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            # Blender would drop the handler without cancel(): never leave a
            # session behind that nothing can end.
            end_session()
            raise

    def _modal(self, context, event):
        session = FTC_OT_calibrate._session
        if session is None:
            return {"CANCELLED"}
        cam_obj = session_camera(session)
        area, region = find_region(context.window, session.area_ptr, session.region_ptr)
        if session.stop_requested or cam_obj is None or area is None:
            return self.finish(context, apply=False)
        if calibrate.space_camera(area.spaces.active, context.scene) != cam_obj or cam_obj.data.ftc.image is None:
            # The view now looks through another camera (or the image is gone).
            return self.finish(context, apply=False)
        settings = cam_obj.data.ftc
        self.update_status(context, area)
        rv3d = area.spaces.active.region_3d
        view = session.view
        if view is None or rv3d.view_perspective != "CAMERA":
            view = None
        mouse = mouse_in_region(area, region, event)

        if event.type in NAVIGATION_EVENTS:
            return {"PASS_THROUGH"}

        # Dragging -------------------------------------------------------
        if session.drag_key is not None:
            if event.type in {"LEFT_SHIFT", "RIGHT_SHIFT"}:
                set_magnifier(session, context.window, event.value == "PRESS")
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type == "MOUSEMOVE":
                set_magnifier(session, context.window, event.shift)
            if event.type == "MOUSEMOVE" and view is not None:
                raw = (event.mouse_x - region.x, event.mouse_y - region.y)
                self.drag(context, session, settings, cam_obj, view, event, raw)
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                calibrate.defer_uncertainty = False
                if snapshot(settings) != session.drag_start:
                    self.push_undo(session, session.drag_start)
                    self.changed(context, cam_obj, reset_pitch=False, key=session.drag_key)
                set_magnifier(session, context.window, False)
                session.drag_key = None
                session.pitch_drag = None
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
                calibrate.defer_uncertainty = False
                restore(settings, session.drag_start)
                set_magnifier(session, context.window, False)
                key, session.drag_key = session.drag_key, None
                self.changed(context, cam_obj, reset_pitch=False, key=key)
                return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"}

        in_area = area.x <= event.mouse_x < area.x + area.width and area.y <= event.mouse_y < area.y + area.height
        if event.type == "Z" and (event.ctrl or event.oskey):
            # Always the session's own undo: Blender's would go back to before the
            # session (no undo step is pushed while it runs) and lose its edits.
            if event.value == "PRESS":
                self.undo_redo(context, session, settings, cam_obj, redo=event.shift)
            return {"RUNNING_MODAL"}

        if mouse is None:
            # Over the sidebar, header or another area: let Blender handle it,
            # except the calibration shortcuts while the mouse is in this area.
            if session.hover is not None:
                session.hover = None
                area.tag_redraw()
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
                calibrate.defer_uncertainty = True
                session.drag_key = key
                session.drag_start = snapshot(settings)
                session.last_mouse = mouse
                if key == "pitch":
                    session.pitch_drag = (settings.pitch_offset, view.region_to_px(*mouse)[1])
                elif key.startswith("vp"):
                    session.active_vp = int(key[2]) - 1
                elif key.startswith("hz") and settings.mode == "VP":
                    session.active_vp = 1
                set_magnifier(session, context.window, event.shift)
                area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type in {"RET", "NUMPAD_ENTER"}:
            return self.finish(context, apply=True)
        if event.type in {"ESC", "RIGHTMOUSE"}:
            return self.finish(context, apply=False)
        if session.shadow_only and event.type in SHORTCUT_KEYS:
            # Calibration shortcuts: not in a shadow session.
            return {"RUNNING_MODAL"}

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
                # The active group may be left over from another count: clamp it.
                count = int(settings.vp_count)
                last = 3 if count == 3 or (count == 2 and settings.use_third_line) else 2
                flip_axis(settings, min(session.active_vp + 1, last))
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
            # Sun handles may have moved too (the light follows them without Live Update).
            ops_sun.orient(settings)

    def set_axis(self, session, settings, letter):
        """Assign ``letter`` to the active vanishing point, swapping with the one that had it.

        With three vanishing points the third axis follows from the first two, so
        its letter is derived and only the first two are stored.
        """
        self.push_undo(session, snapshot(settings))
        axes = [settings.vp1_axis, settings.vp2_axis]
        if settings.vp_count == "3":
            axes.append("+" + draw.remaining_axis(*axes))
        active = min(session.active_vp, len(axes) - 1)
        old = axes[active]
        for i, other in enumerate(axes):
            if i != active and other[1] == letter:
                axes[i] = other[0] + old[1]
        axes[active] = old[0] + letter
        with calibrate.suspended():
            settings.vp1_axis, settings.vp2_axis = axes[:2]

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
        # Shown position: the cube's top handle stays on the cube's vertical edge.
        solution = calibrate.cached_solution(cam_obj.data)
        start = view.to_region(draw.handle_co(settings, solution, session.drag_key))
        pos = (start[0] + dx, start[1] + dy)
        if session.drag_key == "cube_top":
            pos = above_base(view.to_region(calibrate.handle(settings, "cube_base")), start, pos)
        if event.ctrl:
            target = self.snap_target(settings, view, session.drag_key, mouse)
            if target is not None:
                pos = target
        key = session.drag_key
        calibrate.set_handle(settings, key, view.to_norm(*pos))
        if key == "cube_base" and solution is not None:
            # The base moves the whole cube: its top follows, the scale stays.
            w, h = calibrate.image_size(settings)
            base = calibrate.to_pixels(settings, view.to_norm(*pos))
            plane = calibrate.reference_plane(settings)
            top = cube_top_px(solution, base, calibrate.cube_size(settings), plane)
            if top is not None:
                calibrate.set_handle(settings, "cube_top", (float(top[0] / w), float(top[1] / h)))
        # Handles that only place or scale the scene keep the pitch correction.
        self.changed(context, cam_obj, reset_pitch=key not in SCALE_KEYS, key=key)
        if key == "cube_top":
            # Keep the stored top on the edge, where it is shown.
            solution = calibrate.cached_solution(cam_obj.data)
            if solution is not None:
                calibrate.set_handle(settings, key, draw.handle_co(settings, solution, key))


# ----------------------------------------------------------------------------
# Panel helpers


def _panel_camera(context):
    cam = calibrate.view_camera(context)
    return cam if cam is not None and cam.data.ftc.image is not None else None


class FTC_OT_apply(Operator):
    """Solve the calibration and write it into the camera; a running calibration session ends, like Enter"""

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
        ops_orientation.sync(context, cam_obj)
        if match_image_aspect(context.scene, calibrate.image_size(cam_obj.data.ftc)):
            self.report({"INFO"}, "Render height changed to the image's aspect ratio")
        if FTC_OT_calibrate.running(shadow=False):
            # Like Enter: the modal operator sees no session at its next event and stops.
            end_session()
            calibrate.tag_redraw(context)
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
            push_undo(session, snapshot(settings))
        kept = {key: calibrate.handle(settings, key) for key in ops_sun.SUN_KEYS}
        with calibrate.suspended():
            calibrate.reset_handles(settings)
            # Sun inputs, not guides: they stay on the shadow.
            for key, co in kept.items():
                calibrate.set_handle(settings, key, co)
            settings.pitch_offset = 0.0
        calibrate.settings_changed(cam_obj.data, context, reset_pitch=True)
        return {"FINISHED"}


class FTC_OT_flip_axis(Operator):
    """Flip the direction of this axis"""

    bl_idname = "ftc.flip_axis"
    bl_label = "Flip Axis Direction"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(name="Axis", min=1, max=3, default=1, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return _panel_camera(context) is not None

    @classmethod
    def description(cls, context, properties):
        if properties.index == 3:
            return tip_(
                "Flip the third axis. It follows from the first two (the world is right-handed): "
                "axis 2 flips with it, or axis 1 when axis 2 is Z"
            )
        return tip_("Flip the direction of this axis (the arrow on its first guide)")

    def execute(self, context):
        cam_obj = _panel_camera(context)
        settings = cam_obj.data.ftc
        session = FTC_OT_calibrate._session
        if session is not None and session.camera_name == cam_obj.name:
            push_undo(session, snapshot(settings))
        flip_axis(settings, self.index)
        calibrate.settings_changed(cam_obj.data, context, reset_pitch=True)
        return {"FINISHED"}


class FTC_OT_vp_line(Operator):
    bl_description = (
        "Add a guide line to this vanishing point (up to 6), between its first two lines: more lines average out "
        "the placement errors"
    )

    bl_idname = "ftc.vp_line"
    bl_label = "Guide Lines"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(name="Vanishing Point", min=1, max=3, default=1, options={"SKIP_SAVE"})
    remove: BoolProperty(name="Remove", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return _panel_camera(context) is not None

    @classmethod
    def description(cls, context, properties):
        if properties.remove:
            return tip_("Remove the last guide line of this vanishing point (two stay)")
        return tip_(
            "Add a guide line to this vanishing point (up to 6), between its first two lines: more lines "
            "average out the placement errors"
        )

    def execute(self, context):
        cam_obj = _panel_camera(context)
        settings = cam_obj.data.ftc
        count = calibrate.line_count(settings, self.index)
        new = count - 1 if self.remove else count + 1
        if not 2 <= new <= calibrate.MAX_LINES:
            return {"CANCELLED"}
        session = FTC_OT_calibrate._session
        if session is not None and session.camera_name == cam_obj.name:
            push_undo(session, snapshot(settings))
        with calibrate.suspended():
            if not self.remove:
                first_two = {k: calibrate.handle(settings, k) for k in calibrate.vp_keys(self.index)}
                a, b = calibrate.extra_line(first_two, self.index, new)
                calibrate.set_handle(settings, f"vp{self.index}_{new}a", a)
                calibrate.set_handle(settings, f"vp{self.index}_{new}b", b)
            setattr(settings, f"vp{self.index}_lines", new)
        calibrate.settings_changed(cam_obj.data, context, reset_pitch=True)
        return {"FINISHED"}


classes = (FTC_OT_calibrate, FTC_OT_apply, FTC_OT_reset, FTC_OT_flip_axis, FTC_OT_vp_line)


def end_session() -> None:
    """Drop the running session without touching the scene (its data may be gone)."""
    calibrate.defer_uncertainty = False
    session = FTC_OT_calibrate._session
    if session is not None:
        if session.handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(session.handler, "WINDOW")
        clear_header(session)
        restore_cursor(session)
    draw.free_lens()
    FTC_OT_calibrate._session = None
    calibrate.session_camera = None


@persistent
def _on_load_pre(*_args):
    # Loading a file removes the modal handler: clean up the session with it.
    end_session()


@persistent
def _on_undo(*_args):
    """Blender's undo (Edit menu, Undo History) during a session restores old
    settings: re-solve them, or end the session if the image is gone."""
    session = FTC_OT_calibrate._session
    if session is None:
        # The cached solutions may belong to the undone settings: solve again
        # when next needed (the Fit Sun panel).
        calibrate.forget_solutions()
        return
    cam_obj = session_camera(session)
    if cam_obj is None or cam_obj.data.ftc.image is None:
        session.stop_requested = True
    else:
        calibrate.refresh(cam_obj.data)


HANDLERS = (
    (bpy.app.handlers.load_pre, _on_load_pre),
    (bpy.app.handlers.undo_post, _on_undo),
    (bpy.app.handlers.redo_post, _on_undo),
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for handlers, fn in HANDLERS:
        handlers.append(fn)


def unregister():
    for handlers, fn in HANDLERS:
        if fn in handlers:
            handlers.remove(fn)
    end_session()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
