# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests on edges measured on a real photo (tests/data/elevator_lines.json)."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from solver import SolverError, solve_vanishing_points

DATA = json.loads((Path(__file__).parent / "data" / "elevator_lines.json").read_text())
SIZE = tuple(DATA["image_size"])
L = DATA["lines"]


def guide_misfit(sol, lines, axis):
    """Largest angle (degrees) between a guide and the line to the solved vanishing point of ``axis``."""
    d = sol.rotation.T @ np.eye(3)[axis]
    vp = sol.principal_point + sol.focal_px * d[:2] / -d[2]
    worst = 0.0
    for a, b in lines:
        g, t = np.subtract(b, a), vp - np.add(a, b) / 2
        e = math.degrees(math.atan2(g[0] * t[1] - g[1] * t[0], g @ t))
        worst = max(worst, abs((e + 90) % 180 - 90))
    return worst


# Measured guides run left to right (X), bottom to top of the floor towards the
# camera (Y) and top to bottom (Z): +X, -Y and -Z give Z up.
TILES_X = [L["tile_across_c"], L["tile_across_d"]]
TILES_Y = [L["tile_depth_a"], L["tile_depth_b"]]
VERTICALS = [L["vertical_left_jamb"], L["vertical_door_split"], L["vertical_right_door"], L["vertical_right_jamb"]]


def test_two_vanishing_points_fit_the_guides():
    sol = solve_vanishing_points([TILES_X, TILES_Y], ["+X", "-Y"], SIZE)
    assert guide_misfit(sol, TILES_X, 0) < 0.01
    assert guide_misfit(sol, TILES_Y, 1) < 0.01
    assert sol.roll == pytest.approx(4.2, abs=0.3)
    assert not sol.warnings


def test_straighten_reports_the_removed_roll():
    sol = solve_vanishing_points([TILES_X, TILES_Y], ["+X", "-Y"], SIZE, straighten_horizon=True)
    assert abs(sol.roll) < 1e-6
    assert sol.removed_roll == pytest.approx(4.2, abs=0.3)
    # The straightened camera no longer follows the guides: say so.
    assert guide_misfit(sol, TILES_X, 0) > 3.0
    assert any("straighten" in w for w in sol.warnings)


def test_floor_and_verticals_agree_with_exif():
    """Tile depth + verticals: both vanishing points near the image, focal close to
    the EXIF value read on the uncropped 4:3 sensor (~2960 px)."""
    sol = solve_vanishing_points([TILES_Y, VERTICALS], ["+Y", "+Z"], SIZE)
    assert 2900 < sol.focal_px < 3300


WALL_X = [L["wall_door_bottom"], L["wall_threshold"]]
EXIF_FOCAL_PX = 5.895 * 3072 / 6.122  # 35 mm equivalent on the uncropped 4:3 sensor


def test_three_axes_with_exif_focal_follow_every_guide():
    """Wall + floor + verticals with the EXIF focal: the verticals (what an
    extrusion along Z must follow) fit within 0.3° and the roll is stable."""
    sol = solve_vanishing_points([WALL_X, TILES_Y, VERTICALS], ["+X", "-Y", "-Z"], SIZE, focal_px=EXIF_FOCAL_PX)
    jambs = [L["vertical_left_jamb"], L["vertical_right_jamb"]]
    assert guide_misfit(sol, jambs, 2) < 0.3
    # The sliding door edges are softer, measured with ~2 px of noise.
    assert guide_misfit(sol, VERTICALS, 2) < 0.4
    assert guide_misfit(sol, WALL_X, 0) < 0.4
    assert sol.roll == pytest.approx(4.25, abs=0.3)
    assert sol.pitch == pytest.approx(-32.9, abs=0.5)


def test_floor_only_misses_the_verticals():
    """Two floor directions alone leave the verticals several degrees off: the
    case of an extrusion drifting away from the jambs."""
    sol = solve_vanishing_points([TILES_X, TILES_Y], ["+X", "-Y"], SIZE)
    assert guide_misfit(sol, VERTICALS, 2) > 1.0


