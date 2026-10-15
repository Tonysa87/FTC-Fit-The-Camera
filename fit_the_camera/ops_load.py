# SPDX-License-Identifier: GPL-3.0-or-later
"""Load the reference image into a camera and read its EXIF data."""

import os
import tempfile

import bpy
import numpy as np
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from . import calibrate
from .exif import read_exif

IMAGE_GLOB = "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.webp;*.bmp;*.tga;*.exr;*.hdr;*.jp2;*.dpx;*.cin"
NEW = "NEW"
GENERIC_NAME = "FTC Camera"

# Blender keeps only pointers to the strings of dynamic enum items: hold them here.
_camera_items: list = []
_photo_camera_items: list = []


def target_camera(context):
    """Active camera object, else the view/scene camera (``None`` without one)."""
    obj = context.active_object
    if obj is not None and obj.type == "CAMERA" and obj.name in context.scene.objects:
        return obj
    return calibrate.view_camera(context)


def default_camera(context) -> str:
    """Camera proposed for a new photo: the one in use while it has no photo yet,
    otherwise a new camera, so that no calibration is replaced by mistake."""
    cam = target_camera(context)
    if cam is not None and cam.data.ftc.image is None and cam.name in context.scene.objects:
        return cam.name
    return NEW


def _scene_cameras(context):
    scene = getattr(context, "scene", None)
    return sorted((o for o in scene.objects if o.type == "CAMERA"), key=lambda o: o.name) if scene else []


def _camera_label(obj) -> str:
    image = obj.data.ftc.image
    return f"{obj.name}  ·  {image.name}" if image is not None else f"{obj.name}  ({iface_('no photo')})"


def camera_items(_self, context):
    items = [(NEW, "New Camera", "Create a new camera for the photo", "ADD", 0)]
    for i, obj in enumerate(_scene_cameras(context), 1):
        tip = "Load the photo into this camera"
        if obj.data.ftc.image is not None:
            tip = "Load the photo into this camera, replacing its photo"
        items.append((obj.name, _camera_label(obj), tip, "CAMERA_DATA", i))
    _camera_items[:] = items
    return items


def photo_camera_items(_self, context):
    items = [
        (obj.name, _camera_label(obj), "Look through this camera and calibrate it", "CAMERA_DATA", i)
        for i, obj in enumerate(o for o in _scene_cameras(context) if o.data.ftc.image is not None)
    ]
    _photo_camera_items[:] = items
    return items


def new_camera(context, name: str):
    data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, data)
    context.scene.collection.objects.link(cam)
    return cam


def photo_name(path: str) -> str:
    return os.path.splitext(bpy.path.basename(path))[0] or GENERIC_NAME


def background_for(cam_data, image):
    """The camera background entry showing ``image``, if any."""
    if image is None:
        return None
    for bg in cam_data.background_images:
        if bg.image == image:
            return bg
    return None


def set_background(cam_data, image, previous=None) -> None:
    bg = background_for(cam_data, previous) or background_for(cam_data, image)
    if bg is None:
        bg = cam_data.background_images.new()
        bg.alpha = 1.0
    bg.source = "IMAGE"
    bg.image = image
    bg.frame_method = "FIT"
    bg.display_depth = "BACK"
    bg.show_background_image = True
    cam_data.show_background_images = True


def fit_scene_to_image(scene, size) -> None:
    render = scene.render
    render.resolution_x, render.resolution_y = int(size[0]), int(size[1])
    render.pixel_aspect_x = render.pixel_aspect_y = 1.0


def match_image_aspect(scene, size) -> bool:
    """Give the render the image's aspect ratio, keeping its width and percentage
    (the camera frame matches the image only with the same aspect). True when the
    height had to change."""
    if calibrate.aspect_matches(scene, size):
        return False
    render = scene.render
    render.pixel_aspect_x = render.pixel_aspect_y = 1.0
    render.resolution_y = max(4, round(render.resolution_x * size[1] / size[0]))
    return True


def view_through_camera(context, cam_obj) -> None:
    context.scene.camera = cam_obj
    screen = context.screen
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            if space.use_local_camera:
                space.camera = cam_obj
            space.region_3d.view_perspective = "CAMERA"
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is not None:
                # Frame the camera bounds so the whole image is visible.
                with context.temp_override(area=area, region=region):
                    bpy.ops.view3d.view_center_camera()
            area.tag_redraw()


def read_image_exif(image, path):
    if image.packed_file is not None:
        return read_exif(bytes(image.packed_file.data))
    return read_exif(path)


