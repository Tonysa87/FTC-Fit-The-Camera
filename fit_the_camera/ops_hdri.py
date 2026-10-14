# SPDX-License-Identifier: GPL-3.0-or-later
"""Fit HDRI: turn the World's equirectangular HDRI about Z so that its sun lies
on the sun of the photo (Fit Sun). Only the Z rotation of a Mapping node is
changed; the sun's elevation in the HDRI is compared, never changed.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

import bpy
import gpu
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import FloatVectorProperty
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader

from . import calibrate, draw
from .solver.hdri import brightest_point, elevation, luminance, z_rotation

MAPPING_TAG = "ftc_hdri"
THUMB_LONG_SIDE = 1024
# The viewer shows a finer copy (for its magnifier) and takes half the view.
VIEWER_LONG_SIDE = 2048
VIEWER_FRACTION = 0.5
# The HDRI's sun and the computed one differ in elevation beyond this (degrees):
# the shadows will not have the same length.
ELEVATION_WARNING = 10.0
VIEWER_MARGIN = 40.0


def _environments(tree, start, found, seen, path=()) -> None:
    """Environment Textures upstream of the nodes ``start`` of ``tree``, inside
    node groups too (from their active Group Output), each with the group nodes
    that lead to it (outermost first)."""
    stack = list(start)
    while stack:
        node = stack.pop()
        if node.as_pointer() in seen:
            continue
        seen.add(node.as_pointer())
        if node.type == "TEX_ENVIRONMENT":
            found.append((node, path))
        elif node.type == "GROUP" and node.node_tree is not None:
            output = _group_output(node.node_tree)
            if output is not None:
                _environments(node.node_tree, [output], found, seen, path + (node,))
        for socket in node.inputs:
            for link in socket.links:
                if link.is_valid and not link.is_muted:
                    stack.append(link.from_node)


def _group_output(tree):
    return next((n for n in tree.nodes if n.type == "GROUP_OUTPUT" and n.is_active_output), None)


def _found(world) -> list:
    """(Environment Texture, group path) pairs reaching the World output."""
    tree = world.node_tree
    output = next((n for n in tree.nodes if n.type == "OUTPUT_WORLD" and n.is_active_output), None)
    found = []
    _environments(tree, [output] if output is not None else [], found, set())
    return found


def group_path(world, env) -> tuple:
    """Group nodes leading from the World's tree to ``env`` (outermost first)."""
    if world is None or world.node_tree is None:
        return ()
    return next((path for node, path in _found(world) if node == env), ())


def environment(world):
    """The World's Environment Texture node that reaches the output (also inside
    node groups), and why not (empty when usable). Several: the first by name,
    with a warning."""
    if world is None or world.node_tree is None:
        return None, "The World has no nodes: add an Environment Texture with an HDRI"
    if not world.is_editable:
        return None, "The World is linked from a library: make it local to fit its HDRI"
    tree = world.node_tree
    found = [node for node, _path in _found(world)]
    if not found:
        return None, "No Environment Texture reaches the World output"
    node = sorted(found, key=lambda n: (n.id_data != tree, n.name))[0]
    if node.image is None:
        return None, "The Environment Texture has no image"
    if node.projection != "EQUIRECTANGULAR":
        return None, "The Environment Texture is not equirectangular: Fit HDRI needs an equirectangular HDRI"
    if not node.id_data.is_editable:
        return None, "The HDRI's node group is linked from a library: make it local to fit its HDRI"
    if any(n.image != node.image for n in found):
        return node, "Several Environment Textures reach the World output: using the first by name"
    if node.id_data != tree and node.id_data.users > 1:
        return node, "The HDRI's node group is used elsewhere too: it turns there as well"
    return node, ""


def same_image(env):
    """Every Environment Texture next to ``env`` (same node tree) showing its
    image (e.g. one for the light and one for the camera): they turn together."""
    return [n for n in env.id_data.nodes if n.type == "TEX_ENVIRONMENT" and n.image == env.image]


