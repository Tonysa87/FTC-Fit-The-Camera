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

# Context of the generic words (Map, Light, Time...): translated only for FTC.
FTC_CONTEXT = "FTC"

FIELD_STATE_ITEMS = [
    ("MISSING", "Missing", "Not found in the image metadata"),
    ("EXIF", "From EXIF", "Read from the image metadata"),
    ("MANUAL", "Manual", "Entered by hand"),
]


def _changed(self, context):
    calibrate.settings_changed(self.id_data, context, reset_pitch=False)


def _guides_changed(self, context):
    calibrate.settings_changed(self.id_data, context, reset_pitch=True)


def _scale_mode_changed(self, context):
    # The cached solution is still the one before the change: the new scale
    # source is seeded from it, so the scene keeps its size.
    calibrate.seed_cube(self.id_data)
    calibrate.seed_reference(self.id_data)
    calibrate.settings_changed(self.id_data, context, reset_pitch=False)


def _plane_changed(self, context):
    calibrate.seed_cube(self.id_data)
    calibrate.settings_changed(self.id_data, context, reset_pitch=True)
    if self.use_anchor and calibrate.session_camera is None:
        # Aligned to a target: the camera moves at once, like Rotate 90° and Flip.
        cam = calibrate.view_camera(context)
        if cam is not None and cam.data == self.id_data:
            calibrate.update(context, cam, apply=True)


def _third_axis_changed(self, context):
    # The cached solution is still the one before the change: seed from it.
    calibrate.seed_third_axis(self.id_data)
    calibrate.settings_changed(self.id_data, context, reset_pitch=True)


def _manual(field):
    """Update callback marking a camera data field as entered by hand."""

    def update(self, context):
        if not self.loading:
            setattr(self, field + "_state", "MANUAL")
            calibrate.settings_changed(self.id_data, context, reset_pitch=False)

    return update


def _manual_time(self, context):
    if not self.loading:
        self.time_state = "MANUAL"
        self.clock_mismatch = False  # the user has checked the time
        _sun_changed(self, context)


def _manual_offset(self, context):
    if not self.loading:
        self.offset_state = "MANUAL"
        self.clock_mismatch = False
        _sun_changed(self, context)


def _direction_changed(self, context):
    # The compass direction sets the camera yaw (horizon) and the sun's north.
    _manual("direction")(self, context)
    if not self.loading:
        _sun_changed(self, context)


def _manual_location(self, context):
    if not self.loading:
        self.location_state = "MANUAL"
        _sun_changed(self, context)


def _sun_changed(self, context):
    from . import ops_sun

    ops_sun.settings_changed(self.id_data, context)


def _hdri_follow_changed(self, context):
    if self.hdri_fitted and not calibrate.updating():
        from . import ops_hdri, ops_sun

        # Taken over again: from the Mapping's present turn.
        ops_hdri.follow(self.id_data.ftc, context.scene, ops_sun.evaluate(self.id_data.ftc), force=True)


