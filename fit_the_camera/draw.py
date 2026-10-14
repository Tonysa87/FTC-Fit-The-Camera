# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport overlay: guides, handles, verification grid, horizon and magnifier.

Everything is drawn in region pixels with the built-in ``gpu`` shaders, which
work on every GPU backend (OpenGL, Vulkan, Metal).
"""

from __future__ import annotations

import math
import textwrap

import blf
import bpy
import gpu
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from . import calibrate, ops_sun
from .solver.common import SolverError, plane_frame, vanishing_point
from .solver.scale import CUBE_EDGES, cube_corners, cube_top_px
from .solver.sun import shadow_tip_for

HANDLE_RADIUS = 8.0
HANDLE_TICK = 3.5
PICK_RADIUS = 12.0
GUIDE_WIDTH = 1.0
GRID_LINES = 10

WHITE = (1.0, 1.0, 1.0, 1.0)
HORIZON_COLOR = (1.0, 0.85, 0.25, 0.9)
NEUTRAL = (0.9, 0.9, 0.9, 1.0)
ERROR_COLOR = (1.0, 0.35, 0.3, 1.0)
SUN_COLOR = (1.0, 0.6, 0.15, 1.0)
# Length of the north arrow, as a fraction of the camera distance to the origin.
NORTH_LENGTH = 0.15


MAX_DASHES = 200

# Magnifier shown on the dragged handle while Shift is held (fine dragging).
LENS_RADIUS = 100.0
LENS_ZOOM = 4.0
LENS_SEGMENTS = 64
LENS_BACKGROUND = (0.12, 0.12, 0.12, 1.0)


def ui_scale() -> float:
    # Zero when Blender runs without a user interface.
    return bpy.context.preferences.system.ui_scale or 1.0


def axis_colors() -> dict[str, tuple]:
    ui = bpy.context.preferences.themes[0].user_interface
    return {
        "X": (*ui.axis_x, 1.0),
        "Y": (*ui.axis_y, 1.0),
        "Z": (*ui.axis_z, 1.0),
    }


def with_alpha(color, alpha):
    return (color[0], color[1], color[2], color[3] * alpha)


# ----------------------------------------------------------------------------
# Image <-> region mapping


class View:
    """Maps normalised image coordinates to region pixels through the camera frame."""

    def __init__(self, x0, y0, x1, y1, image_size):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.image_size = image_size

    @classmethod
    def try_create(cls, region, rv3d, cam_obj, scene, image_size):
        """View of the camera frame in ``region``, or ``None`` outside camera view."""
        if rv3d is None or rv3d.view_perspective != "CAMERA":
            return None
        frame = cam_obj.data.view_frame(scene=scene)
        mw = cam_obj.matrix_world
        pts = [location_3d_to_region_2d(region, rv3d, mw @ v) for v in frame]
        if any(p is None for p in pts):
            return None
        xs, ys = [p.x for p in pts], [p.y for p in pts]
        if max(xs) - min(xs) < 1.0 or max(ys) - min(ys) < 1.0:
            return None
        return cls(min(xs), min(ys), max(xs), max(ys), image_size)

    def to_region(self, co):
        return (self.x0 + co[0] * (self.x1 - self.x0), self.y0 + co[1] * (self.y1 - self.y0))

    def to_norm(self, x, y):
        return ((x - self.x0) / (self.x1 - self.x0), (y - self.y0) / (self.y1 - self.y0))

    def px_to_region(self, px):
        w, h = self.image_size
        return self.to_region((px[0] / w, px[1] / h))

    def region_to_px(self, x, y):
        u, v = self.to_norm(x, y)
        w, h = self.image_size
        return (u * w, v * h)

    @property
    def pixels_per_image_px(self) -> float:
        return (self.x1 - self.x0) / self.image_size[0]


# ----------------------------------------------------------------------------
# Solution geometry (in image pixels)


def project(solution, points) -> np.ndarray:
    """Project world points (in the solved frame) to image pixels; NaN behind the camera."""
    pts = np.atleast_2d(np.asarray(points, float))
    cam = (pts - solution.position) @ solution.rotation
    out = np.full((len(pts), 2), np.nan)
    front = cam[:, 2] < -1e-9
    out[front] = solution.principal_point + solution.focal_px * cam[front, :2] / (-cam[front, 2:3])
    return out


def project_segment(solution, a, b, near):
    """Project a world segment, clipped in front of the camera; ``None`` if hidden."""
    ca = solution.rotation.T @ (np.asarray(a, float) - solution.position)
    cb = solution.rotation.T @ (np.asarray(b, float) - solution.position)
    za, zb = ca[2], cb[2]
    if za > -near and zb > -near:
        return None
    if za > -near or zb > -near:
        t = (-near - za) / (zb - za)
        clipped = ca + t * (cb - ca)
        if za > -near:
            ca = clipped
        else:
            cb = clipped
    p, f = solution.principal_point, solution.focal_px
    return p + f * ca[:2] / -ca[2], p + f * cb[:2] / -cb[2]


def clip_line_to_rect(point, direction, w, h):
    """Clip the infinite line ``point + t*direction`` to the rectangle [0,w]x[0,h]."""
    t0, t1 = -math.inf, math.inf
    for p, d, lo, hi in ((point[0], direction[0], 0.0, w), (point[1], direction[1], 0.0, h)):
        if abs(d) < 1e-12:
            if p < lo or p > hi:
                return None
            continue
        a, b = (lo - p) / d, (hi - p) / d
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
    if t0 > t1:
        return None
    return (point[0] + t0 * direction[0], point[1] + t0 * direction[1]), (
        point[0] + t1 * direction[0],
        point[1] + t1 * direction[1],
    )


def horizon_line(solution):
    """Image line of the plane Z = 0 at infinity, as (point, direction) in pixels."""
    n = solution.rotation.T @ np.array([0.0, 0.0, 1.0])
    g = math.hypot(n[0], n[1])
    if g < 1e-9:
        return None
    p, f = solution.principal_point, solution.focal_px
    # Points q with n . (q - p, -f) = 0.
    k = n[2] * f / (g * g)
    point = (p[0] + k * n[0], p[1] + k * n[1])
    return point, (-n[1] / g, n[0] / g)


def pitch_handle_px(solution):
    """Where the horizon crosses the vertical line through the image centre."""
    line = horizon_line(solution)
    if line is None:
        return None
    (px, py), (dx, dy) = line
    w, h = solution.image_size
    if abs(dx) < 1e-9:
        return None
    t = (w / 2.0 - px) / dx
    return (w / 2.0, min(max(py + t * dy, 0.0), float(h)))


def vanishing_point_px(settings, index):
    """Least-squares vanishing point of guide group ``index`` (1-based), or ``None``."""
    size = calibrate.image_size(settings)
    try:
        v = vanishing_point(calibrate.group_lines(settings, index), float(max(size)))
    except (ValueError, np.linalg.LinAlgError, calibrate.SolverError):
        return None
    if abs(v[2]) < 1e-12:
        return None
    return float(v[0]), float(v[1])


def scale_cube(settings, solution):
    """World corners of the scale cube (see ``solver.scale.cube_corners``), or ``None``."""
    if solution is None or not calibrate.cube_visible(settings):
        return None
    base = calibrate.to_pixels(settings, calibrate.handle(settings, "cube_base"))
    return cube_corners(solution, base, calibrate.cube_size(settings), calibrate.reference_plane(settings))


def handle_co(settings, solution, key):
    """Normalised position where handle ``key`` is shown and picked. The cube's top
    handle sits on the top of the cube's vertical edge: the solver only uses the
    height along that edge."""
    if key == "cube_top" and solution is not None and calibrate.cube_visible(settings):
        base = calibrate.to_pixels(settings, calibrate.handle(settings, "cube_base"))
        top = cube_top_px(solution, base, calibrate.cube_size(settings), calibrate.reference_plane(settings))
        if top is not None:
            w, h = solution.image_size
            return (float(top[0] / w), float(top[1] / h))
    return calibrate.handle(settings, key)


def length_text(unit_system, value) -> str:
    """A length in scene units as Blender shows it (with the unit scale)."""
    scale = bpy.context.scene.unit_settings.scale_length or 1.0
    return bpy.utils.units.to_string(unit_system, "LENGTH", value * scale, precision=3)


def plane_axes(plane):
    """World axis letters of a reference plane's x, y and normal."""
    frame = plane_frame(plane)
    return tuple("XYZ"[int(np.argmax(np.abs(frame[:, i])))] for i in range(3))