def _upstream(socket):
    """Node feeding ``socket``, through reroutes; ``None`` when unlinked (or muted)."""
    while socket.links:
        link = socket.links[0]
        if not link.is_valid or link.is_muted:
            return None
        if link.from_node.type == "REROUTE":
            socket = link.from_node.inputs[0]
            continue
        return link.from_node
    return None


def mapping_of(env):
    """The Mapping node feeding ``env`` (through reroutes), or ``None``."""
    node = _upstream(env.inputs["Vector"])
    return node if node is not None and node.type == "MAPPING" else None


LIMITED = "The HDRI's rotation input cannot take the angle (its min / max): widen them or Fit HDRI cannot turn it"
UNFOLLOWED = "The rotation of the HDRI's Mapping comes from nodes FTC cannot follow back: Fit HDRI cannot turn it"
ANIMATED = "The rotation of the HDRI is keyframed or driven: Fit HDRI cannot turn it"


@dataclass
class Control:
    """The value that sets one component of a Mapping's rotation, found by
    following its links back (a group's input, a Value node, a Combine XYZ
    field...): rotation = scale * value + offset."""

    socket: object
    component: int | None  # index in a vector socket, None for a float one
    scale: float = 1.0
    offset: float = 0.0
    limits: tuple[float, float] | None = None  # a group input's min / max

    def value(self) -> float:
        v = self.socket.default_value
        return float(v[self.component] if self.component is not None else v)

    def get(self) -> float:
        return self.scale * self.value() + self.offset

    def set(self, rotation: float) -> None:
        """Write the value giving ``rotation`` (radians, any turn of it: the one
        closest to the current value that fits the input's limits)."""
        value = (rotation - self.offset) / self.scale
        turn = abs(2.0 * math.pi / self.scale)
        value += round((self.value() - value) / turn) * turn
        if self.limits is not None:
            lo, hi = self.limits
            while value > hi and value - turn >= lo:
                value -= turn
            while value < lo and value + turn <= hi:
                value += turn
            if not lo - 1e-6 <= value <= hi + 1e-6:
                # Blender may store it anyway, but the input says it is out of range.
                raise ValueError(LIMITED)
        if self.component is None:
            self.socket.default_value = value
        else:
            v = list(self.socket.default_value)
            v[self.component] = value
            self.socket.default_value = v
        if abs(_wrap(self.get() - rotation)) > 1e-4:
            raise ValueError(LIMITED)


# Math operations that are a line in their linked input x (the other one a
# constant k): rotation = a * x + b in terms of k, for x first or second.
def _math_line(op: str, k: float, x_first: bool):
    if op == "ADD":
        return 1.0, k
    if op == "SUBTRACT":
        return (1.0, -k) if x_first else (-1.0, k)
    if op == "MULTIPLY":
        return k, 0.0
    if op == "DIVIDE" and x_first and k != 0.0:
        return 1.0 / k, 0.0
    return None


def _source(socket):
    """(output socket, node) feeding ``socket`` through reroutes; ``None`` when
    unlinked or muted (the socket's own value counts)."""
    while socket.links:
        link = socket.links[0]
        if not link.is_valid or link.is_muted:
            return None
        if link.from_node.type == "REROUTE":
            socket = link.from_node.inputs[0]
            continue
        return link.from_socket, link.from_node
    return None


def _interface_limits(tree, identifier):
    for item in tree.interface.items_tree:
        if getattr(item, "identifier", None) == identifier and hasattr(item, "min_value"):
            return float(item.min_value), float(item.max_value)
    return None


def _animated(socket) -> bool:
    from . import calibrate

    try:
        path = socket.path_from_id("default_value")
    except (TypeError, ValueError):
        return False
    return calibrate._animated(socket.id_data, {path})


