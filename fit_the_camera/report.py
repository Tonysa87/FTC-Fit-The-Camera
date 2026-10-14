# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibration report: what FTC found and where each input came from, as a
dictionary saved as JSON or Markdown (Export Report in Results)."""

from __future__ import annotations

import json
import math
import os
import tomllib
from datetime import UTC, datetime

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper
from mathutils import Matrix

from . import calibrate, ops_sun

MANIFEST = os.path.join(os.path.dirname(__file__), "blender_manifest.toml")


def addon_version() -> str:
    try:
        with open(MANIFEST, "rb") as f:
            return tomllib.load(f).get("version", "")
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def _num(value, digits: int = 6):
    """A float rounded for reading (float32 noise, -0.0 gone); others unchanged."""
    if isinstance(value, float):
        return round(value, digits) + 0.0
    return value


def _field(value, state):
    return {"value": _num(value), "source": state}


def _deg(radians: float, digits: int = 3) -> float:
    return round(math.degrees(radians), digits) + 0.0


def build(cam_obj, scene) -> dict:
    """Everything worth keeping about the calibration of ``cam_obj``."""
    settings = cam_obj.data.ftc
    data = settings.camera_data
    report = {
        "ftc_version": addon_version(),
        "blender_version": bpy.app.version_string,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "camera": cam_obj.name,
        "image": {
            "name": settings.image.name if settings.image else "",
            "file": os.path.basename(bpy.path.abspath(settings.source_path)) if settings.source_path else "",
            "width": data.image_width,
            "height": data.image_height,
        },
        "units": {"system": scene.unit_settings.system, "scale_length": _num(scene.unit_settings.scale_length)},
        "camera_data": {
            "make": data.make,
            "model": data.model,
            "lens": data.lens,
            "focal_mm": _field(data.focal_mm, data.focal_mm_state),
            "focal_35mm": _field(data.focal_35mm, data.focal_35mm_state),
            "sensor_mm": _field(data.sensor_mm, data.sensor_mm_state),
            "compass_direction_deg": _field(data.direction, data.direction_state),
        },
        "calibration": calibration(settings),
        "results": results(settings, cam_obj),
    }
    sun = sun_report(settings, scene)
    if sun is not None:
        report["sun"] = sun
    return report


def calibration(settings) -> dict:
    out = {"mode": settings.mode, "principal_point": settings.pp_mode, "straighten_horizon": settings.straighten}
    if settings.mode == "VP":
        count = int(settings.vp_count)
        out["vanishing_points"] = count
        out["axes"] = [settings.vp1_axis, settings.vp2_axis, settings.vp3_axis][: max(count, 2)]
        out["lines_per_vanishing_point"] = [calibrate.line_count(settings, i) for i in range(1, count + 1)]
        out["third_axis_line"] = count == 2 and settings.use_third_line
        out["focal"] = calibrate.focal_source(settings)
        if settings.scale_mode == "CUBE":
            out["scale"] = {"from": "SCALE_CUBE", "size": round(calibrate.cube_size(settings), 6)}
        else:
            out["scale"] = {
                "from": "REFERENCE_DISTANCE",
                "length": round(settings.ref_length, 6),
                "axis": settings.ref_axis,
                "measured_on": settings.ref_measure_plane,
            }
    elif settings.mode == "RECT":
        out["focal"] = calibrate.focal_source(settings)
        out["rectangle"] = {
            "plane": settings.ref_plane,
            "sides": [_num(settings.rect_width), _num(settings.rect_height)],
        }
    else:
        out["camera_height"] = _num(settings.camera_height)
        compass = settings.yaw_source == "EXIF" and settings.camera_data.direction_state != "MISSING"
        out["yaw"] = _field(
            _num(settings.camera_data.direction if compass else math.degrees(settings.yaw)),
            "EXIF" if compass else "MANUAL",
        )
    out["reference_plane"] = calibrate.reference_plane(settings)
    if settings.use_anchor:
        out["aligned_to"] = settings.align_source
    return out


def results(settings, cam_obj) -> dict:
    res = settings.results
    if not res.valid:
        return {"valid": False, "error": res.error}
    # The pose of the calibration (what Apply writes), not the camera object's,
    # which changes only on Apply or in a session (or by animation).
    solution = calibrate.current_solution(cam_obj.data)
    if solution is None:
        return {"valid": False, "error": res.error}
    bc = calibrate.to_blender(solution, calibrate.image_sensor_mm(settings))
    m = calibrate.alignment_matrix(settings) @ Matrix(bc.matrix_world.tolist())
    applied = all(abs(a - b) < 1e-4 for ra, rb in zip(m, cam_obj.matrix_world) for a, b in zip(ra, rb))
    return {
        "valid": True,
        "warnings": [w for w in res.warnings.splitlines() if w],
        "focal_mm": round(res.lens, 4),
        "focal_px": round(res.focal_px, 3),
        "sensor_mm": round(res.sensor, 4),
        "fov_deg": [_deg(res.fov_h), _deg(res.fov_v)],
        "focal_uncertainty_percent": round(100.0 * res.focal_error, 3) if res.focal_solved else None,
        "angle_uncertainty_deg": round(res.angle_error, 3),
        "guide_fit_deg": _deg(res.guide_misfit),
        "camera_height": round(res.height, 6),
        "distance_to_origin": round(res.distance, 6),
        "pitch_deg": _deg(res.pitch),
        "roll_deg": _deg(res.roll),
        "yaw_deg": _deg(res.yaw),
        "location": [_num(v) for v in m.translation],
        "rotation_euler_xyz_deg": [_deg(a) for a in m.to_euler("XYZ")],
        "applied_to_camera": applied,
    }


def sun_report(settings, scene) -> dict | None:
    """The sun block, only when Fit Sun is in use (a light, a fitted HDRI or a
    shadow): the place of the shot is not written for photos that merely carry
    GPS in their EXIF."""
    sun = settings.sun
    data = settings.camera_data
    if sun.light is None and not sun.hdri_image and not ops_sun.shadow_in_use(settings):
        return None
    state = ops_sun.evaluate(settings)
    out = {"from": sun.source}
    if sun.source == "TIME":
        out["local_time"] = _field(
            f"{data.year:04d}-{data.month:02d}-{data.day:02d} {data.hour:02d}:{data.minute:02d}:{data.second:02d}",
            data.time_state,
        )
        out["utc_offset_hours"] = _field(_num(data.utc_offset, 2), data.offset_state)
        if state.utc is not None:
            out["utc"] = state.utc.astimezone(UTC).isoformat()
        place = ops_sun.location_state(data)
        out["latitude"] = _field(data.gps_latitude, place)
        out["longitude"] = _field(data.gps_longitude, place)
        out["north_from"] = sun.north_source
        out["north_correction_deg"] = _deg(sun.north_correction)
        out["elevation_correction_deg"] = _deg(sun.elevation_correction)
    if state.sun is not None:
        out["azimuth_deg"] = round(state.sun.azimuth, 3)
        out["elevation_deg"] = round(state.sun.elevation, 3)
    if state.y_bearing is not None:
        out["scene_y_bearing_deg"] = round(state.y_bearing, 3)
    if state.direction is not None:
        out["direction_in_scene"] = [round(v, 6) for v in state.direction]
    if state.shadow is not None:
        out["shadow"] = {
            "plane": sun.shadow_plane,
            "elevation_deg": round(ops_sun.elevation_of(state.shadow), 3),
            "spread_deg": round(state.shadow_spread, 3) if math.isfinite(state.shadow_spread) else None,
            "vs_date_elevation_deg": _num(state.shadow_elevation_offset, 3),
            "vs_north_deg": _num(state.shadow_north_offset, 3),
        }
    if state.error:
        out["error"] = state.error
    if state.warnings:
        out["warnings"] = list(state.warnings)
    if sun.light is not None:
        out["light"] = sun.light.name
    if sun.hdri_image:
        out["hdri"] = {
            "image": sun.hdri_image,
            "sun_point_uv": [round(v, 5) for v in sun.hdri_point],
            "rotation_z_deg": _deg(sun.hdri_angle),
            "follows_the_sun": sun.hdri_fitted,
        }
    return out


def _cell(value) -> str:
    """Text safe inside a Markdown table cell."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def to_markdown(report: dict) -> str:
    """The report as a readable Markdown page."""
    lines = [f"# FTC calibration report: {_cell(report['camera'])}", ""]
    lines.append(f"FTC {report['ftc_version']} · Blender {report['blender_version']} · {report['created']}")
    lines.append("")

    def table(title, rows):
        lines.extend([f"## {title}", "", "| | |", "| --- | --- |"])
        for key, value in rows.items():
            if isinstance(value, dict) and set(value) == {"value", "source"}:
                value = f"{value['value']} ({value['source']})"
            elif isinstance(value, dict):
                value = ", ".join(f"{k}: {v}" for k, v in value.items())
            elif key == "warnings" and isinstance(value, list):
                value = "<br>".join(str(v) for v in value) if value else "—"
            elif isinstance(value, list):
                value = ", ".join(str(v) for v in value) if value else "—"
            elif value in ("", None):
                value = "—"
            lines.append(f"| {key.replace('_', ' ')} | {_cell(value)} |")
        lines.append("")

    table("Image", report["image"])
    table("Camera data", report["camera_data"])
    table("Calibration", report["calibration"])
    table("Results", report["results"])
    if "sun" in report:
        table("Sun", report["sun"])
    lines.append(f"Lengths in scene units ({report['units']['system']}, scale {report['units']['scale_length']}).")
    return "\n".join(lines) + "\n"


