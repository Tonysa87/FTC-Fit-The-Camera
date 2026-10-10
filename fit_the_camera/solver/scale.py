# SPDX-License-Identifier: GPL-3.0-or-later
"""Scale cube: a cube of known edge standing on the reference plane.

Its base corner is any image point of the reference plane (the plane through the
world origin); its vertical edge rises along the plane normal, on the camera's
side. Matching the top of that edge to the image sets the scene scale, the same
way a reference distance does. With the scale already known the cube is only a
visual check.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .common import CameraSolution, SolverError, closest_param_on_line, plane_frame, ray


@dataclass
class ScaleCube:
    """Image points of a bottom corner (``base``) and of the top of the vertical
    edge above it (``top``) of a cube of edge ``size`` on ``plane``."""

    base: tuple[float, float]
    top: tuple[float, float]
    size: float
    plane: str = "XY"


# Cosine below which the camera looks across a plane axis (about 78°): the cube
# keeps that axis' + direction instead of following the noise of the guides.
ACROSS = 0.2

BEYOND_HORIZON = "the scale cube's base corner is beyond the horizon of the reference plane: move it closer"


def _plane_hit(centre, direction, normal) -> np.ndarray | None:
    """Point where the ray ``centre + s*direction`` (s > 0) meets the plane through
    the world origin with ``normal``; ``None`` if it never does."""
    den = normal @ direction
    if abs(den) < 1e-9:
        return None
    s = -(normal @ centre) / den
    return centre + s * direction if s > 0.0 else None


def plane_point(image_point, origin_ray, world_to_cam, normal_world, p, f) -> np.ndarray | None:
    """Camera-space point of the plane through the world origin (seen along
    ``origin_ray`` at unit distance) with world ``normal_world``, at
    ``image_point``; ``None`` beyond the plane's horizon."""
    origin = np.asarray(origin_ray, float)
    hit = _plane_hit(-origin, ray(image_point, p, f), world_to_cam @ normal_world)
    return None if hit is None else hit + origin


def cube_distance(cube: ScaleCube, origin_ray, world_to_cam, p, f) -> float:
    """Distance from the camera of the world origin (seen along ``origin_ray``)
    that makes the cube's vertical edge ``cube.size`` long.

    The top handle counts by its foot on the edge's image line, so moving it
    across the edge does not change the scale; a top on the wrong side of the
    plane measures the same height mirrored.
    """
    if cube.size <= 0.0:
        raise SolverError("the scale cube size must be positive")
    origin = np.asarray(origin_ray, float)  # world origin at unit distance
    normal = world_to_cam @ plane_frame(cube.plane)[:, 2]
    base = plane_point(cube.base, origin, world_to_cam, plane_frame(cube.plane)[:, 2], p, f)
    if base is None:
        raise SolverError(BEYOND_HORIZON)
    up = normal if normal @ origin < 0.0 else -normal  # towards the camera
    p = np.asarray(p, float)
    foot = p + f * base[:2] / -base[2]
    along = f * up[:2] + up[2] * (foot - p)  # image direction of the edge at the base
    if along @ along < 1e-18:
        raise SolverError("the scale cube's vertical edge points at the camera")
    top = np.asarray(cube.top, float)
    top = foot + ((top - foot) @ along) / (along @ along) * along
    height = abs(closest_param_on_line(base, up, ray(top, p, f)))
    if height <= 1e-9 * np.linalg.norm(base):
        raise SolverError("the scale cube has no height: drag its top handle away from the base")
    return cube.size / height


def cube_corners(solution: CameraSolution, base_px, size: float, plane: str) -> np.ndarray | None:
    """World corners of the cube standing on ``plane`` with a bottom corner at the
    image point ``base_px``; ``None`` if that point is not on the plane.

    Corner ``i`` is offset by ``size`` along the plane's x if ``i & 1``, its y if
    ``i & 2`` and its normal if ``i & 4``. Along the normal the cube rises towards
    the camera, so corner 4 tops the edge at ``base_px``. In the plane it extends
    the way the camera looks (on a wall: up), whatever the base and the origin:
    a rule based on them flips the cube while a handle is dragged across the
    camera. An axis the camera looks nearly across keeps its + direction.
    """
    frame = plane_frame(plane)
    u, v, n = frame[:, 0], frame[:, 1], frame[:, 2]
    centre = np.asarray(solution.position, float)
    base = _plane_hit(centre, solution.rotation @ ray(base_px, solution.principal_point, solution.focal_px), n)
    if base is None:
        return None
    forward = -np.asarray(solution.rotation, float)[:, 2]

    def ahead(axis):
        return -axis if forward @ axis < -ACROSS else axis

    u = ahead(u)
    if plane == "XY":
        v = ahead(v)
    n = n if centre @ n >= 0.0 else -n
    return np.array([base + size * ((i & 1) * u + (i >> 1 & 1) * v + (i >> 2 & 1) * n) for i in range(8)])


# Pairs of corner indices joined by an edge, grouped by direction (x, y, normal).
CUBE_EDGES = tuple(tuple((i, i | bit) for i in range(8) if not i & bit) for bit in (1, 2, 4))


def cube_top_px(solution: CameraSolution, base_px, size: float, plane: str):
    """Image point of the top of the cube's vertical edge above ``base_px``, or
    ``None`` when the base is not on the plane or the top is behind the camera."""
    corners = cube_corners(solution, base_px, size, plane)
    if corners is None:
        return None
    cam = solution.rotation.T @ (corners[4] - solution.position)
    if cam[2] > -1e-9:
        return None
    return solution.principal_point + solution.focal_px * cam[:2] / -cam[2]
