# SPDX-License-Identifier: GPL-3.0-or-later
"""Fit HDRI: turn the World's equirectangular HDRI about Z so that its sun lies
on the sun of the photo (Fit Sun). Only the Z rotation of a Mapping node is
changed; the sun's elevation in the HDRI is compared, never changed.
"""

from __future__ import annotations

import math

import bpy
import gpu
import numpy as np
from bpy.props import FloatVectorProperty
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader

from . import calibrate, draw
from .solver.hdri import brightest_point, elevation, luminance, z_rotation

MAPPING_TAG = "ftc_hdri"
THUMB_LONG_SIDE = 1024
# The HDRI's sun and the computed one differ in elevation beyond this (degrees):
# the shadows will not have the same length.
ELEVATION_WARNING = 10.0
VIEWER_MARGIN = 40.0


def environment(world):
    """The World's Environment Texture node that reaches the output, and why
    not (empty when usable). Several: the first, with a warning."""
    if world is None or not world.use_nodes or world.node_tree is None:
        return None, "The World has no nodes: add an Environment Texture with an HDRI"
    tree = world.node_tree
    output = next((n for n in tree.nodes if n.type == "OUTPUT_WORLD" and n.is_active_output), None)
    found = []
    seen = set()
    stack = [output] if output is not None else []
    while stack:
        node = stack.pop()
        if node.as_pointer() in seen:
            continue
        seen.add(node.as_pointer())
        if node.type == "TEX_ENVIRONMENT":
            found.append(node)
        for socket in node.inputs:
            for link in socket.links:
                if link.is_valid and not link.is_muted:
                    stack.append(link.from_node)
    if not found:
        return None, "No Environment Texture reaches the World output"
    node = sorted(found, key=lambda n: n.name)[0]
    if node.image is None:
        return None, "The Environment Texture has no image"
    if node.projection != "EQUIRECTANGULAR":
        return None, "The Environment Texture is not equirectangular: Fit HDRI needs an equirectangular HDRI"
    if len(found) > 1:
        return node, "Several Environment Textures reach the World output: using the first by name"
    return node, ""


def mapping_of(env):
    """The Mapping node feeding ``env`` (directly), or ``None``."""
    vector = env.inputs["Vector"]
    if vector.links and vector.links[0].from_node.type == "MAPPING":
        return vector.links[0].from_node
    return None


def ensure_mapping(tree, env):
    """The Mapping node of ``env``; inserted (Texture Coordinate > Mapping,
    tagged) when missing, between ``env`` and whatever fed its vector."""
    mapping = mapping_of(env)
    if mapping is not None:
        return mapping
    vector = env.inputs["Vector"]
    source = vector.links[0].from_socket if vector.links else None
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping[MAPPING_TAG] = True
    mapping.label = "FTC HDRI"
    mapping.location = (env.location.x - 220.0, env.location.y)
    if source is None:
        coords = tree.nodes.new("ShaderNodeTexCoord")
        coords[MAPPING_TAG] = True
        coords.location = (mapping.location.x - 200.0, mapping.location.y)
        source = coords.outputs["Generated"]
    tree.links.new(source, mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], vector)
    return mapping


def set_z(mapping, angle: float) -> None:
    """Set the Z turn of ``mapping`` for a Point/Vector-type rotation ``angle``
    (a Texture-type mapping applies the inverse)."""
    if mapping.vector_type == "TEXTURE":
        angle = -angle
    rotation = mapping.inputs["Rotation"]
    euler = list(rotation.default_value)
    euler[2] = angle
    rotation.default_value = euler


def tilted(mapping) -> bool:
    """X or Y rotation on the mapping: the sun is matched about Z only."""
    rotation = mapping.inputs["Rotation"]
    return rotation.is_linked or abs(rotation.default_value[0]) > 1e-6 or abs(rotation.default_value[1]) > 1e-6


