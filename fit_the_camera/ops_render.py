# SPDX-License-Identifier: GPL-3.0-or-later
"""Render setup: CG over the photo, object roles and the shadow catcher plane.

The photo is an sRGB image: it comes out of the render unchanged only with the
Standard view transform (no look, exposure, gamma, curves or white balance),
since AgX, Filmic, ACES and Khronos PBR Neutral tone map it like the CG. The
world is not rendered (transparent film): the compositor puts the render over
the photo, scaled to the render size. In Cycles the photo is first multiplied by
the Shadow Catcher pass, which carries the shadows and the coloured bounce light
the CG casts on the shadow catchers (with the pass on they leave the alpha of the
render). For a transparent output the pass is off and the shadows stay in alpha.
"""

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty
from bpy.types import Operator, UIList

from . import calibrate
from .ops_align import calibrated_camera
from .ops_load import fit_scene_to_image

TREE_NAME = "FTC Compositing"
TREE_TAG = "ftc_compositing"
CATCHER_NAME = "FTC Shadow Catcher"
CATCHER_TAG = "ftc_shadow_catcher"
# Side of the shadow catcher plane, in camera distances from the origin.
CATCHER_SIZE = 10.0
RENDERABLE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL"}
ALPHA_FORMATS = {"PNG", "OPEN_EXR", "OPEN_EXR_MULTILAYER", "TIFF", "WEBP", "TARGA", "TARGA_RAW", "JPEG2000", "DPX"}

ROLE_ITEMS = [
    ("OBJECT", "CG Object", "Rendered normally: a virtual object added to the photo", "OBJECT_DATA", 0),
    (
        "CATCHER",
        "Shadow Catcher",
        "Stand-in for a real surface of the photo: shows the photo, receives the shadows and light of the CG "
        "objects and hides what is behind it (Cycles only)",
        "SHADING_RENDERED",
        1,
    ),
    (
        "HOLDOUT",
        "Holdout",
        "Stand-in for a real object in front: shows the photo and hides the CG objects behind it, without shadows",
        "HOLDOUT_ON",
        2,
    ),
    ("HIDDEN", "Hidden", "Not rendered: reference or helper geometry", "HIDE_ON", 3),
]


def _get_role(obj):
    if obj.hide_render:
        return 3
    if obj.is_shadow_catcher:
        return 1
    return 2 if obj.is_holdout else 0


def _set_role(obj, value):
    obj.hide_render = value == 3
    obj.is_shadow_catcher = value == 1
    obj.is_holdout = value == 2


def _role_index_changed(scene, context):
    """Clicking an object in the roles list selects it in the viewport."""
    if not 0 <= scene.ftc_role_index < len(scene.objects):
        return
    obj = scene.objects[scene.ftc_role_index]
    layer = context.view_layer
    if obj.name not in layer.objects or not obj.visible_get(view_layer=layer):
        return
    for other in layer.objects.selected:
        other.select_set(False)
    obj.select_set(True)
    layer.objects.active = obj


# ----------------------------------------------------------------------------
# Scene setup


def set_color_management(scene) -> None:
    """Display settings that give back the photo unchanged."""
    scene.display_settings.display_device = "sRGB"
    view = scene.view_settings
    view.view_transform = "Standard"
    view.look = "None"
    view.exposure = 0.0
    view.gamma = 1.0
    view.use_curve_mapping = False
    view.use_white_balance = False
    scene.render.image_settings.color_management = "FOLLOW_SCENE"


def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def compositor_tree(scene):
    """The scene compositor made by FTC, reusing it if present. A tree made by
    the user is kept in the file (fake user) and replaced."""
    tree = scene.compositing_node_group
    if tree is None or not tree.get(TREE_TAG):
        if tree is not None:
            tree.use_fake_user = True
        tree = bpy.data.node_groups.new(TREE_NAME, "CompositorNodeTree")
        tree[TREE_TAG] = True
        scene.compositing_node_group = tree
    return tree