def rotation_control(mapping, path=(), component: int = 2):
    """The Control of ``mapping``'s rotation ``component`` (Z by default), or
    the reason why there is none. ``path``: the group nodes leading to the
    Mapping's tree (outermost first), to step out through a Group Input."""
    socket, comp = mapping.inputs["Rotation"], component
    scale, offset, limits = 1.0, 0.0, None
    path = tuple(path)
    for _step in range(64):
        source = _source(socket)
        if source is None:
            if _animated(socket):
                return ANIMATED
            if socket.type != ("VECTOR" if comp is not None else "VALUE"):
                return UNFOLLOWED
            return Control(socket, comp, scale, offset, limits)
        out, node = source
        if out.type != ("VECTOR" if comp is not None else "VALUE"):
            return UNFOLLOWED  # a conversion between a vector and a number
        limits = None
        kind = node.type
        if kind == "COMBXYZ" and comp is not None:
            socket, comp = node.inputs[comp], None
        elif kind == "VALUE" and comp is None:
            if _animated(out):
                return ANIMATED
            return Control(out, None, scale, offset)
        elif kind == "MATH" and comp is None and not node.use_clamp:
            a, b = node.inputs[0], node.inputs[1]
            x_first = a.is_linked or not b.is_linked
            x, k = (a, b) if x_first else (b, a)
            if node.operation in ("RADIANS", "DEGREES"):
                line, x = (math.radians(1.0) if node.operation == "RADIANS" else math.degrees(1.0), 0.0), a
            else:
                line = _math_line(node.operation, float(k.default_value), x_first)
                if line is None or k.is_linked:
                    return UNFOLLOWED
            offset += scale * line[1]
            scale *= line[0]
            socket = x
        elif kind == "VECT_MATH" and comp is not None and node.operation in ("ADD", "SUBTRACT", "MULTIPLY", "SCALE"):
            a, b = node.inputs[0], node.inputs[1]
            if node.operation == "SCALE":
                k = node.inputs["Scale"]
                if k.is_linked:
                    return UNFOLLOWED
                line = (float(k.default_value), 0.0)
                x = a
            else:
                x_first = a.is_linked or not b.is_linked
                x, k = (a, b) if x_first else (b, a)
                if k.is_linked:
                    return UNFOLLOWED
                line = _math_line(node.operation, float(k.default_value[comp]), x_first)
                if line is None:
                    return UNFOLLOWED
            offset += scale * line[1]
            scale *= line[0]
            socket = x
        elif kind == "GROUP_INPUT" and path:
            outer = path[-1]
            socket = next((s for s in outer.inputs if s.identifier == out.identifier), None)
            if socket is None:
                return UNFOLLOWED
            limits = _interface_limits(outer.node_tree, out.identifier) if comp is None else None
            path = path[:-1]
            if socket.is_linked:
                limits = None
        elif kind == "GROUP" and node.node_tree is not None:
            inner = _group_output(node.node_tree)
            socket = next((s for s in inner.inputs if s.identifier == out.identifier), None) if inner else None
            if socket is None:
                return UNFOLLOWED
            path = path + (node,)
        else:
            return UNFOLLOWED
        if abs(scale) < 1e-12:
            return UNFOLLOWED
    return UNFOLLOWED


def vector_problem(env, world=None) -> str:
    """Why FTC cannot turn ``env``'s HDRI about Z; empty when it can."""
    node = _upstream(env.inputs["Vector"])
    if node is None or node.type == "TEX_COORD":
        return ""
    if node.type != "MAPPING":
        return "The HDRI's vector comes from other nodes (not a Mapping): Fit HDRI cannot turn it"
    control = rotation_control(node, group_path(world, env))
    return control if isinstance(control, str) else ""


def ensure_mapping(tree, env):
    """The Mapping node of ``env``; inserted (Texture Coordinate > Mapping,
    tagged) when missing, after the Texture Coordinate that fed it, if any."""
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


def get_z(mapping, path=()) -> float:
    """Z turn of ``mapping`` as a Point/Vector rotation (Texture type: inverse),
    read where it comes from; ``nan`` when it cannot be followed."""
    control = rotation_control(mapping, path)
    if isinstance(control, str):
        return math.nan
    z = control.get()
    return -z if mapping.vector_type == "TEXTURE" else z


