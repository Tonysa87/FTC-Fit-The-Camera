# SPDX-License-Identifier: GPL-3.0-or-later
"""Align the calibrated reference plane to a target in the scene.

The target is stored as a frame (origin, x, y, normal). The camera is placed so
that the reference plane chosen in the panel (XY, XZ or YZ) lies on it; quarter
turns and a flip resolve the orientation within the plane.
"""

import bmesh
import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import calibrate, ops_orientation
from .ops_modal import FTC_OT_calibrate


def calibrated_camera(context):
    cam = calibrate.view_camera(context)
    return cam if cam is not None and cam.data.ftc.image is not None else None


def frame_matrix(origin, x_axis, normal) -> Matrix:
    """Right-handed frame with ``x_axis`` in the plane and z along ``normal``."""
    z = Vector(normal).normalized()
    x = Vector(x_axis)
    x = (x - x.dot(z) * z).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = origin
    return m


def without_scale(matrix: Matrix) -> Matrix:
    loc, rot, _ = matrix.decompose()
    m = rot.to_matrix().to_4x4()
    m.translation = loc
    return m


def store_target(context, settings, matrix: Matrix, source: str) -> None:
    with calibrate.suspended():
        settings.anchor_matrix = matrix
        settings.align_source = source
        settings.align_rotation = 0
        settings.align_flip = False
    settings.use_anchor = True
    apply_now(context)


def apply_now(context) -> None:
    """Write the camera at once; in a session, re-solve as the session does
    (it writes the camera with Live Update). The "FTC" orientation follows."""
    cam = calibrated_camera(context)
    if cam is None:
        return
    if FTC_OT_calibrate.running() and cam.name == calibrate.session_camera:
        calibrate.settings_changed(cam.data, context, reset_pitch=False)
    else:
        calibrate.update(context, cam, apply=True)
    ops_orientation.sync(context, cam)
    calibrate.tag_redraw(context)


def active_face(context):
    """(object, BMesh, BMFace) of the active or only selected face in Edit Mode,
    or Nones. The BMesh is returned to keep the face valid while it is used."""
    obj = context.edit_object
    if obj is None or obj.type != "MESH":
        return None, None, None
    bm = bmesh.from_edit_mesh(obj.data)
    face = bm.faces.active
    if face is None or not face.select:
        selected = [f for f in bm.faces if f.select]
        face = selected[0] if len(selected) == 1 else None
    return obj, bm, face


class FTC_OT_align_cursor(Operator):
    """Put the reference plane on the 3D cursor: origin at its location, plane axes along its rotation"""

    bl_idname = "ftc.align_cursor"
    bl_label = "3D Cursor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return calibrated_camera(context) is not None

    def execute(self, context):
        settings = calibrated_camera(context).data.ftc
        store_target(context, settings, without_scale(context.scene.cursor.matrix), "3D Cursor")
        return {"FINISHED"}


class FTC_OT_align_selection(Operator):
    bl_description = (
        "Put the reference plane on the selection. Edit Mode: the active face (centre, first edge as X, "
        "normal); with a known rectangle on a 4-sided face its size is taken from the face. "
        "Object Mode: the active object's location and rotation"
    )
    bl_idname = "ftc.align_selection"
    bl_label = "Selection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if calibrated_camera(context) is None:
            return False
        if context.mode == "EDIT_MESH":
            return True
        obj = context.active_object
        return obj is not None and obj != calibrate.view_camera(context)

    def execute(self, context):
        settings = calibrated_camera(context).data.ftc
        if context.mode == "EDIT_MESH":
            obj, _bm, face = active_face(context)
            if face is None:
                self.report({"ERROR"}, "Select one face (or make one face active)")
                return {"CANCELLED"}
            mw = obj.matrix_world
            verts = [mw @ v.co for v in face.verts]
            normal = mw.to_3x3().inverted_safe().transposed() @ face.normal
            # First edge as X, or the next one long enough (and not along the normal).
            edge = next(
                (
                    verts[(i + 1) % len(verts)] - verts[i]
                    for i in range(len(verts))
                    if (verts[(i + 1) % len(verts)] - verts[i]).cross(normal).length > 1e-9
                ),
                None,
            )
            if normal.length < 1e-9 or edge is None:
                self.report({"ERROR"}, "The face has no area: select another face")
                return {"CANCELLED"}
            centre = sum(verts, Vector()) / len(verts)
            store_target(context, settings, frame_matrix(centre, edge, normal.normalized()), f"{obj.name} (face)")
            if settings.mode == "RECT" and len(verts) == 4:
                # The face is the rectangle: corner 0 -> 1 is the first side, 1 -> 2 the second.
                with calibrate.suspended():
                    settings.rect_width = (verts[1] - verts[0]).length
                settings.rect_height = (verts[2] - verts[1]).length
                apply_now(context)
            return {"FINISHED"}
        obj = context.active_object
        store_target(context, settings, without_scale(obj.matrix_world), obj.name)
        return {"FINISHED"}


class FTC_OT_align_clear(Operator):
    """Go back to the scene origin: the calibrated origin and axes are the scene's"""

    bl_idname = "ftc.align_clear"
    bl_label = "Scene Origin"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = calibrated_camera(context)
        return cam is not None and cam.data.ftc.use_anchor

    def execute(self, context):
        calibrated_camera(context).data.ftc.use_anchor = False
        apply_now(context)
        return {"FINISHED"}


class FTC_OT_align_rotate(Operator):
    """Turn the reference plane 90° about its normal on the target (the rectangle's two sides swap with it)"""

    bl_idname = "ftc.align_rotate"
    bl_label = "Rotate 90°"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = calibrated_camera(context)
        return cam is not None and cam.data.ftc.use_anchor

    def execute(self, context):
        settings = calibrated_camera(context).data.ftc
        with calibrate.suspended():
            settings.align_rotation = (settings.align_rotation + 1) % 4
            if settings.mode == "RECT" and settings.align_source.endswith("(face)"):
                settings.rect_width, settings.rect_height = settings.rect_height, settings.rect_width
        apply_now(context)
        return {"FINISHED"}


class FTC_OT_align_flip(Operator):
    """Turn the reference plane over on the target, when the camera ends up behind it"""

    bl_idname = "ftc.align_flip"
    bl_label = "Flip"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = calibrated_camera(context)
        return cam is not None and cam.data.ftc.use_anchor

    def execute(self, context):
        settings = calibrated_camera(context).data.ftc
        with calibrate.suspended():
            settings.align_flip = not settings.align_flip
        apply_now(context)
        return {"FINISHED"}


classes = (FTC_OT_align_cursor, FTC_OT_align_selection, FTC_OT_align_clear, FTC_OT_align_rotate, FTC_OT_align_flip)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
