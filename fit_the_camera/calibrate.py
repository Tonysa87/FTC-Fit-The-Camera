# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge between the stored settings, the solver and the Blender camera."""

from __future__ import annotations

import math
from contextlib import contextmanager

import bpy
import numpy as np
from mathutils import Matrix

from .exif import native_frame
from .solver import (
    CameraSolution,
    ReferenceDistance,
    ScaleCube,
    SolverError,
    cube_top_px,
    focal_px_from_35mm,
    focal_px_from_mm,
    solve_horizon,
    solve_rectangle,
    solve_vanishing_points,
    to_blender,
)
from .solver.common import parse_axis, plane_frame, ray

# Default guide layout, in normalised image coordinates (0..1, origin bottom-left).
# Vanishing point 1 (+X) converges to the right, 2 (+Y) to the left, 3 downwards,
# so the default axes give a right-handed world with Z up.
HANDLE_DEFAULTS = {
    "vp1_1a": (0.55, 0.30),
    "vp1_1b": (0.85, 0.40),
    "vp1_2a": (0.55, 0.70),
    "vp1_2b": (0.85, 0.60),
    "vp2_1a": (0.45, 0.30),
    "vp2_1b": (0.15, 0.40),
    "vp2_2a": (0.45, 0.70),
    "vp2_2b": (0.15, 0.60),
    "vp3_1a": (0.30, 0.80),
    "vp3_1b": (0.32, 0.20),
    "vp3_2a": (0.70, 0.80),
    "vp3_2b": (0.68, 0.20),
    "origin": (0.50, 0.30),
    "ref_a": (0.50, 0.30),
    "ref_b": (0.62, 0.34),
    "cube_base": (0.62, 0.22),
    "cube_top": (0.62, 0.40),
    "pp": (0.50, 0.50),
    "rect_0": (0.20, 0.12),
    "rect_1": (0.80, 0.12),
    "rect_2": (0.66, 0.45),
    "rect_3": (0.34, 0.45),
    "hz_a": (0.80, 0.55),
    "hz_b": (0.20, 0.55),
    # Distant landmark of known compass bearing (north from a landmark, Sun).
    "landmark": (0.50, 0.60),
    # Shadow (Sun): foot and top of a vertical object, tip of its shadow.
    "shadow_foot": (0.40, 0.25),
    "shadow_top": (0.40, 0.45),
    "shadow_tip": (0.55, 0.22),
}

# Guide lines per vanishing point: two by default, up to six (1.1).
MAX_LINES = 6
# Where an extra line goes between the first two lines of its group (fraction
# from the first): spread so that each new line falls in a gap.
EXTRA_LINE_T = {3: 0.5, 4: 0.25, 5: 0.75, 6: 0.125}


def extra_line(layout: dict, index: int, n: int) -> tuple:
    """Default ends of line ``n`` (3..6) of group ``index``: it starts between the
    first two lines of ``layout`` and points at their meeting point (their
    vanishing point), so a new line agrees with the others until it is moved.
    Coordinates are normalised: meeting points survive the uneven scaling."""
    t = EXTRA_LINE_T[n]
    a1, b1, a2, b2 = (np.asarray(layout[f"vp{index}_{k}"], float) for k in ("1a", "1b", "2a", "2b"))
    if (b2 - a2) @ (b1 - a1) < 0.0:
        a2, b2 = b2, a2  # line 2 drawn the other way
    a = a1 + t * (a2 - a1)
    length = (1.0 - t) * np.linalg.norm(b1 - a1) + t * np.linalg.norm(b2 - a2)
    meet = np.cross(np.cross([*a1, 1.0], [*b1, 1.0]), np.cross([*a2, 1.0], [*b2, 1.0]))
    scale = float(np.linalg.norm(meet))
    if scale < 1e-12:
        b = b1 + t * (b2 - b1)  # the two lines coincide
    else:
        # Towards the meeting point, or along it when it is at infinity (parallel lines).
        direction = meet[:2] / meet[2] - a if abs(meet[2]) > 1e-9 * scale else meet[:2]
        if direction @ (b1 - a1) < 0.0:
            direction = -direction
        norm = float(np.linalg.norm(direction))
        b = a + length * direction / norm if norm > 1e-12 else b1 + t * (b2 - b1)
    return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))


def _add_extra_lines(layout: dict) -> None:
    for index in (1, 2, 3):
        for n in range(3, MAX_LINES + 1):
            a, b = extra_line(layout, index, n)
            layout[f"vp{index}_{n}a"], layout[f"vp{index}_{n}b"] = a, b


