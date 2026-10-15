# SPDX-License-Identifier: GPL-3.0-or-later
import struct
import zlib
from datetime import UTC, datetime

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
    # Sensor diagonal 10.20 mm -> 8.16 x 6.12 mm, whatever the crop.
    assert data.sensor_long_side_mm() == pytest.approx(8.163, abs=0.005)
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


def test_implausible_values_are_dropped():
    tiff = build_tiff(
        ifd0=[(exif.TAG_MAKE, ASCII, "Acme"), (exif.TAG_ORIENTATION, SHORT, 300)],
        exif_ifd=[(exif.TAG_FOCAL_LENGTH, RATIONAL, [(10**9, 1)]), (exif.TAG_FOCAL_35MM, SHORT, 24)],
    )
    data = exif.read_exif(jpeg(tiff))
    assert data.make == "Acme"
    assert data.orientation is None  # only 1..8 exist: 300 would rotate the photo
    assert data.focal_mm is None and data.focal_35mm == 24
    assert data.sensor_long_side_mm((4000, 3000)) is None


def test_broken_exif_pointer_keeps_ifd0():
    ifd0 = [(exif.TAG_MAKE, ASCII, "Acme"), (exif.TAG_ORIENTATION, SHORT, 6), (exif.TAG_EXIF_IFD, LONG, 999999)]
    tiff = build_tiff(ifd0=ifd0)
    data = exif.read_exif(jpeg(tiff))
    assert data.make == "Acme" and data.orientation == 6 and data.focal_mm is None


def timed(exif_ifd=(), gps_ifd=()):
    """A JPEG with only time tags."""
    tiff = build_tiff(ifd0=[(exif.TAG_MAKE, ASCII, "Acme")], exif_ifd=list(exif_ifd), gps_ifd=list(gps_ifd))
    return exif.read_exif(jpeg(tiff))


GPS_TIME = [(exif.GPS_DATE, ASCII, "2026:08:04"), (exif.GPS_TIME, RATIONAL, [(16, 1), (52, 1), (18, 1)])]
LOCAL = (exif.TAG_DATETIME_ORIGINAL, ASCII, "2026:08:04 18:52:19")


def test_gps_time_is_utc_and_implies_the_zone():
    """Android phones: GPS time, camera clock, no offset tag (the samples)."""
    t = timed([LOCAL], GPS_TIME).capture_time()
    assert t.source == "GPS" and not t.clock_mismatch
    # The camera clock (18:52:19) gives the instant: the GPS fix is a second older.
    assert t.utc == datetime(2026, 8, 4, 16, 52, 19, tzinfo=UTC)
    assert t.offset_minutes == 120
    assert t.local == datetime(2026, 8, 4, 18, 52, 19)


def test_gps_time_alone():
    t = timed(gps_ifd=GPS_TIME).capture_time()
    assert t.source == "GPS" and t.utc.hour == 16 and t.local is None and t.offset_minutes is None


def test_stale_gps_time_is_flagged():
    """Some phones write the time of the last GPS fix: hours off, not a whole zone."""
    gps = [(exif.GPS_DATE, ASCII, "2026:08:04"), (exif.GPS_TIME, RATIONAL, [(14, 1), (3, 1), (10, 1)])]
    t = timed([LOCAL], gps).capture_time()
    assert t.source == "GPS" and t.clock_mismatch and t.offset_minutes is None
    assert t.local == datetime(2026, 8, 4, 18, 52, 19)


@pytest.mark.parametrize("hours, minutes, zone", [(13, 7, 345), (14, 22, 270), (14, 37, None), (2, 52, None)])
def test_only_real_zones_are_accepted(hours, minutes, zone):
    """+5:45 (Nepal) and +4:30 (Afghanistan) exist, +4:15 and +16:00 do not."""
    gps = [(exif.GPS_DATE, ASCII, "2026:08:04"), (exif.GPS_TIME, RATIONAL, [(hours, 1), (minutes, 1), (19, 1)])]
    t = timed([LOCAL], gps).capture_time()
    assert t.offset_minutes == zone and t.clock_mismatch == (zone is None)