def set_z(mapping, angle: float, path=()) -> None:
    """Set the Z turn of ``mapping`` for a Point/Vector-type rotation ``angle``
    (a Texture-type mapping applies the inverse), where it comes from: the
    Mapping's own field or the value feeding it (a group's input...)."""
    if mapping.vector_type == "TEXTURE":
        angle = -angle
    control = rotation_control(mapping, path)
    if isinstance(control, str):
        raise ValueError(control)
    control.set(angle)


def tilted(mapping, path=()) -> bool:
    """X/Y rotation or a mirrored / uneven X-Y scale: the sun is matched about Z
    only. An X/Y rotation that cannot be followed back counts as tilted."""
    for axis in (0, 1):
        control = rotation_control(mapping, path, axis)
        if isinstance(control, str) or abs(control.get()) > 1e-6:
            return True
    scale = mapping.inputs["Scale"]
    if scale.is_linked:
        return True
    sx, sy = scale.default_value[0], scale.default_value[1]
    return sx <= 0.0 or sy <= 0.0 or abs(sx - sy) > 1e-6 * abs(sx)


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


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


def reduced(rgb: np.ndarray, long_side=THUMB_LONG_SIDE) -> np.ndarray:
    """``rgb`` averaged by blocks down to ``long_side`` (a thumbnail of a thumbnail)."""
    h, w = rgb.shape[:2]
    k = max(1, math.ceil(max(w, h) / long_side))
    if k == 1:
        return rgb
    th, tw = h // k, w // k
    return rgb[: th * k, : tw * k].reshape(th, k, tw, k, 3).mean(axis=(1, 3))


def fit(settings, scene, uv, state=None):
    """Turn the World's HDRI so that its point ``uv`` (the sun) takes the azimuth
    of the computed sun. Returns (Z angle, elevation difference in degrees,
    warning); ``ValueError`` when it cannot."""
    from . import ops_sun

    state = state or ops_sun.evaluate(settings)
    if state.direction is None:
        raise ValueError(state.error or "No sun yet: set Fit Sun first")
    world = scene.world
    env, problem = environment(world)
    if env is None:
        raise ValueError(problem)
    nodes = same_image(env)
    for node in nodes:
        if why := vector_problem(node, world):
            raise ValueError(why)
    angle = z_rotation(uv[0], state.direction)
    warning = problem
    path = group_path(world, env)
    for node in nodes:
        mapping = ensure_mapping(node.id_data, node)
        set_z(mapping, angle, path)
        if tilted(mapping, path):
            warning = "The HDRI's Mapping has an X or Y rotation or scale: its sun is matched about Z only, check it"
    sun_elevation = math.degrees(math.asin(max(-1.0, min(1.0, state.direction.z))))
    return angle, elevation(uv[1]) - sun_elevation, warning


