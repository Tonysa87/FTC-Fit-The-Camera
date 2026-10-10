# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic cameras that project known world points (no pytest dependency)."""

import math
from dataclasses import dataclass

import numpy as np


def rotation_from_angles(pitch, yaw, roll):
    """Camera->world rotation from pitch (up), yaw (clockwise from +Y) and roll
    (counter-clockwise), degrees. A zero camera looks along +Y with Z up."""
    p, y, r = (math.radians(a) for a in (pitch, yaw, roll))

    def rx(a):
        c, s = math.cos(a), math.sin(a)
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])

    def rz(a):
        c, s = math.cos(a), math.sin(a)
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])

    level = rx(math.pi / 2)  # camera looking along +Y, up along +Z
    # Roll is applied in camera space: rotating about camera +Z by +r turns the
    # right vector upwards (counter-clockwise seen from behind the camera).
    return rz(-y) @ rx(p) @ level @ rz(r)


@dataclass
class SyntheticCamera:
    image_size: tuple
    focal_px: float
    principal_point: np.ndarray
    rotation: np.ndarray
    position: np.ndarray

    def project(self, points):
        pts = np.atleast_2d(np.asarray(points, float))
        cam = (pts - self.position) @ self.rotation  # world -> camera
        if np.any(cam[:, 2] >= 0):
            raise ValueError("point behind the camera")
        return self.principal_point + self.focal_px * cam[:, :2] / (-cam[:, 2:3])

    def segment(self, a, b):
        return self.project([a, b])


def make_camera(
    pitch=-12.0,
    yaw=35.0,
    roll=3.0,
    position=(-6.9, -9.8, 2.5),
    focal_mm=35.0,
    image_size=(1920, 1080),
    principal_point=None,
):
    w, h = image_size
    f = focal_mm * max(w, h) / 36.0
    p = np.array([w / 2, h / 2]) if principal_point is None else np.asarray(principal_point, float)
    return SyntheticCamera(image_size, f, p, rotation_from_angles(pitch, yaw, roll), np.asarray(position, float))


def angle_between(r1, r2):
    """Angle in degrees of the relative rotation between two rotation matrices."""
    c = (np.trace(r1.T @ r2) - 1) / 2
    return math.degrees(math.acos(np.clip(c, -1, 1)))