# ----------------------------------------------------------------------------
# Primitives

_shaders: dict[str, gpu.types.GPUShader] = {}


def _shader(name):
    shader = _shaders.get(name)
    if shader is None:
        shader = _shaders[name] = gpu.shader.from_builtin(name)
    return shader


def lines(coords, color, width=1.0):
    """Draw separate segments; ``coords`` is a flat list of 2D points, two per segment."""
    if not coords:
        return
    shader = _shader("POLYLINE_UNIFORM_COLOR")
    shader.bind()
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    shader.uniform_float("lineWidth", width * ui_scale())
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINES", {"pos": [(x, y, 0.0) for x, y in coords]}).draw(shader)


def dashed(a, b, color, width=1.0, dash=8.0):
    length = math.dist(a, b)
    if length < 1e-6:
        return
    # Far vanishing points get longer dashes rather than millions of them.
    n = min(MAX_DASHES, max(1, int(length / (dash * ui_scale()))))
    coords = []
    for i in range(0, n, 2):
        t0, t1 = i / n, min(1.0, (i + 1) / n)
        coords += [(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)]
        coords += [(a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)]
    lines(coords, color, width)


def circle(center, radius, color, width=1.0, segments=24):
    cx, cy = center
    pts = [
        (cx + radius * math.cos(2 * math.pi * i / segments), cy + radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments + 1)
    ]
    coords = []
    for i in range(segments):
        coords += [pts[i], pts[i + 1]]
    lines(coords, color, width)


