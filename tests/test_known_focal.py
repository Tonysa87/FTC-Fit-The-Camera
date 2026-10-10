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
    # Two well-spread vanishing points measure the focal length to ~2%: a known
    # value 10% off is pulled most of the way back.
    sol = two_vps(camera, known_focal_px=camera.focal_px * 1.1)
    assert sol.focal_px == pytest.approx(camera.focal_px, rel=0.025)


def test_guides_drop_a_known_focal_they_cannot_agree_with(camera):
    sol = two_vps(camera, known_focal_px=camera.focal_px * 2.0)
    assert sol.focal_px == pytest.approx(camera.focal_px, rel=0.01)
    assert sol.guide_misfit < 0.1


def test_noisy_guides_keep_a_correct_known_focal():
    """Guides off by up to 25 px, still within a degree of the known focal: the
    known value stays (the guides alone would wander off)."""
    cam = make_camera(yaw=3.0, pitch=-8.0, roll=0.0)
    for error in (10.0, 25.0):
        lines = [guides(cam, "X"), guides(cam, "Y")]
        a, b = lines[0][1]
        lines[0][1] = (a, (b[0], b[1] + error))
        sol = solve_vanishing_points(
            lines, ["+X", "+Y"], cam.image_size, origin=cam.project([0, 0, 0]), known_focal_px=cam.focal_px
        )
        assert sol.focal_px == pytest.approx(cam.focal_px, rel=0.05), error
        assert sol.pitch == pytest.approx(-8.0, abs=1.0)


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


def test_rectangle_keeps_the_known_focal(camera):
    """Four corners barely measure the focal length: even a known value 3x off
    reprojects them within ~9 px, so the rectangle keeps it (it cannot tell a
    zoomed photo; three vanishing points can)."""
    sol = solve_rectangle(corners(camera), WIDTH, HEIGHT, camera.image_size, known_focal_px=camera.focal_px * 1.3)
    assert 1.15 < sol.focal_px / camera.focal_px < 1.3
    exact = solve_rectangle(corners(camera), WIDTH, HEIGHT, camera.image_size, known_focal_px=camera.focal_px)
    assert exact.focal_px == pytest.approx(camera.focal_px, rel=1e-4)
    assert np.allclose(exact.position, camera.position, atol=1e-3 * np.linalg.norm(camera.position))


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


def test_gallery_depth_lines_do_not_drag_the_exif_focal_away():
    """Real gallery photo: the depth lines are not quite perpendicular to the back
    wall. Alone the guides would push the focal to ~15000 px; the EXIF value is
    kept and the large misfit points at the real cause (lines not parallel)."""
    from test_real_photo import G_ACROSS, G_DEPTH, G_EXIF_FOCAL_PX, G_SIZE

    sol = solve_vanishing_points([G_ACROSS, G_DEPTH], ["+X", "+Y"], G_SIZE, known_focal_px=G_EXIF_FOCAL_PX)
    assert sol.focal_px == pytest.approx(G_EXIF_FOCAL_PX, rel=0.05)
    assert sol.guide_misfit > 3.0