def follow(settings, scene, state, *, force=False) -> None:
    """Keep a fitted HDRI on the sun when the sun moves. A Mapping turned by hand
    since the last fit stops the following (``force`` takes it over again)."""
    sun = settings.sun
    if not sun.hdri_fitted or scene is None or state is None or state.direction is None:
        return
    world = scene.world
    env, _problem = environment(world)
    if env is None or env.image.name != sun.hdri_image or vector_problem(env, world):
        return
    mapping = mapping_of(env)
    if mapping is None:
        return
    path = group_path(world, env)
    current = get_z(mapping, path)
    if not force and abs(_wrap(current - sun.hdri_angle)) > 1e-4:
        sun.hdri_fitted = False  # the user took over
        return
    angle = z_rotation(sun.hdri_point[0], state.direction)
    if abs(_wrap(angle - current)) > 1e-7:
        for node in same_image(env):
            other = mapping_of(node)
            if other is not None and not vector_problem(node, world):
                try:
                    set_z(other, angle, path)
                except ValueError:  # beyond the rotation input's limits
                    sun.hdri_fitted = False
                    return
    sun.hdri_angle = angle


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
        # Shift: a magnifier on the mouse (region pixels), the system cursor hidden.
        self.mouse = None
        self.magnify = False
        self.cursor_window = None

    def layout(self, region):
        w, h = self.size
        avail_w = max(100.0, region.width - 2 * VIEWER_MARGIN)
        avail_h = max(50.0, region.height - 3 * VIEWER_MARGIN)
        scale = VIEWER_FRACTION * min(avail_w / w, avail_h / h)
        x0 = (region.width - w * scale) / 2.0
        y0 = (region.height - h * scale) / 2.0
        self.rect = (x0, y0, x0 + w * scale, y0 + h * scale)

    def to_region(self, uv):
        x0, y0, x1, y1 = self.rect
        return x0 + uv[0] * (x1 - x0), y0 + uv[1] * (y1 - y0)

    def to_uv(self, x, y):
        x0, y0, x1, y1 = self.rect
        return (x - x0) / (x1 - x0), (y - y0) / (y1 - y0)

    def inside(self, x, y) -> bool:
        u, v = self.to_uv(x, y)
        return 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0

    def set_magnifier(self, window, on: bool) -> None:
        """Show or hide the lens, hiding the system cursor while it is shown
        (the lens has its own cross hair)."""
        if on == self.magnify:
            return
        self.magnify = on
        if on and window is not None:
            window.cursor_modal_set("NONE")
            self.cursor_window = window
        elif not on:
            self.restore_cursor()

    def restore_cursor(self) -> None:
        window, self.cursor_window = self.cursor_window, None
        if window is not None:
            with contextlib.suppress(ReferenceError):  # the window was closed
                window.cursor_modal_restore()


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
        _markers(viewer, viewer.to_region, s)
        if viewer.pick is not None:
            pick = viewer.to_region(viewer.pick)
            draw.text((pick[0] + 14 * s, pick[1] + 6 * s), f"{elevation(viewer.pick[1]):.1f}°", draw.SUN_COLOR)
        hint = bpy.app.translations.pgettext_iface(
            "Click the sun in the HDRI · Shift: magnifier · Enter: apply · Esc: cancel · the cross is the photo's sun"
        )
        draw.text((x0, y1 + 10 * s), hint, draw.WHITE, 12.0)
        if viewer.magnify and viewer.mouse is not None and viewer.inside(*viewer.mouse):
            _lens(viewer, s)
    finally:
        gpu.state.blend_set("NONE")


def _markers(viewer, to_region, s, clip=None) -> None:
    """The proposal (thin ring), the pick (sun ring) and where the photo's sun
    lands after the turn (cross, same column). ``clip``: (centre, radius) of
    the lens, outside which nothing is drawn."""

    def shown(p, size):
        return clip is None or math.dist(p, clip[0]) + size <= clip[1]

    if viewer.proposal is not None and shown(p := to_region(viewer.proposal), 7.0 * s):
        draw.circle(p, 7.0 * s, draw.with_alpha(draw.WHITE, 0.6))
    if viewer.pick is not None:
        if shown(p := to_region(viewer.pick), 11.0 * s):
            draw.circle(p, 11.0 * s, draw.SUN_COLOR)
        c = to_region((viewer.pick[0], 0.5 + viewer.sun_elevation / 180.0))
        r = 6.0 * s
        if shown(c, r * math.sqrt(2.0)):
            cross = [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r), (c[0] - r, c[1] + r), (c[0] + r, c[1] - r)]
            draw.lines(cross, draw.WHITE, 1.0)


def _lens(viewer, s) -> None:
    """Magnifier on the mouse: the HDRI ``draw.LENS_ZOOM`` times larger, with
    its horizon and markers, and a cross hair on the point a click picks."""
    x0, y0, x1, y1 = viewer.rect
    centre = viewer.mouse
    radius = draw.LENS_RADIUS * s
    zoom = draw.LENS_ZOOM
    uv = viewer.to_uv(*centre)
    uv_radius = (radius / (zoom * (x1 - x0)), radius / (zoom * (y1 - y0)))
    draw._lens_disk(centre, radius, viewer.texture, s, uv, uv_radius)
    gpu.state.blend_set("ALPHA")

    def magnified(point_uv):
        x, y = viewer.to_region(point_uv)
        return centre[0] + zoom * (x - centre[0]), centre[1] + zoom * (y - centre[1])

    inner = radius - 1.0 * s
    dy = magnified((0.0, 0.5))[1] - centre[1]
    if abs(dy) < inner:
        dx = math.sqrt(inner * inner - dy * dy)
        draw.lines([(centre[0] - dx, centre[1] + dy), (centre[0] + dx, centre[1] + dy)], draw.HORIZON_COLOR, 1.0)
    _markers(viewer, magnified, s, (centre, inner))
    gap, arm = 3.0 * s, 9.0 * s
    cx, cy = centre
    hair = [(cx - arm, cy), (cx - gap, cy), (cx + gap, cy), (cx + arm, cy)]
    hair += [(cx, cy - arm), (cx, cy - gap), (cx, cy + gap), (cx, cy + arm)]
    draw.lines(hair, draw.WHITE, 1.0)