_add_extra_lines(HANDLE_DEFAULTS)

# Camera object name of the running calibration session, if any.
session_camera: str | None = None

_solutions: dict[int, CameraSolution] = {}
# True while a handle is dragged: the uncertainty estimate (dozens of solves) waits.
defer_uncertainty = False
_updating = False


# ----------------------------------------------------------------------------
# Settings access


TRANSFORM_PATHS = {
    "location",
    "rotation_euler",
    "rotation_quaternion",
    "rotation_axis_angle",
    "delta_location",
    "delta_rotation_euler",
    "delta_rotation_quaternion",
}
LENS_PATHS = {"lens", "shift_x", "shift_y", "sensor_width", "sensor_height", "sensor_fit", "type"}


def _animated(id_data, paths) -> bool:
    """``id_data`` has keyframes (action or NLA) or drivers on any of ``paths``."""
    anim = id_data.animation_data
    if anim is None:
        return False
    if any(d.data_path in paths for d in anim.drivers):
        return True
    from bpy_extras import anim_utils

    pairs = [(anim.action, anim.action_slot)] if anim.action is not None else []
    pairs += [(s.action, getattr(s, "action_slot", None)) for t in anim.nla_tracks for s in t.strips if s.action]
    for action, slot in pairs:
        bag = anim_utils.action_get_channelbag_for_slot(action, slot) if slot is not None else None
        if bag is not None and any(fc.data_path in paths for fc in bag.fcurves):
            return True
    return False


def transform_overridden(obj) -> bool:
    """Something replaces the calibration written into the camera at the next
    frame change or render: keyframes, drivers or constraints on its transform
    (or on a parent's), or keyframes on its lens."""
    if _animated(obj.data, LENS_PATHS):
        return True
    while obj is not None:
        if _animated(obj, TRANSFORM_PATHS):
            return True
        if any(c.enabled and c.influence > 0.0 for c in obj.constraints):
            return True
        obj = obj.parent
    return False


def aspect_matches(scene, size) -> bool:
    """The render (with its pixel aspect) has the aspect ratio of an image of
    ``size`` pixels, to the pixel."""
    w, h = size
    render = scene.render
    stretch = render.pixel_aspect_x / render.pixel_aspect_y
    return not (w and h) or abs(render.resolution_y - render.resolution_x * stretch * h / w) <= 1.0


def space_camera(space, scene):
    """Camera object a 3D view looks through (its local camera, or the scene's);
    ``None`` when that is not a camera."""
    cam = scene.camera
    if space is not None and space.type == "VIEW_3D" and space.use_local_camera and space.camera:
        cam = space.camera
    return cam if cam is not None and cam.type == "CAMERA" else None


def view_camera(context):
    """Camera object shown by the 3D view in ``context`` (or the scene camera)."""
    return space_camera(getattr(context, "space_data", None), context.scene)


def default_handles(settings) -> dict:
    """Default guide layout. With a known focal length the first two vanishing
    points sit on the centre line at +-focal from the centre, so the untouched
    guides already agree with the camera."""
    layout = dict(HANDLE_DEFAULTS)
    w, h = image_size(settings)
    focal = known_focal_px(settings) if w and h else None
    if not focal:
        return layout
    for index, side in ((1, 1.0), (2, -1.0)):
        vp = (0.5 + side * focal / w, 0.5)
        for line in "12":
            a = HANDLE_DEFAULTS[f"vp{index}_{line}a"]
            t = min(0.6, 0.3 / abs(vp[0] - a[0]))
            layout[f"vp{index}_{line}b"] = (a[0] + t * (vp[0] - a[0]), a[1] + t * (vp[1] - a[1]))
    layout.update(_default_rectangle(settings, focal, w, h))
    _add_extra_lines(layout)
    return layout


