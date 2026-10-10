# SPDX-License-Identifier: GPL-3.0-or-later
"""Render setup: CG over the photo, and the render roles of the scene objects.

The photo is an sRGB image: it comes out of the render unchanged only with the
Standard view transform (no look, exposure, gamma, curves or white balance),
since AgX, Filmic, ACES and Khronos PBR Neutral tone map it like the CG. The
world is not rendered (transparent film): the compositor puts the render over
the photo, scaled to the render size. In Cycles the photo is first multiplied by
the Shadow Catcher pass, which carries the shadows and the coloured bounce light
the CG casts on the shadow catchers (with the pass on they leave the alpha of the
render). For a transparent output the pass is off and the shadows stay in alpha.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty
from bpy.types import Operator, UIList

from . import calibrate
from .ops_align import calibrated_camera
from .ops_load import fit_scene_to_image

TREE_NAME = "FTC Compositing"
TREE_TAG = "ftc_compositing"
RENDERABLE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL"}

ROLE_ITEMS = [
    (
        "CATCHER",
        "Shadow Catcher",
        "Stand-in for a real surface of the photo: shows the photo, receives the shadows and light of the CG "
        "objects and hides what is behind it (Cycles only)",
        "SHADING_RENDERED",
        0,
    ),
    (
        "HOLDOUT",
        "Holdout",
        "Stand-in for a real object in front: shows the photo and hides the CG objects behind it, without shadows",
        "HOLDOUT_ON",
        1,
    ),
    ("NONE", "No Role", "Remove the role: the object is rendered normally", "X", 2),
]


def _set_catcher(obj, value):
    # The two roles exclude each other.
    obj.is_shadow_catcher = value
    if value:
        obj.is_holdout = False


def _set_holdout(obj, value):
    obj.is_holdout = value
    if value:
        obj.is_shadow_catcher = False


def set_role(obj, role: str) -> None:
    """Only the object's own flags change: nothing is created."""
    obj.is_shadow_catcher = role == "CATCHER"
    obj.is_holdout = role == "HOLDOUT"


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
    """Renderable objects of the scene with their render role"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name, icon="OUTLINER_OB_" + item.type)
        sub = row.row(align=True)
        sub.prop(item, "ftc_catcher", text="Catcher", toggle=True)
        sub.prop(item, "ftc_holdout", text="Holdout", toggle=True)

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
    """Give the selected objects a render role (only their settings change: nothing is created)"""

    bl_idname = "ftc.set_role"
    bl_label = "Set Role of Selected"
    bl_options = {"REGISTER", "UNDO"}

    role: EnumProperty(name="Role", description="Render role", items=ROLE_ITEMS)

    @classmethod
    def poll(cls, context):
        return any(o.type in RENDERABLE for o in context.selected_objects)

    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type in RENDERABLE:
                set_role(obj, self.role)
        if self.role == "CATCHER" and context.scene.render.engine != "CYCLES":
            self.report({"WARNING"}, "Shadow catchers work only in Cycles")
        return {"FINISHED"}


classes = (FTC_OT_prepare_render, FTC_UL_roles, FTC_OT_set_role)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.ftc_catcher = BoolProperty(
        name="Shadow Catcher",
        description=ROLE_ITEMS[0][2],
        get=lambda obj: obj.is_shadow_catcher,
        set=_set_catcher,
    )
    bpy.types.Object.ftc_holdout = BoolProperty(
        name="Holdout",
        description=ROLE_ITEMS[1][2],
        get=lambda obj: obj.is_holdout,
        set=_set_holdout,
    )
    bpy.types.Scene.ftc_role_index = IntProperty(
        name="Active Object", description="Object selected in the roles list", update=_role_index_changed
    )


def unregister():
    del bpy.types.Scene.ftc_role_index
    del bpy.types.Object.ftc_holdout
    del bpy.types.Object.ftc_catcher
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
