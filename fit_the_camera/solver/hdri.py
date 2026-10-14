# SPDX-License-Identifier: GPL-3.0-or-later
"""Equirectangular HDRI maths: image point <-> world direction, the sun in it,
and the turn about Z that puts it on a given sun.

Cycles' equirectangular convention (``direction_to_equirectangular``): the
image centre (u = 0.5) looks along +X, u grows clockwise seen from above
(towards -Y), v = 0.5 is the horizon and v = 1 the zenith. u, v are normalised
with the origin at the bottom left, like Blender's pixels. Checked by a Cycles
render in tests_blender (``fit_hdri_renders_the_sun_where_computed``).
"""

from __future__ import annotations

import math

import numpy as np

# Brightest pixels taken as the sun: those above this luminance quantile...
SUN_QUANTILE = 0.999
# ...within this angle of the brightest one (other bright spots are ignored).
SUN_RADIUS_DEG = 10.0


def direction(u: float, v: float) -> np.ndarray:
    """World direction of the image point (u, v)."""
    phi = (0.5 - u) * 2.0 * math.pi  # angle from +X, counter-clockwise
    theta = (v - 0.5) * math.pi  # elevation
    return np.array([math.cos(theta) * math.cos(phi), math.cos(theta) * math.sin(phi), math.sin(theta)])


def image_point(d) -> tuple[float, float]:
    """Image point (u, v) of the world direction ``d``."""
    x, y, z = (float(c) for c in d)
    u = 0.5 - math.atan2(y, x) / (2.0 * math.pi)
    v = 0.5 + math.atan2(z, math.hypot(x, y)) / math.pi
    return u % 1.0, v


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def brightest_point(lum: np.ndarray) -> tuple[float, float]:
    """Image point (u, v) of the sun in an equirectangular luminance map (rows
    bottom to top): the centroid of the brightest pixels around the brightest
    one, across the left/right seam too."""
    h, w = lum.shape
    finite = np.where(np.isfinite(lum), lum, 0.0)
    row, col = np.unravel_index(int(np.argmax(finite)), finite.shape)
    peak = direction((col + 0.5) / w, (row + 0.5) / h)
    rows, cols = np.mgrid[0:h, 0:w]
    u = (cols + 0.5) / w
    v = (rows + 0.5) / h
    phi = (0.5 - u) * 2.0 * math.pi
    theta = (v - 0.5) * math.pi
    dirs = np.stack([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), np.sin(theta)], axis=-1)
    near = dirs @ peak > math.cos(math.radians(SUN_RADIUS_DEG))
    threshold = np.quantile(finite, SUN_QUANTILE)
    mask = near & (finite >= min(threshold, finite[row, col]))
    # Average directions, not (u, v): no trouble at the seam or near the poles.
    weights = np.cos(theta)[mask]  # equal-area pixels
    mean = (dirs[mask] * weights[:, None]).sum(axis=0)
    if np.linalg.norm(mean) < 1e-12:
        return (col + 0.5) / w, (row + 0.5) / h
    return image_point(mean)


def z_rotation(u: float, target) -> float:
    """Rotation about Z (radians) of a Mapping node (Point or Vector type) that
    brings the HDRI column ``u`` onto the azimuth of the world direction
    ``target``. The Mapping node turns the lookup vector: the world direction d
    shows the HDRI at Rz(angle) d."""
    phi_hdri = (0.5 - u) * 2.0 * math.pi
    phi_target = math.atan2(float(target[1]), float(target[0]))
    return (phi_hdri - phi_target + math.pi) % (2.0 * math.pi) - math.pi


def elevation(v: float) -> float:
    """Elevation (degrees) of the image row ``v``."""
    return (v - 0.5) * 180.0