def _default_rectangle(settings, focal, w, h) -> dict:
    """Corners of the known rectangle lying on the floor in the lower part of the
    image, seen 20 degrees from grazing by a camera with ``focal``."""
    below = math.atan(0.22 * h / focal)  # centre of the rectangle under the image centre
    tilt = math.radians(20.0) - below  # camera pitch down (negative: up)
    aspect = settings.rect_height / settings.rect_width if settings.rect_width > 0.0 else 1.0
    side = 0.5 * w / focal
    centre = np.array([0.0, -0.22 * h, -focal])
    centre /= np.linalg.norm(centre)
    away = np.array([0.0, math.sin(tilt), -math.cos(tilt)]) * min(aspect, 2.0)
    corners = {}
    for _ in range(12):  # a wide lens shows the near side large: shrink to fit
        depths = []
        for i, (a, b) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
            x, y, z = centre + side / 2.0 * (a * np.array([1.0, 0.0, 0.0]) + b * away)
            depths.append(z)
            corners[f"rect_{i}"] = (0.5 + focal * x / -z / w, 0.5 + focal * y / -z / h)
        inside = all(0.03 <= c <= 0.97 for co in corners.values() for c in co)
        if inside and all(depth < -0.05 for depth in depths):
            break
        side *= 0.8
    return corners


def ensure_handles(settings) -> None:
    present = {h.name for h in settings.handles}
    for key, co in default_handles(settings).items():
        if key not in present:
            item = settings.handles.add()
            item.name = key
            item.co = co


def handle(settings, key) -> tuple[float, float]:
    item = settings.handles.get(key)
    return tuple(item.co) if item is not None else HANDLE_DEFAULTS[key]


def set_handle(settings, key, co) -> None:
    item = settings.handles.get(key)
    if item is None:
        item = settings.handles.add()
        item.name = key
    item.co = co


def reset_handles(settings) -> None:
    for key, co in default_handles(settings).items():
        set_handle(settings, key, co)


def image_size(settings) -> tuple[int, int]:
    data = settings.camera_data
    if data.image_width and data.image_height:
        return data.image_width, data.image_height
    if settings.image is not None and settings.image.size[0]:
        return tuple(settings.image.size)
    scene = bpy.context.scene
    return scene.render.resolution_x, scene.render.resolution_y


def to_pixels(settings, co) -> tuple[float, float]:
    w, h = image_size(settings)
    return co[0] * w, co[1] * h


def vp_keys(index: int, count: int = 2) -> list[str]:
    """Handle keys of the first ``count`` guide lines of vanishing point
    ``index`` (1-based): a, b of line 1, then of line 2..."""
    return [f"vp{index}_{n}{end}" for n in range(1, count + 1) for end in "ab"]


def line_count(settings, index: int) -> int:
    return getattr(settings, f"vp{index}_lines")


def group_keys(settings, index: int) -> list[str]:
    """Handle keys of every guide line of vanishing point ``index``."""
    return vp_keys(index, line_count(settings, index))


def group_lines(settings, index: int) -> list[tuple]:
    """Guide lines (pixel segments) of vanishing point ``index``."""
    keys = group_keys(settings, index)
    pts = [to_pixels(settings, handle(settings, k)) for k in keys]
    return [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]


def active_handle_keys(settings) -> list[str]:
    """Handles that are visible and editable in the current mode."""
    keys: list[str] = []
    if settings.mode == "VP":
        count = int(settings.vp_count)
        for i in range(1, count + 1):
            keys += group_keys(settings, i)
        if count == 1:
            keys += ["hz_a", "hz_b"]
        if count == 2 and settings.use_third_line:
            keys += ["vp3_1a", "vp3_1b"]
        keys.append("origin")
        if settings.scale_mode == "REFERENCE":
            keys += ["ref_a", "ref_b"]
    elif settings.mode == "RECT":
        keys += [f"rect_{i}" for i in range(4)]
    else:
        keys += ["hz_a", "hz_b"]
    if cube_visible(settings):
        keys.append("cube_base")
    if cube_scales(settings):
        keys.append("cube_top")
    if settings.pp_mode == "MANUAL":
        keys.append("pp")
    sun = settings.sun
    if sun.source == "TIME" and sun.north_source == "LANDMARK":
        keys.append("landmark")
    if sun.source == "SHADOW" or sun.use_shadow or sun.north_source == "SHADOW":
        keys += ["shadow_foot", "shadow_top", "shadow_tip"]
    return keys


def cube_scales(settings) -> bool:
    """The scale cube sets the scene scale (otherwise it is only a visual check)."""
    return settings.mode == "VP" and settings.scale_mode == "CUBE"


def reference_scales(settings) -> bool:
    """The reference distance sets the scene scale."""
    return settings.mode == "VP" and settings.scale_mode == "REFERENCE"


def cube_visible(settings) -> bool:
    """Shown when it sets the scale, or as a visual check where no scale option is
    offered: the reference distance and the cube exclude each other."""
    if reference_scales(settings):
        return False
    return settings.show_cube or cube_scales(settings)