def diamond_outline(center, radius, color):
    cx, cy = center
    pts = [(cx + radius, cy), (cx, cy + radius), (cx - radius, cy), (cx, cy - radius)]
    coords = []
    for i in range(4):
        coords += [pts[i], pts[(i + 1) % 4]]
    lines(coords, color, 1.0)


def text(position, string, color=WHITE, size=11.0):
    font = 0
    blf.size(font, size * ui_scale())
    blf.enable(font, blf.SHADOW)
    blf.shadow(font, 3, 0.0, 0.0, 0.0, 0.8)
    blf.color(font, *color)
    blf.position(font, position[0], position[1], 0.0)
    blf.draw(font, string)
    blf.disable(font, blf.SHADOW)


def handle_radius(hovered=False) -> float:
    return HANDLE_RADIUS * ui_scale() * (1.25 if hovered else 1.0)


def handle_marker(pos, color, *, hovered=False, active=False, frozen=False, first=False):
    """Target symbol: thin ring crossed by four short ticks, centre left clear so
    the exact image point under the handle stays visible."""
    s = ui_scale()
    r = handle_radius(hovered or active)
    inner, outer = r - HANDLE_TICK * s, r + HANDLE_TICK * s
    x, y = pos
    ticks = [
        (x - outer, y), (x - inner, y), (x + inner, y), (x + outer, y),
        (x, y - outer), (x, y - inner), (x, y + inner), (x, y + outer),
    ]  # fmt: skip
    if frozen:
        color = with_alpha(color, 0.45)
    width = 1.6 if hovered or active else 1.0
    lines(ticks, color, width)
    circle(pos, r, color, width, segments=32)
    if first:
        circle(pos, r + 2.0 * HANDLE_TICK * s, color, 1.0, segments=32)


ARROW_SIZE = 10.5


def segment(a, b, color, width=1.0, trim_a=True, trim_b=True, arrow=False, arrow_back=False):
    """Guide line between two handles, stopped at the handle rings. ``arrow``
    adds a chevron before the second handle (before the first with
    ``arrow_back``): the positive axis direction."""
    if arrow and arrow_back:
        a, b, trim_a, trim_b = b, a, trim_b, trim_a
    length = math.dist(a, b)
    r = handle_radius()
    cut = r * (trim_a + trim_b)
    if length <= cut:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    ta = r if trim_a else 0.0
    tb = r if trim_b else 0.0
    end = (b[0] - ux * tb, b[1] - uy * tb)
    coords = [(a[0] + ux * ta, a[1] + uy * ta), end]
    size = ARROW_SIZE * ui_scale()
    if arrow and length > cut + 2.0 * size:
        for side in (1.0, -1.0):
            coords += [end, (end[0] - size * (ux - 0.5 * side * uy), end[1] - size * (uy + 0.5 * side * ux))]
    lines(coords, color, width)


# ----------------------------------------------------------------------------
# Overlay


