# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibration state, stored on each camera data-block and saved in the .blend."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from . import calibrate

AXIS_ITEMS = [
    ("+X", "+X", "Positive X axis"),
    ("-X", "-X", "Negative X axis"),
    ("+Y", "+Y", "Positive Y axis"),
    ("-Y", "-Y", "Negative Y axis"),
    ("+Z", "+Z", "Positive Z axis"),
    ("-Z", "-Z", "Negative Z axis"),
]

FIELD_STATE_ITEMS = [
    ("MISSING", "Missing", "Not found in the image metadata"),
    ("EXIF", "From EXIF", "Read from the image metadata"),
    ("MANUAL", "Manual", "Entered by hand"),
]


def _changed(self, context):
    calibrate.settings_changed(self.id_data, context, reset_pitch=False)


def _guides_changed(self, context):
    calibrate.settings_changed(self.id_data, context, reset_pitch=True)


def _manual(field):
    """Update callback marking a camera data field as entered by hand."""

    def update(self, context):
        if not self.loading:
            setattr(self, field + "_state", "MANUAL")
            calibrate.settings_changed(self.id_data, context, reset_pitch=False)

    return update


class FTC_Handle(PropertyGroup):
    # ``name`` (inherited) is the handle key.
    co: FloatVectorProperty(name="Position", size=2, default=(0.5, 0.5), description="Normalised image position")


class FTC_CameraData(PropertyGroup):
    loading: BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    make: StringProperty(name="Make")
    model: StringProperty(name="Model")
    lens: StringProperty(name="Lens")
    image_width: IntProperty(name="Width", subtype="PIXEL", min=0)
    image_height: IntProperty(name="Height", subtype="PIXEL", min=0)
    orientation: IntProperty(name="Orientation", min=0, max=8, description="EXIF orientation (1 = upright)")

    focal_mm: FloatProperty(
        name="Focal Length",
        description="Real focal length of the lens",
        min=0.0,
        soft_max=1000.0,
        subtype="DISTANCE_CAMERA",
        unit="CAMERA",
        update=_manual("focal_mm"),
    )
    focal_mm_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")
    focal_35mm: FloatProperty(
        name="35 mm Equivalent",
        description="Focal length equivalent on a 36x24 mm frame",
        min=0.0,
        soft_max=1000.0,
        subtype="DISTANCE_CAMERA",
        unit="CAMERA",
        update=_manual("focal_35mm"),
    )
    focal_35mm_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")
    sensor_mm: FloatProperty(
        name="Sensor Width",
        description="Sensor size along the long side of the image",
        min=0.0,
        soft_max=100.0,
        subtype="DISTANCE_CAMERA",
        unit="CAMERA",
        update=_manual("sensor_mm"),
    )
    sensor_mm_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")

    has_gps: BoolProperty()
    gps_latitude: FloatProperty(name="Latitude", precision=6)
    gps_longitude: FloatProperty(name="Longitude", precision=6)
    gps_altitude: FloatProperty(name="Altitude", subtype="DISTANCE", unit="LENGTH")
    direction: FloatProperty(
        name="Direction",
        description="Compass bearing of the view, degrees clockwise from north",
        min=0.0,
        max=360.0,
        update=_manual("direction"),
    )
    direction_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")
    direction_ref: StringProperty(name="Direction Reference", description="T = true north, M = magnetic north")


class FTC_Results(PropertyGroup):
    valid: BoolProperty()
    error: StringProperty()
    warnings: StringProperty()
    focal_px: FloatProperty(name="Focal (px)")
    lens: FloatProperty(name="Focal Length", subtype="DISTANCE_CAMERA", unit="CAMERA")
    sensor: FloatProperty(name="Sensor", subtype="DISTANCE_CAMERA", unit="CAMERA")
    fov_h: FloatProperty(name="Horizontal FOV", subtype="ANGLE")
    fov_v: FloatProperty(name="Vertical FOV", subtype="ANGLE")
    height: FloatProperty(name="Camera Height", subtype="DISTANCE", unit="LENGTH")
    distance: FloatProperty(name="Distance to Origin", subtype="DISTANCE", unit="LENGTH")
    pitch: FloatProperty(name="Pitch", subtype="ANGLE")
    roll: FloatProperty(name="Roll", subtype="ANGLE")
    yaw: FloatProperty(name="Yaw", subtype="ANGLE")
    focal_error: FloatProperty(name="Focal Uncertainty", subtype="FACTOR")
    angle_error: FloatProperty(name="Angle Uncertainty")
    focal_solved: BoolProperty()
    removed_roll: FloatProperty(name="Removed Roll", subtype="ANGLE")