def cube_size(settings) -> float:
    """Edge of the scale cube in scene units (the presets are metres)."""
    if settings.cube_size == "CUSTOM":
        return settings.cube_custom
    return float(settings.cube_size) / (bpy.context.scene.unit_settings.scale_length or 1.0)


# ----------------------------------------------------------------------------
# Camera data


def known_sensor_mm(settings) -> float | None:
    """Long side of the uncropped sensor, as in the camera's specifications."""
    data = settings.camera_data
    if data.sensor_mm_state != "MISSING" and data.sensor_mm > 0.0:
        return data.sensor_mm
    return None


def image_sensor_mm(settings) -> float | None:
    """Sensor size covered by the image's long side (smaller for a cropped image)."""
    sensor = known_sensor_mm(settings)
    if sensor is None:
        return None
    size = image_size(settings)
    return sensor * max(size) / native_frame(size)[0]


def known_focal_px(settings) -> float | None:
    """Focal length in pixels from the camera data, ``None`` if unknown."""
    data = settings.camera_data
    size = image_size(settings)
    sensor = known_sensor_mm(settings)
    if data.focal_mm_state != "MISSING" and data.focal_mm > 0.0 and sensor:
        return focal_px_from_mm(data.focal_mm, sensor, size, native_frame(size))
    if data.focal_35mm_state != "MISSING" and data.focal_35mm > 0.0:
        return focal_px_from_35mm(data.focal_35mm, size, native_frame(size))
    return None


def mode_needs_focal(settings) -> bool:
    return settings.mode == "HORIZON" or (settings.mode == "VP" and settings.vp_count == "1")


def focal_source(settings) -> str:
    """How the focal length is used: "KNOWN" (fixed), "AUTO" (known, refined by
    the guides) or "SOLVE" (from the guides only)."""
    if mode_needs_focal(settings):
        return "KNOWN"
    if pp_solved(settings):
        return "SOLVE"  # the orthocentre fixes the focal length too
    if settings.focal_mode == "AUTO" and known_focal_px(settings) is None:
        return "SOLVE"
    return settings.focal_mode


def pp_solved(settings) -> bool:
    return settings.mode == "VP" and settings.vp_count == "3" and settings.pp_mode == "SOLVE"


def _focal_inputs(settings) -> dict:
    """``focal_px`` / ``known_focal_px`` solver arguments for 2-3 vanishing points
    and the rectangle."""
    source = focal_source(settings)
    if source == "KNOWN":
        focal = known_focal_px(settings)
        if focal is None:
            raise SolverError("the focal length is unknown: enter it in Camera Data")
        return {"focal_px": focal}
    if source == "AUTO":
        return {"known_focal_px": known_focal_px(settings)}
    return {}


# ----------------------------------------------------------------------------
# Solving


