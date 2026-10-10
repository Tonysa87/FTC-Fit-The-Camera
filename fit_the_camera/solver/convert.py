# SPDX-License-Identifier: GPL-3.0-or-later
"""Conversion of a solver result into Blender camera settings.

The solver camera frame already matches Blender's (looking along -Z, Y up), so
the rotation and position go straight into ``Object.matrix_world``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .common import CameraSolution

DEFAULT_SENSOR_MM = 36.0


@dataclass
class BlenderCamera:
    lens: float
    sensor_width: float
    sensor_height: float
    sensor_fit: str
    shift_x: float
    shift_y: float
    resolution: tuple[int, int]
    matrix_world: np.ndarray


def to_blender(
    solution: CameraSolution,
    sensor_long_side_mm: float | None = None,
) -> BlenderCamera:
    """Blender camera data for ``solution``.

    ``sensor_long_side_mm`` is the sensor size along the longer image side; with no
    known sensor a 36 mm sensor is used, which gives the 35 mm equivalent focal
    length. The fit follows the image orientation, so the sensor size always
    applies to the longer side.
    """
    w, h = solution.image_size
    sensor = float(sensor_long_side_mm or DEFAULT_SENSOR_MM)
    fit_size = float(max(w, h))
    fit = "HORIZONTAL" if w >= h else "VERTICAL"
    lens = solution.focal_px * sensor / fit_size
    p = solution.principal_point
    # Blender shift moves the frame, in units of the fitted image side; a frame
    # moved right puts the principal point left of the image centre.
    shift_x = (w / 2.0 - p[0]) / fit_size
    shift_y = (h / 2.0 - p[1]) / fit_size
    return BlenderCamera(
        lens=float(lens),
        sensor_width=sensor,
        sensor_height=sensor,
        sensor_fit=fit,
        shift_x=float(shift_x),
        shift_y=float(shift_y),
        resolution=(int(w), int(h)),
        matrix_world=solution.matrix_world,
    )


def focal_px_from_mm(focal_mm: float, sensor_long_side_mm: float, image_size) -> float:
    return focal_mm * max(image_size) / sensor_long_side_mm


def focal_px_from_35mm(focal_35mm: float, image_size) -> float:
    """Focal length in pixels from the 35 mm equivalent focal length.

    The equivalence is defined on the diagonal (43.27 mm for a 36x24 mm frame),
    so it holds for any image aspect ratio.
    """
    w, h = image_size
    return focal_35mm * float(np.hypot(w, h)) / float(np.hypot(36.0, 24.0))
