# SPDX-License-Identifier: GPL-3.0-or-later
"""A known focal length (EXIF) refined by the guides."""

import numpy as np
import pytest
from synthetic import angle_between, make_camera
from test_plane import HEIGHT, WIDTH, corners
from test_vp import axis_label, guides

from solver import SolverError, solve_rectangle, solve_vanishing_points


def two_vps(cam, **kwargs):
    return solve_vanishing_points(
        [guides(cam, "X"), guides(cam, "Y")],
        [axis_label(cam, "X"), axis_label(cam, "Y")],
        cam.image_size,
        origin=cam.project([0, 0, 0]),
        **kwargs,
    )


def test_exact_known_focal_changes_nothing(camera):
    sol = two_vps(camera, known_focal_px=camera.focal_px)
    assert sol.focal_px == pytest.approx(camera.focal_px, rel=1e-4)
    assert angle_between(sol.rotation, camera.rotation) < 0.01


def test_good_guides_correct_a_wrong_known_focal(camera):
    # Two well-spread vanishing points measure the focal length: they win.
    sol = two_vps(camera, known_focal_px=camera.focal_px * 1.1)
    assert sol.focal_px == pytest.approx(camera.focal_px, rel=0.01)


def test_weak_guides_stay_near_the_known_focal():
    """Nearly frontal view: one vanishing point far away, the guides barely
    measure the focal length, so a noisy guide cannot drag it away."""
    cam = make_camera(yaw=3.0, pitch=-8.0, roll=0.0)
    lines = [guides(cam, "X"), guides(cam, "Y")]
    a, b = lines[0][1]
    lines[0][1] = (a, (b[0], b[1] + 3.0))  # a 3 px placement error
    kwargs = dict(origin=cam.project([0, 0, 0]))
    free = solve_vanishing_points(lines, ["+X", "+Y"], cam.image_size, **kwargs)
    known = solve_vanishing_points(lines, ["+X", "+Y"], cam.image_size, known_focal_px=cam.focal_px, **kwargs)
    assert abs(free.focal_px / cam.focal_px - 1.0) > 0.1
    assert known.focal_px == pytest.approx(cam.focal_px, rel=0.03)
    assert angle_between(known.rotation, cam.rotation) < angle_between(free.rotation, cam.rotation)


def test_rectangle_rejects_a_clearly_wrong_known_focal(camera):
    """A rectangle measures the focal length loosely (~10% with pixel errors), so
    a small error stays, but a zoomed or cropped photo's EXIF value is dropped."""
    sol = solve_rectangle(corners(camera), WIDTH, HEIGHT, camera.image_size, known_focal_px=camera.focal_px * 1.6)
    assert sol.focal_px == pytest.approx(camera.focal_px, rel=0.03)
    assert np.allclose(sol.position, camera.position, atol=0.03 * np.linalg.norm(camera.position))
    assert not sol.warnings


def test_frontal_rectangle_keeps_the_known_focal():
    cam = make_camera(pitch=-85.0, yaw=0.0, roll=0.0, position=(0.3, -0.2, 6.0))
    pts = corners(cam) + np.array([[0, 0], [2.0, 0], [0, 0], [0, -2.0]])  # small placement errors
    sol = solve_rectangle(pts, WIDTH, HEIGHT, cam.image_size, known_focal_px=cam.focal_px)
    assert sol.focal_px == pytest.approx(cam.focal_px, rel=0.03)
    assert not sol.warnings


def test_zoomed_photo_drops_the_exif_focal():
    """Real deck photo taken zoomed: the main-camera EXIF focal (~2966 px) is
    three times too short. Three vanishing points measure the focal length and
    overrule it; two (one far away) do not, and keep it."""
    from test_real_photo import D_ACROSS, D_DEPTH, D_SIZE, D_SPEC_FOCAL_PX, D_VERTICALS

    known = D_SPEC_FOCAL_PX
    sol = solve_vanishing_points([D_ACROSS, D_DEPTH, D_VERTICALS], ["+X", "-Y", "-Z"], D_SIZE, known_focal_px=known)
    assert 7800 < sol.focal_px < 9800, sol.focal_px
    assert sol.guide_misfit < 1.5
    sol = solve_vanishing_points([D_ACROSS, D_VERTICALS], ["+X", "-Z"], D_SIZE, known_focal_px=known)
    assert sol.focal_px == pytest.approx(known, rel=0.05)


def test_known_focal_rescues_incompatible_vanishing_points():
    """Vanishing points on the same side of the principal point fit no camera
    on their own (focal^2 < 0); with a known focal length they still solve."""
    size = (1920, 1080)
    p = np.array([960.0, 540.0])

    def through(vp):
        vp = p + np.asarray(vp, float)
        return [((200.0, 100.0), tuple(vp)), ((200.0, 900.0), tuple(vp))]

    lines = [through((1500.0, 0.0)), through((300.0, 1500.0))]
    with pytest.raises(SolverError):
        solve_vanishing_points(lines, ["+X", "+Y"], size)
    sol = solve_vanishing_points(lines, ["+X", "+Y"], size, known_focal_px=1500.0)
    assert np.isfinite(sol.focal_px) and sol.focal_px > 0.0
