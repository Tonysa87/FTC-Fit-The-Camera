# SPDX-License-Identifier: GPL-3.0-or-later
import math

import numpy as np
import pytest
from synthetic import angle_between, make_camera

from solver import SolverError, solve_horizon


def horizon_points(cam, spread=40.0):
    """Image of two far-away horizontal points either side of the view direction."""
    fwd = -cam.rotation[:, 2]
    heading = math.atan2(fwd[1], fwd[0])
    pts = []
    for delta in (-spread, spread):
        a = heading + math.radians(delta)
        pts.append(cam.position + 1e8 * np.array([math.cos(a), math.sin(a), 0.0]))
    return cam.project(pts)


@pytest.mark.parametrize("pitch,roll", [(-12.0, 3.0), (8.0, -6.0), (0.0, 0.0), (-40.0, 10.0)])
def test_horizon_recovers_pose(pitch, roll):
    cam = make_camera(pitch=pitch, yaw=35.0, roll=roll, position=(0.0, 0.0, 1.7))
    sol = solve_horizon(horizon_points(cam), cam.focal_px, cam.image_size, camera_height=1.7, yaw=35.0)
    assert sol.pitch == pytest.approx(pitch, abs=0.2)
    assert sol.roll == pytest.approx(roll, abs=0.2)
    assert sol.yaw == pytest.approx(35.0, abs=0.2)
    assert angle_between(sol.rotation, cam.rotation) < 0.2
    assert np.allclose(sol.position, [0, 0, 1.7])


def test_point_order_does_not_matter(camera):
    pts = horizon_points(camera)
    a = solve_horizon(pts, camera.focal_px, camera.image_size, camera_height=2.0, yaw=35.0)
    b = solve_horizon(pts[::-1], camera.focal_px, camera.image_size, camera_height=2.0, yaw=35.0)
    assert angle_between(a.rotation, b.rotation) < 1e-4


def test_pitch_matches_closed_form(camera):
    """theta = atan(d / f), d the signed distance from p to the horizon."""
    cam = make_camera(pitch=-15.0, roll=0.0)
    pts = horizon_points(cam)
    d = pts[:, 1].mean() - cam.principal_point[1]
    sol = solve_horizon(pts, cam.focal_px, cam.image_size, camera_height=1.0, yaw=0.0)
    assert sol.pitch == pytest.approx(-math.degrees(math.atan(d / cam.focal_px)), abs=1e-6)


def test_straighten(camera):
    sol = solve_horizon(
        horizon_points(camera), camera.focal_px, camera.image_size, camera_height=1.0, straighten_horizon=True
    )
    assert abs(sol.roll) < 1e-6


def test_requires_focal_and_height(camera):
    pts = horizon_points(camera)
    with pytest.raises(SolverError):
        solve_horizon(pts, 0.0, camera.image_size, camera_height=1.0)
    with pytest.raises(SolverError):
        solve_horizon(pts, camera.focal_px, camera.image_size, camera_height=0.0)
