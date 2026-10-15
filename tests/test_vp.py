# SPDX-License-Identifier: GPL-3.0-or-later
import numpy as np
import pytest
from synthetic import angle_between, make_camera, rotation_from_angles

from solver import ReferenceDistance, SolverError, solve_vanishing_points
from solver.common import CameraSolution

AXIS_VECTORS = {"X": np.array([1.0, 0, 0]), "Y": np.array([0, 1.0, 0]), "Z": np.array([0, 0, 1.0])}

# Two parallel edges per axis, on a 4 m box sitting on the origin.
EDGES = {
    "X": [((-2, -2, 0), (2, -2, 0)), ((-2, 2, 3), (2, 2, 3))],
    "Y": [((-2, -2, 0), (-2, 2, 0)), ((2, -2, 3), (2, 2, 3))],
    "Z": [((-2, -2, 0), (-2, -2, 3)), ((2, 2, 0), (2, 2, 3))],
}


def guides(cam, axis):
    return [cam.segment(a, b) for a, b in EDGES[axis]]


def axis_label(cam, axis):
    """Every EDGES segment runs from its first to its second point along +axis,
    which is what an axis sign means for the solver."""
    return "+" + axis


def assert_matches(sol: CameraSolution, cam, position=True, f_tol=0.01, deg_tol=0.2, pos_tol=0.01):
    assert sol.focal_px == pytest.approx(cam.focal_px, rel=f_tol)
    assert angle_between(sol.rotation, cam.rotation) < deg_tol
    if position:
        assert np.allclose(sol.position, cam.position, atol=pos_tol * np.linalg.norm(cam.position))


def reference(cam, axis="X", length=2.0):
    end = AXIS_VECTORS[axis] * length
    return ReferenceDistance(axis, tuple(cam.project([0, 0, 0])[0]), tuple(cam.project(end)[0]), length)


def test_two_vanishing_points(camera):
    sol = solve_vanishing_points(
        [guides(camera, "X"), guides(camera, "Y")],
        [axis_label(camera, "X"), axis_label(camera, "Y")],
        camera.image_size,
        origin=camera.project([0, 0, 0]),
        reference=reference(camera),
    )
    assert_matches(sol, camera)


def test_two_vanishing_points_x_and_z():
    cam = make_camera(pitch=-25.0, yaw=-60.0, roll=-4.0, position=(9.0, -5.0, 4.0))
    sol = solve_vanishing_points(
        [guides(cam, "Z"), guides(cam, "X")],
        [axis_label(cam, "Z"), axis_label(cam, "X")],
        cam.image_size,
        origin=cam.project([0, 0, 0]),
        reference=reference(cam, "Z", 3.0),
    )
    assert_matches(sol, cam)


@pytest.mark.parametrize(
    ("plane", "axis", "start", "end"),
    [
        # On the floor but away from the origin's axis line (the lift door case).
        ("XY", "X", (-1.5, -1.3, 0), (0.9, -1.3, 0)),
        ("XY", "Y", (1.2, -1.5, 0), (1.2, 1.0, 0)),
        # A height standing anywhere on the floor.
        ("XY", "Z", (1.0, -1.5, 0), (1.0, -1.5, 2.2)),
        # On a wall (XZ through the origin), along X and as a height above it.
        ("XZ", "X", (-1.0, 0, 1.5), (1.5, 0, 1.5)),
        ("XZ", "Z", (0.5, 0, 0.3), (0.5, 0, 2.0)),
    ],
)
def test_reference_distance_anywhere_on_the_plane(camera, plane, axis, start, end):
    start, end = np.array(start, float), np.array(end, float)
    length = float(np.linalg.norm(end - start))
    ref = ReferenceDistance(axis, tuple(camera.project(start)[0]), tuple(camera.project(end)[0]), length, plane)
    sol = solve_vanishing_points(
        [guides(camera, "X"), guides(camera, "Y")],
        [axis_label(camera, "X"), axis_label(camera, "Y")],
        camera.image_size,
        origin=camera.project([0, 0, 0]),
        reference=ref,
    )
    assert_matches(sol, camera)


