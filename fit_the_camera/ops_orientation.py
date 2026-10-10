# SPDX-License-Identifier: GPL-3.0-or-later
"""Transform Orientation "FTC": the photo's calibrated axes in the scene.

With Align to Scene the calibrated world is moved onto a target, so its axes are
no longer the scene's: the orientation lets Blender's own gizmo, G/R/S with axis
constraints and snapping work along them. Without an alignment it equals Global.
It is created or updated on Apply and by the Align to Scene operators.
"""

import bpy
from bpy.types import Operator
from mathutils import Matrix

from . import calibrate

NAME = "FTC"


def orientation_matrix(settings) -> Matrix:
    """3x3 rotation whose columns are the calibrated X, Y, Z axes in the scene."""
    return calibrate.alignment_matrix(settings).to_quaternion().normalized().to_matrix()


def find(scene):
    """The scene's "FTC" orientation, or None. Python has no list of custom
    orientations: a slot is switched to it for a moment and back."""
    slot = scene.transform_orientation_slots[0]
    previous = slot.type
    try:
        slot.type = NAME
    except TypeError:
        return None
    orientation = slot.custom_orientation
    if previous != NAME:
        slot.type = previous
    return orientation


def _view3d_override(context) -> dict | None:
    """Context members for ``transform.create_orientation`` (it needs the main
    region of a 3D view, also when called from the sidebar)."""
    window = context.window or next(iter(context.window_manager.windows), None)
    if window is None:
        return None
    areas = [context.area] if context.area is not None and context.area.type == "VIEW_3D" else []
    areas += [a for a in window.screen.areas if a.type == "VIEW_3D"]
    for area in areas:
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is not None:
            return {"window": window, "screen": window.screen, "area": area, "region": region}
    return None


def create(context):
    """Add the "FTC" orientation (None without a 3D view to create it from)."""
    override = _view3d_override(context)
    if override is None:
        return None
    # From the view: the other sources need an active object or a selection.
    with context.temp_override(**override):
        bpy.ops.transform.create_orientation(name=NAME, use_view=True, use=False, overwrite=True)
    return find(context.scene)


def sync(context, cam_obj, *, create_missing: bool = True):
    """Set the "FTC" orientation to the calibrated axes of ``cam_obj``."""
    scene = context.scene
    orientation = find(scene)
    if orientation is None and create_missing:
        orientation = create(context)
    if orientation is not None:
        orientation.matrix = orientation_matrix(cam_obj.data.ftc)
    return orientation


def in_use(scene) -> bool:
    return scene.transform_orientation_slots[0].type == NAME


class FTC_OT_use_orientation(Operator):
    bl_description = (
        'Make the "FTC" transform orientation (the photo\'s calibrated axes, also after Align to Scene) '
        "the viewport's orientation: gizmo, G/R/S axes and snapping follow the photo. "
        "Click again to go back to Global"
    )
    bl_idname = "ftc.use_orientation"
    bl_label = "FTC Orientation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = calibrate.view_camera(context)
        return in_use(context.scene) or (cam is not None and cam.data.ftc.image is not None)

    def execute(self, context):
        slot = context.scene.transform_orientation_slots[0]
        if in_use(context.scene):
            slot.type = "GLOBAL"
            return {"FINISHED"}
        if sync(context, calibrate.view_camera(context)) is None:
            self.report({"ERROR"}, "No 3D view to create the orientation from")
            return {"CANCELLED"}
        slot.type = NAME
        return {"FINISHED"}


classes = (FTC_OT_use_orientation,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