def solve(settings, overrides: dict | None = None, distance: float | None = None) -> CameraSolution:
    """Solve the camera described by ``settings``; raises ``SolverError``.

    ``overrides`` replaces some handle positions (normalised), without touching
    the stored settings. ``distance`` replaces the vanishing point scale by the
    camera's distance from the origin.
    """
    size = image_size(settings)
    if not size[0] or not size[1]:
        raise SolverError("no image loaded")

    def at(key):
        co = overrides.get(key) if overrides else None
        return to_pixels(settings, co if co is not None else handle(settings, key))

    def _points(_settings, keys):
        return [at(k) for k in keys]

    pp = at("pp") if settings.pp_mode == "MANUAL" else None
    common = {"straighten_horizon": settings.straighten, "pitch_offset": settings.pitch_offset}

    if settings.mode == "VP":
        count = int(settings.vp_count)
        lines = []
        for i in range(1, count + 1):
            pts = _points(settings, group_keys(settings, i))
            lines.append([(pts[k], pts[k + 1]) for k in range(0, len(pts), 2)])
        axes = [settings.vp1_axis, settings.vp2_axis, settings.vp3_axis][: max(count, 2)]
        axis2_line = third_line = None
        focal = _focal_inputs(settings) if count >= 2 else {}
        if count == 2 and settings.use_third_line:
            third_line = tuple(_points(settings, ["vp3_1a", "vp3_1b"]))
        if count == 1:
            focal = {"focal_px": known_focal_px(settings)}
            if focal["focal_px"] is None:
                raise SolverError("one vanishing point needs the focal length: enter it in Camera Data")
            a, b = _points(settings, ["hz_a", "hz_b"])
            axis2_line = (a, b)
        reference = cube = None
        if distance is not None:
            pass
        elif settings.scale_mode == "REFERENCE":
            ra, rb = _points(settings, ["ref_a", "ref_b"])
            reference = ReferenceDistance(settings.ref_axis, ra, rb, settings.ref_length, settings.ref_measure_plane)
        else:
            base, top = _points(settings, ["cube_base", "cube_top"])
            cube = ScaleCube(base, top, cube_size(settings), reference_plane(settings))
        return solve_vanishing_points(
            lines,
            axes,
            size,
            principal_point=pp,
            solve_principal_point=count == 3 and settings.pp_mode == "SOLVE",
            **focal,
            axis2_line=axis2_line,
            third_axis_line=third_line,
            origin=at("origin"),
            reference=reference,
            cube=cube,
            camera_distance=distance or 10.0,
            **common,
        )

    if settings.mode == "RECT":
        return solve_rectangle(
            _points(settings, [f"rect_{i}" for i in range(4)]),
            settings.rect_width,
            settings.rect_height,
            size,
            principal_point=pp,
            plane=reference_plane(settings),
            **_focal_inputs(settings),
            **common,
        )

    focal = known_focal_px(settings)
    if focal is None:
        raise SolverError("the horizon mode needs the focal length: enter it in Camera Data")
    data = settings.camera_data
    if settings.yaw_source == "EXIF" and data.direction_state != "MISSING":
        yaw = data.direction
    else:
        yaw = math.degrees(settings.yaw)
    return solve_horizon(
        _points(settings, ["hz_a", "hz_b"]),
        focal,
        size,
        camera_height=settings.camera_height,
        yaw=yaw,
        principal_point=pp,
        **common,
    )


# Handles that only place or scale the result, not its orientation or focal length.
POSE_ONLY_KEYS = {"origin", "ref_a", "ref_b", "cube_base", "cube_top", "pp", "landmark"}
POSE_ONLY_KEYS |= {"shadow_foot", "shadow_top", "shadow_tip"}
# Assumed placement error of a handle, as a fraction of the long image side.
PLACEMENT_ERROR = 1e-3
UNSTABLE_FOCAL = 0.05
# Guide misfit (degrees) above which the guides and the camera disagree.
MISFIT_KNOWN_FOCAL_DEG = 1.0
MISFIT_DEG = 2.0
# Change of a known focal length by the guides worth pointing out.
FOCAL_SHIFT = 0.15
UNSTABLE_ANGLE_DEG = 1.0


def calibrate_keys(settings) -> list[str]:
    return [k for k in active_handle_keys(settings) if k not in POSE_ONLY_KEYS]


def uncertainty(settings, solution: CameraSolution) -> tuple[float, float]:
    """Spread of the focal length (fraction) and orientation (degrees) when every
    guide handle is misplaced by ``PLACEMENT_ERROR`` of the long image side.

    Linear estimate: each handle coordinate is nudged in turn and the changes are
    added in quadrature. Returns ``inf`` when a nudge makes the input unsolvable.
    """
    w, h = image_size(settings)
    step = PLACEMENT_ERROR * max(w, h)
    focal_var = angle_var = 0.0
    for key in calibrate_keys(settings):
        co = handle(settings, key)
        for axis, size in ((0, w), (1, h)):
            moved = list(co)
            moved[axis] += step / size
            try:
                # The scale does not change focal or angles: keep it, so a reference
                # or cube near the horizon does not fail the nudged solves.
                nudged = solve(settings, {key: tuple(moved)}, distance=float(np.linalg.norm(solution.position)))
            except (SolverError, ArithmeticError, ValueError, np.linalg.LinAlgError):
                return math.inf, math.inf
            focal_var += ((nudged.focal_px - solution.focal_px) / solution.focal_px) ** 2
            cos = (np.trace(solution.rotation.T @ nudged.rotation) - 1.0) / 2.0
            angle_var += math.degrees(math.acos(min(1.0, max(-1.0, cos)))) ** 2
    return math.sqrt(focal_var), math.sqrt(angle_var)