def test_offset_disagreeing_with_gps_is_flagged():
    """A complete camera clock beats a GPS time that disagrees (a stale fix)."""
    t = timed([LOCAL, (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, "+01:00")], GPS_TIME).capture_time()
    assert t.clock_mismatch and t.source == "OFFSET" and t.offset_minutes == 60
    assert t.utc == datetime(2026, 8, 4, 17, 52, 19, tzinfo=UTC)


def test_day_old_gps_fix_loses_to_the_clock_with_offset():
    gps = [(exif.GPS_DATE, ASCII, "2026:08:03"), (exif.GPS_TIME, RATIONAL, [(16, 1), (52, 1), (18, 1)])]
    t = timed([LOCAL, (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, "+02:00")], gps).capture_time()
    assert t.clock_mismatch and t.utc == datetime(2026, 8, 4, 16, 52, 19, tzinfo=UTC)


def test_offset_agreeing_with_gps():
    t = timed([LOCAL, (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, "+02:00")], GPS_TIME).capture_time()
    assert not t.clock_mismatch and t.source == "GPS" and t.offset_minutes == 120


@pytest.mark.parametrize("text, minutes", [("+05:45", 345), ("-09:30", -570), ("+14:00", 840)])
def test_real_offsets(text, minutes):
    assert timed([LOCAL, (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, text)]).offset_minutes == minutes


@pytest.mark.parametrize("text", ["+14:59", "-14:00", "+04:15", "+02:60"])
def test_impossible_offsets_are_none(text):
    assert timed([LOCAL, (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, text)]).offset_minutes is None


def test_impossible_latitude_is_none():
    gps = [(exif.GPS_LAT_REF, ASCII, "N"), (exif.GPS_LAT, RATIONAL, [(95, 1), (0, 1), (0, 1)])]
    assert timed(gps_ifd=gps).gps_latitude is None


def test_offset_time_without_gps():
    t = timed([LOCAL, (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, "-05:30")]).capture_time()
    assert t.source == "OFFSET" and t.offset_minutes == -330
    assert t.utc == datetime(2026, 8, 5, 0, 22, 19, tzinfo=UTC)


def test_local_time_only_needs_the_zone_by_hand():
    t = timed([LOCAL]).capture_time()
    assert t.source == "LOCAL" and t.utc is None and t.local == datetime(2026, 8, 4, 18, 52, 19)


def test_no_time_at_all():
    assert timed().capture_time() is None


@pytest.mark.parametrize(
    "local, offset, date, time",
    [
        ("    :  :     :  :  ", "+2:00", "2026-08-04", [(16, 1), (99, 1), (0, 1)]),
        ("2026:13:40 25:00:00", "+15:00", "garbage", [(16, 1), (52, 1)]),
        ("", "02:00", "2026:02:30", [(16, 1), (52, 1), (18, 0)]),
    ],
)
def test_garbled_time_tags_are_none(local, offset, date, time):
    data = timed(
        [(exif.TAG_DATETIME_ORIGINAL, ASCII, local or " "), (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, offset)],
        [(exif.GPS_DATE, ASCII, date), (exif.GPS_TIME, RATIONAL, time)],
    )
    assert data.datetime_original is None and data.offset_minutes is None and data.gps_datetime is None
    assert data.make == "Acme"


@pytest.mark.parametrize(
    "local, offset, gps",
    [
        (None, None, [(exif.GPS_DATE, ASCII, "9999:12:31"), (exif.GPS_TIME, RATIONAL, [(24, 1), (0, 1), (0, 1)])]),
        ("0001:01:01 00:00:00", "+01:00", []),
        ("9999:12:31 23:00:00", "-05:00", []),
    ],
)
def test_dates_at_the_ends_of_the_calendar_do_not_raise(local, offset, gps):
    tags = [(exif.TAG_DATETIME_ORIGINAL, ASCII, local), (exif.TAG_OFFSET_TIME_ORIGINAL, ASCII, offset)] if local else []
    data = timed(tags, gps)
    assert data.make == "Acme"
    assert data.capture_time() is None