class clipped_to:
    """Context manager restricting drawing to the camera frame."""

    def __init__(self, view):
        self.rect = (
            int(math.floor(view.x0)),
            int(math.floor(view.y0)),
            int(math.ceil(view.x1 - view.x0)),
            int(math.ceil(view.y1 - view.y0)),
        )

    def __enter__(self):
        self.previous = gpu.state.scissor_get()
        gpu.state.scissor_test_set(True)
        gpu.state.scissor_set(*self.rect)

    def __exit__(self, *exc):
        gpu.state.scissor_set(*self.previous)
        gpu.state.scissor_test_set(False)


def _grid(view, solution, opacity, plane="XY"):
    """Verification grid on the reference plane through the origin."""
    dist = float(np.linalg.norm(solution.position))
    if dist <= 0.0:
        return
    spacing = 10.0 ** math.floor(math.log10(dist / 4.0))
    extent = GRID_LINES * spacing
    near = 1e-3 * dist
    colors = axis_colors()
    frame = plane_frame(plane)
    u, v = frame[:, 0], frame[:, 1]
    # Colour each centre line with the world axis it runs along.
    u_axis, v_axis = "XYZ"[int(np.argmax(np.abs(u)))], "XYZ"[int(np.argmax(np.abs(v)))]
    neutral = (0.85, 0.85, 0.85, 0.45 * opacity)
    groups = {u_axis: [], v_axis: [], "N": []}
    for i in range(-GRID_LINES, GRID_LINES + 1):
        c = i * spacing
        for axis, a, b in (
            (u_axis, -extent * u + c * v, extent * u + c * v),
            (v_axis, c * u - extent * v, c * u + extent * v),
        ):
            seg = project_segment(solution, a, b, near)
            if seg is None:
                continue
            groups[axis if i == 0 else "N"] += [view.px_to_region(seg[0]), view.px_to_region(seg[1])]
    lines(groups["N"], neutral, 1.0)
    lines(groups[u_axis], with_alpha(colors[u_axis], opacity), 1.0)
    lines(groups[v_axis], with_alpha(colors[v_axis], opacity), 1.0)


def _horizon(view, solution):
    line = horizon_line(solution)
    if line is None:
        return
    w, h = solution.image_size
    seg = clip_line_to_rect(line[0], line[1], w, h)
    if seg is not None:
        lines([view.px_to_region(seg[0]), view.px_to_region(seg[1])], HORIZON_COLOR, 1.0)


def _cube(view, solution, settings, unit_system):
    """Wireframe scale cube, each edge in the colour of the world axis it runs along."""
    corners = scale_cube(settings, solution)
    if corners is None:
        return
    colors = axis_colors()
    near = 1e-3 * float(np.linalg.norm(solution.position))
    for axis, edges in zip(plane_axes(calibrate.reference_plane(settings)), CUBE_EDGES):
        coords = []
        for i, j in edges:
            seg = project_segment(solution, corners[i], corners[j], near)
            if seg is not None:
                coords += [view.px_to_region(seg[0]), view.px_to_region(seg[1])]
        lines(coords, with_alpha(colors[axis], 0.9), 1.0)
    top = project(solution, corners[4])[0]
    if not np.isnan(top).any():
        s = ui_scale()
        pos = view.px_to_region(top)
        size = length_text(unit_system, calibrate.cube_size(settings))
        text((pos[0] + 12 * s, pos[1] + 4 * s), size, NEUTRAL)


def _origin_gizmo(view, solution, settings):
    colors = axis_colors()
    dist = float(np.linalg.norm(solution.position))
    length = 0.08 * dist
    origin = project(solution, [0.0, 0.0, 0.0])[0]
    if np.isnan(origin).any():
        return
    o = view.px_to_region(origin)
    for axis, vec in (("X", (length, 0, 0)), ("Y", (0, length, 0)), ("Z", (0, 0, length))):
        tip = project(solution, [vec])[0]
        if not np.isnan(tip).any():
            segment(o, view.px_to_region(tip), colors[axis], 1.0, trim_b=False)