def load_camera_data(settings, exif, size) -> None:
    """Fill the camera data fields from EXIF; absent values are marked missing."""
    data = settings.camera_data
    data.loading = True
    try:
        data.make = exif.make or ""
        data.model = exif.model or ""
        data.lens = exif.lens or ""
        data.image_width, data.image_height = int(size[0]), int(size[1])
        data.orientation = exif.orientation or 0
        sensor = exif.sensor_long_side_mm(size)
        for field, value in (("focal_mm", exif.focal_mm), ("focal_35mm", exif.focal_35mm), ("sensor_mm", sensor)):
            setattr(data, field, value or 0.0)
            setattr(data, field + "_state", "EXIF" if value else "MISSING")
        data.gps_altitude = exif.gps_altitude or 0.0
        data.direction = exif.gps_direction or 0.0
        data.direction_state = "EXIF" if exif.gps_direction is not None else "MISSING"
        data.direction_ref = exif.gps_direction_ref or ""
    finally:
        data.loading = False
    load_time_place(data, exif)
    # Android phones rarely write the compass: then the north comes from a map.
    with calibrate.suspended():
        if exif.gps_direction is not None:
            settings.sun.north_source = "COMPASS"
        elif settings.sun.north_source == "COMPASS":
            settings.sun.north_source = "SIDE"


def load_time_place(data, exif, keep_entered=False) -> None:
    """Shooting time and place from EXIF; absent values are marked missing, or
    with ``keep_entered`` (Read from Photo) left as they are: a place or a zone
    typed by hand survives a photo without them."""
    data.loading = True
    try:
        has_gps = exif.gps_latitude is not None and exif.gps_longitude is not None
        if has_gps or not keep_entered:
            data.has_gps = has_gps
            data.gps_latitude = exif.gps_latitude or 0.0
            data.gps_longitude = exif.gps_longitude or 0.0
            data.location_state = "EXIF" if has_gps else "MISSING"
        when = exif.capture_time()
        if when is None and keep_entered:
            return
        data.time_from_gps = when is not None and when.source == "GPS"
        data.clock_mismatch = when is not None and when.clock_mismatch
        if when is None:
            data.time_state = data.offset_state = "MISSING"
            return
        if when.offset_minutes is not None:
            local, offset = when.local, when.offset_minutes
        elif when.utc is not None and (when.local is None or when.clock_mismatch):
            # Only the GPS time can be trusted: show it as UTC.
            local, offset = when.utc.replace(tzinfo=None), 0
        else:
            local, offset = when.local, None
        data.year, data.month, data.day = local.year, local.month, local.day
        data.hour, data.minute, data.second = local.hour, local.minute, local.second
        data.time_state = "EXIF"
        if offset is not None or not keep_entered:
            data.utc_offset = (offset or 0) / 60.0
            data.offset_state = "EXIF" if offset is not None else "MISSING"
    finally:
        data.loading = False


class FTC_OT_load_image(Operator, ImportHelper):
    """Load a reference image as camera background and read its camera data"""

    bl_idname = "ftc.load_image"
    bl_label = "Load Image"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default=IMAGE_GLOB, options={"HIDDEN"})
    camera: EnumProperty(
        name="Camera",
        description="Camera that receives the photo: a new one, or one of the scene (its photo is replaced)",
        items=camera_items,
        options={"SKIP_SAVE"},
    )
    name_after_photo: BoolProperty(
        name="Name After Photo",
        description='Name the new camera after the photo file (otherwise "FTC Camera")',
        default=True,
    )

    def invoke(self, context, event):
        self.camera = default_camera(context)
        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "camera")
        row = layout.row()
        row.active = self.camera == NEW
        row.prop(self, "name_after_photo")

    def execute(self, context):
        path = self.filepath
        # From a script without a choice: the same camera the file browser proposes.
        choice = self.camera if self.properties.is_property_set("camera") else default_camera(context)
        cam_obj = None
        if choice != NEW:
            cam_obj = context.scene.objects.get(choice)
            if cam_obj is None or cam_obj.type != "CAMERA":
                self.report({"ERROR"}, "The chosen camera is no longer in the scene")
                return {"CANCELLED"}
        existing = {i.as_pointer() for i in bpy.data.images}
        try:
            image = bpy.data.images.load(path, check_existing=True)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        size = tuple(image.size)
        if not size[0] or not size[1]:
            if image.as_pointer() not in existing:
                bpy.data.images.remove(image)
            self.report({"ERROR"}, "Cannot read the image")
            return {"CANCELLED"}

        if cam_obj is None:
            cam_obj = new_camera(context, photo_name(path) if self.name_after_photo else GENERIC_NAME)
        settings = cam_obj.data.ftc
        set_background(cam_obj.data, image, previous=settings.image)
        first_load = len(settings.handles) == 0 or settings.image is None
        if first_load:
            # A new photo starts with the reference distance. Set here and not as the
            # property default: older files that never chose keep the cube's scale.
            with calibrate.suspended():
                settings.scale_mode = "REFERENCE"
        settings.image = image
        settings.source_path = path
        load_camera_data(settings, read_image_exif(image, bpy.path.abspath(path)), size)
        calibrate.ensure_handles(settings)
        if first_load:
            calibrate.reset_handles(settings)
        fit_scene_to_image(context.scene, size)
        view_through_camera(context, cam_obj)
        select_camera(context, cam_obj)
        calibrate.refresh(cam_obj.data)
        sync_render_photo(context.scene)

        data = settings.camera_data
        if data.orientation not in (0, 1):
            self.report({"WARNING"}, "The image is stored rotated: use 'Make Upright Copy' in Camera Data")
        elif data.focal_mm_state == "MISSING" and data.focal_35mm_state == "MISSING":
            self.report({"WARNING"}, "Focal length not found in the image metadata")
        return {"FINISHED"}