def test_reference_distance_beyond_the_horizon(camera):
    ref = ReferenceDistance("X", (0.0, camera.image_size[1] - 1.0), (10.0, camera.image_size[1] - 1.0), 1.0)
    above = camera.project([0, 1e6, 0])[0][1] < camera.image_size[1] - 1.0
    if not above:
        pytest.skip("the horizon is not inside the image")
    with pytest.raises(SolverError, match="beyond the horizon"):
        solve_vanishing_points(
            [guides(camera, "X"), guides(camera, "Y")],
            [axis_label(camera, "X"), axis_label(camera, "Y")],
            camera.image_size,
            origin=camera.project([0, 0, 0]),
            reference=ref,
        )


def test_camera_distance_scale(camera):
    sol = solve_vanishing_points(
        [guides(camera, "X"), guides(camera, "Y")],
        [axis_label(camera, "X"), axis_label(camera, "Y")],
        camera.image_size,
        origin=camera.project([0, 0, 0]),
        camera_distance=float(np.linalg.norm(camera.position)),
    )
    assert_matches(sol, camera)


def test_three_vanishing_points_recover_principal_point():
    cam = make_camera(pitch=-30.0, yaw=40.0, roll=2.0, position=(-8.0, -9.0, 9.0), principal_point=(1010.0, 515.0))
    sol = solve_vanishing_points(
        [guides(cam, "X"), guides(cam, "Y"), guides(cam, "Z")],
        [axis_label(cam, "X"), axis_label(cam, "Y"), axis_label(cam, "Z")],
        cam.image_size,
        solve_principal_point=True,
        origin=cam.project([0, 0, 0]),
        reference=reference(cam),
    )
    assert np.allclose(sol.principal_point, cam.principal_point, atol=0.5)
    assert_matches(sol, cam)


def test_one_vanishing_point_with_known_focal():
    cam = make_camera(pitch=-8.0, yaw=5.0, roll=1.5, position=(0.5, -10.0, 1.6))
    sol = solve_vanishing_points(
        [guides(cam, "Y")],
        [axis_label(cam, "Y"), axis_label(cam, "X")],
        cam.image_size,
        focal_px=cam.focal_px,
        axis2_line=cam.segment((-2, 0.5, 0), (2, 0.5, 0)),
        origin=cam.project([0, 0, 0]),
        reference=reference(cam),
    )
    assert_matches(sol, cam)


@pytest.mark.parametrize("flip_line", [False, True])
def test_one_vertical_vanishing_point_and_an_x_line(flip_line):
    """Camera looking down at a wall: verticals vanish below the image, one line
    along the wall gives X."""
    cam = make_camera(pitch=-33.0, yaw=8.0, roll=4.0, position=(0.4, -7.0, 4.5))
    line = cam.segment((-1.5, 0.0, 0.0), (1.5, 0.0, 0.0))
    sol = solve_vanishing_points(
        [guides(cam, "Z")],
        [axis_label(cam, "Z"), "-X" if flip_line else "+X"],
        cam.image_size,
        focal_px=cam.focal_px,
        axis2_line=line[::-1] if flip_line else line,
        origin=cam.project([0, 0, 0]),
        reference=reference(cam),
    )
    # Reversing the line reverses the axis; the label says so.
    assert_matches(sol, cam)


def test_one_vanishing_point_requires_focal(camera):
    with pytest.raises(SolverError):
        solve_vanishing_points([guides(camera, "Y")], ["+Y", "+X"], camera.image_size, axis2_line=((0, 0), (1, 0)))


