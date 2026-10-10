# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibration from 1, 2 or 3 vanishing points.

Each vanishing point is given by two or more image segments that are parallel in
the world, and by the world axis they run along (``"+X"``, ``"-Y"``, ...). The
axis sign says which way the axis points: ``"+X"`` means +X runs away from the
camera towards the vanishing point.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .common import (
    CameraSolution,
    SolverError,
    as_points,
    closest_param_on_line,
    complete_frame,
    finish_rotation,
    homogeneous_ray,
    image_center,
    is_finite_vp,
    parse_axis,
    ray,
    vanishing_point,
)


@dataclass
class ReferenceDistance:
    """A known world distance between two image points on the world axis that
    passes through the origin."""

    axis: str
    start: tuple[float, float]
    end: tuple[float, float]
    length: float


def orthocenter(a, b, c) -> np.ndarray:
    """Orthocentre of the triangle ``abc``."""
    a, b, c = (np.asarray(v, dtype=float) for v in (a, b, c))
    # Altitude from a is perpendicular to bc, altitude from b perpendicular to ac.
    m = np.array([c - b, c - a])
    rhs = np.array([(c - b) @ a, (c - a) @ b])
    if abs(np.linalg.det(m)) < 1e-9 * max(1.0, float(np.abs(m).max()) ** 2):
        raise SolverError("the three vanishing points are collinear")
    return np.linalg.solve(m, rhs)


def focal_from_two_vps(v1, v2, p) -> float:
    f2 = -float((np.asarray(v1) - p) @ (np.asarray(v2) - p))
    if f2 <= 0.0:
        raise SolverError("vanishing points are not compatible with a real camera: move the guides")
    return float(np.sqrt(f2))


def second_axis_from_horizon(d1, v1_h, horizon_dir, p, f) -> np.ndarray:
    """Direction orthogonal to ``d1`` whose vanishing point lies on the image line
    through the first vanishing point with direction ``horizon_dir``.

    The returned direction is oriented so that its image moves along ``horizon_dir``.
    """
    h = np.asarray(horizon_dir, dtype=float)
    if np.linalg.norm(h) < 1e-9:
        raise SolverError("the horizon direction has zero length")
    h = h / np.linalg.norm(h)
    # Back-projected plane of the image line through v1 with direction h.
    normal = np.cross(homogeneous_ray(v1_h, p, f), [h[0], h[1], 0.0])
    d2 = np.cross(normal, d1)
    n = np.linalg.norm(d2)
    if n < 1e-9:
        raise SolverError("the horizon line passes through the principal point direction")
    d2 /= n
    # Image displacement of a point moving along d2 from the first vanishing point
    # direction, used only to pick the sign.
    if d2[:2] @ h < 0.0:
        d2 = -d2
    return d2


def solve_vanishing_points(
    vp_lines,
    axes,
    image_size,
    *,
    principal_point=None,
    focal_px: float | None = None,
    horizon_dir=None,
    origin=None,
    camera_distance: float = 10.0,
    reference: ReferenceDistance | None = None,
    straighten_horizon: bool = False,
    pitch_offset: float = 0.0,
) -> CameraSolution:
    """Solve a camera from 1, 2 or 3 vanishing points.

    * ``vp_lines``: one list of segments per vanishing point.
    * ``axes``: world axis of each vanishing point. With one vanishing point the
      second entry is the axis of ``horizon_dir``.
    * 1 point: ``focal_px`` and ``horizon_dir`` are required.
    * 2 points: the focal length is solved, the principal point is ``principal_point``
      (image centre by default).
    * 3 points: the principal point is the orthocentre of the vanishing points.
    * ``origin``: image point of the world origin (image centre by default).
    * Scale: ``reference`` if given, otherwise ``camera_distance`` from the origin.
    """
    count = len(vp_lines)
    if count not in (1, 2, 3):
        raise SolverError("use 1, 2 or 3 vanishing points")
    parsed = [parse_axis(a) for a in axes]
    if len(parsed) < 2:
        raise SolverError("two axes are required")
    if parsed[0][0] == parsed[1][0]:
        raise SolverError("the first two vanishing points must use different axes")

    w, h = image_size
    scale = float(max(w, h))
    vps = [vanishing_point(lines, scale) for lines in vp_lines]
    warnings: list[str] = []

    if count == 1:
        if not focal_px or focal_px <= 0.0:
            raise SolverError("one vanishing point needs a known focal length")
        if horizon_dir is None:
            raise SolverError("one vanishing point needs the horizon direction")
        p = image_center(image_size) if principal_point is None else np.asarray(principal_point, float)
        f = float(focal_px)
        d1 = homogeneous_ray(vps[0], p, f)
        d2 = second_axis_from_horizon(d1, vps[0], horizon_dir, p, f)
    else:
        for v in vps:
            if not is_finite_vp(v, image_size):
                raise SolverError("guide lines are parallel in the image: the vanishing point is at infinity")
        pts = [v[:2] for v in vps]
        if count == 3:
            p = orthocenter(*pts)
        else:
            p = image_center(image_size) if principal_point is None else np.asarray(principal_point, float)
        f = focal_from_two_vps(pts[0], pts[1], p)
        d1, d2 = ray(pts[0], p, f), ray(pts[1], p, f)

    (i, si), (j, sj) = parsed[0], parsed[1]
    # Columns of world->camera are the world axes expressed in camera space.
    world_to_cam = complete_frame({i: si * d1, j: sj * d2})
    rotation = finish_rotation(world_to_cam.T, straighten_horizon, pitch_offset)
    world_to_cam = rotation.T

    o = image_center(image_size) if origin is None else as_points(origin)[0]
    r_o = ray(o, p, f)
    if reference is not None:
        k, _ = parse_axis(reference.axis)
        axis_cam = world_to_cam[:, k]
        t_a = closest_param_on_line(r_o, axis_cam, ray(reference.start, p, f))
        t_b = closest_param_on_line(r_o, axis_cam, ray(reference.end, p, f))
        unit_length = abs(t_b - t_a)
        if unit_length < 1e-9 or reference.length <= 0.0:
            raise SolverError("the reference distance is zero")
        distance = reference.length / unit_length
    else:
        if camera_distance <= 0.0:
            raise SolverError("the camera distance must be positive")
        distance = camera_distance
    origin_cam = distance * r_o
    position = -rotation @ origin_cam
    if position[2] < 0.0:
        warnings.append("the camera is below the XY plane: flip an axis if this is not intended")

    return CameraSolution(
        image_size=(int(w), int(h)),
        focal_px=f,
        principal_point=np.asarray(p, float),
        rotation=rotation,
        position=position,
        warnings=warnings,
    )