def build_compositor(scene, image, shadow_pass: bool):
    """Render over the photo, the photo darkened by the Shadow Catcher pass."""
    tree = compositor_tree(scene)
    tree.nodes.clear()
    tree.interface.clear()
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    nodes, link = tree.nodes, tree.links.new

    render = nodes.new("CompositorNodeRLayers")
    render.location = (-300, 160)
    photo = nodes.new("CompositorNodeImage")
    photo.label = "Photo"
    photo.image = image
    photo.location = (-700, -160)
    scale = nodes.new("CompositorNodeScale")
    scale.location = (-460, -160)
    scale.inputs["Type"].default_value = "Render Size"
    scale.inputs["Frame Type"].default_value = "Fit"
    # Extend, not Clip: clipping blends the border pixels with transparency.
    scale.inputs["Extension X"].default_value = "Extend"
    scale.inputs["Extension Y"].default_value = "Extend"
    link(photo.outputs["Image"], scale.inputs["Image"])
    background = scale.outputs["Image"]

    if shadow_pass and "Shadow Catcher" in render.outputs:
        shadows = nodes.new("ShaderNodeMix")
        shadows.label = "Shadows on Photo"
        shadows.data_type = "RGBA"
        shadows.blend_type = "MULTIPLY"
        shadows.location = (-220, -160)
        link(background, _socket(shadows.inputs, "A_Color"))
        link(render.outputs["Shadow Catcher"], _socket(shadows.inputs, "B_Color"))
        background = _socket(shadows.outputs, "Result_Color")

    over = nodes.new("CompositorNodeAlphaOver")
    over.location = (40, 40)
    link(background, over.inputs["Background"])
    link(render.outputs["Image"], over.inputs["Foreground"])
    output = nodes.new("NodeGroupOutput")
    output.location = (280, 80)
    link(over.outputs["Image"], output.inputs[0])
    viewer = nodes.new("CompositorNodeViewer")
    viewer.location = (280, -80)
    link(over.outputs["Image"], viewer.inputs["Image"])
    scene.render.use_compositing = True
    return tree


def drop_compositor(scene) -> None:
    """Remove the FTC compositor from the scene (a user's tree is left alone)."""
    tree = scene.compositing_node_group
    if tree is not None and tree.get(TREE_TAG):
        scene.compositing_node_group = None
        if tree.users == 0:
            bpy.data.node_groups.remove(tree)


def has_catchers(scene) -> bool:
    return any(o.is_shadow_catcher and not o.hide_render for o in scene.objects)


