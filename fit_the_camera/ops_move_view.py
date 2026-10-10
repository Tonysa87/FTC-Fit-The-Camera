# SPDX-License-Identifier: GPL-3.0-or-later
"""Move Along View: slide objects or vertices along the ray from the active camera.

Every point P moves to C + (P - C) * factor, with C the camera position, so it
stays fixed in the camera image and only its distance from the camera changes.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import calibrate

DRAG_SPEED = 0.004
FINE_FACTOR = 0.1
NUMERIC_CHARS = {
    "ZERO": "0",
    "ONE": "1",
    "TWO": "2",
    "THREE": "3",
    "FOUR": "4",
    "FIVE": "5",
    "SIX": "6",
    "SEVEN": "7",
    "EIGHT": "8",
    "NINE": "9",
    "NUMPAD_0": "0",
    "NUMPAD_1": "1",
    "NUMPAD_2": "2",
    "NUMPAD_3": "3",
    "NUMPAD_4": "4",
    "NUMPAD_5": "5",
    "NUMPAD_6": "6",
    "NUMPAD_7": "7",
    "NUMPAD_8": "8",
    "NUMPAD_9": "9",
    "PERIOD": ".",
    "NUMPAD_PERIOD": ".",
    "COMMA": ".",
}


def moved(point: Vector, camera: Vector, factor: float) -> Vector:
    return camera + (point - camera) * factor


def top_level_selection(context, camera_obj):
    """Selected objects, skipping the camera and objects whose parent also moves."""
    selected = {o for o in context.selected_objects if o != camera_obj}
    result = []
    for obj in selected:
        parent = obj.parent
        while parent is not None and parent not in selected:
            parent = parent.parent
        if parent is None:
            result.append(obj)
    return result


class FTC_OT_move_along_view(Operator):
    """Move the selection towards or away from the active camera, keeping it fixed in the camera image"""

    bl_idname = "ftc.move_along_view"
    bl_label = "Move Along View"
    bl_options = {"REGISTER", "UNDO", "BLOCKING", "GRAB_CURSOR_X"}

    factor: FloatProperty(
        name="Distance Factor",
        description="New distance from the camera divided by the current one",
        default=1.0,
        min=1e-4,
        soft_max=10.0,
    )
    scale_objects: BoolProperty(
        name="Scale with Distance",
        description="Scale objects by the same factor so their size in the image does not change",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        if cam is None:
            return False
        if context.mode == "EDIT_MESH":
            return True
        return context.mode == "OBJECT" and any(o != cam for o in context.selected_objects)

    # ------------------------------------------------------------------
    # Applying

    def capture(self, context):
        """Remember the original state, used by the modal loop and to cancel."""
        cam = calibrate.view_camera(context) or context.scene.camera
        self._camera = cam.matrix_world.translation.copy()
        self._objects = []
        self._meshes = []
        if context.mode == "EDIT_MESH":
            for obj in context.objects_in_mode_unique_data:
                if obj.type != "MESH":
                    continue
                bm = bmesh.from_edit_mesh(obj.data)
                verts = {i: v.co.copy() for i, v in enumerate(bm.verts) if v.select}
                if verts:
                    self._meshes.append((obj.name, verts))
        else:
            for obj in top_level_selection(context, cam):
                self._objects.append((obj.name, obj.matrix_world.copy()))

    def reference_distance(self) -> float:
        """Distance from the camera of the median moved point."""
        points = [m.translation for _, m in self._objects]
        for name, verts in self._meshes:
            mw = bpy.data.objects[name].matrix_world
            points += [mw @ co for co in verts.values()]
        if not points:
            return 0.0
        median = sum(points, Vector()) / len(points)
        return (median - self._camera).length

    def apply(self, factor: float) -> None:
        c = self._camera
        for name, original in self._objects:
            obj = bpy.data.objects[name]
            loc, rot, scale = original.decompose()
            if self.scale_objects:
                scale = scale * factor
            obj.matrix_world = Matrix.LocRotScale(moved(loc, c, factor), rot, scale)
        for name, verts in self._meshes:
            obj = bpy.data.objects[name]
            mw = obj.matrix_world
            inv = mw.inverted_safe()
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            for index, co in verts.items():
                bm.verts[index].co = inv @ moved(mw @ co, c, factor)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)

    def execute(self, context):
        self.capture(context)
        if not self._objects and not self._meshes:
            self.report({"WARNING"}, "Nothing selected to move")
            return {"CANCELLED"}
        self.apply(self.factor)
        return {"FINISHED"}

    # ------------------------------------------------------------------
    # Interactive

    def invoke(self, context, event):
        self.capture(context)
        if not self._objects and not self._meshes:
            self.report({"WARNING"}, "Nothing selected to move")
            return {"CANCELLED"}
        self._distance = self.reference_distance()
        self._start_x = event.mouse_x
        self._log_factor = 0.0
        self._last_x = event.mouse_x
        self._typed = ""
        self.factor = 1.0
        context.window_manager.modal_handler_add(self)
        self.status(context)
        return {"RUNNING_MODAL"}

    def status(self, context):
        distance = self._distance * self.factor
        unit = context.scene.unit_settings.system
        shown = self._typed + "|" if self._typed else bpy.utils.units.to_string(unit, "LENGTH", distance, precision=4)
        scale = "  (scaling objects)" if self.scale_objects and self._objects else ""
        context.area.header_text_set(
            f"Move Along View  distance: {shown}  factor: {self.factor:.4f}{scale}  |  "
            "Drag: closer/farther  Shift: fine  type a distance  S: toggle scale  Enter/LMB: confirm  Esc/RMB: cancel"
        )

    def modal(self, context, event):
        if event.type == "MOUSEMOVE" and not self._typed:
            dx = event.mouse_x - self._last_x
            self._last_x = event.mouse_x
            self._log_factor += dx * DRAG_SPEED * (FINE_FACTOR if event.shift else 1.0)
            self.factor = math.exp(self._log_factor)
        elif event.value == "PRESS" and event.type in NUMERIC_CHARS:
            char = NUMERIC_CHARS[event.type]
            if char != "." or "." not in self._typed:
                self._typed += char
        elif event.value == "PRESS" and event.type == "BACK_SPACE":
            self._typed = self._typed[:-1]
        elif event.value == "PRESS" and event.type == "S":
            self.scale_objects = not self.scale_objects
        elif event.value == "PRESS" and event.type in {"RET", "NUMPAD_ENTER", "LEFTMOUSE"}:
            context.area.header_text_set(None)
            return {"FINISHED"}
        elif event.value == "PRESS" and event.type in {"ESC", "RIGHTMOUSE"}:
            self.apply(1.0)
            context.area.header_text_set(None)
            return {"CANCELLED"}
        else:
            return {"RUNNING_MODAL"}

        if not self._typed:
            self.factor = math.exp(self._log_factor)
        else:
            try:
                value = bpy.utils.units.to_value(context.scene.unit_settings.system, "LENGTH", self._typed)
            except ValueError:
                value = None
            if value and value > 0.0 and self._distance > 0.0:
                self.factor = value / self._distance
        self.apply(self.factor)
        self.status(context)
        return {"RUNNING_MODAL"}


def menu_func(self, context):
    self.layout.operator(FTC_OT_move_along_view.bl_idname)


classes = (FTC_OT_move_along_view,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_transform_object.append(menu_func)
    bpy.types.VIEW3D_MT_transform.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_transform.remove(menu_func)
    bpy.types.VIEW3D_MT_transform_object.remove(menu_func)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
