# SPDX-License-Identifier: GPL-3.0-or-later
import numpy as np
import pytest
from synthetic import make_camera
from test_vp import assert_matches, axis_label, guides

from solver import ScaleCube, SolverError, cube_corners, solve_vanishing_points
from solver.common import CameraSolution


def solve_with_cube(cam, cube):
    return solve_vanishing_points(
        [guides(cam, "X"), guides(cam, "Y")],
        [axis_label(cam, "X"), axis_label(cam, "Y")],
        cam.image_size,
        origin=cam.project([0, 0, 0]),
        cube=cube,
    )


def cube_on(cam, base, top, size, plane="XY"):
    return ScaleCube(tuple(cam.project(base)[0]), tuple(cam.project(top)[0]), size, plane)


def test_cube_on_the_floor_sets_the_scale(camera):
    cube = cube_on(camera, (1.0, 0.5, 0.0), (1.0, 0.5, 1.5), 1.5)
    assert_matches(solve_with_cube(camera, cube), camera)


def test_cube_base_anywhere_on_the_plane(camera):
    cube = cube_on(camera, (-3.0, 4.0, 0.0), (-3.0, 4.0, 0.2), 0.2)
    assert_matches(solve_with_cube(camera, cube), camera)


def test_top_handle_off_the_edge_uses_the_closest_point(camera):
    """Only the height along the vertical edge counts."""
    cube = cube_on(camera, (1.0, 0.5, 0.0), (1.0, 0.5, 1.0), 1.0)
    cube.top = (cube.top[0] + 6.0, cube.top[1])
    assert_matches(solve_with_cube(camera, cube), camera, pos_tol=0.003)


def test_cube_on_a_wall(camera):
    # XZ is the wall facing -Y: the camera (y < 0) sees its front, the cube grows towards -Y.
    cube = cube_on(camera, (1.0, 0.0, 0.5), (1.0, -0.5, 0.5), 0.5, plane="XZ")
    assert_matches(solve_with_cube(camera, cube), camera)


def test_base_beyond_the_horizon_is_an_error(camera):
    cube = cube_on(camera, (1.0, 0.5, 0.0), (1.0, 0.5, 1.0), 1.0)
    cube.base = (cube.base[0], camera.image_size[1] * 2.0)
    with pytest.raises(SolverError, match="horizon"):
        solve_with_cube(camera, cube)


def test_top_below_the_base_measures_the_mirrored_height(camera):
    """A top handle on the wrong side of the plane (e.g. after switching the
    reference plane) still gives a valid scale instead of breaking the solve."""
    cube = cube_on(camera, (1.0, 0.5, 0.0), (1.0, 0.5, -1.0), 1.0)
    sol = solve_with_cube(camera, cube)
    assert np.isfinite(sol.position).all()
    flat = cube_on(camera, (1.0, 0.5, 0.0), (1.0, 0.5, 0.0), 1.0)
    with pytest.raises(SolverError, match="no height"):
        solve_with_cube(camera, flat)


def test_top_handle_across_the_edge_keeps_the_scale(camera):
    """The top handle counts by its foot on the edge's image line."""
    cube = cube_on(camera, (1.0, 0.5, 0.0), (1.0, 0.5, 1.0), 1.0)
    edge = np.subtract(cube.top, cube.base)
    across = np.array([-edge[1], edge[0]]) / np.linalg.norm(edge)
    cube.top = tuple(np.add(cube.top, 120.0 * across))
    assert_matches(solve_with_cube(camera, cube), camera, pos_tol=1e-6)


def as_solution(cam):
    return CameraSolution(cam.image_size, cam.focal_px, cam.principal_point, cam.rotation, cam.position)


@pytest.mark.parametrize(
    ("plane", "base", "up"),
    [("XY", (1.0, 0.5, 0.0), (0, 0, 1)), ("XZ", (1.0, 0.0, 0.5), (0, -1, 0)), ("YZ", (0.0, 1.0, 0.5), (-1, 0, 0))],
)
def test_cube_corners_stand_on_the_plane_towards_the_camera(camera, plane, base, up):
    corners = cube_corners(as_solution(camera), camera.project(base)[0], 2.0, plane)
    assert np.allclose(corners[0], base, atol=1e-9)
    assert np.allclose(corners[4], np.add(base, np.multiply(up, 2.0)), atol=1e-9)
    # In the plane the cube extends the way the camera looks; on a wall it goes up.
    forward = -camera.rotation[:, 2]
    assert (corners[1] - corners[0]) @ forward > -0.2 * 2.0
    if plane == "XY":
        assert (corners[2] - corners[0]) @ forward > -0.2 * 2.0
    else:
        assert np.allclose(corners[2] - corners[0], (0, 0, 2.0), atol=1e-9)


def test_cube_keeps_its_direction_while_the_origin_moves():
    """Moving the origin (the camera position relative to it) must not flip the cube."""
    directions = set()
    for x in np.linspace(-0.5, 0.5, 11):
        cam = make_camera(pitch=-35.0, yaw=0.0, position=(x, -6.0, 4.0))
        corners = cube_corners(as_solution(cam), (cam.image_size[0] * 0.5, cam.image_size[1] * 0.3), 1.0, "XY")
        directions.add(tuple(np.round(np.r_[corners[1] - corners[0], corners[2] - corners[0]], 9)))
    assert len(directions) == 1, directions


def test_cube_keeps_its_direction_while_the_base_moves():
    """Dragging the base across the camera (left to right, near to far) must not
    flip the cube to the other side."""
    cam = make_camera(pitch=-35.0, yaw=0.0, position=(0.0, -6.0, 4.0))
    solution = as_solution(cam)
    w, h = cam.image_size
    directions = set()
    for x in np.linspace(0.05, 0.95, 19) * w:
        for y in np.linspace(0.05, 0.6, 8) * h:
            corners = cube_corners(solution, (x, y), 1.0, "XY")
            if corners is None:
                continue
            directions.add(tuple(np.round(np.r_[corners[1] - corners[0], corners[2] - corners[0]], 9)))
    assert len(directions) == 1, directions


def test_cube_corners_none_beyond_the_horizon():
    cam = make_camera(pitch=-5.0)
    assert cube_corners(as_solution(cam), (cam.image_size[0] / 2, cam.image_size[1] * 0.9), 1.0, "XY") is None
