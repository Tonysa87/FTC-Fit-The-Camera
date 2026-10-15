# SPDX-License-Identifier: GPL-3.0-or-later
"""Sun of the photo -> a Sun light.

The sun comes from the shooting time and place (its height; around the scene it
is placed by the compass of the photo, by a shadow, or by the user: the scene
axis it comes from, turned by eye), or straight from a shadow in the photo. The
scene is Z up. FTC only turns the light: its strength, colour and angle stay the
user's.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import bpy
import numpy as np
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import calibrate, ops_load
from .exif import read_exif
from .solver.common import SolverError
from .solver.sun import (
    Shadow,
    SunPosition,
    azimuth_spread,
    heading,
    scene_direction,
    shadow_direction,
    shadow_uncertainty,
    sun_position,
    y_bearing,
)
from .translations import message

SUN_NAME = "FTC Sun"
AXIS_VECTORS = {"+X": (1.0, 0.0, 0.0), "+Y": (0.0, 1.0, 0.0), "-X": (-1.0, 0.0, 0.0), "-Y": (0.0, -1.0, 0.0)}
SHADOW_KEYS = ("shadow_foot", "shadow_top", "shadow_tip")
# Handles that are sun inputs, not calibration guides.
SUN_KEYS = set(SHADOW_KEYS)
# Shadow and date/place disagreeing beyond these (degrees) is worth a red value.
SHADOW_NORTH_ALERT = 5.0
SHADOW_ELEVATION_ALERT = 2.0
# Raise never takes the sun lower than this (degrees).
MIN_RAISED_ELEVATION = 0.5


@dataclass
class SunState:
    """What the Sun section knows. ``error`` blocks the light; ``sun`` may still
    be shown (e.g. below the horizon)."""

    utc: datetime | None = None
    sun: SunPosition | None = None
    # Compass bearing (degrees) of the calibrated world's +Y: the scene +Y when the
    # alignment only turns about Z (``scene_y_bearing`` otherwise).
    y_bearing: float | None = None
    direction: Vector | None = None  # towards the sun, in the scene
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    # Sun measured on the shadow (scene; ``shadow_world`` in the calibrated
    # world, Z up), its spread (degrees) or why not.
    shadow: Vector | None = None
    shadow_world: np.ndarray | None = None
    shadow_spread: float = 0.0
    shadow_error: str = ""
    # Shadow minus date/place: north (degrees, the sign of North Correction)
    # with the spread of the shadow's heading, and elevation.
    shadow_north_offset: float | None = None
    shadow_north_spread: float = 0.0
    shadow_elevation_offset: float | None = None


def north_source(settings) -> str:
    """COMPASS, SHADOW or SIDE (the development builds' MAP and LANDMARK read as SIDE)."""
    source = settings.sun.north_source
    return source if source in ("COMPASS", "SHADOW") else "SIDE"


def shadow_in_use(settings) -> bool:
    sun = settings.sun
    if sun.source == "SHADOW":
        return True
    # With the compass or a side: the shadow checks the north and the height.
    return north_source(settings) == "SHADOW" or sun.use_shadow


def shadow_of(settings) -> Shadow:
    """The shadow handles, in image pixels."""
    foot, top, tip = (calibrate.to_pixels(settings, calibrate.handle(settings, k)) for k in SHADOW_KEYS)
    return Shadow(foot, top, tip, settings.sun.shadow_plane)


def measure_shadow(settings, solution, state) -> None:
    """Fill ``state.shadow`` (scene direction), its spread, or ``shadow_error``."""
    if solution is None:
        state.shadow_error = "Calibrate the camera first: the shadow is measured through it"
        return
    shadow = shadow_of(settings)
    try:
        d = shadow_direction(solution, shadow)
        step = calibrate.PLACEMENT_ERROR * max(calibrate.image_size(settings))
        state.shadow_spread = shadow_uncertainty(solution, shadow, step)
    except SolverError as exc:
        state.shadow_error = str(exc)
        return
    state.shadow_world = np.asarray(d, float)
    state.shadow = Vector((scene_rotation(settings) @ d).tolist())
    if all(math.dist(calibrate.handle(settings, k), calibrate.HANDLE_DEFAULTS[k]) < 1e-6 for k in SHADOW_KEYS):
        state.warnings.append("Place the shadow handles on the photo (Calibrate Shadow)")


def north_offset_alert(state) -> bool:
    """Shadow and north disagree beyond the alert and beyond the shadow's noise."""
    off = state.shadow_north_offset
    return off is not None and abs(off) > max(SHADOW_NORTH_ALERT, 2.0 * state.shadow_north_spread)


def elevation_of(direction) -> float:
    return math.degrees(math.asin(max(-1.0, min(1.0, float(direction[2])))))


def location_state(data) -> str:
    """1.0 files have ``has_gps`` but no location state."""
    if data.location_state == "MISSING" and data.has_gps:
        return "EXIF"
    return data.location_state


def shooting_time(data) -> datetime:
    """Aware shooting time; ``ValueError`` with a message for the panel."""
    if data.time_state == "MISSING":
        raise ValueError("Date and time unknown: enter the local time of the shot, or Read from Photo")
    if data.offset_state == "MISSING":
        raise ValueError("Time zone unknown: enter the UTC offset of the local time, daylight saving included")
    try:
        local = datetime(data.year, data.month, data.day, data.hour, data.minute, data.second)
    except ValueError:
        raise ValueError("Invalid date") from None
    return local.replace(tzinfo=timezone(timedelta(hours=data.utc_offset)))


def scene_rotation(settings) -> np.ndarray:
    """Calibrated world -> scene rotation (the alignment, without its scale)."""
    m = calibrate.alignment_matrix(settings).to_3x3().normalized()
    return np.array([list(row) for row in m])


def compass_north(settings, solution) -> tuple[float | None, str]:
    """Compass bearing of the calibrated world's +Y (degrees) from the photo's
    compass, or ``None`` and why."""
    data = settings.camera_data
    if data.direction_state == "MISSING":
        return None, "No compass direction in the photo: use Side or Shadow"
    if solution is None:
        return None, "Calibrate the camera first: the north is found from its view"
    bearing = data.direction
    if data.direction_ref.upper().startswith("M"):
        bearing += math.degrees(settings.sun.declination)
    result = y_bearing(bearing, solution.forward)
    return result, "" if result is not None else "The camera looks straight up or down: no north from its compass"


# Steeper than this (degrees from the horizon) a phone's compass heading is unreliable.
STEEP_VIEW_DEG = 70.0


def evaluate(settings, solution=None) -> SunState:
    """Sun of the photo for ``settings``. Never writes: safe in draw callbacks.

    Worked out in the calibrated world, whose Z is the photo's vertical, then
    turned into the scene: an alignment that tilts Z (a sloped face) tilts the
    sky with it, as it does the measured shadow."""
    state = SunState()
    data = settings.camera_data
    sun = settings.sun
    north = north_source(settings)
    if solution is None:
        solution = calibrate.current_solution(settings.id_data)
    correction = math.degrees(sun.north_correction)
    if north == "COMPASS":
        bearing, north_error = compass_north(settings, solution)
        if bearing is not None:
            state.y_bearing = (bearing + correction) % 360.0
    if shadow_in_use(settings):
        measure_shadow(settings, solution, state)

    if sun.source == "SHADOW":
        # Measured in the scene: no time, place or north needed.
        if state.shadow is None:
            state.error = state.shadow_error
        else:
            state.direction = state.shadow
        return state

    try:
        when = shooting_time(data)
    except ValueError as exc:
        state.error = str(exc)
        return state
    if location_state(data) == "MISSING":
        state.error = "Place unknown: enter latitude and longitude (the nearest town is close enough)"
        return state
    state.utc = when
    try:
        state.sun = sun_position(when, data.gps_latitude, data.gps_longitude)
    except ValueError:
        state.error = "Place unknown: enter latitude and longitude (the nearest town is close enough)"
        return state
    if not state.sun.above_horizon:
        state.error = "The sun is below the horizon at that time: check date, time and UTC offset"
        return state
    if data.clock_mismatch:
        if data.time_from_gps:
            state.warnings.append("The GPS time and the camera clock disagree: check the time (GPS time used)")
        else:
            state.warnings.append(
                "The GPS time and the camera clock disagree: check the time (camera clock and its time zone used)"
            )
    if north == "COMPASS" and data.direction_state != "MISSING" and solution is not None:
        if data.direction_ref.upper().startswith("M") and sun.declination == 0.0:
            state.warnings.append("Magnetic compass: enter the declination of the place")
        if abs(math.degrees(math.asin(max(-1.0, min(1.0, float(solution.forward[2])))))) > STEEP_VIEW_DEG:
            state.warnings.append("The camera looks steeply up or down: its compass is unreliable, check the north")

    # North implied by the shadow: the sun's bearing minus the shadow's heading.
    shadow_bearing = None
    if state.shadow_world is not None and heading(state.shadow_world) is not None:
        shadow_bearing = y_bearing(state.sun.azimuth, state.shadow_world)
        state.shadow_elevation_offset = elevation_of(state.shadow_world) - state.sun.elevation
    if north == "SHADOW":
        if shadow_bearing is None:
            state.error = state.shadow_error or "The sun is almost overhead: its shadow gives no north"
            return state
        # Measured, not estimated: no turn by eye.
        state.y_bearing = shadow_bearing % 360.0
    elif north == "SIDE":
        # The sun comes from the chosen scene axis, turned by eye: the north follows.
        side = scene_rotation(settings).T @ np.array(AXIS_VECTORS[sun.sun_side])
        side_bearing = y_bearing(state.sun.azimuth, side)
        if side_bearing is None:
            state.error = "The alignment stands the chosen side axis upright: pick another side"
            return state
        state.y_bearing = (side_bearing + correction) % 360.0
    elif state.y_bearing is None:
        state.error = north_error
        return state
    if north != "SHADOW" and shadow_bearing is not None:
        # The turn the shadow asks for (add it to Turn / North Correction).
        state.shadow_north_offset = (shadow_bearing - state.y_bearing + 180.0) % 360.0 - 180.0
        state.shadow_north_spread = azimuth_spread(state.shadow_spread, state.shadow_world)
    world = scene_direction(raised(state.sun, sun), state.y_bearing)
    state.direction = Vector((scene_rotation(settings) @ world).tolist())
    return state


def scene_y_bearing(settings, state) -> float | None:
    """Compass bearing of the scene +Y; ``None`` without a north or when the
    alignment stands +Y upright."""
    if state.y_bearing is None:
        return None
    h = heading(scene_rotation(settings).T @ np.array([0.0, 1.0, 0.0]))
    return None if h is None else (state.y_bearing + h) % 360.0


def raised(position: SunPosition, sun) -> SunPosition:
    """The date's sun with the Elevation Correction, kept between just above the
    horizon (a horizontal light casts no shadow at all) and the zenith."""
    elevation = position.elevation + math.degrees(sun.elevation_correction)
    return SunPosition(position.azimuth, min(90.0, max(MIN_RAISED_ELEVATION, elevation)))


def north_vector(y_bear: float) -> Vector:
    """Scene direction of true north for a +Y bearing."""
    a = math.radians(-y_bear)
    return Vector((math.sin(a), math.cos(a), 0.0))


def light_problem(light) -> str:
    """Why FTC cannot (or not lastingly) turn ``light``; empty when it can."""
    if light is None:
        return ""
    if not light.users_scene:
        return "The light is in no scene (deleted?): pick another one or add a New Sun"
    if not light.is_editable:
        return "The light cannot be edited (linked from a library): pick another one or add a New Sun"
    if calibrate.transform_overridden(light):
        return "Keyframes, drivers or constraints on the light (or its parent) override its rotation"
    return ""


def orient(settings, solution=None) -> SunState | None:
    """Turn the camera's Sun light towards the sun (its location and scale
    stay), and a fitted World HDRI with it."""
    from . import ops_hdri  # (it imports draw, which imports this module)

    light = settings.sun.light
    usable = light is not None and bool(light.users_scene) and light.is_editable
    if not usable and not settings.sun.hdri_fitted:
        return None
    state = evaluate(settings, solution)
    ops_hdri.follow(settings, bpy.context.scene, state)
    if not usable or state.direction is None:
        return state
    # A Sun light shines along its local -Z: the world +Z must point at the sun.
    # Solve in the parent's space (mirrored or non-uniform parents included).
    parent = Matrix.Identity(3)
    if light.parent is not None:
        parent = (light.parent.matrix_world @ light.matrix_parent_inverse).to_3x3()
    try:
        local = parent.inverted() @ state.direction
    except ValueError:
        return state
    # matrix_basis, not matrix_world: the latter lags behind a location just set.
    loc, _rot, scale = light.matrix_basis.decompose()
    if scale.z < 0.0:
        # A mirrored light: its own +Z is flipped by the scale.
        local = -local
    rot = local.normalized().to_track_quat("Z", "Y")
    light.matrix_basis = Matrix.LocRotScale(loc, rot, scale)
    return state


def settings_changed(cam_data, context) -> None:
    """Update callback of the sun and time/place settings."""
    if not isinstance(cam_data, bpy.types.Camera) or calibrate.updating():
        return
    if calibrate.cached_solution(cam_data) is None and cam_data.ftc.image is not None:
        calibrate.refresh(cam_data)
    orient(cam_data.ftc)
    calibrate.tag_redraw(context)


def sun_settings(context):
    cam = calibrate.view_camera(context)
    return cam.data.ftc if cam is not None and cam.data.ftc.image is not None else None


class FTC_OT_new_sun(Operator):
    """Add a Sun light that follows the sun of the photo (only its direction: strength and colour are yours)"""

    bl_idname = "ftc.new_sun"
    bl_label = "New Sun"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return sun_settings(context) is not None

    def execute(self, context):
        settings = sun_settings(context)
        cam_data = settings.id_data
        if calibrate.cached_solution(cam_data) is None:
            calibrate.refresh(cam_data)
        light_data = bpy.data.lights.new(SUN_NAME, "SUN")
        obj = bpy.data.objects.new(SUN_NAME, light_data)
        layer = context.view_layer.active_layer_collection
        usable = layer is not None and not layer.exclude and layer.collection.library is None
        (layer.collection if usable else context.scene.collection).objects.link(obj)
        state = evaluate(settings)
        # Above the scene origin, towards the sun: the light's line points at the origin.
        origin = calibrate.alignment_matrix(settings).translation
        reach = max(1.0, 0.5 * settings.results.distance) if settings.results.valid else 5.0
        obj.location = origin + (state.direction or Vector((0.0, 0.0, 1.0))) * reach
        settings.sun.light = obj  # orients it
        if state.error:
            self.report({"WARNING"}, message(state.error, bpy.app.translations.pgettext_rpt))
        return {"FINISHED"}


class FTC_OT_read_photo_time(Operator):
    """Read the date, time and place of the shot again from the photo, replacing what was entered by hand"""

    bl_idname = "ftc.read_photo_time"
    bl_label = "Read from Photo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return sun_settings(context) is not None

    def execute(self, context):
        settings = sun_settings(context)
        # The original file first: an upright copy is packed without EXIF.
        source = bpy.path.abspath(settings.source_path) if settings.source_path else ""
        if source and os.path.isfile(source):
            exif = read_exif(source)
        else:
            exif = ops_load.read_image_exif(settings.image, bpy.path.abspath(settings.image.filepath))
        if exif.capture_time() is None and exif.gps_latitude is None:
            self.report({"WARNING"}, "No date, time or place found in the photo")
            return {"CANCELLED"}
        ops_load.load_time_place(settings.camera_data, exif, keep_entered=True)
        settings_changed(settings.id_data, context)
        return {"FINISHED"}


classes = (FTC_OT_new_sun, FTC_OT_read_photo_time)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