def _is_sun_light(self, obj):
    return obj.type == "LIGHT" and obj.data.type == "SUN"


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
        description="Long side of the camera sensor, as in its specifications (for cropped photos too)",
        min=0.0,
        soft_max=100.0,
        subtype="DISTANCE_CAMERA",
        unit="CAMERA",
        update=_manual("sensor_mm"),
    )
    sensor_mm_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")

    has_gps: BoolProperty()
    gps_latitude: FloatProperty(
        name="Latitude",
        translation_context=FTC_CONTEXT,
        description="Where the photo was taken, degrees north (negative south); a city is close enough for the sun",
        min=-90.0,
        max=90.0,
        precision=6,
        update=_manual_location,
    )
    gps_longitude: FloatProperty(
        name="Longitude",
        translation_context=FTC_CONTEXT,
        description="Where the photo was taken, degrees east (negative west); a city is close enough for the sun",
        min=-180.0,
        max=180.0,
        precision=6,
        update=_manual_location,
    )
    # 1.0 files have has_gps but no state: ops_sun.location_state() reads both.
    location_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")
    gps_altitude: FloatProperty(name="Altitude", subtype="DISTANCE", unit="LENGTH")
    direction: FloatProperty(
        name="Direction",
        description="Compass bearing of the view, degrees clockwise from north",
        min=0.0,
        max=360.0,
        update=_direction_changed,
    )
    direction_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")
    direction_ref: StringProperty(name="Direction Reference", description="T = true north, M = magnetic north")

    # Shooting time: local date and time with its UTC offset (UTC itself, offset
    # 0, when only the GPS time is known).
    year: IntProperty(
        name="Year",
        translation_context=FTC_CONTEXT,
        description="Year of the shot",
        min=1900,
        max=2100,
        default=2000,
        update=_manual_time,
    )
    month: IntProperty(
        name="Month",
        translation_context=FTC_CONTEXT,
        description="Month of the shot",
        min=1,
        max=12,
        default=1,
        update=_manual_time,
    )
    day: IntProperty(
        name="Day",
        translation_context=FTC_CONTEXT,
        description="Day of the shot",
        min=1,
        max=31,
        default=1,
        update=_manual_time,
    )
    hour: IntProperty(
        name="Hour",
        translation_context=FTC_CONTEXT,
        description="Local hour of the shot",
        min=0,
        max=23,
        default=12,
        update=_manual_time,
    )
    minute: IntProperty(
        name="Minute",
        translation_context=FTC_CONTEXT,
        description="Minute of the shot",
        min=0,
        max=59,
        update=_manual_time,
    )
    second: IntProperty(
        name="Second",
        translation_context=FTC_CONTEXT,
        description="Second of the shot",
        min=0,
        max=59,
        update=_manual_time,
    )
    time_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")
    utc_offset: FloatProperty(
        name="UTC Offset",
        translation_context=FTC_CONTEXT,
        description="Time zone of the local time, daylight saving included (e.g. +2 for Italy in summer)",
        min=-12.0,
        max=14.0,
        step=25,
        precision=2,
        update=_manual_offset,
    )
    offset_state: EnumProperty(items=FIELD_STATE_ITEMS, default="MISSING")
    time_from_gps: BoolProperty(description="The time is the GPS time (UTC) of the photo")
    clock_mismatch: BoolProperty(description="The GPS time and the camera clock disagree")


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
    # Solved focal length / known one - 1, with "Known + Guides"; 0 otherwise.
    focal_shift: FloatProperty()
    removed_roll: FloatProperty(name="Removed Roll", subtype="ANGLE")
    guide_misfit: FloatProperty(name="Guide Fit", subtype="ANGLE")