class FTC_OT_prepare_render(Operator):
    """Set up colour management, transparent film and compositor to render the CG over the photo"""

    bl_idname = "ftc.prepare_render"
    bl_label = "Prepare Render"
    bl_options = {"REGISTER", "UNDO"}

    output: EnumProperty(
        name="Output",
        description="What the render gives",
        items=[
            (
                "PHOTO",
                "Over the Photo",
                "The CG over the photo, with the shadows on the shadow catchers: the final image",
            ),
            (
                "ALPHA",
                "Transparent",
                "Only the CG and its shadows on a transparent background, to composite in another program",
            ),
        ],
        default="PHOTO",
    )
    use_cycles: BoolProperty(
        name="Use Cycles",
        description="Switch the render engine to Cycles: EEVEE has no shadow catcher",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return calibrated_camera(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "output", expand=True)
        layout.prop(self, "use_cycles")
        col = layout.column(align=True)
        col.label(text="View Transform: Standard, the photo unchanged", icon="INFO")
        col.label(text="Film: Transparent", icon="BLANK1")

    def execute(self, context):
        scene = context.scene
        settings = calibrated_camera(context).data.ftc
        if self.use_cycles:
            scene.render.engine = "CYCLES"
        cycles = scene.render.engine == "CYCLES"
        set_color_management(scene)
        scene.render.film_transparent = True
        fit_scene_to_image(scene, calibrate.image_size(settings))
        over_photo = self.output == "PHOTO"
        for layer in scene.view_layers:
            if hasattr(layer, "cycles"):
                layer.cycles.use_pass_shadow_catcher = over_photo and cycles
        if over_photo:
            build_compositor(scene, settings.image, shadow_pass=cycles)
        else:
            drop_compositor(scene)
            image = scene.render.image_settings
            if image.file_format not in ALPHA_FORMATS:
                image.file_format = "PNG"
            image.color_mode = "RGBA"
        if not cycles and has_catchers(scene):
            self.report({"WARNING"}, "Shadow catchers work only in Cycles")
        return {"FINISHED"}


# ----------------------------------------------------------------------------
# Object roles


class FTC_UL_roles(UIList):
    """Renderable objects of the scene with their role in the render"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name, icon="OUTLINER_OB_" + item.type)
        row.prop(item, "ftc_role", text="")

    def filter_items(self, context, data, propname):
        objects = getattr(data, propname)
        helper = bpy.types.UI_UL_list
        flags = helper.filter_items_by_name(self.filter_name, self.bitflag_filter_item, objects, "name")
        if not flags:
            flags = [self.bitflag_filter_item] * len(objects)
        flags = [f if o.type in RENDERABLE else 0 for f, o in zip(flags, objects)]
        return flags, helper.sort_items_by_name(objects, "name")


class FTC_OT_set_role(Operator):
    """Give the selected objects a role in the render"""

    bl_idname = "ftc.set_role"
    bl_label = "Set Role of Selected"
    bl_options = {"REGISTER", "UNDO"}

    role: EnumProperty(name="Role", description="Role in the render", items=ROLE_ITEMS)

    @classmethod
    def poll(cls, context):
        return any(o.type in RENDERABLE for o in context.selected_objects)

    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type in RENDERABLE:
                obj.ftc_role = self.role
        return {"FINISHED"}


# ----------------------------------------------------------------------------
# Shadow catcher plane


def catcher_object(scene):
    return next((o for o in scene.objects if o.get(CATCHER_TAG)), None)


class FTC_OT_add_catcher(Operator):
    """Add a shadow catcher plane on the calibrated reference plane, or move the existing one there"""

    bl_idname = "ftc.add_catcher"
    bl_label = "Shadow Catcher Plane"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = calibrated_camera(context)
        return cam is not None and cam.data.ftc.results.valid

    def execute(self, context):
        settings = calibrated_camera(context).data.ftc
        size = CATCHER_SIZE * max(settings.results.distance, calibrate.cube_size(settings), 1e-3)
        obj = catcher_object(context.scene)
        if obj is None:
            mesh = bpy.data.meshes.new(CATCHER_NAME)
            obj = bpy.data.objects.new(CATCHER_NAME, mesh)
            obj[CATCHER_TAG] = True
            (context.collection or context.scene.collection).objects.link(obj)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2)
        bm.to_mesh(obj.data)
        bm.free()
        obj.matrix_world = calibrate.alignment_matrix(settings) @ calibrate.reference_frame(settings)
        obj.ftc_role = "CATCHER"
        # Wireframe in the viewport, so it does not cover the photo.
        obj.display_type = "WIRE"
        layer = context.view_layer
        for other in layer.objects.selected:
            other.select_set(False)
        if obj.name in layer.objects:
            obj.select_set(True)
            layer.objects.active = obj
        if context.scene.render.engine != "CYCLES":
            self.report({"WARNING"}, "Shadow catchers work only in Cycles")
        return {"FINISHED"}


classes = (FTC_OT_prepare_render, FTC_UL_roles, FTC_OT_set_role, FTC_OT_add_catcher)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.ftc_role = EnumProperty(
        name="Render Role",
        description="Role of the object when the CG is rendered over the photo",
        items=ROLE_ITEMS,
        get=_get_role,
        set=_set_role,
    )
    bpy.types.Scene.ftc_role_index = IntProperty(
        name="Active Object", description="Object selected in the roles list", update=_role_index_changed
    )


def unregister():
    del bpy.types.Scene.ftc_role_index
    del bpy.types.Object.ftc_role
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