def test_noisy_guides_stay_within_tolerance():
    cam = make_camera()
    rng = np.random.default_rng(7)
    # Long edges spanning the scene, with half a pixel of noise on every endpoint.
    long_edges = {
        "X": [((-6, -2, 0), (6, -2, 0)), ((-6, 3, 4), (6, 3, 4)), ((-6, 6, 0), (6, 6, 0))],
        "Y": [((-3, -4, 0), (-3, 8, 0)), ((3, -4, 4), (3, 8, 4)), ((5, -4, 0), (5, 8, 0))],
    }
    lines = [[cam.segment(a, b) + rng.normal(0, 0.5, (2, 2)) for a, b in long_edges[k]] for k in ("X", "Y")]
    sol = solve_vanishing_points(
        lines,
        [axis_label(cam, "X"), axis_label(cam, "Y")],
        cam.image_size,
        origin=cam.project([0, 0, 0]),
        reference=reference(cam),
    )
    assert_matches(sol, cam, pos_tol=0.02)


def test_negative_axis_labels_flip_the_world(camera):
    labels = [axis_label(camera, "X"), axis_label(camera, "Y")]
    flipped = [("-" if lab[0] == "+" else "+") + lab[1] for lab in labels]
    sol = solve_vanishing_points(
        [guides(camera, "X"), guides(camera, "Y")], flipped, camera.image_size, origin=camera.project([0, 0, 0])
    )
    # Negating X and Y is a 180 degree turn about Z.
    turned = np.diag([-1.0, -1.0, 1.0]) @ camera.rotation
    assert angle_between(sol.rotation, turned) < 0.2


def test_impossible_configuration_is_reported(camera):
    # Two vanishing points on the same side of the principal point: f^2 < 0.
    lines_a = [((100, 500), (300, 520)), ((100, 300), (300, 330))]
    lines_b = [((100, 700), (300, 690)), ((100, 200), (300, 230))]
    with pytest.raises(SolverError):
        solve_vanishing_points([lines_a, lines_b], ["+X", "+Y"], camera.image_size)


def test_parallel_guides_are_reported(camera):
    lines_a = [((100, 500), (300, 500)), ((100, 300), (300, 300))]
    with pytest.raises(SolverError):
        solve_vanishing_points([lines_a, guides(camera, "Y")], ["+X", "+Y"], camera.image_size)


def test_straighten_removes_roll_and_keeps_origin(camera):
    origin_px = camera.project([0, 0, 0])
    sol = solve_vanishing_points(
        [guides(camera, "X"), guides(camera, "Y")],
        [axis_label(camera, "X"), axis_label(camera, "Y")],
        camera.image_size,
        origin=origin_px,
        straighten_horizon=True,
    )
    assert abs(sol.roll) < 1e-6
    assert sol.pitch == pytest.approx(-12.0, abs=0.2)
    origin_cam = sol.rotation.T @ (np.zeros(3) - sol.position)
    projected = sol.principal_point + sol.focal_px * origin_cam[:2] / -origin_cam[2]
    assert np.allclose(projected, origin_px, atol=1e-6)


def test_pitch_offset(camera):
    args = (
        [guides(camera, "X"), guides(camera, "Y")],
        [axis_label(camera, "X"), axis_label(camera, "Y")],
        camera.image_size,
    )
    base = solve_vanishing_points(*args)
    tilted = solve_vanishing_points(*args, pitch_offset=np.radians(5.0))
    assert tilted.pitch == pytest.approx(base.pitch + 5.0, abs=1e-6)


def test_reported_angles():
    cam = make_camera(pitch=-12.0, yaw=35.0, roll=3.0)
    sol = CameraSolution(cam.image_size, cam.focal_px, cam.principal_point, cam.rotation, cam.position)
    assert sol.pitch == pytest.approx(-12.0, abs=1e-9)
    assert sol.yaw == pytest.approx(35.0, abs=1e-9)
    assert sol.roll == pytest.approx(3.0, abs=1e-9)
    assert sol.camera_height == pytest.approx(2.5)
    level = CameraSolution((100, 100), 50.0, np.array([50.0, 50.0]), rotation_from_angles(0, 0, 0), np.zeros(3))
    assert level.fov[0] == pytest.approx(90.0)