def thumbnail(image, long_side=THUMB_LONG_SIDE) -> np.ndarray:
    """RGB pixels (rows bottom to top) of ``image`` reduced to ``long_side`` by
    averaging blocks: a sun of a few pixels survives as a bright pixel.

    A file or packed image is reduced by Blender on a copy, then removed (no
    full float copy in Python: a 16k HDRI is 2 GB). A generated or edited
    image is read as it is: a copy would come back regenerated, blank."""
    w, h = image.size
    if not w or not h:
        raise ValueError("The HDRI image cannot be read")
    k = max(1, math.ceil(max(w, h) / long_side))
    if image.source == "GENERATED" or image.is_dirty or k == 1:
        px = np.empty(w * h * 4, dtype=np.float32)
        image.pixels.foreach_get(px)
        rgb = px.reshape(h, w, 4)[..., :3]
        th, tw = h // k, w // k
        if k > 1:
            rgb = rgb[: th * k, : tw * k].reshape(th, k, tw, k, 3).mean(axis=(1, 3))
        return rgb
    tw, th = max(2, w // k), max(1, h // k)
    copy = image.copy()
    try:
        copy.scale(tw, th)
        px = np.empty(tw * th * 4, dtype=np.float32)
        copy.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(copy)
    return px.reshape(th, tw, 4)[..., :3]


def fit(settings, scene, uv, state=None):
    """Turn the World's HDRI so that its point ``uv`` (the sun) takes the azimuth
    of the computed sun. Returns (elevation difference in degrees, warning)."""
    from . import ops_sun

    state = state or ops_sun.evaluate(settings)
    if state.direction is None:
        raise ValueError(state.error or "No sun yet: set Fit Sun first")
    world = scene.world
    env, problem = environment(world)
    if env is None:
        raise ValueError(problem)
    mapping = ensure_mapping(world.node_tree, env)
    set_z(mapping, z_rotation(uv[0], state.direction))
    warning = problem
    if tilted(mapping):
        warning = "The HDRI's Mapping has an X or Y rotation: its sun is matched about Z only, check it"
    sun_elevation = math.degrees(math.asin(max(-1.0, min(1.0, state.direction.z))))
    return elevation(uv[1]) - sun_elevation, warning


def follow(settings, scene, state) -> None:
    """Keep a fitted HDRI on the sun when the sun moves (no warnings)."""
    sun = settings.sun
    if not sun.hdri_fitted or scene is None or state is None or state.direction is None:
        return
    env, _problem = environment(scene.world)
    if env is None or env.image is None or env.image.name != sun.hdri_image:
        return
    mapping = mapping_of(env)
    if mapping is not None and mapping.id_data.is_editable:
        set_z(mapping, z_rotation(sun.hdri_point[0], state.direction))


# ----------------------------------------------------------------------------
# Viewer


def _display(rgb: np.ndarray) -> np.ndarray:
    """Tone-mapped RGBA (0..1) for showing an HDR thumbnail."""
    lum = luminance(rgb)
    key = float(np.median(lum[np.isfinite(lum)])) or 1.0
    x = np.clip(np.nan_to_num(rgb / (4.0 * key)), 0.0, None)
    out = np.ones((*rgb.shape[:2], 4), dtype=np.float32)
    out[..., :3] = (x / (1.0 + x)) ** (1.0 / 2.2)
    return out


class Viewer:
    """State of the running Fit HDRI viewer (one at a time)."""

    def __init__(self, area, region, rgb, proposal, sun_elevation):
        self.area_ptr = area.as_pointer()
        self.region_ptr = region.as_pointer()
        h, w = rgb.shape[:2]
        self.size = (w, h)
        pixels = _display(rgb)
        buf = gpu.types.Buffer("FLOAT", w * h * 4, pixels.ravel())
        self.texture = gpu.types.GPUTexture((w, h), format="RGBA16F", data=buf)
        self.proposal = proposal
        self.pick = proposal
        self.sun_elevation = sun_elevation
        self.handler = None
        self.rect = (0.0, 0.0, 1.0, 1.0)

    def layout(self, region):
        w, h = self.size
        avail_w = max(100.0, region.width - 2 * VIEWER_MARGIN)
        avail_h = max(50.0, region.height - 3 * VIEWER_MARGIN)
        scale = min(avail_w / w, avail_h / h)
        x0 = (region.width - w * scale) / 2.0
        y0 = (region.height - h * scale) / 2.0
        self.rect = (x0, y0, x0 + w * scale, y0 + h * scale)

    def to_region(self, uv):
        x0, y0, x1, y1 = self.rect
        return x0 + uv[0] * (x1 - x0), y0 + uv[1] * (y1 - y0)

    def to_uv(self, x, y):
        x0, y0, x1, y1 = self.rect
        return (x - x0) / (x1 - x0), (y - y0) / (y1 - y0)


def draw_viewer(viewer):
    """POST_PIXEL draw callback of the viewer's region."""
    region = bpy.context.region
    if region is None or region.as_pointer() != viewer.region_ptr:
        return
    paint(viewer, region)


def paint(viewer, region):
    """Draw the viewer into the current framebuffer (``region``: width, height)."""
    viewer.layout(region)
    x0, y0, x1, y1 = viewer.rect
    s = draw.ui_scale()
    gpu.state.blend_set("ALPHA")
    try:
        shader = gpu.shader.from_builtin("IMAGE")
        batch = batch_for_shader(
            shader,
            "TRI_FAN",
            {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1)), "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1))},
        )
        shader.bind()
        shader.uniform_sampler("image", viewer.texture)
        batch.draw(shader)
        # Horizon, frame, the proposal (thin ring), the pick (the sun ring) and
        # where the computed sun lands after the turn (cross, same column).
        horizon = (y0 + y1) / 2.0
        draw.lines([(x0, horizon), (x1, horizon)], draw.HORIZON_COLOR, 1.0)
        draw.lines([(x0, y0), (x1, y0), (x1, y0), (x1, y1), (x1, y1), (x0, y1), (x0, y1), (x0, y0)], draw.NEUTRAL)
        if viewer.proposal is not None:
            draw.circle(viewer.to_region(viewer.proposal), 7.0 * s, draw.with_alpha(draw.WHITE, 0.6))
        if viewer.pick is not None:
            pick = viewer.to_region(viewer.pick)
            draw.circle(pick, 11.0 * s, draw.SUN_COLOR)
            target_v = 0.5 + viewer.sun_elevation / 180.0
            c = viewer.to_region((viewer.pick[0], target_v))
            r = 6.0 * s
            cross = [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r), (c[0] - r, c[1] + r), (c[0] + r, c[1] - r)]
            draw.lines(cross, draw.WHITE, 1.0)
            draw.text((pick[0] + 14 * s, pick[1] + 6 * s), f"{elevation(viewer.pick[1]):.1f}°", draw.SUN_COLOR)
        hint = bpy.app.translations.pgettext_iface(
            "Click the sun in the HDRI · Enter: apply · Esc: cancel · the cross is the photo's sun"
        )
        draw.text((x0, y1 + 10 * s), hint, draw.WHITE, 12.0)
    finally:
        gpu.state.blend_set("NONE")