def seed_cube(cam_data, solution: CameraSolution | None = None) -> None:
    """Put the scale cube's top handle on the top of its vertical edge for
    ``solution`` (default: the cached one), so that the scale stays as it is.

    Used when the reference plane changes, when the cube takes over the scale and
    for files saved before the cube existed. A base corner that is not on the
    reference plane moves next to the origin.
    """
    settings = cam_data.ftc
    if _updating and solution is None:
        return  # settings written together (``suspended``, undo): keep their handles
    solution = solution or cached_solution(cam_data)
    if not cube_scales(settings) or solution is None:
        return
    w, h = image_size(settings)
    size, plane = cube_size(settings), reference_plane(settings)
    base = to_pixels(settings, handle(settings, "cube_base"))
    top = cube_top_px(solution, base, size, plane)

    def inside(p):
        return p is not None and -0.05 * w <= p[0] <= 1.05 * w and -0.05 * h <= p[1] <= 1.05 * h

    if not (inside(base) and inside(top)):
        # E.g. a base left on the floor when the plane becomes a wall.
        # Half an edge from the origin along the plane, so both handles stay pickable.
        frame = plane_frame(plane)
        near = project_point(solution, 0.5 * size * (frame[:, 0] + frame[:, 1]))
        if near is None:
            return
        base = near
        top = cube_top_px(solution, base, size, plane)
        if top is None:
            return
    with suspended():
        set_handle(settings, "cube_base", (float(base[0] / w), float(base[1] / h)))
        set_handle(settings, "cube_top", (float(top[0] / w), float(top[1] / h)))


def seed_reference(cam_data) -> None:
    """When the reference distance takes over the scale with its handles still
    untouched (the defaults), lay them out for the current scale: the scene keeps
    its size, as when the cube takes over."""
    settings = cam_data.ftc
    if _updating or not reference_scales(settings):
        return
    solution = cached_solution(cam_data)
    if solution is None:
        return
    defaults = default_handles(settings)
    if any(math.dist(handle(settings, k), defaults[k]) > 1e-6 for k in ("ref_a", "ref_b")):
        return
    w, h = image_size(settings)
    frame = plane_frame(settings.ref_measure_plane)
    normal = frame[:, 2]
    start_px = to_pixels(settings, defaults["ref_a"])
    direction = solution.rotation @ ray(start_px, solution.principal_point, solution.focal_px)
    den = normal @ direction
    if abs(den) < 1e-9:
        return
    t = -(normal @ solution.position) / den
    if t <= 0.0:
        return
    start = solution.position + t * direction
    k, _ = parse_axis(settings.ref_axis)
    axis = np.eye(3)[k]
    for sign in (1.0, -1.0):
        end = project_point(solution, start + sign * settings.ref_length * axis)
        if end is not None and 0.0 <= end[0] <= w and 0.0 <= end[1] <= h:
            with suspended():
                set_handle(settings, "ref_b", (float(end[0] / w), float(end[1] / h)))
            return


def project_point(solution: CameraSolution, point):
    """Image point of a world point, ``None`` behind the camera."""
    cam = solution.rotation.T @ (np.asarray(point, float) - solution.position)
    if cam[2] > -1e-9:
        return None
    return solution.principal_point + solution.focal_px * cam[:2] / -cam[2]


def _migrate_cube(cam_data) -> None:
    """Files saved before the scale cube: seed it so that the camera keeps its
    distance from the origin (the old "Camera Distance")."""
    settings = cam_data.ftc
    if not cube_scales(settings) or settings.handles.get("cube_top") is not None or not len(settings.handles):
        return
    users = [o for o in bpy.data.objects if o.data == cam_data]
    if not users:
        return
    distance = (users[0].matrix_world.translation - alignment_matrix(settings).translation).length
    if distance <= 0.0:
        return
    try:
        solution = solve(settings, distance=distance)
    except (SolverError, ArithmeticError, ValueError, np.linalg.LinAlgError):
        return
    seed_cube(cam_data, solution)