class FTC_OT_fit_hdri(Operator):
    # One line: a docstring's line breaks would reach the tooltip (and miss its translation).
    bl_description = (
        "Turn the World's HDRI about Z so that its sun takes the direction of the photo's sun: click the sun on "
        "the HDRI (FTC proposes the brightest spot), Enter applies"
    )
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
        angle, difference, warning = fit(settings, context.scene, uv, state)
        sun = settings.sun
        sun.hdri_point = uv
        sun.hdri_image = env.image.name
        sun.hdri_angle = angle
        with calibrate.suspended():
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
                if uv is None:
                    raise ValueError("No clear sun in the HDRI: click it in the Fit HDRI viewer (3D view)")
            self._apply(context, settings, state, env, uv)
        except ValueError as exc:
            self.report({"ERROR"}, bpy.app.translations.pgettext_tip(str(exc)))
            return {"CANCELLED"}
        return {"FINISHED"}

    def invoke(self, context, event):
        close_viewer()
        if context.area is None or context.area.type != "VIEW_3D" or self.point[0] >= 0.0:
            return self.execute(context)
        try:
            settings, state, env = self._prepare(context)
            rgb = thumbnail(env.image, VIEWER_LONG_SIDE)
        except ValueError as exc:
            self.report({"ERROR"}, bpy.app.translations.pgettext_tip(str(exc)))
            return {"CANCELLED"}
        region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        if region is None:
            return self.execute(context)
        sun_elevation = math.degrees(math.asin(max(-1.0, min(1.0, state.direction.z))))
        viewer = Viewer(context.area, region, rgb, brightest_point(luminance(reduced(rgb))), sun_elevation)
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
            if event.type in {"MOUSEMOVE", "LEFT_SHIFT", "RIGHT_SHIFT"}:
                region = next((r for r in context.area.regions if r.as_pointer() == viewer.region_ptr), None)
                if region is not None:
                    viewer.mouse = (event.mouse_x - region.x, event.mouse_y - region.y)
                    viewer.set_magnifier(context.window, event.shift and viewer.inside(*viewer.mouse))
                    if viewer.magnify or event.type != "MOUSEMOVE":
                        context.area.tag_redraw()
                return {"RUNNING_MODAL"}
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
                self.point = viewer.pick  # kept for Adjust Last Operation
                try:
                    self._apply(context, settings, state, env, viewer.pick)
                except ValueError as exc:
                    self.report({"ERROR"}, bpy.app.translations.pgettext_tip(str(exc)))
                    self.finish(context)
                    return {"CANCELLED"}
                self.finish(context)
                return {"FINISHED"}
            if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
                self.finish(context)
                return {"CANCELLED"}
        except Exception:
            self.finish(context)
            raise
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        # Blender drops the modal (file loaded, window closed): drop the viewer too.
        close_viewer()

    def finish(self, context):
        close_viewer()
        if context.area is not None:
            context.area.tag_redraw()


def close_viewer() -> None:
    viewer = FTC_OT_fit_hdri._viewer
    if viewer is not None:
        viewer.restore_cursor()
    if viewer is not None and viewer.handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(viewer.handler, "WINDOW")
    FTC_OT_fit_hdri._viewer = None


@persistent
def _on_load_pre(*_args):
    close_viewer()


classes = (FTC_OT_fit_hdri,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister():
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    close_viewer()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