def pack_as_jpeg(image) -> None:
    """Pack a generated image as JPEG, like its source photo: ``pack()`` alone
    always stores a PNG, several times larger. Saved through a temporary file."""
    folder = tempfile.mkdtemp(prefix="ftc_")
    name = bpy.path.clean_name(image.name) + ".jpg"
    path = os.path.join(folder, name)
    try:
        image.filepath_raw = path
        image.file_format = "JPEG"
        image.update()
        image.save(filepath=path, quality=95)
        image.pack()
    finally:
        if os.path.exists(path):
            os.remove(path)
        os.rmdir(folder)
    # Where "Unpack" puts it: next to the .blend file.
    image.filepath_raw = "//" + name


class FTC_OT_use_camera(Operator):
    """Look through another camera with a photo and calibrate it (it becomes the scene camera)"""

    bl_idname = "ftc.use_camera"
    bl_label = "Use Camera"
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "camera"

    camera: EnumProperty(name="Camera", description="Camera with a photo to work on", items=photo_camera_items)

    def execute(self, context):
        cam_obj = context.scene.objects.get(self.camera)
        if cam_obj is None or cam_obj.type != "CAMERA":
            return {"CANCELLED"}
        view_through_camera(context, cam_obj)
        select_camera(context, cam_obj)
        calibrate.refresh(cam_obj.data)
        sync_render_photo(context.scene)
        return {"FINISHED"}


def select_camera(context, cam_obj) -> None:
    # Imported here: ops_render imports this module.
    from .ops_render import select_only

    select_only(context, cam_obj)


def sync_render_photo(scene) -> None:
    # Imported here: ops_render imports this module.
    from .ops_render import sync_photo

    sync_photo(scene)


def _orient(pixels: np.ndarray, orientation: int) -> np.ndarray:
    """Apply an EXIF orientation to a top-down (rows, cols, channels) array."""
    ops = {
        2: lambda a: a[:, ::-1],
        3: lambda a: a[::-1, ::-1],
        4: lambda a: a[::-1],
        5: lambda a: a.transpose(1, 0, 2),
        6: lambda a: np.rot90(a, -1),
        7: lambda a: a[::-1, ::-1].transpose(1, 0, 2),
        8: lambda a: np.rot90(a, 1),
    }
    return ops.get(orientation, lambda a: a)(pixels)


class FTC_OT_upright_image(Operator):
    """Create an upright copy of an image stored rotated (EXIF orientation), packed in the .blend file"""

    bl_idname = "ftc.upright_image"
    bl_label = "Make Upright Copy"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = calibrate.view_camera(context)
        return cam is not None and cam.data.ftc.image is not None and cam.data.ftc.camera_data.orientation > 1

    def execute(self, context):
        cam_obj = calibrate.view_camera(context)
        settings = cam_obj.data.ftc
        src = settings.image
        w, h = src.size
        if w * h == 0:
            self.report({"ERROR"}, "The photo cannot be read: is its file missing?")
            return {"CANCELLED"}
        buf = np.empty(w * h * src.channels, dtype=np.float32)
        src.pixels.foreach_get(buf)
        # Blender stores rows bottom-up; EXIF orientation is defined top-down.
        top_down = buf.reshape(h, w, src.channels)[::-1]
        upright = np.ascontiguousarray(_orient(top_down, settings.camera_data.orientation)[::-1])
        nh, nw = upright.shape[:2]

        name = os.path.splitext(src.name)[0] + " (upright)"
        image = bpy.data.images.new(name, nw, nh, alpha=src.channels == 4, float_buffer=src.is_float)
        if not src.is_float:
            # A float copy keeps its linear default: the pixels read above are
            # already linear, and it is packed as OpenEXR.
            image.colorspace_settings.name = src.colorspace_settings.name
        if src.channels == 4:
            image.pixels.foreach_set(upright.ravel())
        else:
            rgba = np.ones((nh, nw, 4), dtype=np.float32)
            rgba[..., : src.channels] = upright
            image.pixels.foreach_set(rgba.ravel())
        # Commit the pixels written above: without it, save/pack can read stale data.
        image.update()
        if src.file_format == "JPEG":
            pack_as_jpeg(image)
        else:
            image.pack()

        set_background(cam_obj.data, image, previous=src)
        settings.image = image
        data = settings.camera_data
        data.loading = True
        data.image_width, data.image_height = nw, nh
        data.orientation = 1
        data.loading = False
        calibrate.reset_handles(settings)
        fit_scene_to_image(context.scene, (nw, nh))
        calibrate.refresh(cam_obj.data)
        from . import ops_sun  # (ops_sun imports this module)

        ops_sun.orient(settings)
        sync_render_photo(context.scene)
        calibrate.tag_redraw(context)
        return {"FINISHED"}


classes = (FTC_OT_load_image, FTC_OT_use_camera, FTC_OT_upright_image)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