def _north(view, solution, settings):
    """North arrow and sun direction on the horizontal plane through the origin."""
    state = ops_sun.evaluate(settings, solution)
    if state.y_bearing is None:
        return
    to_calibrated = ops_sun.scene_rotation(settings).T
    length = NORTH_LENGTH * float(np.linalg.norm(solution.position))
    origin = project(solution, [0.0, 0.0, 0.0])[0]
    if np.isnan(origin).any():
        return
    o = view.px_to_region(origin)
    s = ui_scale()
    north = np.array(ops_sun.north_vector(state.y_bearing))
    arrows = [(north, WHITE, "N", True)]
    if state.direction is not None:
        flat = np.array([state.direction.x, state.direction.y, 0.0])
        if np.linalg.norm(flat) > 1e-6:
            arrows.append(
                (flat / np.linalg.norm(flat), SUN_COLOR, bpy.app.translations.pgettext_iface("Sun", "FTC"), False)
            )
    for vec, color, label, solid in arrows:
        tip = project(solution, [to_calibrated @ vec * length])[0]
        if np.isnan(tip).any():
            continue
        t = view.px_to_region(tip)
        if solid:
            segment(o, t, color, 1.0, trim_a=False, trim_b=False, arrow=True)
        else:
            dashed(o, t, color, 1.0, 5.0)
        text((t[0] + 6 * s, t[1] + 6 * s), label, color)


def _shadow(view, solution, settings):
    """The vertical object, the sun ray through its top to the shadow tip, and
    where the sun of the date and place would put that tip (a cross)."""
    foot, top, tip = (view.to_region(calibrate.handle(settings, k)) for k in ops_sun.SHADOW_KEYS)
    segment(foot, top, SUN_COLOR, 1.0)
    if settings.sun.shadow_plane == "XY":
        segment(foot, tip, with_alpha(SUN_COLOR, 0.5), 1.0)
    dashed(top, tip, SUN_COLOR, 1.0, 5.0)
    if settings.sun.source != "TIME":
        return
    state = ops_sun.evaluate(settings, solution)
    if state.direction is None:
        return
    to_calibrated = ops_sun.scene_rotation(settings).T
    try:
        hit = shadow_tip_for(solution, ops_sun.shadow_of(settings), to_calibrated @ np.array(state.direction))
    except SolverError:
        return
    if hit is None:
        return
    px = project(solution, [hit])[0]
    if np.isnan(px).any():
        return
    c = view.px_to_region(px)
    r = 5.0 * ui_scale()
    lines([(c[0] - r, c[1] - r), (c[0] + r, c[1] + r), (c[0] - r, c[1] + r), (c[0] + r, c[1] - r)], WHITE, 1.0)


def axis_letter(label: str) -> str:
    return label.lstrip("+-")


def session_camera(session):
    """The session's camera object, followed through a rename; ``None`` if gone."""
    obj = bpy.data.objects.get(session.camera_name)
    if obj is None or obj.as_pointer() != session.camera_ptr:
        obj = next((o for o in bpy.data.objects if o.as_pointer() == session.camera_ptr), None)
        if obj is not None:
            session.camera_name = obj.name
    return obj if obj is not None and obj.type == "CAMERA" else None


def draw_overlay(session):
    """POST_PIXEL draw callback for the calibration session."""
    context = bpy.context
    region = context.region
    if region is None or region.as_pointer() != session.region_ptr:
        return
    cam_obj = session_camera(session)
    if cam_obj is None:
        return
    settings = cam_obj.data.ftc
    view = View.try_create(region, context.region_data, cam_obj, context.scene, calibrate.image_size(settings))
    # Events use the frame of the last draw, when camera and view matrices agree.
    session.view = view
    if view is None:
        return
    solution = calibrate.cached_solution(cam_obj.data)
    unit_system = context.scene.unit_settings.system
    draw_guides(view, settings, solution, session, unit_system)
    if magnifying(session):
        draw_lens(view, settings, solution, session, unit_system)


def session_keys(settings, session) -> list[str]:
    """Handles shown (and picked) in ``session``: only the shadow's in Calibrate Shadow."""
    keys = calibrate.active_handle_keys(settings)
    if getattr(session, "shadow_only", False):
        keys = [k for k in keys if k in ops_sun.SHADOW_KEYS]
    return keys


