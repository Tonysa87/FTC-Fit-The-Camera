# SPDX-License-Identifier: GPL-3.0-or-later
"""Position of the sun in the sky for a time and place, or from a shadow.

NOAA's solar position equations (Meeus, *Astronomical Algorithms*, 1998), the
ones behind the NOAA Solar Position Calculator: about 0.01° between 1900 and
2100, plenty for a light. Azimuth in degrees clockwise from true north,
elevation in degrees above the horizon, with the NOAA atmospheric refraction
(the sun as seen, which is what the photo shows).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from .common import SolverError, closest_param_on_line, plane_frame, ray

# Julian day of 2000-01-01 12:00 UTC (J2000.0).
J2000 = 2451545.0
UNIX_EPOCH_JD = 2440587.5


@dataclass(frozen=True)
class SunPosition:
    azimuth: float  # degrees clockwise from true north, 0..360
    elevation: float  # degrees above the horizon (negative below)

    @property
    def above_horizon(self) -> bool:
        return self.elevation > 0.0


def julian_day(utc: datetime) -> float:
    """Julian day of a timezone-aware datetime."""
    if utc.tzinfo is None:
        raise ValueError("the time must carry its UTC offset")
    return UNIX_EPOCH_JD + utc.astimezone(UTC).timestamp() / 86400.0


def refraction(elevation: float) -> float:
    """NOAA's atmospheric refraction correction (degrees) for a geometric
    elevation (degrees): standard atmosphere, sea level."""
    if elevation > 85.0:
        return 0.0
    t = math.tan(math.radians(elevation))
    if elevation > 5.0:
        seconds = 58.1 / t - 0.07 / t**3 + 0.000086 / t**5
    elif elevation > -0.575:
        e = elevation
        seconds = 1735.0 + e * (-518.2 + e * (103.4 + e * (-12.79 + e * 0.711)))
    else:
        seconds = -20.772 / t
    return seconds / 3600.0


def sun_position(utc: datetime, latitude: float, longitude: float, refract: bool = True) -> SunPosition:
    """Sun seen from ``latitude`` / ``longitude`` (degrees, north and east
    positive) at ``utc`` (a timezone-aware datetime)."""
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        raise ValueError("latitude or longitude out of range")
    jc = (julian_day(utc) - J2000) / 36525.0

    mean_long = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    mean_anom = math.radians(357.52911 + jc * (35999.05029 - 0.0001537 * jc))
    ecc = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    centre = (
        math.sin(mean_anom) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2 * mean_anom) * (0.019993 - 0.000101 * jc)
        + math.sin(3 * mean_anom) * 0.000289
    )
    omega = math.radians(125.04 - 1934.136 * jc)
    app_long = math.radians(mean_long + centre - 0.00569 - 0.00478 * math.sin(omega))
    mean_obliq = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    obliq = math.radians(mean_obliq + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(obliq) * math.sin(app_long))

    # Equation of time (minutes): apparent minus mean solar time.
    y = math.tan(obliq / 2.0) ** 2
    l0 = math.radians(mean_long)
    eq_time = 4.0 * math.degrees(
        y * math.sin(2 * l0)
        - 2 * ecc * math.sin(mean_anom)
        + 4 * ecc * y * math.sin(mean_anom) * math.cos(2 * l0)
        - 0.5 * y * y * math.sin(4 * l0)
        - 1.25 * ecc * ecc * math.sin(2 * mean_anom)
    )
    t = utc.astimezone(UTC)
    minutes = t.hour * 60.0 + t.minute + (t.second + t.microsecond * 1e-6) / 60.0
    solar_time = (minutes + eq_time + 4.0 * longitude) % 1440.0
    hour_angle = math.radians(solar_time / 4.0 - 180.0)

    lat = math.radians(latitude)
    cos_zenith = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    elevation = 90.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))
    azimuth = math.degrees(
        math.atan2(
            math.sin(hour_angle),
            math.cos(hour_angle) * math.sin(lat) - math.tan(decl) * math.cos(lat),
        )
    )
    azimuth = (azimuth + 180.0) % 360.0
    if refract:
        elevation += refraction(elevation)
    return SunPosition(azimuth, elevation)


def direction_enu(azimuth: float, elevation: float) -> np.ndarray:
    """Unit vector towards the sun in a local frame: x east, y north, z up."""
    az, el = math.radians(azimuth), math.radians(elevation)
    return np.array([math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)])


# ----------------------------------------------------------------------------
# Scene north. The scene is Z up; its north is given by the compass bearing of
# the scene's +Y axis ("Y bearing"): 0 when +Y points to true north, 90 when it
# points east. Bearings and headings are degrees clockwise seen from above.

# Below this horizontal length (sine of ~0.6°) a direction has no usable heading.
MIN_HORIZONTAL = 0.01


def heading(vector) -> float | None:
    """Heading of a scene direction, degrees clockwise from +Y seen from above;
    ``None`` when it is (nearly) vertical."""
    x, y = float(vector[0]), float(vector[1])
    if math.hypot(x, y) < MIN_HORIZONTAL * float(np.linalg.norm(vector)):
        return None
    return math.degrees(math.atan2(x, y)) % 360.0


def y_bearing(bearing: float, direction) -> float | None:
    """Bearing of the scene +Y axis, given that the scene ``direction`` points to
    compass ``bearing`` (a camera view with its EXIF direction, a landmark ray,
    a scene axis read on a map). ``None`` when ``direction`` is vertical."""
    h = heading(direction)
    return None if h is None else (bearing - h) % 360.0


def scene_direction(sun: SunPosition, y_bear: float) -> np.ndarray:
    """Unit vector towards the sun in the scene."""
    return direction_enu(sun.azimuth - y_bear, sun.elevation)


# ----------------------------------------------------------------------------
# Sun from a shadow: a vertical object standing on the ground (foot and top) and
# the shadow of its top on the ground or on a wall. The sun lies along the line
# from the shadow's tip through the top (Kee, O'Brien, Farid 2013: in the image
# that line passes through the projected light). Calibrated world, Z up; the
# ground (XY) and the walls (XZ, YZ) pass through the origin.


@dataclass(frozen=True)
class Shadow:
    """Image points (pixels) of the foot and top of a vertical object and of the
    tip of the top's shadow, which lies on ``plane`` (through the origin)."""

    foot: tuple[float, float]
    top: tuple[float, float]
    tip: tuple[float, float]
    plane: str = "XY"


