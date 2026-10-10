# SPDX-License-Identifier: GPL-3.0-or-later
"""Random and degenerate guide layouts: the solvers either solve or raise SolverError."""

import contextlib
import math

import numpy as np
import pytest

from solver import SolverError, solve_horizon, solve_rectangle, solve_vanishing_points

SIZE = (1920, 1080)
AXES = ["+X", "+Y", "-Z"]


def random_lines(rng, count, degenerate):
    groups = []
    for _ in range(count):
        a = rng.uniform(-200, 2100, 2)
        if degenerate:
            # Nearly parallel or nearly collinear pairs, short segments, coincident points.
            d = rng.normal(0, 1, 2)
            b = a + d * rng.choice([1e-3, 0.5, 5, 400])
            offset = rng.normal(0, 1, 2) * rng.choice([0.0, 1e-4, 0.5, 300])
            groups.append([(a, b), (a + offset, b + offset + rng.normal(0, 1e-3, 2))])
        else:
            groups.append([(a, rng.uniform(-200, 2100, 2)), (rng.uniform(-200, 2100, 2), rng.uniform(-200, 2100, 2))])
    return groups


def check(solution):
    values = [solution.focal_px, *solution.rotation.ravel(), *solution.position]
    assert all(math.isfinite(v) for v in values)
    assert solution.focal_px > 0


@pytest.mark.parametrize("degenerate", [False, True])
@pytest.mark.parametrize("count", [1, 2, 3])
def test_vanishing_points_never_crash(count, degenerate):
    rng = np.random.default_rng(count * 10 + degenerate)
    for _ in range(400):
        groups = random_lines(rng, count, degenerate)
        kwargs = {}
        if count == 1 or rng.random() < 0.3:
            kwargs["focal_px"] = float(rng.choice([1.0, 500.0, 2000.0, 1e6]))
        if count == 1:
            kwargs["axis2_line"] = random_lines(rng, 1, degenerate)[0][0]
        if count == 2 and rng.random() < 0.3:
            kwargs["third_axis_line"] = random_lines(rng, 1, degenerate)[0][0]
        try:
            sol = solve_vanishing_points(groups, AXES[: max(count, 2)], SIZE, **kwargs)
        except SolverError:
            continue
        check(sol)


@pytest.mark.parametrize("degenerate", [False, True])
def test_rectangle_and_horizon_never_crash(degenerate):
    rng = np.random.default_rng(5 + degenerate)
    for _ in range(400):
        corners = rng.uniform(-200, 2100, (4, 2))
        if degenerate:
            corners[1] = corners[0] + rng.normal(0, 1e-3, 2)
        with contextlib.suppress(SolverError):
            check(solve_rectangle(corners, 1.0, 2.0, SIZE, focal_px=float(rng.choice([0.0, 1500.0]))))
        a = rng.uniform(-200, 2100, 2)
        b = a + (rng.normal(0, 1e-6, 2) if degenerate else rng.normal(0, 500, 2))
        with contextlib.suppress(SolverError):
            check(solve_horizon([a, b], 1500.0, SIZE, camera_height=1.6))
