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
    # flips X instead, a half turn of the world about Z.
    sol = solve_rectangle(corners(camera, flip_y=True), WIDTH, HEIGHT, camera.image_size, focal_px=camera.focal_px)
    assert sol.position[2] > 0
    half_turn = np.diag([-1.0, -1.0, 1.0])
    assert angle_between(sol.rotation, half_turn @ camera.rotation) < 0.2
    assert np.allclose(sol.position, half_turn @ camera.position, atol=1e-6)


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


@pytest.mark.parametrize("plane", ["XZ", "YZ"])
def test_rectangle_on_a_wall(plane):
    """A rectangle on a wall: first edge horizontal, second edge vertical."""
    from solver.common import plane_frame

    # Look at the wall's front: XZ faces -Y, YZ faces +X.
    cam = make_camera(pitch=-5.0, yaw=20.0 if plane == "XZ" else -110.0, roll=2.0, position=(0.0, 0.0, 0.0))
    frame = plane_frame(plane)
    hw, hh = WIDTH / 2, HEIGHT / 2
    centre = cam.rotation @ np.array([0.3, 0.2, -6.0])  # 6 m in front of the camera
    world = [centre + frame @ np.array([x, y, 0.0]) for x, y in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
    sol = solve_rectangle(cam.project(world), WIDTH, HEIGHT, cam.image_size, plane=plane)
    assert sol.focal_px == pytest.approx(cam.focal_px, rel=0.01)
    # World axes are only defined up to the rectangle's centre: compare rotations.
    assert angle_between(sol.rotation, cam.rotation) < 0.2
    assert sol.pitch == pytest.approx(-5.0, abs=0.2)
    straight = solve_rectangle(cam.project(world), WIDTH, HEIGHT, cam.image_size, plane=plane, straighten_horizon=True)
    assert abs(straight.roll) < 1e-6
    assert straight.pitch == pytest.approx(-5.0, abs=0.2)


def test_wall_seen_from_behind_keeps_z_up():
    """Corners ordered as seen from the back of an XZ wall: Z must stay up."""
    from solver.common import plane_frame

    cam = make_camera(pitch=-5.0, yaw=200.0, roll=2.0, position=(0.0, 0.0, 0.0))
    frame = plane_frame("XZ")
    centre = cam.rotation @ np.array([0.3, 0.2, -6.0])
    hw, hh = WIDTH / 2, HEIGHT / 2
    world = [centre + frame @ np.array([x, y, 0.0]) for x, y in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
    sol = solve_rectangle(cam.project(world), WIDTH, HEIGHT, cam.image_size, plane="XZ")
    assert sol.rotation[2, 1] > 0.9  # camera up vector still points up
    assert sol.pitch == pytest.approx(-5.0, abs=0.2)