def seed_third_axis(cam_data) -> None:
    """Place the untouched third-axis guides along the third axis of the current
    camera, so that switching to three vanishing points (or adding the third axis
    line) starts from consistent guides."""
    settings = cam_data.ftc
    solution = cached_solution(cam_data)
    keys = vp_keys(3)
    if settings.mode != "VP" or solution is None:
        return
    if any(math.dist(handle(settings, k), HANDLE_DEFAULTS[k]) > 1e-6 for k in keys):
        return  # the user already placed them
    w, h = image_size(settings)
    axis = 3 - "XYZ".index(settings.vp1_axis[1]) - "XYZ".index(settings.vp2_axis[1])
    d = solution.rotation[axis, :]  # third axis in camera space
    p, f = solution.principal_point, solution.focal_px
    co = []
    for u in (0.3, 0.7):
        q = np.array([u * w, 0.5 * h])
        start = np.array([q[0] - p[0], q[1] - p[1], -f]) / f  # point at depth 1 on the ray
        end = start + 0.05 * d
        if end[2] >= -1e-6:
            end = start - 0.05 * d
        q2 = p + f * end[:2] / -end[2]
        direction = (q2 - q) / max(np.linalg.norm(q2 - q), 1e-9)
        half = 0.3 * h
        for point in (q - direction * half, q + direction * half):
            co.append((float(point[0] / w), float(point[1] / h)))
    with suspended():
        for key, c in zip(keys, co):
            set_handle(settings, key, c)
        # Extra lines of the group follow the new first two.
        first_two = {k: handle(settings, k) for k in keys}
        for n in range(3, line_count(settings, 3) + 1):
            a, b = extra_line(first_two, 3, n)
            set_handle(settings, f"vp3_{n}a", a)
            set_handle(settings, f"vp3_{n}b", b)


def cached_solution(cam_data) -> CameraSolution | None:
    return _solutions.get(cam_data.session_uid)


def current_solution(cam_data) -> CameraSolution | None:
    """The cached solution, or one solved now (and cached) without storing the
    results: safe in draw callbacks, e.g. after a file was opened."""
    solution = _solutions.get(cam_data.session_uid)
    if solution is not None or cam_data.ftc.image is None:
        return solution
    try:
        solution = solve(cam_data.ftc)
    except (SolverError, ArithmeticError, ValueError, np.linalg.LinAlgError):
        return None
    if not _finite(solution):
        return None
    _solutions[cam_data.session_uid] = solution
    return solution


def forget_solutions() -> None:
    """Drop every cached solution (they may not match the settings any more)."""
    _solutions.clear()


def _store_results(settings, solution: CameraSolution | None, error: str) -> None:
    res = settings.results
    res.valid = solution is not None
    res.error = error
    if solution is None:
        res.warnings = ""
        return
    bc = to_blender(solution, image_sensor_mm(settings))
    fov_h, fov_v = solution.fov
    warnings = list(solution.warnings)
    if defer_uncertainty:
        # While a handle is being dragged: keep the last estimate, refresh on release.
        focal_err, angle_err = res.focal_error, res.angle_error
    else:
        focal_err, angle_err = uncertainty(settings, solution)
    res.focal_error = min(focal_err, 10.0)
    res.angle_error = min(angle_err, 180.0)
    # A known focal length is an input, not something the guides can destabilise.
    source = focal_source(settings)
    focal_solved = source != "KNOWN"
    res.focal_solved = focal_solved
    res.focal_shift = solution.focal_px / known_focal_px(settings) - 1.0 if source == "AUTO" else 0.0
    if (focal_solved and focal_err > UNSTABLE_FOCAL) or angle_err > UNSTABLE_ANGLE_DEG:
        warnings.insert(
            0,
            f"unstable calibration (focal ±{100 * min(focal_err, 9.99):.0f}%, angles ±{min(angle_err, 99):.1f}°): "
            "use longer guides further apart, add a third axis line or a third vanishing point, "
            "or use the known focal length",
        )
    res.guide_misfit = math.radians(solution.guide_misfit)
    # Independent checks: a misfit names its cause even when the focal also moved.
    head = []
    if source == "KNOWN" and solution.guide_misfit > MISFIT_KNOWN_FOCAL_DEG:
        head.append(
            f"the guides disagree with the known focal length by up to {solution.guide_misfit:.1f}°: "
            "the photo may be cropped or zoomed, try solving the focal length"
        )
    elif solution.guide_misfit > MISFIT_DEG:
        head.append(
            f"the guides do not meet consistently (up to {solution.guide_misfit:.1f}° off): "
            "some lines may not be parallel to their axis"
        )
    if abs(res.focal_shift) > FOCAL_SHIFT:
        head.append(
            f"the guides overrule the known focal length ({100 * res.focal_shift:+.0f}%): "
            "the photo may be cropped or zoomed"
        )
    warnings[:0] = head
    res.warnings = "\n".join(warnings)
    res.removed_roll = math.radians(solution.removed_roll)
    res.focal_px = solution.focal_px
    res.lens = bc.lens
    res.sensor = bc.sensor_width
    res.fov_h = math.radians(fov_h)
    res.fov_v = math.radians(fov_v)
    res.pitch = math.radians(solution.pitch)
    res.roll = math.radians(solution.roll)
    res.yaw = math.radians(solution.yaw)
    res.height = solution.camera_height
    res.distance = float((solution.position @ solution.position) ** 0.5)