GALLERY = json.loads((Path(__file__).parent / "data" / "gallery_lines.json").read_text())
GL = GALLERY["lines"]
G_SIZE = tuple(GALLERY["image_size"])
G_ACROSS = [v for k, v in GL.items() if k.startswith("across")]
G_VERTICALS = [v for k, v in GL.items() if k.startswith("vertical")]
G_DEPTH = [v for k, v in GL.items() if k.startswith("depth")]
G_EXIF_FOCAL_PX = 25.0 * math.hypot(*G_SIZE) / math.hypot(36.0, 24.0)  # native 4:3 image


def test_gallery_back_wall_and_verticals_agree_with_exif():
    """Near one-point perspective: horizontals of the back wall + verticals with
    the EXIF focal fit every one of the nine lines within 0.3 degrees."""
    sol = solve_vanishing_points([G_ACROSS, G_VERTICALS], ["+X", "-Z"], G_SIZE, focal_px=G_EXIF_FOCAL_PX)
    assert guide_misfit(sol, G_ACROSS, 0) < 0.3
    assert guide_misfit(sol, G_VERTICALS, 2) < 0.3
    assert sol.pitch == pytest.approx(3.9, abs=0.3)
    assert abs(sol.roll) < 0.3


def test_gallery_depth_lines_are_not_perpendicular_to_the_back_wall():
    """The light rails and side floor lines look like depth lines but are not:
    with the well-determined camera they miss the depth vanishing point by degrees."""
    sol = solve_vanishing_points([G_ACROSS, G_VERTICALS], ["+X", "-Z"], G_SIZE, focal_px=G_EXIF_FOCAL_PX)
    assert guide_misfit(sol, G_DEPTH, 1) > 3.0


def test_far_horizontal_vanishing_point_cannot_give_the_focal_length():
    """Back wall horizontals vanish ~160000 px away: two vanishing points cannot
    solve the focal length; a clear error explains why."""
    with pytest.raises(SolverError, match="perpendicular"):
        solve_vanishing_points([G_ACROSS, G_DEPTH], ["+X", "+Y"], G_SIZE)


DECK = json.loads((Path(__file__).parent / "data" / "deck_lines.json").read_text())
DL = DECK["lines"]
D_SIZE = tuple(DECK["image_size"])
D_DEPTH = [v for k, v in DL.items() if k.startswith("depth")]
D_ACROSS = [v for k, v in DL.items() if k.startswith("across")]
D_VERTICALS = [v for k, v in DL.items() if k.startswith("vertical")]
# Spec-sheet focal: 4.745 mm on a 6.4 mm 4:3 sensor, square crop -> 4000 px native width.
D_SPEC_FOCAL_PX = 4.745 * 4000 / 6.4


def test_zoomed_photo_solves_its_own_focal_length():
    """Three vanishing points find a long focal length (zoomed photo) on which
    every guide agrees."""
    sol = solve_vanishing_points([D_ACROSS, D_DEPTH, D_VERTICALS], ["+X", "-Y", "-Z"], D_SIZE)
    assert 7800 < sol.focal_px < 9800
    assert sol.guide_misfit < 1.5
    assert sol.position[2] > 0
    assert sol.pitch == pytest.approx(-9.9, abs=1.0)


def test_wrong_known_focal_shows_up_as_guide_misfit():
    """Forcing the main-camera focal on a zoomed photo leaves guides degrees off:
    the misfit is what lets the add-on warn about it."""
    sol = solve_vanishing_points([D_ACROSS, D_DEPTH, D_VERTICALS], ["+X", "-Y", "-Z"], D_SIZE, focal_px=D_SPEC_FOCAL_PX)
    assert sol.guide_misfit > 3.0
    exact = solve_vanishing_points([D_ACROSS, D_DEPTH, D_VERTICALS], ["+X", "-Y", "-Z"], D_SIZE)
    assert exact.guide_misfit < sol.guide_misfit