def draw_guides(view, settings, solution, session, unit_system):
    """Draw the whole overlay for ``settings`` into the current framebuffer."""
    colors = axis_colors()
    s = ui_scale()
    # Calibrate Shadow: the shadow and its handles over the grid, horizon and origin.
    shadow_only = getattr(session, "shadow_only", False)

    gpu.state.blend_set("ALPHA")
    try:
        if solution is not None:
            if settings.show_grid and settings.grid_opacity > 0.0:
                with clipped_to(view):
                    _grid(view, solution, settings.grid_opacity, calibrate.reference_plane(settings))
            _horizon(view, solution)
            if not shadow_only:
                with clipped_to(view):
                    _cube(view, solution, settings, unit_system)

        frozen = settings.freeze and not shadow_only
        keys = session_keys(settings, session)
        labels = [settings.vp1_axis, settings.vp2_axis, settings.vp3_axis]

        def hpos(key):
            return view.to_region(handle_co(settings, solution, key))

        if shadow_only:
            pass
        elif settings.mode == "VP":
            count = int(settings.vp_count)
            third_line = count == 2 and settings.use_third_line
            if count == 3 or third_line:
                labels[2] = third_axis(labels[0], labels[1])
            for i in range(1, count + 1):
                color = colors[axis_letter(labels[i - 1])]
                k = calibrate.group_keys(settings, i)
                width = GUIDE_WIDTH * (1.6 if session.active_vp == i - 1 else 1.0)
                segs = [hpos(key) for key in k]
                pairs = [(segs[n], segs[n + 1]) for n in range(0, len(segs), 2)]
                # The first guide carries the axis sign: it gets the arrow. The
                # third axis follows from the first two: show where it really runs.
                back = i == 3 and runs_backwards(settings, solution, labels[2], k[0], k[1])
                segment(segs[0], segs[1], color, width, arrow=i < 3 or solution is not None, arrow_back=back)
                for a, b in pairs[1:]:
                    segment(a, b, color, width)
                vp = vanishing_point_px(settings, i)
                if vp is not None:
                    vpr = view.px_to_region(vp)
                    for a, b in pairs:
                        near = b if math.dist(b, vpr) < math.dist(a, vpr) else a
                        d = math.dist(near, vpr)
                        if d > handle_radius():
                            t = handle_radius() / d
                            start = (near[0] + (vpr[0] - near[0]) * t, near[1] + (vpr[1] - near[1]) * t)
                            dashed(start, vpr, with_alpha(color, 0.5), 1.0)
                mid = ((segs[0][0] + segs[1][0]) / 2, (segs[0][1] + segs[1][1]) / 2)
                text((mid[0] + 8 * s, mid[1] + 8 * s), labels[i - 1], color)
            if count == 1:
                color = colors[axis_letter(settings.vp2_axis)]
                segment(hpos("hz_a"), hpos("hz_b"), color, GUIDE_WIDTH, arrow=True)
                text((hpos("hz_b")[0] + 8 * s, hpos("hz_b")[1] + 8 * s), settings.vp2_axis, color)
            if third_line:
                color = colors[axis_letter(labels[2])]
                a, b = hpos("vp3_1a"), hpos("vp3_1b")
                back = runs_backwards(settings, solution, labels[2], "vp3_1a", "vp3_1b")
                segment(a, b, color, GUIDE_WIDTH, arrow=solution is not None, arrow_back=back)
                text(((a[0] + b[0]) / 2 + 8 * s, (a[1] + b[1]) / 2 + 8 * s), labels[2], color)
            if settings.scale_mode == "REFERENCE":
                color = colors[settings.ref_axis]
                a, b = hpos("ref_a"), hpos("ref_b")
                dashed(a, b, color, 1.0, 5.0)
                length = length_text(unit_system, settings.ref_length)
                text((b[0] + 8 * s, b[1] - 16 * s), length, color)
        elif settings.mode == "RECT":
            pts = [hpos(f"rect_{i}") for i in range(4)]
            first, second = plane_axes(calibrate.reference_plane(settings))[:2]
            edge_colors = [colors[first], colors[second], colors[first], colors[second]]
            for i in range(4):
                segment(pts[i], pts[(i + 1) % 4], edge_colors[i], GUIDE_WIDTH)
        else:
            segment(hpos("hz_a"), hpos("hz_b"), HORIZON_COLOR, GUIDE_WIDTH)

        if solution is not None:
            _origin_gizmo(view, solution, settings)
            if settings.sun.show_north:
                _north(view, solution, settings)
            if ops_sun.shadow_in_use(settings):
                _shadow(view, solution, settings)

        if solution is not None and not shadow_only and settings.mode == "VP" and int(settings.vp_count) == 3:
            pp = view.px_to_region(solution.principal_point)
            lines(
                [(pp[0] - 8 * s, pp[1]), (pp[0] + 8 * s, pp[1]), (pp[0], pp[1] - 8 * s), (pp[0], pp[1] + 8 * s)],
                NEUTRAL,
                1.0,
            )

        for key in keys:
            if key == "origin":
                color = WHITE
            elif key == "pp":
                color = NEUTRAL
            elif key.startswith("vp"):
                color = colors[axis_letter(labels[int(key[2]) - 1])]
            elif key.startswith("ref"):
                color = colors[settings.ref_axis]
            elif key.startswith("cube"):
                color = colors[plane_axes(calibrate.reference_plane(settings))[2]]
            elif key in ops_sun.SHADOW_KEYS:
                color = SUN_COLOR
            elif key.startswith("hz"):
                color = colors[axis_letter(settings.vp2_axis)] if settings.mode == "VP" else HORIZON_COLOR
            else:
                first, second = plane_axes(calibrate.reference_plane(settings))[:2]
                color = colors[first] if key in ("rect_0", "rect_1") else colors[second]
            handle_marker(
                hpos(key),
                color,
                hovered=key == session.hover,
                active=key == session.drag_key,
                frozen=frozen,
                first=key == "rect_0",
            )

        if solution is not None and not shadow_only:
            ph = pitch_handle_px(solution)
            if ph is not None:
                pos = view.px_to_region(ph)
                hovered = session.hover == "pitch" or session.drag_key == "pitch"
                diamond_outline(pos, handle_radius(hovered) + 2.0 * s, HORIZON_COLOR)

        res = settings.results
        if shadow_only:
            pass
        elif not res.valid and res.error:
            text((view.x0 + 10 * s, view.y1 - 22 * s), res.error, ERROR_COLOR, 13.0)
        elif res.warnings:
            chars = max(30, int((view.x1 - view.x0 - 20 * s) / (6.5 * s)))
            wrapped = [w for line in res.warnings.splitlines() for w in textwrap.wrap(line, chars)]
            for i, line in enumerate(wrapped):
                text((view.x0 + 10 * s, view.y1 - (22 + 16 * i) * s), line, HORIZON_COLOR, 12.0)
    finally:
        gpu.state.blend_set("NONE")


