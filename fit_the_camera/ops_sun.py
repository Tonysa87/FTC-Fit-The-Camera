# SPDX-License-Identifier: GPL-3.0-or-later
"""Sun of the photo: shooting time and place -> sun in the scene -> a Sun light.

The scene is Z up. Its north comes from the compass of the photo, from the map
bearing of a scene axis or from a distant landmark; FTC only turns the light,
its strength, colour and angle stay the user's.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import bpy
import numpy as np
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import calibrate, ops_load
from .solver.common import ray
from .solver.sun import SunPosition, scene_direction, sun_position, y_bearing

SUN_NAME = "FTC Sun"
AXIS_VECTORS = {"+X": (1.0, 0.0, 0.0), "+Y": (0.0, 1.0, 0.0), "-X": (-1.0, 0.0, 0.0), "-Y": (0.0, -1.0, 0.0)}
LANDMARK_KEY = "landmark"


@dataclass
class SunState:
    """What the Sun section knows. ``error`` blocks the light; ``sun`` may still
    be shown (e.g. below the horizon)."""

    utc: datetime | None = None
    sun: SunPosition | None = None
    y_bearing: float | None = None  # compass bearing of the scene +Y, degrees
    direction: Vector | None = None  # towards the sun, in the scene
    error: str = ""
    warnings: list[str] = field(default_factory=list)


def location_state(data) -> str:
    """1.0 files have ``has_gps`` but no location state."""
    if data.location_state == "MISSING" and data.has_gps:
        return "EXIF"
    return data.location_state


def shooting_time(data) -> datetime:
    """Aware shooting time; ``ValueError`` with a message for the panel."""
    if data.time_state == "MISSING":
        raise ValueError("Date and time unknown: enter the local time of the shot")
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


def scene_north(settings, solution) -> tuple[float | None, str]:
    """Compass bearing of the scene +Y (degrees), or ``None`` and why."""
    sun = settings.sun
    data = settings.camera_data
    source = sun.north_source
    if source == "MAP":
        bearing = y_bearing(math.degrees(sun.map_bearing), AXIS_VECTORS[sun.map_axis])
        return bearing, ""
    if solution is None:
        return None, "Calibrate the camera first: the north is found from its view"
    rotation = scene_rotation(settings) @ solution.rotation
    if source == "COMPASS":
        if data.direction_state == "MISSING":
            return None, "No compass direction in the photo: use Map or Landmark"
        bearing = data.direction
        if data.direction_ref.upper().startswith("M"):
            bearing += math.degrees(sun.declination)
        view = rotation @ np.array([0.0, 0.0, -1.0])
        result = y_bearing(bearing, view)
        return result, "" if result is not None else "The camera looks straight up or down: no north from its compass"
    w, h = solution.image_size
    co = calibrate.handle(settings, LANDMARK_KEY)
    direction = rotation @ ray((co[0] * w, co[1] * h), solution.principal_point, solution.focal_px)
    result = y_bearing(math.degrees(sun.landmark_bearing), direction)
    return result, "" if result is not None else "The landmark is straight above or below the camera: move it"


def evaluate(settings, solution=None) -> SunState:
    """Sun of the photo for ``settings``. Never writes: safe in draw callbacks."""
    state = SunState()
    data = settings.camera_data
    if solution is None:
        solution = calibrate.cached_solution(settings.id_data)
    try:
        when = shooting_time(data)
    except ValueError as exc:
        state.error = str(exc)
        return state
    if location_state(data) == "MISSING":
        state.error = "Place unknown: enter latitude and longitude (the nearest town is close enough)"
        return state
    state.utc = when
    state.sun = sun_position(when, data.gps_latitude, data.gps_longitude)
    if not state.sun.above_horizon:
        state.error = "The sun is below the horizon at that time: check date, time and UTC offset"
        return state
    if data.clock_mismatch:
        state.warnings.append("The GPS time and the camera clock disagree: check the time (GPS time used)")
    if (
        settings.sun.north_source == "COMPASS"
        and data.direction_ref.upper().startswith("M")
        and settings.sun.declination == 0.0
    ):
        state.warnings.append("Magnetic compass: enter the declination of the place")
    bearing, why = scene_north(settings, solution)
    if bearing is None:
        state.error = why
        return state
    state.y_bearing = (bearing + math.degrees(settings.sun.north_correction)) % 360.0
    state.direction = Vector(scene_direction(state.sun, state.y_bearing).tolist())
    return state


def north_vector(y_bear: float) -> Vector:
    """Scene direction of true north for a +Y bearing."""
    a = math.radians(-y_bear)
    return Vector((math.sin(a), math.cos(a), 0.0))


def orient(settings) -> SunState | None:
    """Turn the camera's Sun light towards the sun; its location and scale stay."""
    light = settings.sun.light
    if light is None:
        return None
    state = evaluate(settings)
    if state.direction is None:
        return state
    # A Sun light shines along its local -Z: +Z points at the sun.
    rot = state.direction.to_track_quat("Z", "Y")
    if light.parent is not None:
        rot = (light.parent.matrix_world @ light.matrix_parent_inverse).to_quaternion().inverted() @ rot
    # matrix_basis, not matrix_world: the latter lags behind a location just set.
    loc, _rot, scale = light.matrix_basis.decompose()
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
        context.collection.objects.link(obj)
        state = evaluate(settings)
        # Above the scene origin, towards the sun: the light's line points at the origin.
        origin = calibrate.alignment_matrix(settings).translation
        reach = max(1.0, 0.5 * settings.results.distance) if settings.results.valid else 5.0
        obj.location = origin + (state.direction or Vector((0.0, 0.0, 1.0))) * reach
        settings.sun.light = obj  # orients it
        if state.error:
            self.report({"WARNING"}, bpy.app.translations.pgettext_tip(state.error))
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
        image = settings.image
        path = bpy.path.abspath(settings.source_path or image.filepath)
        exif = ops_load.read_image_exif(image, path)
        ops_load.load_time_place(settings.camera_data, exif)
        settings_changed(settings.id_data, context)
        return {"FINISHED"}


classes = (FTC_OT_new_sun, FTC_OT_read_photo_time)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
