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
# Side of the shadow catcher plane, in camera distances from the origin.
CATCHER_SIZE = 10.0
RENDERABLE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL"}

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


def select_only(context, obj) -> None:
    """Make ``obj`` the only selected and the active object, in Object Mode only:
    changing the active object leaves an object in Edit Mode stuck in it."""
    layer = context.view_layer
    if context.mode != "OBJECT" or obj.name not in layer.objects or not obj.visible_get(view_layer=layer):
        return
    for other in layer.objects.selected:
        other.select_set(False)
    obj.select_set(True)
    layer.objects.active = obj


def _role_index_changed(scene, context):
    """Clicking an object in the roles list selects it in the viewport."""
    if 0 <= scene.ftc_role_index < len(scene.objects):
        select_only(context, scene.objects[scene.ftc_role_index])


# ----------------------------------------------------------------------------
# Scene setup


def _try_set(data, prop, value) -> bool:
    """Set an enum whose items depend on the setup (engines, OCIO config)."""
    try:
        setattr(data, prop, value)
    except TypeError:
        return False
    return True


def set_color_management(scene) -> bool:
    """Display settings that give back the photo unchanged. False when the colour
    configuration (OCIO) has no sRGB display or Standard view to set."""
    display, view = scene.display_settings, scene.view_settings
    found = _try_set(display, "display_device", "sRGB") and _try_set(view, "view_transform", "Standard")
    _try_set(view, "look", "None")
    view.exposure = 0.0
    view.gamma = 1.0
    view.use_curve_mapping = False
    view.use_white_balance = False
    scene.render.image_settings.color_management = "FOLLOW_SCENE"
    return found


def color_ready(scene) -> bool:
    """The scene shows the photo unchanged, with a transparent film."""
    view = scene.view_settings
    return (
        scene.render.film_transparent
        and scene.display_settings.display_device == "sRGB"
        and view.view_transform == "Standard"
        and view.look == "None"
        and view.exposure == 0.0
        and view.gamma == 1.0
        and not view.use_curve_mapping
        and not view.use_white_balance
    )


def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def compositor_tree(scene):
    """The scene compositor made by FTC, reusing it if present. A tree made by
    the user is kept in the file (fake user) and replaced."""
    tree = scene.compositing_node_group
    if tree is None or not tree.get(TREE_TAG):
        if tree is not None:
            tree.use_fake_user = True
        # An FTC tree left without users (the scene got another one) is reused.
        tree = next((t for t in bpy.data.node_groups if t.get(TREE_TAG) and t.users == 0), None)
        if tree is None:
            tree = bpy.data.node_groups.new(TREE_NAME, "CompositorNodeTree")
            tree[TREE_TAG] = True
        scene.compositing_node_group = tree
    elif tree.users > 1:
        # Shared with another scene: rebuilding it would change that scene too.
        tree = tree.copy()
        scene.compositing_node_group = tree
    return tree


def build_compositor(scene, image, layer_name: str, shadow_pass: bool):
    """Render of the view layer ``layer_name`` over the photo, the photo
    darkened by the Shadow Catcher pass."""
    tree = compositor_tree(scene)
    tree.nodes.clear()
    tree.interface.clear()
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    nodes, link = tree.nodes, tree.links.new

    render = nodes.new("CompositorNodeRLayers")
    render.layer = layer_name
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


def set_alpha_output(image) -> None:
    """Keep the output format if it stores alpha, otherwise switch to PNG."""
    try:
        image.color_mode = "RGBA"
    except TypeError:
        if getattr(image, "media_type", "IMAGE") != "IMAGE":
            image.media_type = "IMAGE"
        image.file_format = "PNG"
        image.color_mode = "RGBA"


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
        render = scene.render
        settings = calibrated_camera(context).data.ftc
        warnings = []
        if self.use_cycles and not _try_set(render, "engine", "CYCLES"):
            warnings.append("Cycles is not available (add-on disabled): engine unchanged")
        cycles = render.engine == "CYCLES"
        if not set_color_management(scene):
            warnings.append("Custom colour configuration: set a view that leaves the photo unchanged by hand")
        render.film_transparent = True
        # A cropped border render would squeeze the whole photo into the region.
        render.use_crop_to_border = False
        fit_scene_to_image(scene, calibrate.image_size(settings))
        over_photo = self.output == "PHOTO"
        for layer in scene.view_layers:
            if hasattr(layer, "cycles"):
                layer.cycles.use_pass_shadow_catcher = over_photo and cycles
        if over_photo:
            build_compositor(scene, settings.image, context.view_layer.name, shadow_pass=cycles)
            if sum(layer.use for layer in scene.view_layers) > 1:
                warnings.append("Only the active view layer is composited over the photo")
            if not settings.image.has_data and not settings.image.size[0]:
                warnings.append("The photo file is missing: the render will have no background")
        else:
            drop_compositor(scene)
            if scene.compositing_node_group is not None:
                # A compositor of the user's would not give the plain transparent render.
                render.use_compositing = False
                warnings.append("Compositing turned off for the transparent output")
            set_alpha_output(render.image_settings)
        if not cycles and has_catchers(scene):
            warnings.append("Shadow catchers work only in Cycles")
        for text in warnings:
            self.report({"WARNING"}, text)
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
        flags = helper.filter_items_by_name(
            self.filter_name, self.bitflag_filter_item, objects, "name", reverse=self.use_filter_invert
        )
        if not flags:
            flags = [self.bitflag_filter_item] * len(objects)
        flags = [f if o.type in RENDERABLE else 0 for f, o in zip(flags, objects)]
        order = helper.sort_items_by_name(objects, "name") if self.use_filter_sort_alpha else []
        return flags, order


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


def catcher_object(settings, scene):
    """The shadow catcher plane made for this camera, if still in the scene."""
    obj = settings.shadow_catcher
    return obj if obj is not None and obj.name in scene.objects else None


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
        size = CATCHER_SIZE * settings.results.distance
        obj = catcher_object(settings, context.scene)
        if obj is None:
            obj = bpy.data.objects.new(CATCHER_NAME, bpy.data.meshes.new(CATCHER_NAME))
            (context.collection or context.scene.collection).objects.link(obj)
            settings.shadow_catcher = obj
        elif obj.data.users > 1:
            # Shared with a linked duplicate: reshape a copy only.
            obj.data = obj.data.copy()
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2)
        bm.to_mesh(obj.data)
        bm.free()
        obj.matrix_world = calibrate.alignment_matrix(settings) @ calibrate.reference_frame(settings)
        obj.ftc_role = "CATCHER"
        # Wireframe in the viewport, so it does not cover the photo.
        obj.display_type = "WIRE"
        select_only(context, obj)
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
