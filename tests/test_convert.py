# SPDX-License-Identifier: GPL-3.0-or-later
import numpy as np
import pytest
from synthetic import make_camera

from solver import focal_px_from_35mm, focal_px_from_mm, to_blender
from solver.common import CameraSolution


def solution(cam):
    return CameraSolution(cam.image_size, cam.focal_px, cam.principal_point, cam.rotation, cam.position)


def test_landscape_lens_and_fit():
    cam = make_camera(focal_mm=50.0, image_size=(6000, 4000))
    bc = to_blender(solution(cam), 36.0)
    assert bc.lens == pytest.approx(50.0)
    assert bc.sensor_fit == "HORIZONTAL"
    assert bc.shift_x == pytest.approx(0.0) and bc.shift_y == pytest.approx(0.0)
    assert np.allclose(bc.matrix_world[:3, :3], cam.rotation)


def test_portrait_uses_long_side():
    cam = make_camera(focal_mm=50.0, image_size=(4000, 6000))
    bc = to_blender(solution(cam), 36.0)
    assert bc.sensor_fit == "VERTICAL"
    assert bc.lens == pytest.approx(50.0)


def test_unknown_sensor_gives_35mm_equivalent():
    cam = make_camera(focal_mm=24.0, image_size=(4032, 3024))
    assert to_blender(solution(cam)).lens == pytest.approx(24.0)


def test_shift_from_principal_point():
    cam = make_camera(image_size=(2000, 1000), principal_point=(900.0, 600.0))
    bc = to_blender(solution(cam))
    assert bc.shift_x == pytest.approx(0.05)
    assert bc.shift_y == pytest.approx(-0.05)


def test_focal_conversions():
    assert focal_px_from_mm(50.0, 36.0, (6000, 4000)) == pytest.approx(50.0 * 6000 / 36.0)
    # 3:2 image: the diagonal equivalence equals the width equivalence.
    assert focal_px_from_35mm(50.0, (6000, 4000)) == pytest.approx(50.0 * 6000 / 36.0)
