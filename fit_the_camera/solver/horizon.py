# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibration from the horizon line, a known focal length and the camera height.

The horizon fixes pitch and roll; the heading (yaw) cannot be seen in the image
and is supplied by the caller (from EXIF or by hand). The camera is placed at
``(0, 0, camera_height)``, so the world origin is on the ground below it.
"""

from __future__ import annotations

import math

import numpy as np

from .common import CameraSolution, SolverError, as_points, finish_rotation, image_center, ray


def solve_horizon(
    horizon,
    focal_px: float,
    image_size,
    *,
    camera_height: float,
    yaw: float = 0.0,
    principal_point=None,
    straighten_horizon: bool = False,
    pitch_offset: float = 0.0,
) -> CameraSolution:
    """Solve a camera from two image points on the horizon.

    ``yaw`` is the heading in degrees, clockwise from +Y (as a compass bearing
    with north on +Y).
    """
    if not focal_px or focal_px <= 0.0:
        raise SolverError("the horizon mode needs a known focal length")
    if camera_height <= 0.0:
        raise SolverError("the camera height must be positive")
    a, b = as_points(horizon)[:2]
    if np.linalg.norm(b - a) < 1e-9:
        raise SolverError("the horizon line has zero length")

    w, h = image_size
    p = image_center(image_size) if principal_point is None else np.asarray(principal_point, float)
    f = float(focal_px)

    # The horizon is the image of the plane through the camera centre parallel to
    # the ground: its normal is the world up vector in camera space.
    up = np.cross(ray(a, p, f), ray(b, p, f))
    up /= np.linalg.norm(up)
    if up[1] < 0.0:  # the camera is assumed not to be upside down
        up = -up

    fwd = np.array([0.0, 0.0, -1.0])
    heading_cam = fwd - (fwd @ up) * up
    n = np.linalg.norm(heading_cam)
    if n < 1e-6:
        raise SolverError("the camera looks straight up or down: the horizon is undefined")
    heading_cam /= n

    psi = math.radians(yaw)
    heading_world = np.array([math.sin(psi), math.cos(psi), 0.0])
    z_world = np.array([0.0, 0.0, 1.0])
    cam_basis = np.column_stack([up, heading_cam, np.cross(heading_cam, up)])
    world_basis = np.column_stack([z_world, heading_world, np.cross(heading_world, z_world)])
    rotation = world_basis @ cam_basis.T  # camera -> world
    warnings: list[str] = []
    rotation, removed_roll = finish_rotation(rotation, straighten_horizon, pitch_offset, warnings)

    return CameraSolution(
        image_size=(int(w), int(h)),
        focal_px=f,
        principal_point=np.asarray(p, float),
        rotation=rotation,
        position=np.array([0.0, 0.0, float(camera_height)]),
        warnings=warnings,
        removed_roll=removed_roll,
    )
