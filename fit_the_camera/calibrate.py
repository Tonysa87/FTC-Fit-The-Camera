# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge between the stored settings, the solver and the Blender camera."""

from __future__ import annotations

import math
from contextlib import contextmanager

import bpy
from mathutils import Matrix

from .solver import (
    CameraSolution,
    ReferenceDistance,
    SolverError,
    focal_px_from_35mm,
    focal_px_from_mm,
    solve_horizon,
    solve_rectangle,
    solve_vanishing_points,
    to_blender,
)

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
    "pp": (0.50, 0.50),
    "rect_0": (0.30, 0.20),
    "rect_1": (0.70, 0.20),
    "rect_2": (0.62, 0.42),
    "rect_3": (0.38, 0.42),
    "hz_a": (0.80, 0.55),
    "hz_b": (0.20, 0.55),
}

# Camera object name of the running calibration session, if any.
session_camera: str | None = None

_solutions: dict[int, CameraSolution] = {}
_updating = False


# ----------------------------------------------------------------------------
# Settings access


def view_camera(context):
    """Camera object shown by the 3D view in ``context`` (or the scene camera)."""
    space = getattr(context, "space_data", None)
    if space is not None and space.type == "VIEW_3D" and space.use_local_camera and space.camera:
        return space.camera
    cam = context.scene.camera
    return cam if cam is not None and cam.type == "CAMERA" else None


def ensure_handles(settings) -> None:
    present = {h.name for h in settings.handles}
    for key, co in HANDLE_DEFAULTS.items():
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
    for key, co in HANDLE_DEFAULTS.items():
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


def vp_keys(index: int) -> list[str]:
    """Handle keys of the two guide lines of vanishing point ``index`` (1-based)."""
    return [f"vp{index}_1a", f"vp{index}_1b", f"vp{index}_2a", f"vp{index}_2b"]


def active_handle_keys(settings) -> list[str]:
    """Handles that are visible and editable in the current mode."""
    keys: list[str] = []
    if settings.mode == "VP":
        count = int(settings.vp_count)
        for i in range(1, count + 1):
            keys += vp_keys(i)
        if count == 1:
            keys += ["hz_a", "hz_b"]
        keys.append("origin")
        if settings.scale_mode == "REFERENCE":
            keys += ["ref_a", "ref_b"]
        if settings.pp_mode == "MANUAL" and count != 3:
            keys.append("pp")
    elif settings.mode == "RECT":
        keys += [f"rect_{i}" for i in range(4)]
        if settings.pp_mode == "MANUAL":
            keys.append("pp")
    else:
        keys += ["hz_a", "hz_b"]
        if settings.pp_mode == "MANUAL":
            keys.append("pp")
    return keys


# ----------------------------------------------------------------------------
# Camera data


def known_sensor_mm(settings) -> float | None:
    data = settings.camera_data
    if data.sensor_mm_state != "MISSING" and data.sensor_mm > 0.0:
        return data.sensor_mm
    return None


def known_focal_px(settings) -> float | None:
    """Focal length in pixels from the camera data, ``None`` if unknown."""
    data = settings.camera_data
    size = image_size(settings)
    sensor = known_sensor_mm(settings)
    if data.focal_mm_state != "MISSING" and data.focal_mm > 0.0 and sensor:
        return focal_px_from_mm(data.focal_mm, sensor, size)
    if data.focal_35mm_state != "MISSING" and data.focal_35mm > 0.0:
        return focal_px_from_35mm(data.focal_35mm, size)
    return None


def mode_needs_focal(settings) -> bool:
    return settings.mode == "HORIZON" or (settings.mode == "VP" and settings.vp_count == "1")


# ----------------------------------------------------------------------------
# Solving


def _points(settings, keys):
    return [to_pixels(settings, handle(settings, k)) for k in keys]


def solve(settings) -> CameraSolution:
    """Solve the camera described by ``settings``; raises ``SolverError``."""
    size = image_size(settings)
    if not size[0] or not size[1]:
        raise SolverError("no image loaded")
    pp = to_pixels(settings, handle(settings, "pp")) if settings.pp_mode == "MANUAL" else None
    common = {"straighten_horizon": settings.straighten, "pitch_offset": settings.pitch_offset}

    if settings.mode == "VP":
        count = int(settings.vp_count)
        lines = []
        for i in range(1, count + 1):
            a1, b1, a2, b2 = _points(settings, vp_keys(i))
            lines.append([(a1, b1), (a2, b2)])
        axes = [settings.vp1_axis, settings.vp2_axis, settings.vp3_axis][: max(count, 2)]
        horizon_dir = None
        focal = None
        if count == 1:
            focal = known_focal_px(settings)
            if focal is None:
                raise SolverError("one vanishing point needs the focal length: enter it in Camera Data")
            a, b = _points(settings, ["hz_a", "hz_b"])
            horizon_dir = (b[0] - a[0], b[1] - a[1])
        reference = None
        if settings.scale_mode == "REFERENCE":
            ra, rb = _points(settings, ["ref_a", "ref_b"])
            reference = ReferenceDistance(settings.ref_axis, ra, rb, settings.ref_length)
        return solve_vanishing_points(
            lines,
            axes,
            size,
            principal_point=pp,
            focal_px=focal,
            horizon_dir=horizon_dir,
            origin=to_pixels(settings, handle(settings, "origin")),
            camera_distance=settings.camera_distance,
            reference=reference,
            **common,
        )

    if settings.mode == "RECT":
        focal = known_focal_px(settings) if settings.rect_use_focal else None
        if settings.rect_use_focal and focal is None:
            raise SolverError("the focal length is unknown: enter it in Camera Data")
        return solve_rectangle(
            _points(settings, [f"rect_{i}" for i in range(4)]),
            settings.rect_width,
            settings.rect_height,
            size,
            principal_point=pp,
            focal_px=focal,
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


def cached_solution(cam_data) -> CameraSolution | None:
    return _solutions.get(cam_data.session_uid)


def _store_results(settings, solution: CameraSolution | None, error: str) -> None:
    res = settings.results
    res.valid = solution is not None
    res.error = error
    if solution is None:
        res.warnings = ""
        return
    sensor = known_sensor_mm(settings)
    bc = to_blender(solution, sensor)
    fov_h, fov_v = solution.fov
    res.warnings = "\n".join(solution.warnings)
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


def refresh(cam_data) -> CameraSolution | None:
    """Solve ``cam_data``'s settings, cache the solution and store the results."""
    settings = cam_data.ftc
    try:
        solution = solve(settings)
        error = ""
    except SolverError as exc:
        solution, error = None, str(exc)
    if solution is None:
        _solutions.pop(cam_data.session_uid, None)
    else:
        _solutions[cam_data.session_uid] = solution
    _store_results(settings, solution, error)
    return solution


def apply_solution(cam_obj, solution: CameraSolution) -> None:
    """Write ``solution`` into the camera object and its data."""
    settings = cam_obj.data.ftc
    bc = to_blender(solution, known_sensor_mm(settings))
    cam = cam_obj.data
    cam.type = "PERSP"
    cam.lens_unit = "MILLIMETERS"
    cam.sensor_fit = bc.sensor_fit
    cam.sensor_width = bc.sensor_width
    cam.sensor_height = bc.sensor_height
    cam.lens = bc.lens
    cam.shift_x = bc.shift_x
    cam.shift_y = bc.shift_y
    matrix = Matrix(bc.matrix_world.tolist())
    if settings.use_anchor:
        matrix = Matrix(settings.anchor_matrix) @ matrix
    cam_obj.matrix_world = matrix


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
