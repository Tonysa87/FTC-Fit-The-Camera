# SPDX-License-Identifier: GPL-3.0-or-later
import math
from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest

from solver.sun import (
    SunPosition,
    direction_enu,
    heading,
    julian_day,
    refraction,
    scene_direction,
    sun_position,
    y_bearing,
)

# Reference: NREL SPA (pvlib 0.16.1 ``spa_python``, sea level, 1013.25 hPa, 10 °C,
# delta T 69.2 s). Name, UTC time, latitude, longitude, azimuth, geometric
# elevation, apparent elevation.
SPA = [
    ("Milan summer", "2026-06-21 10:30:00", 45.4642, 9.19, 148.5083, 65.3036, 65.3114),
    ("Rome winter", "2025-12-21 13:00:00", 41.9028, 12.4964, 207.1792, 19.7279, 19.7744),
    ("Rome after sunset", "2025-12-21 15:45:00", 41.9028, 12.4964, 239.0715, -1.3174, -1.3174),
    ("Tromso midnight sun", "2024-06-21 22:00:00", 69.6496, 18.956, 349.3975, 3.4522, 3.6617),
    ("Sydney", "2023-03-15 02:00:00", -33.8688, 151.2093, 2.0199, 58.4116, 58.4220),
    ("Buenos Aires", "2022-07-04 19:20:00", -34.6037, -58.3816, 312.5309, 15.2122, 15.2728),
    ("Quito", "2021-09-23 17:10:00", -0.1807, -78.4678, 260.0050, 89.0022, 89.0025),
    ("Anchorage", "2027-11-02 21:00:00", 61.2181, -149.9003, 169.2797, 13.4145, 13.4830),
    ("Suva", "2030-01-10 23:30:00", -18.1248, 178.4501, 111.5674, 79.0373, 79.0405),
    ("Reykjavik", "2026-03-20 12:00:00", 64.1466, -21.9426, 153.8979, 23.4677, 23.5063),
    ("Singapore", "2020-02-29 04:15:00", 1.3521, 103.8198, 120.7811, 71.9853, 71.9908),
    ("McMurdo", "2025-01-01 00:00:00", -77.8463, 166.6683, 15.9406, 34.7364, 34.7608),
]


def angle_between(a, b):
    return math.degrees(math.acos(min(1.0, float(np.dot(a, b)))))


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize("case", SPA, ids=[c[0] for c in SPA])
def test_matches_spa(case):
    _, time, lat, lon, azimuth, elevation, apparent = case
    # The azimuth alone is meaningless near the zenith: compare directions.
    geometric = sun_position(utc(time), lat, lon, refract=False)
    error = angle_between(direction_enu(geometric.azimuth, geometric.elevation), direction_enu(azimuth, elevation))
    assert error < 0.05
    if elevation > 0.0:
        seen = sun_position(utc(time), lat, lon)
        error = angle_between(direction_enu(seen.azimuth, seen.elevation), direction_enu(azimuth, apparent))
        assert error < 0.05


def test_nrel_spa_paper_example():
    # Reda & Andreas (2004), table A5.1: 820 hPa, 11 °C, so allow for the
    # sea-level refraction used here (~0.004° at 40° elevation).
    t = datetime(2003, 10, 17, 12, 30, 30, tzinfo=timezone(timedelta(hours=-7)))
    sun = sun_position(t, 39.742476, -105.1786)
    assert sun.azimuth == pytest.approx(194.34024, abs=0.05)
    assert 90.0 - sun.elevation == pytest.approx(50.11162, abs=0.05)


def test_local_time_with_offset_equals_utc():
    t = datetime(2026, 9, 14, 17, 18, 53, tzinfo=timezone(timedelta(hours=2)))
    assert sun_position(t, 45.0, 9.0) == sun_position(t.astimezone(UTC), 45.0, 9.0)


def test_naive_time_is_refused():
    with pytest.raises(ValueError):
        sun_position(datetime(2026, 6, 21, 12), 45.0, 9.0)
    with pytest.raises(ValueError):
        julian_day(datetime(2026, 6, 21, 12))


def test_out_of_range_place_is_refused():
    with pytest.raises(ValueError):
        sun_position(utc("2026-06-21 12:00:00"), 91.0, 9.0)
    with pytest.raises(ValueError):
        sun_position(utc("2026-06-21 12:00:00"), 45.0, 181.0)


def test_julian_day_of_j2000():
    assert julian_day(utc("2000-01-01 12:00:00")) == pytest.approx(2451545.0)


def test_noon_sun_is_south_in_the_north_and_north_in_the_south():
    # Around the March equinox the sun crosses the meridian near 12:07 local
    # mean time; at longitude 0 that is 12:07 UTC.
    t = utc("2026-03-20 12:07:00")
    north = sun_position(t, 45.0, 0.0)
    south = sun_position(t, -45.0, 0.0)
    assert north.azimuth == pytest.approx(180.0, abs=1.0)
    assert abs((south.azimuth + 180.0) % 360.0 - 180.0) < 1.0
    assert north.elevation == pytest.approx(45.0, abs=0.5)


def test_refraction_lifts_the_sun_most_at_the_horizon():
    assert refraction(90.0) == 0.0
    assert refraction(45.0) == pytest.approx(58.0 / 3600.0, abs=0.001)
    assert 0.4 < refraction(0.0) < 0.6
    assert refraction(30.0) < refraction(5.0) < refraction(0.0)


def test_night_sun_is_below_the_horizon():
    assert not sun_position(utc("2026-06-21 23:00:00"), 45.0, 9.0).above_horizon


def test_direction_enu_axes():
    np.testing.assert_allclose(direction_enu(0.0, 0.0), [0.0, 1.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(direction_enu(90.0, 0.0), [1.0, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(direction_enu(123.0, 90.0), [0.0, 0.0, 1.0], atol=1e-12)


def test_heading_is_clockwise_from_y():
    assert heading([0.0, 1.0, 0.0]) == pytest.approx(0.0)
    assert heading([1.0, 0.0, -5.0]) == pytest.approx(90.0)
    assert heading([0.0, -2.0, 0.3]) == pytest.approx(180.0)
    assert heading([-1.0, 0.0, 0.0]) == pytest.approx(270.0)
    assert heading([0.0, 0.0, -1.0]) is None
    assert heading([0.001, 0.0, -1.0]) is None


def test_y_bearing_from_a_view_direction():
    # The camera looks along +X and the compass says east: +Y is north.
    assert y_bearing(90.0, [1.0, 0.0, -0.2]) == pytest.approx(0.0)
    # The camera looks along +Y and the compass says 30°: +Y points to 30°.
    assert y_bearing(30.0, [0.0, 1.0, 0.0]) == pytest.approx(30.0)
    # Looking along -X towards north: +X is south, +Y is east.
    assert y_bearing(0.0, [-1.0, 0.0, 0.0]) == pytest.approx(90.0)
    assert y_bearing(10.0, [0.0, 0.0, 1.0]) is None


def test_scene_direction_follows_the_north():
    sun = SunPosition(azimuth=239.0, elevation=56.0)
    # +Y north: the scene is the local east-north-up frame.
    np.testing.assert_allclose(scene_direction(sun, 0.0), direction_enu(239.0, 56.0), atol=1e-12)
    # A camera looking at the sun's compass bearing sees it straight ahead.
    view = np.array([0.3, 0.8, -0.1])
    d = scene_direction(sun, y_bearing(239.0, view))
    assert heading(d) == pytest.approx(heading(view))
    assert math.degrees(math.asin(d[2])) == pytest.approx(56.0)