class FTC_OT_fit_hdri(Operator):
    """Turn the World's HDRI about Z so that its sun takes the direction of the photo's sun: click the sun on
    the HDRI (FTC proposes the brightest spot), Enter applies"""

    bl_idname = "ftc.fit_hdri"
    bl_label = "Fit HDRI"
    bl_options = {"REGISTER", "UNDO"}

    # Scripts and tests: the sun's point on the HDRI, skipping the viewer.
    point: FloatVectorProperty(
        name="Sun Point",
        description="Point of the sun on the HDRI (0..1, origin bottom-left); negative: let FTC find it",
        size=2,
        default=(-1.0, -1.0),
        options={"SKIP_SAVE"},
    )

    _viewer: Viewer | None = None

    @classmethod
    def poll(cls, context):
        cam = calibrate.view_camera(context)
        return cam is not None and cam.data.ftc.image is not None and context.scene.world is not None

    def _prepare(self, context):
        from . import ops_sun

        settings = calibrate.view_camera(context).data.ftc
        state = ops_sun.evaluate(settings)
        if state.direction is None:
            raise ValueError(state.error or "No sun yet: set Fit Sun first")
        env, problem = environment(context.scene.world)
        if env is None:
            raise ValueError(problem)
        return settings, state, env

    def _apply(self, context, settings, state, env, uv):
        difference, warning = fit(settings, context.scene, uv, state)
        sun = settings.sun
        sun.hdri_point = uv
        sun.hdri_image = env.image.name
        sun.hdri_fitted = True
        if warning:
            self.report({"WARNING"}, bpy.app.translations.pgettext_tip(warning))
        if abs(difference) > ELEVATION_WARNING:
            self.report(
                {"WARNING"},
                bpy.app.translations.pgettext_tip(
                    "The HDRI's sun is {:+.0f}° off the photo's in elevation: the shadows will not have the same length"
                ).format(difference),
            )
        calibrate.tag_redraw(context)

    def execute(self, context):
        try:
            settings, state, env = self._prepare(context)
            uv = tuple(self.point)
            if uv[0] < 0.0:
                uv = brightest_point(luminance(thumbnail(env.image)))
            self._apply(context, settings, state, env, uv)
        except ValueError as exc:
            self.report({"ERROR"}, bpy.app.translations.pgettext_tip(str(exc)))
            return {"CANCELLED"}
        return {"FINISHED"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or self.point[0] >= 0.0:
            return self.execute(context)
        try:
            settings, state, env = self._prepare(context)
            rgb = thumbnail(env.image)
        except ValueError as exc:
            self.report({"ERROR"}, bpy.app.translations.pgettext_tip(str(exc)))
            return {"CANCELLED"}
        region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        if region is None:
            return self.execute(context)
        sun_elevation = math.degrees(math.asin(max(-1.0, min(1.0, state.direction.z))))
        viewer = Viewer(context.area, region, rgb, brightest_point(luminance(rgb)), sun_elevation)
        viewer.handler = bpy.types.SpaceView3D.draw_handler_add(draw_viewer, (viewer,), "WINDOW", "POST_PIXEL")
        FTC_OT_fit_hdri._viewer = viewer
        self._state = (settings, state, env)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        viewer = FTC_OT_fit_hdri._viewer
        if viewer is None:
            return {"CANCELLED"}
        try:
            if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
                return {"PASS_THROUGH"}
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                area = context.area
                region = next((r for r in area.regions if r.as_pointer() == viewer.region_ptr), None)
                if region is not None:
                    u, v = viewer.to_uv(event.mouse_x - region.x, event.mouse_y - region.y)
                    if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                        viewer.pick = (u, v)
                        area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS" and viewer.pick is not None:
                settings, state, env = self._state
                self._apply(context, settings, state, env, viewer.pick)
                self.finish(context)
                return {"FINISHED"}
            if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
                self.finish(context)
                return {"CANCELLED"}
        except Exception:
            self.finish(context)
            raise
        return {"RUNNING_MODAL"}

    def finish(self, context):
        close_viewer()
        if context.area is not None:
            context.area.tag_redraw()


def close_viewer() -> None:
    viewer = FTC_OT_fit_hdri._viewer
    if viewer is not None and viewer.handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(viewer.handler, "WINDOW")
    FTC_OT_fit_hdri._viewer = None


classes = (FTC_OT_fit_hdri,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    close_viewer()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
