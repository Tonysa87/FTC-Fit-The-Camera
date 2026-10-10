# SPDX-License-Identifier: GPL-3.0-or-later
"""Move Along View: slide objects or vertices along the ray from the active camera.

Every point P moves to C + (P - C) * factor, with C the camera position, so it
stays fixed in the camera image and only its distance from the camera changes.

The Ray Gizmo runs the same operator from a handle on the selection, shown in the
camera view: an arrow towards the camera, seen end-on there (the physics sign for
"towards you", a ring with a dot), with chevrons for the horizontal drag.
"""

from __future__ import annotations

import math

import bmesh
import bpy
import gpu
from bpy.props import BoolProperty, FloatProperty
from bpy.types import Gizmo, GizmoGroup, Operator
from mathutils import Matrix, Vector

from . import calibrate
from .ops_modal import FTC_OT_calibrate

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


def ray_frame(centre: Vector, camera: Vector, view_right: Vector) -> Matrix | None:
    """Frame at ``centre`` with z towards the camera and x along the view's right
    direction: a shape in its xy plane is seen face-on from the camera."""
    z = camera - centre
    if z.length < 1e-9:
        return None
    z.normalize()
    x = view_right - view_right.dot(z) * z
    if x.length < 1e-9:
        x = z.orthogonal()
    x.normalize()
    m = Matrix((x, z.cross(x), z)).transposed().to_4x4()
    m.translation = centre
    return m


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
        options={"SKIP_SAVE"},
    )
    release_confirm: BoolProperty(
        name="Confirm on Release",
        description="Finish when the mouse button is released (dragging the Ray Gizmo)",
        default=False,
        options={"HIDDEN", "SKIP_SAVE"},
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
        if not self.properties.is_property_set("scale_objects"):
            self.scale_objects = context.scene.ftc_ray_scale
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
        elif (event.value == "PRESS" and event.type in {"RET", "NUMPAD_ENTER", "LEFTMOUSE"}) or (
            self.release_confirm and event.value == "RELEASE" and event.type == "LEFTMOUSE"
        ):
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


# ----------------------------------------------------------------------
# Ray Gizmo

# Shape units are pixels at 1/1.35 scale: Blender scales gizmos by 75 px (default Gizmo Size) per unit.
GIZMO_SCALE = 1.35 / 75.0
RING = (10.0, 12.0)  # inner, outer radius
DOT = 3.0
CHEVRON = (17.0, 23.0, 4.5)  # inner x, tip x, half height
PICK = 25.0
OUTLINE = 1.0


def _disc(r0: float, r1: float, segments: int = 32) -> list:
    """Triangles of an annulus (a disc when ``r0`` is 0)."""
    tris = []
    for i in range(segments):
        a, b = (2.0 * math.pi * k / segments for k in (i, i + 1))
        p0, p1 = (r0 * math.cos(a), r0 * math.sin(a)), (r0 * math.cos(b), r0 * math.sin(b))
        q0, q1 = (r1 * math.cos(a), r1 * math.sin(a)), (r1 * math.cos(b), r1 * math.sin(b))
        tris += [p0, q0, q1]
        if r0 > 0.0:
            tris += [p0, q1, p1]
    return tris


def _chevrons(grow: float) -> list:
    inner, tip, half = CHEVRON
    tris = []
    for side in (-1.0, 1.0):
        tris += [
            (side * (inner - grow), half + grow * 1.6),
            (side * (inner - grow), -half - grow * 1.6),
            (side * (tip + grow * 1.6), 0.0),
        ]
    return tris


def gizmo_shape(grow: float = 0.0) -> list:
    """Ring, dot and left/right chevrons as 2D triangles; ``grow`` widens every
    part by that many pixels (the dark outline under it)."""
    return _disc(RING[0] - grow, RING[1] + grow) + _disc(0.0, DOT + grow) + _chevrons(grow)


def selection_centre(context, camera_obj) -> Vector | None:
    """Median of what Move Along View moves (as its reference distance), or None."""
    points = []
    if context.mode == "EDIT_MESH":
        for obj in context.objects_in_mode_unique_data:
            if obj.type != "MESH" or not obj.data.total_vert_sel:
                continue
            mw = obj.matrix_world
            points += [mw @ v.co for v in bmesh.from_edit_mesh(obj.data).verts if v.select]
    elif context.mode == "OBJECT":
        points = [o.matrix_world.translation for o in top_level_selection(context, camera_obj)]
    return sum(points, Vector()) / len(points) if points else None


def gizmo_wanted(context) -> bool:
    if not context.scene.ftc_ray_gizmo or FTC_OT_calibrate.running():
        return False
    rv3d = context.region_data
    if rv3d is None or rv3d.view_perspective != "CAMERA":
        return False
    return calibrate.view_camera(context) is not None and context.mode in {"OBJECT", "EDIT_MESH"}


class FTC_GT_ray_handle(Gizmo):
    bl_idname = "FTC_GT_ray_handle"

    __slots__ = ("shape", "outline", "pick")

    def setup(self):
        if not hasattr(self, "shape"):
            self.shape = self.new_custom_shape("TRIS", gizmo_shape())
            self.outline = self.new_custom_shape("TRIS", gizmo_shape(OUTLINE))
            self.pick = self.new_custom_shape("TRIS", _disc(0.0, PICK))

    def draw(self, context):
        # A dark outline keeps the light handle visible on a bright photo.
        batch, shader = self.outline
        gpu.state.blend_set("ALPHA")
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(self.matrix_world)
            shader.uniform_float("color", (0.0, 0.0, 0.0, 0.6))
            batch.draw(shader)
        gpu.state.blend_set("NONE")
        self.draw_custom_shape(self.shape)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.pick, select_id=select_id)


