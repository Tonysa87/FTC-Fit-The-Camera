# SPDX-License-Identifier: GPL-3.0-or-later
import math

import numpy as np
import pytest

from solver.hdri import brightest_point, direction, elevation, image_point, z_rotation


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


@pytest.mark.parametrize("u, v", [(0.5, 0.5), (0.25, 0.7), (0.9, 0.2), (0.01, 0.5), (0.6, 0.95)])
def test_point_and_direction_round_trip(u, v):
    assert image_point(direction(u, v)) == pytest.approx((u, v))


def test_cycles_convention():
    np.testing.assert_allclose(direction(0.5, 0.5), [1.0, 0.0, 0.0], atol=1e-12)
    # Clockwise seen from above: a quarter turn right of +X is -Y.
    np.testing.assert_allclose(direction(0.75, 0.5), [0.0, -1.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(direction(0.3, 1.0), [0.0, 0.0, 1.0], atol=1e-12)
    assert elevation(0.75) == pytest.approx(45.0)


def _sky(w, h, u0, v0, radius_deg=1.0, sun=5000.0):
    rows, cols = np.mgrid[0:h, 0:w]
    sun_dir = direction(u0, v0)
    lum = np.full((h, w), 0.5)
    u = (cols + 0.5) / w
    v = (rows + 0.5) / h
    phi = (0.5 - u) * 2 * math.pi
    theta = (v - 0.5) * math.pi
    dirs = np.stack([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), np.sin(theta)], -1)
    lum[dirs @ sun_dir > math.cos(math.radians(radius_deg))] = sun
    # A bright cloud elsewhere, dimmer than the sun.
    cloud = direction((u0 + 0.4) % 1.0, 0.6)
    lum[dirs @ cloud > math.cos(math.radians(6.0))] = 40.0
    return lum


@pytest.mark.parametrize("u0, v0", [(0.3, 0.62), (0.999, 0.55), (0.0005, 0.7), (0.5, 0.9)])
def test_brightest_point_finds_the_sun(u0, v0):
    lum = _sky(1024, 512, u0, v0)
    u, v = brightest_point(lum)
    got, want = direction(u, v), direction(u0, v0)
    assert math.degrees(math.acos(min(1.0, got @ want))) < 0.3


def test_z_rotation_puts_the_sun_on_the_target():
    target = np.array([math.cos(0.4) * math.cos(-2.0), math.cos(0.4) * math.sin(-2.0), math.sin(0.4)])
    u, v = 0.31, image_point(target)[1]
    angle = z_rotation(u, target)
    # The world direction ``target`` shows the HDRI at Rz(angle) @ target.
    assert image_point(rz(angle) @ target) == pytest.approx((u, v))
