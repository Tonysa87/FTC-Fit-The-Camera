# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared geometry for the FTC solvers.

Conventions used by every solver:

* Image points are in pixels, origin at the bottom-left corner, x right, y up.
* The camera frame is Blender's: x right, y up, looking along -z.
  A pixel ``q`` back-projects to the direction ``(q - p, -f)`` where ``p`` is the
  principal point and ``f`` the focal length in pixels.
* The world is right-handed with Z up.
* ``rotation`` is camera->world: its columns are the camera axes in world space,
  so it can be written directly into a Blender camera ``matrix_world``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

AXES = ("X", "Y", "Z")


class SolverError(Exception):
    """The input does not define a valid camera."""


@dataclass
class CameraSolution:
    image_size: tuple[int, int]
    focal_px: float
    principal_point: np.ndarray
    rotation: np.ndarray
    position: np.ndarray
    warnings: list[str] = field(default_factory=list)
    # Roll (degrees) taken out by "straighten horizon"; 0 when the option is off.
    removed_roll: float = 0.0
    # Largest angle (degrees) between a guide and the line to its solved vanishing
    # point, before straightening: how well the camera follows the guides.
    guide_misfit: float = 0.0

    @property
    def forward(self) -> np.ndarray:
        return -self.rotation[:, 2]

    @property
    def pitch(self) -> float:
        """Elevation of the view direction above the horizontal plane, degrees."""
        return math.degrees(math.asin(np.clip(self.forward[2], -1.0, 1.0)))

    @property
    def yaw(self) -> float:
        """Heading of the view direction, degrees clockwise from +Y (0..360)."""
        fwd = self.forward
        if math.hypot(fwd[0], fwd[1]) < 1e-9:
            # Looking straight up or down: use the camera up vector instead.
            fwd = self.rotation[:, 1] * (1.0 if self.forward[2] < 0.0 else -1.0)
        return math.degrees(math.atan2(fwd[0], fwd[1])) % 360.0

    @property
    def roll(self) -> float:
        """Rotation about the view axis, degrees, positive counter-clockwise."""
        right, up = self.rotation[:, 0], self.rotation[:, 1]
        return math.degrees(math.atan2(right[2], up[2]))

    @property
    def fov(self) -> tuple[float, float]:
        """Horizontal and vertical field of view, degrees."""
        w, h = self.image_size
        f = self.focal_px
        return (
            math.degrees(2.0 * math.atan(w / (2.0 * f))),
            math.degrees(2.0 * math.atan(h / (2.0 * f))),
        )

    @property
    def camera_height(self) -> float:
        return float(self.position[2])

    @property
    def matrix_world(self) -> np.ndarray:
        m = np.eye(4)
        m[:3, :3] = self.rotation
        m[:3, 3] = self.position
        return m


def parse_axis(axis: str) -> tuple[int, float]:
    """``"+X"`` / ``"-Z"`` / ``"Y"`` -> (axis index, sign)."""
    axis = axis.strip().upper()
    sign = -1.0 if axis.startswith("-") else 1.0
    letter = axis.lstrip("+-")
    if letter not in AXES:
        raise ValueError(f"invalid axis {axis!r}")
    return AXES.index(letter), sign


def image_center(image_size) -> np.ndarray:
    w, h = image_size
    return np.array([w / 2.0, h / 2.0])


def as_points(points) -> np.ndarray:
    return np.asarray(points, dtype=float).reshape(-1, 2)


def ray(point, p, f) -> np.ndarray:
    """Unit direction, in camera space, of the ray through an image point."""
    d = np.array([point[0] - p[0], point[1] - p[1], -f], dtype=float)
    return d / np.linalg.norm(d)


def homogeneous_ray(vp_h, p, f) -> np.ndarray:
    """Unit camera-space direction of a homogeneous image point (may be at infinity).

    The sign is chosen so that the direction points in front of the camera (z <= 0).
    """
    x, y, w = vp_h
    d = np.array([x - p[0] * w, y - p[1] * w, -f * w], dtype=float)
    d /= np.linalg.norm(d)
    return -d if d[2] > 0.0 else d


def vanishing_point(lines, scale: float) -> np.ndarray:
    """Least-squares intersection of image lines, as a homogeneous point.

    ``lines`` is a sequence of segments ``((x1, y1), (x2, y2))``. Coordinates are
    divided by ``scale`` for conditioning; the result is in pixel units, with the
    last component normalised to 1 when the point is finite.
    """
    segs = np.asarray(lines, dtype=float).reshape(-1, 2, 2) / scale
    if len(segs) < 2:
        raise SolverError("a vanishing point needs at least two lines")
    rows = []
    for a, b in segs:
        if np.linalg.norm(b - a) < 1e-9:
            raise SolverError("a guide line has zero length")
        line = np.cross([a[0], a[1], 1.0], [b[0], b[1], 1.0])
        rows.append(line / np.linalg.norm(line[:2]))
    _, sv, vt = np.linalg.svd(np.array(rows))
    if sv[1] < 1e-7 * sv[0]:
        raise SolverError("the guide lines of a vanishing point lie on one line: move them apart")
    v = vt[-1]
    v = np.array([v[0] * scale, v[1] * scale, v[2]])
    if abs(v[2]) > 1e-12:
        v = v / v[2]
    return v


def is_finite_vp(vp_h, image_size, limit: float = 1e3) -> bool:
    """True when the vanishing point lies within ``limit`` image sizes of the image."""
    if abs(vp_h[2]) < 1e-12:
        return False
    return float(np.max(np.abs(vp_h[:2] / vp_h[2]))) < limit * max(image_size)