class FTC_GGT_move_along_rays(GizmoGroup):
    bl_idname = "FTC_GGT_move_along_rays"
    bl_label = "Move Along Camera Rays"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}

    @classmethod
    def poll(cls, context):
        return gizmo_wanted(context)

    def setup(self, context):
        gz = self.gizmos.new(FTC_GT_ray_handle.bl_idname)
        gz.target_set_operator(FTC_OT_move_along_view.bl_idname).release_confirm = True
        gz.scale_basis = GIZMO_SCALE
        gz.color = 0.9, 0.9, 0.9
        gz.alpha = 0.9
        gz.color_highlight = 1.0, 1.0, 1.0
        gz.alpha_highlight = 1.0
        self.handle = gz

    def draw_prepare(self, context):
        gz = self.handle
        cam = calibrate.view_camera(context)
        centre = selection_centre(context, cam) if cam is not None else None
        frame = None
        if centre is not None:
            right = context.region_data.view_rotation @ Vector((1.0, 0.0, 0.0))
            frame = ray_frame(centre, cam.matrix_world.translation, right)
        gz.hide = frame is None
        if frame is not None:
            gz.matrix_basis = frame


def _redraw_views(_self, context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def menu_func(self, context):
    self.layout.operator(FTC_OT_move_along_view.bl_idname)


classes = (FTC_OT_move_along_view, FTC_GT_ray_handle, FTC_GGT_move_along_rays)


def register():
    bpy.types.Scene.ftc_ray_gizmo = BoolProperty(
        name="Ray Gizmo",
        description=(
            "Show a handle on the selection in the camera view: drag it left or right to move the selection "
            "along the camera rays (closer or farther, fixed in the image). Shift: fine"
        ),
        default=False,
        update=_redraw_views,
    )
    bpy.types.Scene.ftc_ray_scale = BoolProperty(
        name="Scale with Distance",
        description="Moving along the camera rays also scales objects, so their size in the image does not change",
        default=False,
    )
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_transform_object.append(menu_func)
    bpy.types.VIEW3D_MT_transform.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_transform.remove(menu_func)
    bpy.types.VIEW3D_MT_transform_object.remove(menu_func)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ftc_ray_scale
    del bpy.types.Scene.ftc_ray_gizmo