# ----------------------------------------------------------------------------
# Magnifier


def magnifying(session) -> bool:
    """The lens is shown while a handle (not the pitch diamond) is dragged with Shift."""
    return bool(getattr(session, "magnify", False)) and session.drag_key not in (None, "pitch")


def lens_view(view, centre, zoom, size) -> View:
    """``view`` magnified ``zoom`` times about the region point ``centre``, moved
    so that ``centre`` lands in the middle of a ``size`` x ``size`` buffer."""
    half = size / 2.0

    def moved(x, y):
        return (half + (x - centre[0]) * zoom, half + (y - centre[1]) * zoom)

    x0, y0 = moved(view.x0, view.y0)
    x1, y1 = moved(view.x1, view.y1)
    return View(x0, y0, x1, y1, view.image_size)


_lens_buffer: dict = {}


def _lens_target(size: int):
    """Cached texture and framebuffer for the lens; float, so dark tones keep their
    precision. A plain framebuffer, not a ``GPUOffScreen``: leaving a nested
    offscreen binds the window's framebuffer instead of the region's, while
    ``GPUFrameBuffer.bind()`` restores the one that was bound."""
    if _lens_buffer.get("size") != size:
        texture = gpu.types.GPUTexture((size, size), format="RGBA16F")
        _lens_buffer.update(size=size, texture=texture, framebuffer=gpu.types.GPUFrameBuffer(color_slots=texture))
    return _lens_buffer["texture"], _lens_buffer["framebuffer"]


def free_lens() -> None:
    # Textures and framebuffers are freed with their last reference.
    _lens_buffer.clear()


