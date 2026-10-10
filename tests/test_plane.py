# SPDX-License-Identifier: GPL-3.0-or-later
import numpy as np
import pytest
from synthetic import angle_between, make_camera

from solver import SolverError, solve_rectangle

WIDTH, HEIGHT = 4.0, 2.5


def corners(cam, width=WIDTH, height=HEIGHT, flip_y=False):
    hw, hh = width / 2, height / 2
    y = -1.0 if flip_y else 1.0
    pts = [(-hw, -hh * y, 0), (hw, -hh * y, 0), (hw, hh * y, 0), (-hw, hh * y, 0)]
    return cam.project(pts)


def test_known_focal(camera):
    sol = solve_rectangle(corners(camera), WIDTH, HEIGHT, camera.image_size, focal_px=camera.focal_px)
    assert angle_between(sol.rotation, camera.rotation) < 0.2
    assert np.allclose(sol.position, camera.position, atol=1e-6)


def test_unknown_focal(camera):
    sol = solve_rectangle(corners(camera), WIDTH, HEIGHT, camera.image_size)
    assert sol.focal_px == pytest.approx(camera.focal_px, rel=0.01)
    assert angle_between(sol.rotation, camera.rotation) < 0.2
    assert np.allclose(sol.position, camera.position, atol=0.01 * np.linalg.norm(camera.position))
    assert not sol.warnings


def test_unknown_focal_steep_view():
    cam = make_camera(pitch=-50.0, yaw=-120.0, roll=-5.0, position=(5.0, 3.0, 6.0), focal_mm=24.0)
    sol = solve_rectangle(corners(cam), WIDTH, HEIGHT, cam.image_size)
    assert sol.focal_px == pytest.approx(cam.focal_px, rel=0.01)
    assert angle_between(sol.rotation, cam.rotation) < 0.2


def test_reversed_corner_order_keeps_camera_above(camera):
    # Corners listed clockwise would put the camera below the plane: the solver
    # flips Y, which here gives back the true world frame.
    sol = solve_rectangle(corners(camera, flip_y=True), WIDTH, HEIGHT, camera.image_size, focal_px=camera.focal_px)
    assert sol.position[2] > 0
    assert angle_between(sol.rotation, camera.rotation) < 0.2
    assert np.allclose(sol.position, camera.position, atol=1e-6)


def test_frontal_rectangle_warns():
    cam = make_camera(pitch=-85.0, yaw=0.0, roll=0.0, position=(0.0, -0.5, 6.0))
    try:
        sol = solve_rectangle(corners(cam), WIDTH, HEIGHT, cam.image_size)
    except SolverError:
        return  # also acceptable: no positive focal estimate at all
    assert sol.warnings


def test_non_convex_corners_rejected(camera):
    pts = corners(camera)[[0, 2, 1, 3]]
    with pytest.raises(SolverError):
        solve_rectangle(pts, WIDTH, HEIGHT, camera.image_size)


def test_noisy_corners():
    cam = make_camera(pitch=-35.0, focal_mm=28.0, position=(-4.0, -5.5, 4.0))
    rng = np.random.default_rng(3)
    sol = solve_rectangle(corners(cam, 8.0, 6.0) + rng.normal(0, 0.3, (4, 2)), 8.0, 6.0, cam.image_size)
    assert sol.focal_px == pytest.approx(cam.focal_px, rel=0.02)
    assert angle_between(sol.rotation, cam.rotation) < 0.3
