# SPDX-License-Identifier: GPL-3.0-or-later
import struct
import zlib

import exif
import pytest
from exif_builder import ASCII, LONG, RATIONAL, SHORT, build_tiff

PHONE = dict(
    ifd0=[(exif.TAG_MAKE, ASCII, "Apple"), (exif.TAG_MODEL, ASCII, "iPhone 15"), (exif.TAG_ORIENTATION, SHORT, 6)],
    exif_ifd=[
        (exif.TAG_FOCAL_LENGTH, RATIONAL, [(686, 100)]),
        (exif.TAG_FOCAL_35MM, SHORT, 24),
        (exif.TAG_PIXEL_X, LONG, 4032),
        (exif.TAG_PIXEL_Y, LONG, 3024),
        (exif.TAG_LENS_MAKE, ASCII, "Apple"),
        (exif.TAG_LENS_MODEL, ASCII, "iPhone 15 back camera 6.86mm f/1.6"),
    ],
    gps_ifd=[
        (exif.GPS_LAT_REF, ASCII, "N"),
        (exif.GPS_LAT, RATIONAL, [(45, 1), (30, 1), (36, 1)]),
        (exif.GPS_LON_REF, ASCII, "W"),
        (exif.GPS_LON, RATIONAL, [(9, 1), (11, 1), (0, 1)]),
        (exif.GPS_DIRECTION_REF, ASCII, "T"),
        (exif.GPS_DIRECTION, RATIONAL, [(12345, 100)]),
    ],
)


def jpeg(tiff):
    app1 = b"Exif\0\0" + tiff
    return (
        b"\xff\xd8"
        + b"\xff\xe0"
        + struct.pack(">H", 16)
        + b"JFIF\0"
        + b"\0" * 9
        + (b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1)
        + b"\xff\xda\0\x02"
        + b"\xff\xd9"
    )


def png(tiff):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"eXIf", tiff) + chunk(b"IEND", b"")


def webp(tiff):
    body = b"WEBP" + b"VP8 " + struct.pack("<I", 2) + b"\0\0" + b"EXIF" + struct.pack("<I", len(tiff)) + tiff
    return b"RIFF" + struct.pack("<I", len(body)) + body


@pytest.mark.parametrize("endian", ["<", ">"])
@pytest.mark.parametrize("wrap", [jpeg, png, webp, lambda t: t])
def test_phone_photo(endian, wrap):
    data = exif.read_exif(wrap(build_tiff(**PHONE, endian=endian)))
    assert data.make == "Apple" and data.model == "iPhone 15"
    assert data.focal_mm == pytest.approx(6.86)
    assert data.focal_35mm == 24
    assert (data.pixel_x, data.pixel_y) == (4032, 3024)
    assert data.orientation == 6
    assert data.lens == "Apple iPhone 15 back camera 6.86mm f/1.6"
    assert data.gps_latitude == pytest.approx(45.51)
    assert data.gps_longitude == pytest.approx(-(9 + 11 / 60))
    assert data.gps_direction == pytest.approx(123.45)
    assert data.gps_direction_ref == "T"
    # Crop factor 24 / 6.86 -> sensor diagonal 12.37 mm, long side 9.9 mm on 4:3.
    assert data.sensor_long_side_mm() == pytest.approx(9.896, abs=0.01)


def test_square_crop_assumes_a_4_3_sensor():
    """1:1 phone photo: the 35 mm equivalent refers to the uncropped 4:3 sensor."""
    tiff = build_tiff(
        ifd0=[(exif.TAG_MAKE, ASCII, "motorola")],
        exif_ifd=[
            (exif.TAG_FOCAL_LENGTH, RATIONAL, [(5895, 1000)]),
            (exif.TAG_FOCAL_35MM, SHORT, 25),
            (exif.TAG_PIXEL_X, LONG, 3072),
            (exif.TAG_PIXEL_Y, LONG, 3072),
        ],
    )
    data = exif.read_exif(jpeg(tiff))
    # Sensor diagonal 10.20 mm -> 8.16 x 6.12 mm; the square crop is 6.12 mm wide.
    assert data.sensor_long_side_mm() == pytest.approx(6.122, abs=0.005)
    assert exif.native_frame((3072, 3072)) == (4096.0, 3072.0)
    assert exif.native_frame((1920, 1080)) == (1920.0, 1440.0)
    assert exif.native_frame((6000, 4000)) == (6000.0, 4000.0)


def test_focal_plane_resolution_sensor():
    tiff = build_tiff(
        ifd0=[(exif.TAG_MAKE, ASCII, "Canon")],
        exif_ifd=[
            (exif.TAG_FOCAL_LENGTH, RATIONAL, [(50, 1)]),
            (exif.TAG_PIXEL_X, LONG, 6000),
            (exif.TAG_PIXEL_Y, LONG, 4000),
            (exif.TAG_FOCAL_PLANE_X_RES, RATIONAL, [(6000000, 1424)]),  # 6000 px over 35.6 mm... in inches
            (exif.TAG_FOCAL_PLANE_Y_RES, RATIONAL, [(4000000, 949)]),
            (exif.TAG_FOCAL_PLANE_UNIT, SHORT, 2),
        ],
    )
    data = exif.read_exif(jpeg(tiff))
    assert data.focal_35mm is None
    assert data.sensor_long_side_mm() == pytest.approx(1.424 * 25.4, rel=1e-6)


def test_missing_fields_are_none():
    data = exif.read_exif(jpeg(build_tiff(ifd0=[(exif.TAG_MAKE, ASCII, "Nikon")])))
    assert data.make == "Nikon"
    assert data.focal_mm is None and data.focal_35mm is None and data.gps_direction is None
    assert data.sensor_long_side_mm((6000, 4000)) is None


@pytest.mark.parametrize(
    "blob",
    [b"", b"not an image", b"\xff\xd8\xff\xe1\x00\x08Exif\0\0", b"\xff\xd8" + b"\xff\xe1\xff\xff" + b"Exif\0\0II*\0"],
)
def test_garbage_does_not_raise(blob):
    assert exif.read_exif(blob).is_empty()


def test_missing_file(tmp_path):
    assert exif.read_exif(tmp_path / "missing.jpg").is_empty()
