# SPDX-License-Identifier: GPL-3.0-or-later
"""Least-squares refinement of a camera on all the guide lines at once.

The closed-form solutions use exactly two vanishing points. When more guides are
available (a third vanishing point, or a known focal length) this refines the
rotation, and the focal length unless it is known, so that every guide line
passes as closely as possible through the vanishing point of its axis.

The residual of a guide (a, b) is the distance of its end points from the image
line joining its midpoint to the axis vanishing point, in homogeneous
coordinates, so it stays well defined when a vanishing point is very far away.
"""

from __future__ import annotations

import math

import numpy as np

from .common import rotation_about

MAX_ITERATIONS = 30
_STEP = 1e-6


def _small_rotation(w) -> np.ndarray:
    angle = float(np.linalg.norm(w))
    return np.eye(3) if angle < 1e-15 else rotation_about(w / angle, angle)


def _prepare(groups):
    """Stack the guides: homogeneous end points and the axis of each guide."""
    axes, ends_a, ends_b = [], [], []
    for axis, lines in groups:
        for a, b in lines:
            axes.append(axis)
            ends_a.append((a[0], a[1], 1.0))
            ends_b.append((b[0], b[1], 1.0))
    return np.array(axes), np.array(ends_a, float), np.array(ends_b, float)


def residuals(groups, p, f, rotation) -> np.ndarray:
    """Pixel residuals of every guide end point.

    ``groups`` is a list of (world axis index, [(a, b), ...]) or the output of
    ``_prepare``; ``rotation`` is camera -> world.
    """
    axes, ha, hb = groups if isinstance(groups, tuple) else _prepare(groups)
    k = np.array([[f, 0.0, p[0]], [0.0, f, p[1]], [0.0, 0.0, 1.0]])
    d = rotation[axes, :]  # world axis of each guide, in camera space
    v = (k @ np.column_stack([d[:, 0], d[:, 1], -d[:, 2]]).T).T  # vanishing points, homogeneous
    lines = np.cross((ha + hb) / 2.0, v)
    norm = np.hypot(lines[:, 0], lines[:, 1])
    norm = np.where(norm < 1e-12, np.inf, norm)  # vanishing point on the midpoint: no residual
    ra = np.einsum("ij,ij->i", lines, ha) / norm
    rb = np.einsum("ij,ij->i", lines, hb) / norm
    return np.column_stack([ra, rb]).ravel()


def refine(groups, p, f: float, rotation: np.ndarray, *, fix_focal: bool) -> tuple[float, np.ndarray, float]:
    """Levenberg-Marquardt on (log focal, small rotation in camera space).

    Returns the refined focal length, camera -> world rotation and the RMS
    residual in pixels.
    """
    n_params = 3 if fix_focal else 4
    groups = _prepare(groups)

    def unpack(x):
        focal = f if fix_focal else f * math.exp(x[3])
        return focal, rotation @ _small_rotation(x[:3])

    x = np.zeros(n_params)
    r = residuals(groups, p, *unpack(x))
    cost = float(r @ r)
    damping = 1e-3
    for _ in range(MAX_ITERATIONS):
        jac = np.empty((len(r), n_params))
        for i in range(n_params):
            dx = np.zeros(n_params)
            dx[i] = _STEP
            jac[:, i] = (residuals(groups, p, *unpack(x + dx)) - r) / _STEP
        a = jac.T @ jac
        g = jac.T @ r
        improved = False
        while damping < 1e10:
            step = -np.linalg.solve(a + damping * np.diag(np.diag(a) + 1e-12), g)
            r_new = residuals(groups, p, *unpack(x + step))
            cost_new = float(r_new @ r_new)
            if cost_new < cost:
                x, r, improved = x + step, r_new, True
                done = cost - cost_new < 1e-9 * max(cost, 1e-12)
                cost = cost_new
                damping = max(damping * 0.3, 1e-9)
                break
            damping *= 10.0
        if not improved or done or np.linalg.norm(step) < 1e-12:
            break
    focal, rot = unpack(x)
    # Re-orthonormalise against drift.
    u, _, vt = np.linalg.svd(rot)
    return focal, u @ vt, math.sqrt(cost / max(len(r), 1))