def _finite(solution: CameraSolution) -> bool:
    values = [solution.focal_px, *solution.rotation.ravel(), *solution.position, *solution.principal_point]
    return all(math.isfinite(float(v)) for v in values) and solution.focal_px > 0.0


def refresh(cam_data) -> CameraSolution | None:
    """Solve ``cam_data``'s settings, cache the solution and store the results."""
    settings = cam_data.ftc
    _migrate_cube(cam_data)
    try:
        solution = solve(settings)
        error = ""
    except SolverError as exc:
        solution, error = None, str(exc)
    except (ArithmeticError, ValueError, np.linalg.LinAlgError):
        # Nearly degenerate guides, typically mid-drag: report, never raise.
        solution, error = None, "the guides do not define a camera: move them apart"
    if solution is not None and not _finite(solution):
        solution, error = None, "the guides do not define a camera: move them apart"
    if solution is None:
        _solutions.pop(cam_data.session_uid, None)
    else:
        _solutions[cam_data.session_uid] = solution
    _store_results(settings, solution, error)
    return solution


def reference_plane(settings) -> str:
    """Plane used for the rectangle, the grid and the alignment (always the
    ground in horizon mode)."""
    return "XY" if settings.mode == "HORIZON" else settings.ref_plane


def reference_frame(settings) -> Matrix:
    """Reference plane frame in the calibrated world, with the user's quarter
    turns and flip: x, y in the plane and z along its normal."""
    frame = Matrix(plane_frame(reference_plane(settings)).tolist()).to_4x4()
    frame = frame @ Matrix.Rotation(math.radians(90.0 * settings.align_rotation), 4, "Z")
    if settings.align_flip:
        frame = frame @ Matrix.Rotation(math.pi, 4, "X")
    return frame


def alignment_matrix(settings) -> Matrix:
    """Calibrated world -> scene: puts the reference plane frame on the target."""
    if not settings.use_anchor:
        return Matrix.Identity(4)
    return Matrix(settings.anchor_matrix) @ reference_frame(settings).inverted()


def apply_solution(cam_obj, solution: CameraSolution) -> None:
    """Write ``solution`` into the camera object and its data."""
    settings = cam_obj.data.ftc
    bc = to_blender(solution, image_sensor_mm(settings))
    cam = cam_obj.data
    cam.type = "PERSP"
    cam.lens_unit = "MILLIMETERS"
    cam.sensor_fit = bc.sensor_fit
    cam.sensor_width = bc.sensor_width
    cam.sensor_height = bc.sensor_height
    cam.lens = bc.lens
    cam.shift_x = bc.shift_x
    cam.shift_y = bc.shift_y
    cam_obj.matrix_world = alignment_matrix(settings) @ Matrix(bc.matrix_world.tolist())
    # The Sun light follows the camera's north (compass, landmark).
    from . import ops_sun

    ops_sun.orient(settings, solution)


def update(context, cam_obj, *, apply: bool) -> CameraSolution | None:
    solution = refresh(cam_obj.data)
    if apply and solution is not None:
        apply_solution(cam_obj, solution)
    return solution


def settings_changed(cam_data, context, *, reset_pitch: bool) -> None:
    """Property update callback: re-solve, and write the camera in a live session."""
    global _updating
    if _updating or not isinstance(cam_data, bpy.types.Camera):
        return
    _updating = True
    try:
        settings = cam_data.ftc
        if reset_pitch and settings.pitch_offset != 0.0:
            settings.pitch_offset = 0.0
        session_obj = bpy.data.objects.get(session_camera) if session_camera else None
        if session_obj is not None and session_obj.data == cam_data:
            update(context, session_obj, apply=settings.live)
        else:
            refresh(cam_data)
    finally:
        _updating = False
    tag_redraw(context)


def updating() -> bool:
    """True inside ``suspended()`` or while a change is being solved."""
    return _updating


@contextmanager
def suspended():
    """Set several properties without re-solving after each one."""
    global _updating
    previous = _updating
    _updating = True
    try:
        yield
    finally:
        _updating = previous


def tag_redraw(context) -> None:
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()
