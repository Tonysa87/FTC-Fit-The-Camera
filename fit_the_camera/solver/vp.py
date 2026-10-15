# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibration from 1, 2 or 3 vanishing points.

Each vanishing point is given by two or more image segments that are parallel in
the world, and by the world axis they run along (``"+X"``, ``"-Y"``, ...). The
axis sign follows the first segment of the group: ``"+X"`` means +X runs along it
from its first to its second end point. Unlike "towards the vanishing point",
this stays put when the vanishing point is far away and jumps across infinity.
"""

from __future__ import annotations

import math
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
    orthonormalize,
    parse_axis,
    plane_frame,
    ray,
    vanishing_point,
)
from .refine import focal_prior_weight, refine
from .scale import ScaleCube, cube_distance, plane_point


@dataclass
class ReferenceDistance:
    """A known world distance between two image points. The start lies on the
    reference ``plane`` (through the world origin), anywhere on it. With an
    ``axis`` in the plane the end lies on the plane too; with the plane normal
    (a height) the end lies on the line along the normal through the start."""

    axis: str
    start: tuple[float, float]
    end: tuple[float, float]
    length: float
    plane: str = "XY"


def orthocenter(a, b, c) -> np.ndarray:
    """Orthocentre of the triangle ``abc``."""
    a, b, c = (np.asarray(v, dtype=float) for v in (a, b, c))
    # Altitude from a is perpendicular to bc, altitude from b perpendicular to ac.
    m = np.array([c - b, c - a])
    rhs = np.array([(c - b) @ a, (c - a) @ b])
    if abs(np.linalg.det(m)) < 1e-9 * max(1.0, float(np.abs(m).max()) ** 2):
        raise SolverError("the three vanishing points are collinear")
    return np.linalg.solve(m, rhs)


BEYOND_HORIZON_REF = (
    "the first reference handle is beyond the horizon of its plane: move it closer",
    "the second reference handle is beyond the horizon of its plane: move it closer",
)


def reference_distance(reference: ReferenceDistance, origin_ray, world_to_cam, p, f) -> float:
    """Distance from the camera of the world origin (seen along ``origin_ray``)
    that makes the reference ``reference.length`` long."""
    if reference.length <= 0.0:
        raise SolverError("the reference distance is zero")
    k, _ = parse_axis(reference.axis)
    frame = plane_frame(reference.plane)
    start = plane_point(reference.start, origin_ray, world_to_cam, frame[:, 2], p, f)
    if start is None:
        raise SolverError(BEYOND_HORIZON_REF[0])
    if abs(frame[k, 2]) > 0.5:
        # A height: the end is on the line along the normal through the start.
        unit_length = abs(closest_param_on_line(start, world_to_cam[:, k], ray(reference.end, p, f)))
    else:
        end = plane_point(reference.end, origin_ray, world_to_cam, frame[:, 2], p, f)
        if end is None:
            raise SolverError(BEYOND_HORIZON_REF[1])
        unit_length = float(np.linalg.norm(end - start))
    if unit_length < 1e-9 * np.linalg.norm(start):
        raise SolverError("the reference distance is zero")
    return reference.length / unit_length


INCOMPATIBLE = (
    "the vanishing points do not fit a real camera: the two directions are probably not perpendicular "
    "in reality (e.g. two facades that are nearly parallel), or one vanishes too far away; "
    "use the known focal length or other lines"
)


def focal_from_two_vps(v1, v2, p) -> float:
    f2 = -float((np.asarray(v1) - p) @ (np.asarray(v2) - p))
    if f2 <= 0.0:
        raise SolverError(INCOMPATIBLE)
    return float(np.sqrt(f2))


def second_axis_from_line(d1, line, p, f) -> np.ndarray:
    """Direction of the second axis from one image segment parallel to it.

    The second axis is orthogonal to ``d1``, so its vanishing point lies on the
    vanishing line of the planes orthogonal to ``d1``: the points ``q`` with
    ``(q - p, -f) . d1 = 0``. It is where the segment's line crosses it. The
    positive direction runs along the segment, from its first to its second end.
    """
    a, b = (np.asarray(v, dtype=float) for v in line)
    u = b - a
    if np.linalg.norm(u) < 1e-9:
        raise SolverError("the second axis line has zero length")
    den = u @ d1[:2]
    t = (f * d1[2] - (a - p) @ d1[:2]) / den if abs(den) > 1e-12 * np.linalg.norm(u) else None
    if t is None or abs(t) * np.linalg.norm(u) > 1e9 * f:
        d2 = np.array([u[0], u[1], 0.0])
    else:
        q = a + t * u
        d2 = np.array([q[0] - p[0], q[1] - p[1], -f])
    d2 -= (d2 @ d1) * d1
    n = np.linalg.norm(d2)
    if n < 1e-9:
        raise SolverError("the second axis line points at the first vanishing point")
    return orient_along(d2 / n, (a, b), p, f)


def orient_along(d, line, p, f) -> np.ndarray:
    """Flip camera-space direction ``d`` so that, in the image, a point moving
    along it travels from the guide's first handle towards its second.

    The image velocity of a point on the guide moving along ``d`` is
    ``f * d.xy + d.z * (m - p)`` (``m`` the guide midpoint): it is smooth even
    when the vanishing point goes to infinity, so the sign never jumps.
    """
    a, b = (np.asarray(e, float) for e in line)
    m = (a + b) / 2.0
    velocity = f * d[:2] + d[2] * (m - p)
    return -d if velocity @ (b - a) < 0.0 else d


def axis_direction(vp_h, lines, p, f) -> np.ndarray:
    """Camera-space direction of a guide group's axis; its positive side runs
    along the first guide, from the first to the second handle."""
    return orient_along(homogeneous_ray(vp_h, p, f), lines[0], p, f)


def max_misfit(groups, p, f, rotation) -> float:
    """Largest angle (degrees) between a guide and the line from its midpoint to
    the vanishing point of its axis; works for vanishing points at infinity."""
    worst = 0.0
    for axis, lines in groups:
        d = rotation[axis, :]
        v = np.array([f * d[0] - p[0] * d[2], f * d[1] - p[1] * d[2], -d[2]])  # K @ (d.x, d.y, -d.z)
        for a, b in lines:
            a, b = np.asarray(a, float), np.asarray(b, float)
            u = b - a
            t = v[:2] - (a + b) / 2.0 * v[2]
            if np.linalg.norm(u) < 1e-9 or np.linalg.norm(t) < 1e-9:
                continue
            angle = math.degrees(math.atan2(abs(u[0] * t[1] - u[1] * t[0]), abs(u @ t)))
            worst = max(worst, angle)
    return worst


def best_pair_focal(vps, p, image_size) -> float:
    """Focal length from the best conditioned pair of vanishing points."""
    best = None
    for a, b in ((0, 1), (0, 2), (1, 2))[: 1 if len(vps) == 2 else 3]:
        va, vb = vps[a], vps[b]
        if not (is_finite_vp(va, image_size) and is_finite_vp(vb, image_size)):
            continue
        f2 = -float((va[:2] - p) @ (vb[:2] - p))
        if f2 <= 0.0:
            continue
        f = math.sqrt(f2)
        # Both axes well away from the image plane give a stable focal length.
        quality = min(abs(ray(va[:2], p, f)[2]), abs(ray(vb[:2], p, f)[2]))
        if best is None or quality > best[0]:
            best = (quality, f)
    if best is None:
        if len(vps) == 2 and not all(is_finite_vp(v, image_size) for v in vps):
            raise SolverError("guide lines are parallel in the image: the vanishing point is at infinity")
        raise SolverError(INCOMPATIBLE)
    return best[1]


# Largest guide misfit (degrees) that still counts as agreeing with a known focal length.
KNOWN_FOCAL_TOLERANCE_DEG = 1.0


def refine_known_focal(groups, p, prior, guides_focal, initial_rotation):
    """Known focal length refined by the guides, as far as they measure it.

    The guides overrule it only when they cannot agree with it (a guide more
    than ``KNOWN_FOCAL_TOLERANCE_DEG`` off, e.g. a cropped or zoomed photo) and
    fit clearly better with their own focal length.
    """
    known = prior[0]
    f, rotation, _ = refine(groups, p, known, initial_rotation(known), fix_focal=False, focal_prior=prior)
    misfit = max_misfit(groups, p, f, rotation)
    if misfit <= KNOWN_FOCAL_TOLERANCE_DEG or guides_focal is None:
        return f, rotation
    f_g, rotation_g, _ = refine(groups, p, guides_focal, initial_rotation(guides_focal), fix_focal=False)
    if max_misfit(groups, p, f_g, rotation_g) < 0.75 * misfit:
        return f_g, rotation_g
    return f, rotation


def solve_vanishing_points(
    vp_lines,
    axes,
    image_size,
    *,
    principal_point=None,
    solve_principal_point: bool = False,
    focal_px: float | None = None,
    known_focal_px: float | None = None,
    axis2_line=None,
    origin=None,
    camera_distance: float = 10.0,
    reference: ReferenceDistance | None = None,
    cube: ScaleCube | None = None,
    third_axis_line=None,
    straighten_horizon: bool = False,
    pitch_offset: float = 0.0,
) -> CameraSolution:
    """Solve a camera from 1, 2 or 3 vanishing points.

    * ``vp_lines``: one list of segments per vanishing point.
    * ``axes``: world axis of each vanishing point. With one vanishing point the
      second entry is the axis of ``axis2_line``.
    * 1 point: ``focal_px`` and ``axis2_line`` (one segment parallel to the second
      axis) are required.
    * 2 or 3 points: the focal length is solved, unless ``focal_px`` is given; the
      principal point is ``principal_point`` (image centre by default). When there
      is more data than the two-point formula uses (a third vanishing point, or a
      known focal length) the camera is refined by least squares on all guides.
    * ``known_focal_px``: with 2 or 3 points and no ``focal_px``, a focal length
      known from the camera (EXIF): the guides refine it by least squares, as far
      as they measure it, and overrule it only when they cannot agree with it
      (see ``refine_known_focal``).
    * 3 points with ``solve_principal_point``: the principal point is the
      orthocentre of the vanishing points (closed form, no refinement).
    * ``third_axis_line``: with two vanishing points, an optional segment along the
      third axis (e.g. one vertical edge) that joins the least squares.
    * ``origin``: image point of the world origin (image centre by default).
    * Scale: ``reference`` or ``cube`` if given, otherwise ``camera_distance``
      from the origin.
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

    (i, si), (j, sj) = parsed[0], parsed[1]
    k = 3 - i - j
    if count == 1:
        if not focal_px or focal_px <= 0.0:
            raise SolverError("one vanishing point needs a known focal length")
        if axis2_line is None:
            raise SolverError("one vanishing point needs a line along the second axis")
        p = image_center(image_size) if principal_point is None else np.asarray(principal_point, float)
        f = float(focal_px)
        d1 = axis_direction(vps[0], vp_lines[0], p, f)
        d2 = second_axis_from_line(d1, axis2_line, p, f)
        rotation = complete_frame({i: si * d1, j: sj * d2}).T
        groups = [(i, vp_lines[0]), (j, [axis2_line])]
    else:
        if count == 3 and solve_principal_point:
            for v in vps:
                if not is_finite_vp(v, image_size):
                    raise SolverError("guide lines are parallel in the image: the vanishing point is at infinity")
            p = orthocenter(*(v[:2] for v in vps))
            f = focal_from_two_vps(vps[0][:2], vps[1][:2], p)
        else:
            p = image_center(image_size) if principal_point is None else np.asarray(principal_point, float)
            guides_focal = None
            if focal_px:
                f = float(focal_px)
            else:
                try:
                    f = guides_focal = best_pair_focal(vps, p, image_size)
                except SolverError:
                    # The guides alone fit no camera: the known focal length can.
                    if not known_focal_px:
                        raise
                    f = float(known_focal_px)

        def initial_rotation(f):
            dirs = [axis_direction(v, lines, p, f) for v, lines in zip(vps, vp_lines)]
            if count == 2:
                return complete_frame({i: si * dirs[0], j: sj * dirs[1]}).T
            # The third axis follows the first two: orient its direction to match.
            third = np.cross(si * dirs[0], sj * dirs[1]) * (1.0 if (j - i) % 3 == 1 else -1.0)
            cols = np.zeros((3, 3))
            cols[:, i], cols[:, j] = si * dirs[0], sj * dirs[1]
            cols[:, k] = dirs[2] if dirs[2] @ third >= 0.0 else -dirs[2]
            return orthonormalize(cols).T

        rotation = initial_rotation(f)

        # More data than the closed form uses: least squares on every guide.
        groups = [(axis, lines) for axis, lines in zip((i, j, k), vp_lines)]
        if count == 2 and third_axis_line is not None:
            groups.append((k, [third_axis_line]))
        groups = [(axis, [tuple(map(tuple, seg)) for seg in lines]) for axis, lines in groups]
        prior = None
        if known_focal_px and not focal_px and not (count == 3 and solve_principal_point):
            prior = (float(known_focal_px), focal_prior_weight(image_size))
        overdetermined = count == 3 or focal_px or prior or third_axis_line is not None
        if overdetermined and not (count == 3 and solve_principal_point):
            if prior:
                f, rotation = refine_known_focal(groups, p, prior, guides_focal, initial_rotation)
            else:
                f, rotation, _ = refine(groups, p, f, rotation, fix_focal=bool(focal_px))

    misfit = max_misfit(groups, p, f, rotation)
    rotation, removed_roll = finish_rotation(rotation, straighten_horizon, pitch_offset, warnings)
    world_to_cam = rotation.T

    o = image_center(image_size) if origin is None else as_points(origin)[0]
    r_o = ray(o, p, f)
    if reference is not None:
        distance = reference_distance(reference, r_o, world_to_cam, p, f)
    elif cube is not None:
        distance = cube_distance(cube, r_o, world_to_cam, p, f)
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
        removed_roll=removed_roll,
        guide_misfit=misfit,
    )
