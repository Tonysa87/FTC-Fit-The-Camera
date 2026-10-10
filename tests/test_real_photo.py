# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests on edges measured on a real photo (tests/data/elevator_lines.json)."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from solver import solve_vanishing_points

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