def _photo(view, image) -> None:
    """The photo over the camera frame of ``view``, as the camera background shows it."""
    try:
        texture = gpu.texture.from_image(image)
    except Exception:  # no pixels (missing file): the lens shows the guides only
        return
    shader = _shader("IMAGE")
    shader.bind()
    shader.uniform_sampler("image", texture)
    corners = [(view.x0, view.y0), (view.x1, view.y0), (view.x1, view.y1), (view.x0, view.y1)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    batch_for_shader(shader, "TRIS", {"pos": corners, "texCoord": uvs}, indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)


def _disk(centre, radius, texture, uv_centre=(0.5, 0.5), uv_radius=(0.5, 0.5)) -> None:
    """``texture`` mapped onto a disk: the ellipse ``uv_centre`` ± ``uv_radius``
    of the texture (by default its inscribed circle) fills the disk."""
    shader = _shader("IMAGE")
    shader.bind()
    shader.uniform_sampler("image", texture)
    pos, uvs = [centre], [uv_centre]
    for i in range(LENS_SEGMENTS + 1):
        a = 2.0 * math.pi * i / LENS_SEGMENTS
        pos.append((centre[0] + radius * math.cos(a), centre[1] + radius * math.sin(a)))
        uvs.append((uv_centre[0] + uv_radius[0] * math.cos(a), uv_centre[1] + uv_radius[1] * math.sin(a)))
    tris = [(0, i, i + 1) for i in range(1, LENS_SEGMENTS + 1)]
    batch_for_shader(shader, "TRIS", {"pos": pos, "texCoord": uvs}, indices=tris).draw(shader)


def draw_lens(view, settings, solution, session, unit_system) -> None:
    """Magnifier centred on the dragged handle: the photo and the whole overlay
    ``LENS_ZOOM`` times larger, the handle fixed in the middle while the photo
    slides under it."""
    s = ui_scale()
    radius = LENS_RADIUS * s
    size = int(math.ceil(2.0 * radius))
    centre = view.to_region(handle_co(settings, solution, session.drag_key))
    zoomed = lens_view(view, centre, LENS_ZOOM, size)
    texture, framebuffer = _lens_target(size)
    viewport = gpu.state.viewport_get()
    with framebuffer.bind():
        gpu.state.viewport_set(0, 0, size, size)
        framebuffer.clear(color=LENS_BACKGROUND)
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(
                Matrix(((2.0 / size, 0, 0, -1.0), (0, 2.0 / size, 0, -1.0), (0, 0, 1.0, 0), (0, 0, 0, 1.0)))
            )
            if settings.image is not None:
                _photo(zoomed, settings.image)
            draw_guides(zoomed, settings, solution, session, unit_system)
    gpu.state.viewport_set(*viewport)
    _lens_disk(centre, radius, texture, s)


def _lens_disk(centre, radius, texture, s, uv_centre=(0.5, 0.5), uv_radius=(0.5, 0.5)) -> None:
    """The lens: ``texture`` on a disk (see ``_disk``), its rim and zoom label."""
    gpu.state.blend_set("ALPHA")
    try:
        _disk(centre, radius, texture, uv_centre, uv_radius)
        circle(centre, radius + 1.0 * s, (0.0, 0.0, 0.0, 0.6), 1.0, segments=LENS_SEGMENTS)
        circle(centre, radius, (1.0, 1.0, 1.0, 0.9), 1.5, segments=LENS_SEGMENTS)
        corner = (centre[0] + 0.62 * radius, centre[1] + 0.82 * radius)
        text(corner, f"\u00d7{LENS_ZOOM:g}", NEUTRAL)
    finally:
        gpu.state.blend_set("NONE")


def third_axis(a: str, b: str) -> str:
    """Signed third axis of the right-handed frame whose first two axes are ``a``
    and ``b`` (e.g. "+X", "+Y" -> "+Z")."""
    i, j = "XYZ".index(axis_letter(a)), "XYZ".index(axis_letter(b))
    sign = (-1 if a.startswith("-") else 1) * (-1 if b.startswith("-") else 1) * (1 if (j - i) % 3 == 1 else -1)
    return ("+" if sign > 0 else "-") + remaining_axis(a, b)


def runs_backwards(settings, solution, label, key_a, key_b) -> bool:
    """True when the world axis ``label`` runs from handle ``key_b`` towards
    ``key_a`` in the image (see ``solver.vp.orient_along``)."""
    if solution is None:
        return False
    a, b = (np.asarray(calibrate.to_pixels(settings, calibrate.handle(settings, k))) for k in (key_a, key_b))
    d = solution.rotation["XYZ".index(axis_letter(label)), :] * (-1.0 if label.startswith("-") else 1.0)
    velocity = solution.focal_px * d[:2] + d[2] * ((a + b) / 2.0 - solution.principal_point)
    return bool(velocity @ (b - a) < 0.0)


def remaining_axis(a: str, b: str) -> str:
    letters = {"X", "Y", "Z"} - {axis_letter(a), axis_letter(b)}
    return letters.pop() if len(letters) == 1 else "Z"