class FTC_Sun(PropertyGroup):
    """Sun of the photo: where the scene north is and which light follows it."""

    source: EnumProperty(
        name="Sun From",
        translation_context=FTC_CONTEXT,
        description="Where the direction of the sun comes from",
        items=[
            ("TIME", "Date and Place", "Computed from the date, time and place of the shot, with the scene north"),
            ("SHADOW", "Shadow", "Measured on a shadow in the photo: no date, place or north needed"),
        ],
        default="TIME",
        update=_sun_changed,
    )
    use_shadow: BoolProperty(
        name="Check with a Shadow",
        translation_context=FTC_CONTEXT,
        description=(
            "Show the shadow handles (foot and top of something vertical, tip of its shadow) to check the north "
            "and the sun's height: the × marks where the Fit Sun sun puts the shadow tip"
        ),
        update=_sun_changed,
    )
    shadow_plane: EnumProperty(
        name="Shadow On",
        translation_context=FTC_CONTEXT,
        description="Plane through the origin where the tip of the shadow lies (the foot is always on the ground)",
        items=[
            ("XY", "Ground", "The ground: plane XY through the origin"),
            ("XZ", "Wall XZ", "The wall XZ through the origin: put the origin where the wall meets the ground"),
            ("YZ", "Wall YZ", "The wall YZ through the origin: put the origin where the wall meets the ground"),
        ],
        default="XY",
        update=_sun_changed,
    )

    light: PointerProperty(
        name="Light",
        translation_context=FTC_CONTEXT,
        description="Sun light that FTC turns towards the sun of the photo (only its rotation is changed)",
        type=bpy.types.Object,
        poll=_is_sun_light,
        update=_sun_changed,
    )
    north_source: EnumProperty(
        name="North",
        translation_context=FTC_CONTEXT,
        description="How the sun is placed around the scene (its height comes from the date)",
        items=[
            ("COMPASS", "Compass", "From the compass direction of the photo (EXIF), rarely written by Android phones"),
            # MAP and LANDMARK: 1.1 development builds only, read as SIDE (enum
            # items are stored by index: never remove or reorder them).
            ("MAP", "Map", "Replaced by Side"),
            ("LANDMARK", "Landmark", "Replaced by Side"),
            (
                "SHADOW",
                "Shadow",
                "From a shadow in the photo (shadow handles in Calibrate Shadow) and the sun of the date and place",
            ),
            (
                "SIDE",
                "Side",
                "Pick the scene axis the sun comes from, then turn it by eye until the CG shadows match the photo",
            ),
        ],
        default="SIDE",
        update=_sun_changed,
    )
    sun_side: EnumProperty(
        name="Sun From Axis",
        translation_context=FTC_CONTEXT,
        description=(
            "Scene axis the sun comes from: the shadows in the photo fall the other way "
            "(-Y is usually behind the camera)"
        ),
        items=[
            ("+X", "+X", "The sun comes from the +X side"),
            ("-X", "-X", "The sun comes from the -X side"),
            ("+Y", "+Y", "The sun comes from the +Y side"),
            ("-Y", "-Y", "The sun comes from the -Y side"),
        ],
        default="-Y",
        update=_sun_changed,
    )
    declination: FloatProperty(
        name="Declination",
        translation_context=FTC_CONTEXT,
        description=(
            "Magnetic declination at the place, east positive: added to a magnetic compass direction "
            "(look it up for the place and year)"
        ),
        subtype="ANGLE",
        soft_min=-0.6,
        soft_max=0.6,
        update=_sun_changed,
    )
    north_correction: FloatProperty(
        name="North Correction",
        translation_context=FTC_CONTEXT,
        description=(
            "Turns the sun about the vertical (with the compass: the scene north): adjust it until the CG "
            "shadows match the photo; phone compasses are often 5-15° off"
        ),
        subtype="ANGLE",
        soft_min=-3.141592653589793,
        soft_max=3.141592653589793,
        update=_sun_changed,
    )
    elevation_correction: FloatProperty(
        name="Elevation Correction",
        translation_context=FTC_CONTEXT,
        description=(
            "Raises (or lowers) the sun from the height of the date and time: adjust it until the CG "
            "shadows are as long as in the photo (it makes up for small calibration and clock errors)"
        ),
        subtype="ANGLE",
        soft_min=-0.17453292519943295,
        soft_max=0.17453292519943295,
        update=_sun_changed,
    )
    # Fit HDRI: the sun's point on the World HDRI, kept on the sun when it moves.
    hdri_point: FloatVectorProperty(
        size=2,
        description="Point of the sun on the HDRI picked by Fit HDRI (0..1, origin bottom-left)",
    )
    hdri_image: StringProperty(description="HDRI image fitted by Fit HDRI")
    hdri_angle: FloatProperty(description="Z turn last given to the HDRI by FTC (radians)")
    hdri_fitted: BoolProperty(
        name="Follow the Sun",
        translation_context=FTC_CONTEXT,
        description=(
            "Keep the World HDRI on the sun when the sun moves (north, time). Fit HDRI turns it on; turning the "
            "HDRI's Mapping by hand turns it off"
        ),
        update=_hdri_follow_changed,
    )
    show_north: BoolProperty(
        name="North",
        translation_context=FTC_CONTEXT,
        description="Show the scene north and the sun direction on the ground through the origin while calibrating",
        default=False,
    )


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
        update=_third_axis_changed,
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
    vp1_lines: IntProperty(
        name="Lines",
        translation_context=FTC_CONTEXT,
        description="Guide lines of vanishing point 1 (2 to 6): more lines average out the placement errors",
        min=2,
        max=6,
        default=2,
        update=_guides_changed,
    )
    vp2_lines: IntProperty(
        name="Lines",
        translation_context=FTC_CONTEXT,
        description="Guide lines of vanishing point 2 (2 to 6): more lines average out the placement errors",
        min=2,
        max=6,
        default=2,
        update=_guides_changed,
    )
    vp3_lines: IntProperty(
        name="Lines",
        translation_context=FTC_CONTEXT,
        description="Guide lines of vanishing point 3 (2 to 6): more lines average out the placement errors",
        min=2,
        max=6,
        default=2,
        update=_guides_changed,
    )
    active_vp: IntProperty(default=0, min=0, max=2, options={"HIDDEN"})
    handles: CollectionProperty(type=FTC_Handle)

    scale_mode: EnumProperty(
        name="Scale",
        description="How the real-world size of the scene is set",
        items=[
            (
                "CUBE",
                "Scale Cube",
                "A cube of known size standing on the reference plane: drag its top handle until it matches "
                "something of that height in the photo",
            ),
            (
                "REFERENCE",
                "Reference Distance",
                "A known length between two points of a plane (Measured On), or a height above it",
            ),
        ],
        default="CUBE",
        update=_scale_mode_changed,
    )
    cube_size: EnumProperty(
        name="Cube Size",
        description="Edge length of the scale cube",
        items=[
            ("0.1", "10 cm", "Cube edge of 10 cm"),
            ("0.2", "20 cm", "Cube edge of 20 cm"),
            ("0.5", "50 cm", "Cube edge of 50 cm"),
            ("1", "1 m", "Cube edge of 1 m"),
            ("2", "2 m", "Cube edge of 2 m"),
            ("5", "5 m", "Cube edge of 5 m"),
            ("10", "10 m", "Cube edge of 10 m"),
            ("CUSTOM", "Custom Size", "Enter the edge length"),
        ],
        default="1",
        update=_changed,
    )
    cube_custom: FloatProperty(
        name="Custom Size",
        description="Edge length of the scale cube",
        default=1.0,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )
    show_cube: BoolProperty(
        name="Scale Cube",
        description=(
            "Show the cube of known size on the reference plane, to check the scale by eye "
            "(known rectangle and horizon)"
        ),
        default=False,
        update=_changed,
    )
    ref_axis: EnumProperty(
        name="Reference Axis",
        description=(
            "Direction of the reference distance: along the reference plane both ends lie on the plane, "
            "anywhere on it; along its normal it is a height above the first end"
        ),
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
    ref_measure_plane: EnumProperty(
        name="Measured On",
        description=(
            "Plane through the origin that holds the reference distance: both ends along an axis of it, "
            "or a height along its normal from the first end"
        ),
        items=[
            ("XY", "XY", "Floor or any horizontal plane"),
            ("XZ", "XZ", "Wall facing -Y, with Z up"),
            ("YZ", "YZ", "Wall facing +X, with Z up"),
        ],
        default="XY",
        update=_changed,
    )

    rect_width: FloatProperty(
        name="First Side",
        description="Real length of the rectangle's first side (corner 1 to 2), along the "
        "reference plane's first axis: X on XY and XZ, Y on YZ",
        default=1.0,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )
    rect_height: FloatProperty(
        name="Second Side",
        description="Real length of the rectangle's second side (corner 2 to 3), along the "
        "reference plane's second axis: Y on XY, Z on XZ and YZ",
        default=1.0,
        min=1e-4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_changed,
    )
    focal_mode: EnumProperty(
        name="Focal Length",
        description="Where the focal length comes from (vanishing points and rectangle)",
        items=[
            (
                "AUTO",
                "Known + Guides",
                "Start from the focal length in Camera Data and let the guides correct it as far as they "
                "measure it; when it is unknown, solve it from the guides",
            ),
            ("SOLVE", "Guides Only", "Solve the focal length from the guides, ignoring Camera Data"),
            (
                "KNOWN",
                "Known Only",
                "Use the focal length in Camera Data as it is: the guides only set the orientation",
            ),
        ],
        default="AUTO",
        update=_changed,
    )
    use_third_line: BoolProperty(
        name="Third Axis Line",
        description=(
            "With two vanishing points, add one line along the third axis (e.g. a vertical edge): it joins "
            "the calibration and keeps that axis on the image"
        ),
        default=False,
        update=_third_axis_changed,
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
        description="Calibrated plane used for the rectangle, the grid, the scale cube and the scene alignment",
        items=[
            ("XY", "XY", "Floor or any horizontal plane"),
            ("XZ", "XZ", "Wall facing -Y, with Z up"),
            ("YZ", "YZ", "Wall facing +X, with Z up"),
        ],
        default="XY",
        update=_plane_changed,
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
    sun: PointerProperty(type=FTC_Sun)


classes = (FTC_Handle, FTC_CameraData, FTC_Results, FTC_Sun, FTC_Settings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Camera.ftc = PointerProperty(type=FTC_Settings)


def unregister():
    del bpy.types.Camera.ftc
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
