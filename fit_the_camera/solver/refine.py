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
# Bounds that keep a degenerate configuration from diverging: the focal length
# stays within e^4 (x55) of its start and changes at most x2.7 per step; a step
# turns the camera by at most ~30 degrees.
MAX_LOG_FOCAL = 4.0
MAX_LOG_FOCAL_STEP = 1.0
MAX_ROTATION_STEP = 0.5
_STEP = 1e-6
# A known focal length refined by the guides: assumed placement error of a guide
# end point (fraction of the long image side) and spread of the known focal length.
GUIDE_NOISE = 1e-3
FOCAL_PRIOR_SPREAD = 0.05


def small_rotation(w) -> np.ndarray:
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


def least_squares(fun, n_params: int, bounded) -> tuple[np.ndarray, float]:
    """Bounded Levenberg-Marquardt from ``x = 0``: minimises ``|fun(x)|^2``.

    ``bounded`` shortens a step. Returns the parameters and the final cost; an
    infinite cost if ``fun(0)`` is not finite.
    """
    x = np.zeros(n_params)
    r = fun(x)
    cost = float(r @ r)
    if not math.isfinite(cost):
        return x, math.inf
    damping = 1e-3
    for _ in range(MAX_ITERATIONS):
        jac = np.empty((len(r), n_params))
        for i in range(n_params):
            dx = np.zeros(n_params)
            dx[i] = _STEP
            jac[:, i] = (fun(x + dx) - r) / _STEP
        if not np.all(np.isfinite(jac)):
            break
        a = jac.T @ jac
        g = jac.T @ r
        improved = done = False
        while damping < 1e10:
            try:
                step = bounded(-np.linalg.solve(a + damping * np.diag(np.diag(a) + 1e-12), g))
            except np.linalg.LinAlgError:
                damping *= 10.0
                continue
            r_new = fun(x + step)
            cost_new = float(r_new @ r_new)
            if math.isfinite(cost_new) and cost_new < cost:
                x, r, improved = x + step, r_new, True
                done = cost - cost_new < 1e-9 * max(cost, 1e-12)
                cost = cost_new
                damping = max(damping * 0.3, 1e-9)
                break
            damping *= 10.0
        if not improved or done or np.linalg.norm(step) < 1e-12:
            break
    return x, cost


def focal_prior_residual(focal: float, known: float, weight: float) -> float:
    """Residual of a focal length against a known one, ``FOCAL_PRIOR_SPREAD``
    weighing as much as a guide end point off by ``GUIDE_NOISE``."""
    return weight * math.log(focal / known)


def focal_prior_weight(image_size) -> float:
    """Weight of ``log(f / f_known)`` against pixel residuals: a guide end point
    off by ``GUIDE_NOISE`` of the long side costs as much as the focal length off
    by ``FOCAL_PRIOR_SPREAD``."""
    return GUIDE_NOISE * float(max(image_size)) / FOCAL_PRIOR_SPREAD


def refine(
    groups,
    p,
    f: float,
    rotation: np.ndarray,
    *,
    fix_focal: bool,
    focal_prior: tuple[float, float] | None = None,
) -> tuple[float, np.ndarray, float]:
    """Levenberg-Marquardt on (log focal, small rotation in camera space).

    ``focal_prior`` = (known focal, weight) adds ``focal_prior_residual``: the
    guides refine the known focal length as far as they actually measure it.
    Returns the refined focal length, camera -> world rotation and the final
    cost (squared pixels, prior included). Steps are bounded so that
    nearly degenerate guides (common while a handle is being dragged) cannot throw
    the solution to infinity.
    """
    n_params = 3 if fix_focal else 4
    groups = _prepare(groups)

    def unpack(x):
        focal = f if fix_focal else f * math.exp(min(max(x[3], -MAX_LOG_FOCAL), MAX_LOG_FOCAL))
        return focal, rotation @ small_rotation(x[:3])

    def fun(x):
        focal, rot = unpack(x)
        r = residuals(groups, p, focal, rot)
        if focal_prior is None or fix_focal:
            return r
        return np.append(r, focal_prior_residual(focal, *focal_prior))

    def bounded(step):
        rot = float(np.linalg.norm(step[:3]))
        if rot > MAX_ROTATION_STEP:
            step = step * (MAX_ROTATION_STEP / rot)
        if not fix_focal and abs(step[3]) > MAX_LOG_FOCAL_STEP:
            step = step * (MAX_LOG_FOCAL_STEP / abs(step[3]))
        return step

    x, cost = least_squares(fun, n_params, bounded)
    focal, rot = unpack(x)
    # Re-orthonormalise against drift.
    u, _, vt = np.linalg.svd(rot)
    return focal, u @ vt, cost