def test_three_vanishing_points_refined_with_centred_principal_point():
    cam = make_camera(pitch=-30.0, yaw=40.0, roll=2.0, position=(-8.0, -9.0, 9.0))
    rng = np.random.default_rng(11)
    lines = [[seg + rng.normal(0, 0.5, (2, 2)) for seg in guides(cam, k)] for k in ("X", "Y", "Z")]
    sol = solve_vanishing_points(
        lines,
        [axis_label(cam, "X"), axis_label(cam, "Y"), axis_label(cam, "Z")],
        cam.image_size,
        origin=cam.project([0, 0, 0]),
        reference=reference(cam),
    )
    assert np.allclose(sol.principal_point, cam.principal_point)
    assert_matches(sol, cam, pos_tol=0.02)


def test_known_focal_refines_rotation_on_both_pairs(camera):
    sol = solve_vanishing_points(
        [guides(camera, "X"), guides(camera, "Y")],
        [axis_label(camera, "X"), axis_label(camera, "Y")],
        camera.image_size,
        focal_px=camera.focal_px,
        origin=camera.project([0, 0, 0]),
        reference=reference(camera),
    )
    assert sol.focal_px == camera.focal_px
    assert_matches(sol, camera)


def test_refinement_handles_a_far_vanishing_point():
    """Nearly frontal wall: X vanishes very far; three groups still converge."""
    cam = make_camera(pitch=-32.0, yaw=1.0, roll=4.0, position=(0.3, -4.0, 1.6), focal_mm=30.0)
    sol = solve_vanishing_points(
        [guides(cam, "X"), guides(cam, "Y"), guides(cam, "Z")],
        [axis_label(cam, "X"), axis_label(cam, "Y"), axis_label(cam, "Z")],
        cam.image_size,
        origin=cam.project([0, 0, 0]),
        reference=reference(cam),
    )
    assert_matches(sol, cam)


# Extra guides (1.1): more lines per vanishing point, on other edges of the same box.
EXTRA_EDGES = {
    "X": [((-2, 0, 1.5), (2, 0, 1.5)), ((-2, -2, 3), (2, -2, 3)), ((-2, 2, 0), (2, 2, 0)), ((-2, 1, 2), (2, 1, 2))],
    "Y": [((0, -2, 1.5), (0, 2, 1.5)), ((-2, -2, 3), (-2, 2, 3)), ((2, -2, 0), (2, 2, 0)), ((1, -2, 2), (1, 2, 2))],
}


def test_more_lines_average_out_the_noise(camera):
    """Four lines per vanishing point beat two under the same 2 px noise."""
    rng = np.random.default_rng(7)

    def lines(axis, count):
        edges = (EDGES[axis] + EXTRA_EDGES[axis])[:count]
        return [tuple(tuple(p + rng.normal(0.0, 2.0, 2)) for p in camera.segment(a, b)) for a, b in edges]

    errors = {2: [], 4: []}
    for _ in range(60):
        for count in (2, 4):
            sol = solve_vanishing_points(
                [lines("X", count), lines("Y", count)],
                ["+X", "+Y"],
                camera.image_size,
                origin=camera.project([0, 0, 0]),
                reference=reference(camera),
            )
            errors[count].append(angle_between(sol.rotation, camera.rotation))
    assert np.mean(errors[4]) < 0.8 * np.mean(errors[2]), (np.mean(errors[2]), np.mean(errors[4]))


def test_guides_on_one_line_are_rejected():
    from solver.common import vanishing_point

    with pytest.raises(SolverError):
        vanishing_point([((0.0, 0.0), (100.0, 10.0)), ((200.0, 20.0), (300.0, 30.0))], 1000.0)
