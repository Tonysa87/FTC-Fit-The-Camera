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

from . import calibrate, ops_sun

MANIFEST = os.path.join(os.path.dirname(__file__), "blender_manifest.toml")


def addon_version() -> str:
    try:
        with open(MANIFEST, "rb") as f:
            return tomllib.load(f).get("version", "")
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def _field(value, state):
    return {"value": round(value, 6) if isinstance(value, float) else value, "source": state}


def _deg(radians: float, digits: int = 3) -> float:
    return round(math.degrees(radians), digits)


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
        "units": {"system": scene.unit_settings.system, "scale_length": scene.unit_settings.scale_length},
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
        out["focal_mode"] = settings.focal_mode
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
        out["focal_mode"] = settings.focal_mode
        out["rectangle"] = {"plane": settings.ref_plane, "sides": [settings.rect_width, settings.rect_height]}
    else:
        out["camera_height"] = round(settings.camera_height, 6)
        out["yaw_from"] = settings.yaw_source
    out["reference_plane"] = calibrate.reference_plane(settings)
    if settings.use_anchor:
        out["aligned_to"] = settings.align_source
    return out


def results(settings, cam_obj) -> dict:
    res = settings.results
    if not res.valid:
        return {"valid": False, "error": res.error}
    m = cam_obj.matrix_world
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
        "location": [round(v, 6) for v in m.translation],
        "rotation_euler_xyz_deg": [_deg(a) for a in m.to_euler("XYZ")],
    }


def sun_report(settings, scene) -> dict | None:
    """The sun block, when Fit Sun is in use (a sun, a light or a shadow)."""
    sun = settings.sun
    data = settings.camera_data
    state = ops_sun.evaluate(settings)
    if state.direction is None and sun.light is None and not ops_sun.shadow_in_use(settings):
        return None
    out = {"from": sun.source}
    if sun.source == "TIME":
        out["local_time"] = _field(
            f"{data.year:04d}-{data.month:02d}-{data.day:02d} {data.hour:02d}:{data.minute:02d}:{data.second:02d}",
            data.time_state,
        )
        out["utc_offset_hours"] = _field(data.utc_offset, data.offset_state)
        if state.utc is not None:
            out["utc"] = state.utc.astimezone(UTC).isoformat()
        place = ops_sun.location_state(data)
        out["latitude"] = _field(data.gps_latitude, place)
        out["longitude"] = _field(data.gps_longitude, place)
        out["north_from"] = sun.north_source
        out["north_correction_deg"] = _deg(sun.north_correction)
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
            "vs_date_elevation_deg": state.shadow_elevation_offset,
            "vs_north_deg": state.shadow_north_offset,
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


def to_markdown(report: dict) -> str:
    """The report as a readable Markdown page."""
    lines = [f"# FTC calibration report: {report['camera']}", ""]
    lines.append(f"FTC {report['ftc_version']} · Blender {report['blender_version']} · {report['created']}")
    lines.append("")

    def table(title, rows):
        lines.extend([f"## {title}", "", "| | |", "| --- | --- |"])
        for key, value in rows.items():
            if isinstance(value, dict) and set(value) == {"value", "source"}:
                value = f"{value['value']} ({value['source']})"
            elif isinstance(value, dict):
                value = ", ".join(f"{k}: {v}" for k, v in value.items())
            elif isinstance(value, list):
                value = ", ".join(str(v) for v in value) if value else "—"
            elif value in ("", None):
                value = "—"
            lines.append(f"| {key.replace('_', ' ')} | {value} |")
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

    def invoke(self, context, event):
        cam = calibrate.view_camera(context)
        if not self.filepath:
            self.filepath = bpy.path.clean_name(cam.name) + "_ftc_report.md"
        return super().invoke(context, event)

    def execute(self, context):
        cam = calibrate.view_camera(context)
        report = build(cam, context.scene)
        path = bpy.path.ensure_ext(self.filepath, ".json" if self.format == "JSON" else ".md")
        text = json.dumps(report, indent=2, ensure_ascii=False) if self.format == "JSON" else to_markdown(report)
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