def _plane_hit(centre, direction, normal):
    den = float(normal @ direction)
    if abs(den) < 1e-12:
        return None
    s = -float(normal @ centre) / den
    return centre + s * direction if s > 0.0 else None


def shadow_points(solution, shadow: Shadow):
    """World foot, top and tip of ``shadow`` seen by ``solution``; ``SolverError``
    when a point is off its plane or the object has no height."""
    centre = np.asarray(solution.position, float)
    rot = np.asarray(solution.rotation, float)
    p, f = solution.principal_point, solution.focal_px
    up = np.array([0.0, 0.0, 1.0])
    foot = _plane_hit(centre, rot @ ray(shadow.foot, p, f), up)
    if foot is None:
        raise SolverError("the foot of the object is beyond the horizon: put it on the ground")
    height = closest_param_on_line(foot - centre, up, rot @ ray(shadow.top, p, f))
    if height <= 1e-9 * float(np.linalg.norm(foot - centre)):
        raise SolverError("the top of the object must be above its foot")
    tip = _plane_hit(centre, rot @ ray(shadow.tip, p, f), plane_frame(shadow.plane)[:, 2])
    if tip is None:
        raise SolverError("the shadow tip is beyond the horizon of its plane")
    return foot, foot + height * up, tip


def shadow_direction(solution, shadow: Shadow) -> np.ndarray:
    """Unit vector towards the sun (calibrated world) measured from ``shadow``."""
    _foot, top, tip = shadow_points(solution, shadow)
    d = top - tip
    n = float(np.linalg.norm(d))
    if n < 1e-12:
        raise SolverError("the shadow tip is on the top of the object")
    d /= n
    if d[2] <= 0.0:
        raise SolverError("this shadow puts the sun below the horizon: check the handles and the shadow plane")
    return d


def shadow_uncertainty(solution, shadow: Shadow, step: float) -> float:
    """Spread (degrees) of the measured sun direction when each handle moves by
    ``step`` pixels, coordinate by coordinate, added in quadrature; ``inf`` when
    a nudge makes the shadow unreadable."""
    base = shadow_direction(solution, shadow)
    total = 0.0
    for name in ("foot", "top", "tip"):
        for axis in (0, 1):
            co = list(getattr(shadow, name))
            co[axis] += step
            nudged = Shadow(**{**shadow.__dict__, name: tuple(co)})
            try:
                d = shadow_direction(solution, nudged)
            except SolverError:
                return math.inf
            total += math.degrees(math.acos(min(1.0, float(base @ d)))) ** 2
    return math.sqrt(total)


def shadow_tip_for(solution, shadow: Shadow, sun) -> np.ndarray | None:
    """Where the top's shadow falls on the shadow plane for a sun direction
    ``sun`` (calibrated world): the check of a computed sun against the photo."""
    _foot, top, _tip = shadow_points(solution, shadow)
    return _plane_hit(top, -np.asarray(sun, float), plane_frame(shadow.plane)[:, 2])
