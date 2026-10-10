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
    """Only the height along the vertical edge counts: a sideways miss in the image
    changes the scale very little."""
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


def test_top_below_the_base_is_an_error(camera):
    cube = cube_on(camera, (1.0, 0.5, 0.0), (1.0, 0.5, -1.0), 1.0)
    with pytest.raises(SolverError, match="above its base"):
        solve_with_cube(camera, cube)


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
    # The cube extends away from the camera within the plane.
    for corner in (1, 2):
        assert (corners[corner] - corners[0]) @ (corners[0] - camera.position) > 0.0


def test_cube_corners_none_beyond_the_horizon():
    cam = make_camera(pitch=-5.0)
    assert cube_corners(as_solution(cam), (cam.image_size[0] / 2, cam.image_size[1] * 0.9), 1.0, "XY") is None
