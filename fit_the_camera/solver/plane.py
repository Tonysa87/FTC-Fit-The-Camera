# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibration from a rectangle of known size lying on the world plane Z = 0.

The four image corners are given in order. The first edge (corner 0 -> 1) runs
along +X and measures ``width``; the second edge (corner 1 -> 2) measures
``height``. The rectangle is centred on the world origin. If the corners are
ordered so that the camera would end up below the plane, the Y axis is flipped
so the camera always looks at the rectangle from above.
"""

from __future__ import annotations

import math

import numpy as np

from .common import (
    CameraSolution,
    SolverError,
    as_points,
    finish_rotation,
    image_center,
    orthonormalize,
)

# Below this angle between the plane normal and the view axis the focal length
# cannot be estimated reliably from a rectangle.
FRONTAL_LIMIT_DEG = 12.0


def _normalization(points: np.ndarray) -> np.ndarray:
    """Hartley normalisation: centroid at origin, mean distance sqrt(2)."""
    c = points.mean(axis=0)
    d = np.linalg.norm(points - c, axis=1).mean()
    s = math.sqrt(2.0) / d if d > 0.0 else 1.0
    return np.array([[s, 0.0, -s * c[0]], [0.0, s, -s * c[1]], [0.0, 0.0, 1.0]])


def homography(src, dst) -> np.ndarray:
    """Normalised DLT homography mapping ``src`` points to ``dst`` points."""
    src, dst = as_points(src), as_points(dst)
    if len(src) < 4 or len(src) != len(dst):
        raise SolverError("a homography needs four point pairs")
    ts, td = _normalization(src), _normalization(dst)
    hs = (ts @ np.column_stack([src, np.ones(len(src))]).T).T
    hd = (td @ np.column_stack([dst, np.ones(len(dst))]).T).T
    rows = []
    for (x, y, _), (u, v, _) in zip(hs, hd):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    _, sv, vt = np.linalg.svd(np.array(rows))
    if sv[-2] < 1e-10 * sv[0]:
        raise SolverError("the rectangle corners are degenerate (three corners are collinear)")
    hn = vt[-1].reshape(3, 3)
    hmat = np.linalg.inv(td) @ hn @ ts
    return hmat / np.linalg.norm(hmat)


def _is_convex(points: np.ndarray) -> bool:
    signs = []
    for k in range(4):
        a, b, c = points[k], points[(k + 1) % 4], points[(k + 2) % 4]
        u, v = b - a, c - b
        signs.append(u[0] * v[1] - u[1] * v[0] > 0.0)
    return all(signs) or not any(signs)


def focal_from_homography(hmat: np.ndarray) -> float | None:
    """Focal length (pixels) from the two Zhang constraints, principal point at
    the origin of the image coordinates and square pixels. ``None`` if no
    positive estimate exists."""
    h1, h2 = hmat[:, 0], hmat[:, 1]
    # With K = diag(f, f, -1), omega = diag(1/f^2, 1/f^2, 1); the unknown is x = 1/f^2.
    #   h1' omega h2 = 0            -> a1 x + b1 = 0
    #   h1' omega h1 = h2' omega h2 -> a2 x + b2 = 0
    a1, b1 = h1[0] * h2[0] + h1[1] * h2[1], h1[2] * h2[2]
    a2, b2 = h1[0] ** 2 + h1[1] ** 2 - h2[0] ** 2 - h2[1] ** 2, h1[2] ** 2 - h2[2] ** 2
    a = np.array([a1, a2])
    b = np.array([b1, b2])
    if a @ a > 0.0:
        x = -(a @ b) / (a @ a)
        if x > 0.0:
            return 1.0 / math.sqrt(x)
    estimates = [-bi / ai for ai, bi in zip(a, b) if abs(ai) > 1e-15 and -bi / ai > 0.0]
    if not estimates:
        return None
    return 1.0 / math.sqrt(float(np.mean(estimates)))


def _pose(hmat: np.ndarray, f: float) -> tuple[np.ndarray, np.ndarray]:
    """World->camera rotation and origin in camera space from a plane homography."""
    k_inv = np.diag([1.0 / f, 1.0 / f, -1.0])
    m = k_inv @ hmat
    lam = 2.0 / (np.linalg.norm(m[:, 0]) + np.linalg.norm(m[:, 1]))
    # The plane origin must be in front of the camera (negative camera z).
    if m[2, 2] * lam > 0.0:
        lam = -lam
    r1, r2, t = lam * m[:, 0], lam * m[:, 1], lam * m[:, 2]
    world_to_cam = orthonormalize(np.column_stack([r1, r2, np.cross(r1, r2)]))
    return world_to_cam, t


def solve_rectangle(
    corners,
    width: float,
    height: float,
    image_size,
    *,
    principal_point=None,
    focal_px: float | None = None,
    straighten_horizon: bool = False,
    pitch_offset: float = 0.0,
) -> CameraSolution:
    """Solve a camera from the four image corners of a known rectangle."""
    if width <= 0.0 or height <= 0.0:
        raise SolverError("the rectangle size must be positive")
    img = as_points(corners)
    if len(img) != 4:
        raise SolverError("the rectangle needs four corners")
    if not _is_convex(img):
        raise SolverError("the rectangle corners must form a convex shape, in order")

    w, h = image_size
    p = image_center(image_size) if principal_point is None else np.asarray(principal_point, float)
    centred = img - p
    warnings: list[str] = []

    def solve_for(y_sign: float):
        hw, hh = width / 2.0, height / 2.0
        plane = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]]) * [1.0, y_sign]
        hmat = homography(plane, centred)
        f = focal_px
        if not f:
            f = focal_from_homography(hmat)
            if f is None:
                raise SolverError("the focal length cannot be estimated from this rectangle")
        world_to_cam, origin_cam = _pose(hmat, f)
        position = -world_to_cam.T @ origin_cam
        return f, world_to_cam, origin_cam, position

    f, world_to_cam, origin_cam, position = solve_for(1.0)
    if position[2] < 0.0:
        f, world_to_cam, origin_cam, position = solve_for(-1.0)

    if not focal_px:
        # Angle between the plane normal and the optical axis.
        tilt = math.degrees(math.acos(min(1.0, abs(world_to_cam[2, 2]))))
        if tilt < FRONTAL_LIMIT_DEG:
            warnings.append("the rectangle is almost facing the camera: the focal length estimate is unstable")

    rotation, removed_roll = finish_rotation(world_to_cam.T, straighten_horizon, pitch_offset, warnings)
    position = -rotation @ origin_cam
    return CameraSolution(
        image_size=(int(w), int(h)),
        focal_px=float(f),
        principal_point=np.asarray(p, float),
        rotation=rotation,
        position=position,
        warnings=warnings,
        removed_roll=removed_roll,
    )