class FTC_OT_export_report(Operator, ExportHelper):
    bl_description = (
        "Save the calibration report: focal length, sensor, field of view, camera position and rotation, "
        "accuracy, guide fit, the source of every input and the sun, as Markdown or JSON"
    )
    bl_idname = "ftc.export_report"
    bl_label = "Export Report"

    filename_ext = ".md"
    filter_glob: StringProperty(default="*.md;*.json", options={"HIDDEN"})
    format: EnumProperty(
        name="Format",
        description="File format of the report",
        items=[
            ("MARKDOWN", "Markdown", "A readable page (.md)"),
            ("JSON", "JSON", "Data for other programs (.json)"),
        ],
        default="MARKDOWN",
    )

    @classmethod
    def poll(cls, context):
        cam = calibrate.view_camera(context)
        return cam is not None and cam.data.ftc.image is not None

    def check(self, context):
        # Keep the extension in step with the format.
        self.filename_ext = ".json" if self.format == "JSON" else ".md"
        return super().check(context)

    def _ext(self) -> str:
        return ".json" if self.format == "JSON" else ".md"

    def invoke(self, context, event):
        cam = calibrate.view_camera(context)
        self.filename_ext = self._ext()
        if not self.filepath:
            name = bpy.path.clean_name(cam.name) + "_ftc_report" + self._ext()
            folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
            self.filepath = os.path.join(folder, name) if folder else name
        return super().invoke(context, event)

    def execute(self, context):
        cam = calibrate.view_camera(context)
        report = build(cam, context.scene)
        root, ext = os.path.splitext(self.filepath)
        path = (root if ext.lower() in (".md", ".json") else self.filepath) + self._ext()
        try:
            text = (
                json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
                if self.format == "JSON"
                else to_markdown(report)
            )
        except ValueError as exc:  # a NaN or infinity would be invalid JSON
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, bpy.app.translations.pgettext_tip("Report saved: {}").format(path))
        return {"FINISHED"}


classes = (FTC_OT_export_report,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