class FTC_Settings(PropertyGroup):
    image: PointerProperty(name="Image", type=bpy.types.Image)
    source_path: StringProperty(name="Source", subtype="FILE_PATH", description="Original image file")

    mode: EnumProperty(
        name="Mode",
        description="What in the image defines the camera",
        items=[
            ("VP", "Vanishing Points", "Calibrate from parallel lines converging to 1, 2 or 3 vanishing points"),
            ("RECT", "Known Rectangle", "Calibrate from the four corners of a rectangle of known size"),
            ("HORIZON", "Horizon", "Calibrate from the horizon line and the camera height"),
        ],
        default="VP",
        update=_guides_changed,
    )
    vp_count: EnumProperty(
        name="Vanishing Points",
        description="Number of vanishing points to draw",
        items=[
            ("1", "1", "One vanishing point: needs the focal length and the horizon direction"),
            ("2", "2", "Two vanishing points: solves the focal length"),
            ("3", "3", "Three vanishing points: solves focal length and principal point"),
        ],
        default="2",
        update=_guides_changed,
    )
    vp1_axis: EnumProperty(
        name="Vanishing Point 1",
        description="World axis of the first guide pair (the sign says which way it runs, away from the camera)",
        items=AXIS_ITEMS,
        default="+X",
        update=_guides_changed,
    )
    vp2_axis: EnumProperty(
        name="Vanishing Point 2",
        description="World axis of the second guide pair, or of the axis line with one vanishing point",
        items=AXIS_ITEMS,
        default="+Y",
        update=_guides_changed,
    )
    vp3_axis: EnumProperty(
        name="Vanishing Point 3",
        description="World axis of the third guide pair (follows from the first two)",
        items=AXIS_ITEMS,
        default="+Z",
        update=_guides_changed,
    )
    active_vp: IntProperty(default=0, min=0, max=2, options={"HIDDEN"})
    handles: CollectionProperty(type=FTC_Handle)

    scale_mode: EnumProperty(
        name="Scale",
        description="How the real-world size of the scene is set",
        items=[
            ("DISTANCE", "Camera Distance", "Distance from the camera to the origin"),
            ("REFERENCE", "Reference Distance", "A known length along an axis, starting from the origin line"),
        ],
        default="DISTANCE",
        update=_changed,
    )
    camera_distance: FloatProperty(
        name="Camera Distance",
        description="Distance from the camera to the origin handle",
        default=10.0,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )
    ref_axis: EnumProperty(
        name="Reference Axis",
        description="Axis along which the reference distance is measured",
        items=[("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")],
        default="X",
        update=_changed,
    )
    ref_length: FloatProperty(
        name="Reference Length",
        description="Real length between the two reference handles",
        default=1.0,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )

    rect_width: FloatProperty(
        name="Width",
        description="Real length of the rectangle's first edge (corner 1 to 2)",
        default=1.0,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )
    rect_height: FloatProperty(
        name="Height",
        description="Real length of the rectangle's second edge (corner 2 to 3)",
        default=1.0,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )
    use_known_focal: BoolProperty(
        name="Use Known Focal Length",
        description=(
            "Use the focal length from the camera data instead of solving it: the guides then only set the "
            "orientation, which is much more stable when a vanishing point is far away"
        ),
        default=False,
        update=_changed,
    )
    use_third_line: BoolProperty(
        name="Third Axis Line",
        description=(
            "With two vanishing points, add one line along the third axis (e.g. a vertical edge): it joins "
            "the calibration and keeps that axis on the image"
        ),
        default=False,
        update=_guides_changed,
    )

    camera_height: FloatProperty(
        name="Camera Height",
        description="Height of the camera above the ground",
        default=1.6,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )
    yaw_source: EnumProperty(
        name="Yaw",
        description="Where the camera heading comes from",
        items=[("EXIF", "From EXIF", "Use the image direction from GPS metadata"), ("MANUAL", "Manual", "")],
        default="EXIF",
        update=_changed,
    )
    yaw: FloatProperty(
        name="Yaw",
        description="Heading of the camera, clockwise from +Y",
        subtype="ANGLE",
        update=_changed,
    )

    pp_mode: EnumProperty(
        name="Principal Point",
        description="Point of the image hit by the optical axis",
        items=[
            ("CENTER", "Center", "Principal point at the image centre"),
            ("MANUAL", "Manual", "Drag the principal point in the viewport"),
            (
                "SOLVE",
                "Solve",
                "Three vanishing points only: solve it as their orthocentre (unstable when one is far away)",
            ),
        ],
        default="CENTER",
        update=_changed,
    )
    straighten: BoolProperty(name="Straighten Horizon", description="Force zero roll", default=False, update=_changed)
    pitch_offset: FloatProperty(
        name="Pitch Correction",
        description="Manual tilt from the horizon handle; reset when the guides change",
        subtype="ANGLE",
        update=_changed,
    )

    live: BoolProperty(
        name="Live Update",
        description="Write the camera on every change while calibrating",
        default=True,
        update=_changed,
    )
    freeze: BoolProperty(name="Freeze Guides", description="Lock the guides against accidental edits")
    show_grid: BoolProperty(name="Grid", description="Show the verification grid on the reference plane", default=True)
    grid_opacity: FloatProperty(
        name="Grid Opacity",
        description="Opacity of the verification grid",
        default=0.6,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )

    ref_plane: EnumProperty(
        name="Reference Plane",
        description="Calibrated plane used for the rectangle, the grid and the scene alignment",
        items=[
            ("XY", "XY", "Floor or any horizontal plane"),
            ("XZ", "XZ", "Wall facing -Y, with Z up"),
            ("YZ", "YZ", "Wall facing +X, with Z up"),
        ],
        default="XY",
        update=_guides_changed,
    )
    use_anchor: BoolProperty(
        name="Align to Scene",
        description="Place the reference plane on the stored scene target (3D cursor, face or object)",
        update=_changed,
    )
    # Scene target frame: origin, x axis, y axis and normal of the target plane.
    anchor_matrix: FloatVectorProperty(size=(4, 4), subtype="MATRIX")
    align_source: StringProperty(name="Aligned To", description="Scene target of the alignment")
    align_rotation: IntProperty(
        name="Rotation",
        description="Quarter turns of the reference plane about its normal on the target",
        min=0,
        max=3,
        update=_changed,
    )
    align_flip: BoolProperty(name="Flip", description="Turn the reference plane over on the target", update=_changed)

    camera_data: PointerProperty(type=FTC_CameraData)
    results: PointerProperty(type=FTC_Results)


classes = (FTC_Handle, FTC_CameraData, FTC_Results, FTC_Settings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Camera.ftc = PointerProperty(type=FTC_Settings)


def unregister():
    del bpy.types.Camera.ftc
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