def orthonormalize(m: np.ndarray) -> np.ndarray:
    """Closest rotation matrix (det = +1) to ``m``."""
    u, _, vt = np.linalg.svd(m)
    r = u @ vt
    if np.linalg.det(r) < 0.0:
        u[:, -1] *= -1.0
        r = u @ vt
    return r


def complete_frame(cols: dict[int, np.ndarray]) -> np.ndarray:
    """Build a right-handed frame from two known axes ``{index: vector}``.

    Returns a 3x3 matrix whose column ``k`` is axis ``k``.
    """
    (i, a), (j, b) = sorted(cols.items())
    k = 3 - i - j
    # (i, j, k) is an even permutation of (0, 1, 2) when k follows j cyclically.
    c = np.cross(a, b) if (j - i) % 3 == 1 else np.cross(b, a)
    m = np.zeros((3, 3))
    m[:, i], m[:, j], m[:, k] = a, b, c
    return orthonormalize(m)


def rotation_about(axis, angle: float) -> np.ndarray:
    """Rotation matrix about a unit axis (Rodrigues), angle in radians."""
    x, y, z = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    c, s = math.cos(angle), math.sin(angle)
    k = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) * c + s * k + (1.0 - c) * np.outer([x, y, z], [x, y, z])


def straighten(rotation: np.ndarray) -> np.ndarray:
    """Remove the roll of a camera->world rotation, keeping its view direction."""
    fwd = -rotation[:, 2]
    right = np.cross(fwd, [0.0, 0.0, 1.0])
    n = np.linalg.norm(right)
    if n < 1e-9:  # looking straight up or down: roll is undefined
        return rotation
    right /= n
    up = np.cross(right, fwd)
    return np.column_stack([right, up, -fwd])


def adjust_pitch(rotation: np.ndarray, delta: float) -> np.ndarray:
    """Tilt a camera->world rotation up by ``delta`` radians about its horizontal axis."""
    if delta == 0.0:
        return rotation
    # Horizontal axis perpendicular to the view direction: rotating about it
    # changes the elevation by exactly ``delta`` and keeps the heading, even
    # when the camera is rolled.
    axis = np.cross(-rotation[:, 2], [0.0, 0.0, 1.0])
    if np.linalg.norm(axis) < 1e-9:
        axis = rotation[:, 0]
    return rotation_about(axis, delta) @ rotation


# Below this, removing the roll does not visibly move the guides.
ROLL_WARNING_DEG = 0.05
# Templates: the panel translates them with their numbers ({} = text).
ROLL_REMOVED = "straighten horizon removed {}° of roll: the camera no longer matches the guides"


def finish_rotation(
    rotation: np.ndarray, straighten_horizon: bool, pitch_offset: float, warnings: list[str]
) -> tuple[np.ndarray, float]:
    """Apply the user's straighten / pitch adjustments to a solved rotation.

    Returns the new rotation and the roll removed by straightening, in degrees.
    Straightening a camera that is really rolled breaks the fit with the guides,
    so that case is reported in ``warnings``.
    """
    removed = 0.0
    if straighten_horizon:
        right, up = rotation[:, 0], rotation[:, 1]
        removed = math.degrees(math.atan2(right[2], up[2]))
        rotation = straighten(rotation)
        if abs(removed) > ROLL_WARNING_DEG:
            warnings.append(ROLL_REMOVED.format(f"{removed:+.1f}"))
    return adjust_pitch(rotation, pitch_offset), removed


# Columns: world axes of the plane's local x, y and normal. The local frame of a
# plane solver (plane = local z = 0) maps onto the world through these matrices.
_PLANE_FRAMES = {
    "XY": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "XZ": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    "YZ": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
}


def plane_frame(plane: str) -> np.ndarray:
    """Rotation whose columns are the world directions of a reference plane's
    local x, y and normal: XY is the floor, XZ and YZ are walls with y up."""
    return np.array(_PLANE_FRAMES[plane], dtype=float).T


def reframe(
    solution: CameraSolution,
    frame: np.ndarray,
    *,
    straighten_horizon: bool = False,
    pitch_offset: float = 0.0,
) -> CameraSolution:
    """Express ``solution`` in a world rotated by ``frame`` (new = frame @ old),
    then apply the straighten / pitch adjustments there, keeping the world origin
    at the same image point."""
    origin_cam = -solution.rotation.T @ solution.position
    warnings = list(solution.warnings)
    rotation, removed = finish_rotation(frame @ solution.rotation, straighten_horizon, pitch_offset, warnings)
    return CameraSolution(
        image_size=solution.image_size,
        focal_px=solution.focal_px,
        principal_point=solution.principal_point,
        rotation=rotation,
        position=-rotation @ origin_cam,
        warnings=warnings,
        removed_roll=removed,
    )


def closest_param_on_line(origin, direction, ray_dir) -> float:
    """Parameter ``t`` of the point of ``origin + t*direction`` closest to the ray
    through the camera centre with direction ``ray_dir``."""
    o = np.asarray(origin, dtype=float)
    a = np.asarray(direction, dtype=float)
    r = np.asarray(ray_dir, dtype=float)
    # Minimise |o + t a - s r|^2 over t and s.
    m = np.array([[a @ a, -(a @ r)], [a @ r, -(r @ r)]])
    rhs = -np.array([a @ o, r @ o])
    if abs(np.linalg.det(m)) < 1e-12:
        raise SolverError("the reference point lies on a line parallel to its axis")
    t, _ = np.linalg.solve(m, rhs)
    return float(t)
