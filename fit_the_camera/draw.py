# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport overlay: guides, handles, verification grid and horizon.

Everything is drawn in region pixels with the built-in ``gpu`` shaders, which
work on every GPU backend (OpenGL, Vulkan, Metal).
"""

from __future__ import annotations

import math

import blf
import bpy
import gpu
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader

from . import calibrate
from .solver.common import vanishing_point

HANDLE_RADIUS = 7.0
HANDLE_GAP = 2.5
HANDLE_TICK = 5.0
PICK_RADIUS = 12.0
GUIDE_WIDTH = 2.0
GRID_LINES = 10

WHITE = (1.0, 1.0, 1.0, 1.0)
SHADOW = (0.0, 0.0, 0.0, 0.7)
HORIZON_COLOR = (1.0, 0.85, 0.25, 0.9)
NEUTRAL = (0.9, 0.9, 0.9, 1.0)
ERROR_COLOR = (1.0, 0.35, 0.3, 1.0)


MAX_DASHES = 200


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
    a1, b1, a2, b2 = (calibrate.to_pixels(settings, calibrate.handle(settings, k)) for k in calibrate.vp_keys(index))
    size = calibrate.image_size(settings)
    try:
        v = vanishing_point([(a1, b1), (a2, b2)], float(max(size)))
    except (ValueError, np.linalg.LinAlgError, calibrate.SolverError):
        return None
    if abs(v[2]) < 1e-12:
        return None
    return float(v[0]), float(v[1])


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
    lines(coords, SHADOW, 3.5)
    lines(coords, color, 1.5)


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
    """Hollow ring with a crosshair whose centre is left clear, so the exact
    image point under the handle stays visible."""
    s = ui_scale()
    r = handle_radius(hovered or active)
    gap, reach = HANDLE_GAP * s, r + HANDLE_TICK * s
    x, y = pos
    cross = [
        (x - reach, y), (x - gap, y), (x + gap, y), (x + reach, y),
        (x, y - reach), (x, y - gap), (x, y + gap), (x, y + reach),
    ]  # fmt: skip
    if active:
        color = WHITE
    elif frozen:
        color = with_alpha(color, 0.45)
    # A dark outline under the colour keeps the marker readable on bright images.
    lines(cross, SHADOW, 3.0)
    circle(pos, r, SHADOW, 3.5)
    if first:
        circle(pos, r + 4.0 * s, SHADOW, 3.5)
        circle(pos, r + 4.0 * s, color, 1.5)
    lines(cross, color, 1.0)
    circle(pos, r, color, 1.5)


def segment(a, b, color, width=1.0, trim_a=True, trim_b=True):
    """Guide line between two handles, stopped at the handle rings."""
    length = math.dist(a, b)
    r = handle_radius()
    cut = r * (trim_a + trim_b)
    if length <= cut:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    ta = r if trim_a else 0.0
    tb = r if trim_b else 0.0
    lines([(a[0] + ux * ta, a[1] + uy * ta), (b[0] - ux * tb, b[1] - uy * tb)], color, width)


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


def _grid(view, solution, opacity):
    dist = float(np.linalg.norm(solution.position))
    if dist <= 0.0:
        return
    spacing = 10.0 ** math.floor(math.log10(dist / 4.0))
    extent = GRID_LINES * spacing
    near = 1e-3 * dist
    colors = axis_colors()
    neutral = (0.85, 0.85, 0.85, 0.45 * opacity)
    groups = {"X": [], "Y": [], "N": []}
    for i in range(-GRID_LINES, GRID_LINES + 1):
        c = i * spacing
        for axis, a, b in (("X", (-extent, c, 0.0), (extent, c, 0.0)), ("Y", (c, -extent, 0.0), (c, extent, 0.0))):
            seg = project_segment(solution, a, b, near)
            if seg is None:
                continue
            groups[axis if i == 0 else "N"] += [view.px_to_region(seg[0]), view.px_to_region(seg[1])]
    lines(groups["N"], neutral, 1.0)
    lines(groups["X"], with_alpha(colors["X"], opacity), 1.5)
    lines(groups["Y"], with_alpha(colors["Y"], opacity), 1.5)


def _horizon(view, solution):
    line = horizon_line(solution)
    if line is None:
        return
    w, h = solution.image_size
    seg = clip_line_to_rect(line[0], line[1], w, h)
    if seg is not None:
        lines([view.px_to_region(seg[0]), view.px_to_region(seg[1])], HORIZON_COLOR, 1.5)


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
            segment(o, view.px_to_region(tip), colors[axis], 2.5, trim_b=False)


def axis_letter(label: str) -> str:
    return label.lstrip("+-")


def draw_overlay(session):
    """POST_PIXEL draw callback for the calibration session."""
    context = bpy.context
    region = context.region
    if region is None or region.as_pointer() != session.region_ptr:
        return
    cam_obj = bpy.data.objects.get(session.camera_name)
    if cam_obj is None or cam_obj.type != "CAMERA":
        return
    settings = cam_obj.data.ftc
    view = View.try_create(region, context.region_data, cam_obj, context.scene, calibrate.image_size(settings))
    # Events use the frame of the last draw, when camera and view matrices agree.
    session.view = view
    if view is None:
        return
    draw_guides(view, settings, calibrate.cached_solution(cam_obj.data), session, context.scene.unit_settings.system)


def draw_guides(view, settings, solution, session, unit_system):
    """Draw the whole overlay for ``settings`` into the current framebuffer."""
    colors = axis_colors()
    s = ui_scale()

    gpu.state.blend_set("ALPHA")
    try:
        if solution is not None:
            if settings.show_grid and settings.grid_opacity > 0.0:
                with clipped_to(view):
                    _grid(view, solution, settings.grid_opacity)
            _horizon(view, solution)

        frozen = settings.freeze
        keys = calibrate.active_handle_keys(settings)
        labels = [settings.vp1_axis, settings.vp2_axis, settings.vp3_axis]

        def hpos(key):
            return view.to_region(calibrate.handle(settings, key))

        if settings.mode == "VP":
            count = int(settings.vp_count)
            if count == 3:
                labels[2] = remaining_axis(labels[0], labels[1])
            for i in range(1, count + 1):
                color = colors[axis_letter(labels[i - 1])]
                k = calibrate.vp_keys(i)
                width = GUIDE_WIDTH * (1.5 if session.active_vp == i - 1 else 1.0)
                segs = [hpos(k[0]), hpos(k[1]), hpos(k[2]), hpos(k[3])]
                segment(segs[0], segs[1], color, width)
                segment(segs[2], segs[3], color, width)
                vp = vanishing_point_px(settings, i)
                if vp is not None:
                    vpr = view.px_to_region(vp)
                    for a, b in ((segs[0], segs[1]), (segs[2], segs[3])):
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
                segment(hpos("hz_a"), hpos("hz_b"), color, GUIDE_WIDTH)
                text((hpos("hz_b")[0] + 8 * s, hpos("hz_b")[1] + 8 * s), settings.vp2_axis, color)
            if settings.scale_mode == "REFERENCE":
                color = colors[settings.ref_axis]
                a, b = hpos("ref_a"), hpos("ref_b")
                dashed(a, b, color, 2.0, 5.0)
                length = bpy.utils.units.to_string(unit_system, "LENGTH", settings.ref_length, precision=3)
                text((b[0] + 8 * s, b[1] - 16 * s), length, color)
        elif settings.mode == "RECT":
            pts = [hpos(f"rect_{i}") for i in range(4)]
            edge_colors = [colors["X"], colors["Y"], colors["X"], colors["Y"]]
            for i in range(4):
                segment(pts[i], pts[(i + 1) % 4], edge_colors[i], GUIDE_WIDTH)
        else:
            segment(hpos("hz_a"), hpos("hz_b"), HORIZON_COLOR, GUIDE_WIDTH)

        if solution is not None:
            _origin_gizmo(view, solution, settings)

        if solution is not None and settings.mode == "VP" and int(settings.vp_count) == 3:
            pp = view.px_to_region(solution.principal_point)
            lines(
                [(pp[0] - 8 * s, pp[1]), (pp[0] + 8 * s, pp[1]), (pp[0], pp[1] - 8 * s), (pp[0], pp[1] + 8 * s)],
                NEUTRAL,
                1.5,
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
            elif key.startswith("hz"):
                color = colors[axis_letter(settings.vp2_axis)] if settings.mode == "VP" else HORIZON_COLOR
            else:
                color = colors["X"] if key in ("rect_0", "rect_1") else colors["Y"]
            handle_marker(
                hpos(key),
                color,
                hovered=key == session.hover,
                active=key == session.drag_key,
                frozen=frozen,
                first=key == "rect_0",
            )

        if solution is not None:
            ph = pitch_handle_px(solution)
            if ph is not None:
                pos = view.px_to_region(ph)
                hovered = session.hover == "pitch" or session.drag_key == "pitch"
                diamond_outline(pos, handle_radius(hovered) + 2.0 * s, HORIZON_COLOR)

        res = settings.results
        if not res.valid and res.error:
            text((view.x0 + 10 * s, view.y1 - 22 * s), res.error, ERROR_COLOR, 13.0)
        elif res.warnings:
            text((view.x0 + 10 * s, view.y1 - 22 * s), res.warnings.splitlines()[0], HORIZON_COLOR, 12.0)
    finally:
        gpu.state.blend_set("NONE")


def remaining_axis(a: str, b: str) -> str:
    letters = {"X", "Y", "Z"} - {axis_letter(a), axis_letter(b)}
    return letters.pop() if len(letters) == 1 else "Z"
