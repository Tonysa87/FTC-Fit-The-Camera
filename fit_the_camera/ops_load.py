# SPDX-License-Identifier: GPL-3.0-or-later
"""Load the reference image into a camera and read its EXIF data."""

import os

import bpy
import numpy as np
from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from . import calibrate
from .exif import read_exif

IMAGE_GLOB = "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.webp;*.bmp;*.tga;*.exr;*.hdr;*.jp2;*.dpx;*.cin"


def target_camera(context, create: bool):
    """Active camera object, else the view/scene camera, else a new camera."""
    obj = context.active_object
    if obj is not None and obj.type == "CAMERA":
        return obj
    cam = calibrate.view_camera(context)
    if cam is not None or not create:
        return cam
    data = bpy.data.cameras.new("FTC Camera")
    cam = bpy.data.objects.new("FTC Camera", data)
    context.scene.collection.objects.link(cam)
    return cam


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
        data.has_gps = exif.gps_latitude is not None and exif.gps_longitude is not None
        data.gps_latitude = exif.gps_latitude or 0.0
        data.gps_longitude = exif.gps_longitude or 0.0
        data.gps_altitude = exif.gps_altitude or 0.0
        data.direction = exif.gps_direction or 0.0
        data.direction_state = "EXIF" if exif.gps_direction is not None else "MISSING"
        data.direction_ref = exif.gps_direction_ref or ""
    finally:
        data.loading = False


class FTC_OT_load_image(Operator, ImportHelper):
    """Load a reference image as camera background and read its camera data"""

    bl_idname = "ftc.load_image"
    bl_label = "Load Image"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default=IMAGE_GLOB, options={"HIDDEN"})

    def execute(self, context):
        path = self.filepath
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

        cam_obj = target_camera(context, create=True)
        settings = cam_obj.data.ftc
        set_background(cam_obj.data, image, previous=settings.image)
        first_load = len(settings.handles) == 0 or settings.image is None
        settings.image = image
        settings.source_path = path
        load_camera_data(settings, read_image_exif(image, bpy.path.abspath(path)), size)
        calibrate.ensure_handles(settings)
        if first_load:
            calibrate.reset_handles(settings)
        fit_scene_to_image(context.scene, size)
        view_through_camera(context, cam_obj)
        calibrate.refresh(cam_obj.data)

        data = settings.camera_data
        if data.orientation not in (0, 1):
            self.report({"WARNING"}, "The image is stored rotated: use 'Make Upright Copy' in Camera Data")
        elif data.focal_mm_state == "MISSING" and data.focal_35mm_state == "MISSING":
            self.report({"WARNING"}, "Focal length not found in the image metadata")
        return {"FINISHED"}


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
        buf = np.empty(w * h * src.channels, dtype=np.float32)
        src.pixels.foreach_get(buf)
        # Blender stores rows bottom-up; EXIF orientation is defined top-down.
        top_down = buf.reshape(h, w, src.channels)[::-1]
        upright = np.ascontiguousarray(_orient(top_down, settings.camera_data.orientation)[::-1])
        nh, nw = upright.shape[:2]

        name = os.path.splitext(src.name)[0] + " (upright)"
        image = bpy.data.images.new(name, nw, nh, alpha=src.channels == 4, float_buffer=src.is_float)
        image.colorspace_settings.name = src.colorspace_settings.name
        if src.channels == 4:
            image.pixels.foreach_set(upright.ravel())
        else:
            rgba = np.ones((nh, nw, 4), dtype=np.float32)
            rgba[..., : src.channels] = upright
            image.pixels.foreach_set(rgba.ravel())
        if src.file_format == "JPEG":
            # Packed as JPEG like the source: a PNG of a photo is several times larger.
            image.file_format = "JPEG"
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
        calibrate.tag_redraw(context)
        return {"FINISHED"}


classes = (FTC_OT_load_image, FTC_OT_upright_image)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
