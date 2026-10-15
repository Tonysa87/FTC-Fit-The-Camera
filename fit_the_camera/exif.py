# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal EXIF reader in pure Python.

Reads the tags FTC needs from JPEG, TIFF, PNG (``eXIf``) and WebP files. It never
guesses: a tag that is absent or unreadable is ``None``.
"""

from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta, timezone

# IFD0 / EXIF / GPS tags used by FTC.
TAG_MAKE = 0x010F
TAG_MODEL = 0x0110
TAG_ORIENTATION = 0x0112
TAG_EXIF_IFD = 0x8769
TAG_GPS_IFD = 0x8825
TAG_DATETIME_ORIGINAL = 0x9003
TAG_OFFSET_TIME_ORIGINAL = 0x9011
TAG_FOCAL_LENGTH = 0x920A
TAG_PIXEL_X = 0xA002
TAG_PIXEL_Y = 0xA003
TAG_FOCAL_PLANE_X_RES = 0xA20E
TAG_FOCAL_PLANE_Y_RES = 0xA20F
TAG_FOCAL_PLANE_UNIT = 0xA210
TAG_FOCAL_35MM = 0xA405
TAG_LENS_MAKE = 0xA433
TAG_LENS_MODEL = 0xA434
GPS_LAT_REF, GPS_LAT, GPS_LON_REF, GPS_LON = 0x0001, 0x0002, 0x0003, 0x0004
GPS_ALT_REF, GPS_ALT = 0x0005, 0x0006
GPS_TIME = 0x0007
GPS_DIRECTION_REF, GPS_DIRECTION = 0x0010, 0x0011
GPS_DATE = 0x001D

# EXIF focal plane resolution unit -> millimetres per unit.
FOCAL_PLANE_UNITS_MM = {2: 25.4, 3: 10.0, 4: 1.0, 5: 0.001}

# Diagonal of a 36x24 mm frame, the reference of 35 mm equivalent focal lengths.
FULL_FRAME_DIAGONAL_MM = math.hypot(36.0, 24.0)

# Image aspect ratios taken as the sensor's own (uncropped) frame.
NATIVE_ASPECTS = (4.0 / 3.0, 3.0 / 2.0)


def native_frame(image_size) -> tuple[float, float]:
    """Long and short side, in image pixels, of the sensor frame the image comes from.

    4:3 and 3:2 images are taken as uncropped. Any other aspect (1:1, 16:9, ...)
    is taken as the largest centred crop of a 4:3 sensor, which is what phones do;
    their 35 mm equivalent focal length refers to that uncropped frame.
    """
    long_side, short_side = float(max(image_size)), float(min(image_size))
    aspect = long_side / short_side
    if any(abs(aspect - n) / n < 0.01 for n in NATIVE_ASPECTS):
        return long_side, short_side
    if aspect > 4.0 / 3.0:
        return long_side, long_side * 3.0 / 4.0
    return short_side * 4.0 / 3.0, short_side


def is_native_aspect(image_size) -> bool:
    return native_frame(image_size) == (float(max(image_size)), float(min(image_size)))


_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
_MAX_ENTRIES = 1000


@dataclass
class ExifData:
    make: str | None = None
    model: str | None = None
    lens_make: str | None = None
    lens_model: str | None = None
    focal_mm: float | None = None
    focal_35mm: float | None = None
    pixel_x: int | None = None
    pixel_y: int | None = None
    focal_plane_x_res: float | None = None
    focal_plane_y_res: float | None = None
    focal_plane_unit: int | None = None
    orientation: int | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    gps_altitude: float | None = None
    gps_direction: float | None = None
    gps_direction_ref: str | None = None
    # Shooting time: the camera clock (local, naive), its UTC offset in minutes
    # when written, and the GPS time (UTC, aware).
    datetime_original: datetime | None = None
    offset_minutes: int | None = None
    gps_datetime: datetime | None = None

    def is_empty(self) -> bool:
        return all(getattr(self, f.name) is None for f in fields(self))

    @property
    def lens(self) -> str | None:
        parts = [p for p in (self.lens_make, self.lens_model) if p]
        if len(parts) == 2 and parts[1].lower().startswith(parts[0].lower()):
            parts = parts[1:]
        return " ".join(parts) or None

    def sensor_long_side_mm(self, image_size=None) -> float | None:
        """Long side of the (uncropped) sensor, derived from EXIF only: the same
        figure as a camera's specifications, whatever crop the image is.

        Uses the crop factor (real vs 35 mm equivalent focal length) when both are
        present, otherwise the focal plane resolution. ``None`` if neither is usable.
        """
        size = (self.pixel_x, self.pixel_y) if self.pixel_x and self.pixel_y else image_size
        if not size or not all(size):
            return None
        native_long, native_short = native_frame(size)
        if self.focal_mm and self.focal_35mm:
            diagonal = FULL_FRAME_DIAGONAL_MM * self.focal_mm / self.focal_35mm
            value = diagonal * native_long / math.hypot(native_long, native_short)
            if 1.0 < value < 100.0:
                return value
        unit = FOCAL_PLANE_UNITS_MM.get(self.focal_plane_unit or 2)
        if unit and self.focal_plane_x_res:
            pixel_pitch = unit / self.focal_plane_x_res
            value = pixel_pitch * native_long
            if 1.0 < value < 100.0:
                return value
        return None

    def capture_time(self) -> CaptureTime | None:
        """When the photo was taken, from the best source available; ``None``
        for dates at the ends of the calendar (year 1 or 9999 shifted by a zone)."""
        try:
            return capture_time(self.datetime_original, self.offset_minutes, self.gps_datetime)
        except OverflowError:
            return None


# The GPS time and the camera clock agree when they differ by a time zone
# within this many minutes (phones: a few seconds). Zones are whole or half
# hours, plus the few at 45 minutes; a stale GPS fix rarely lands on one.
CLOCK_TOLERANCE_MIN = 1.0
QUARTER_ZONES_MIN = (345, 525, 765, 825)  # +5:45, +8:45, +12:45, +13:45


def _is_zone(minutes: int) -> bool:
    return -12 * 60 <= minutes <= 14 * 60 and (minutes % 30 == 0 or minutes in QUARTER_ZONES_MIN)


@dataclass
class CaptureTime:
    """Shooting time. ``utc`` is ``None`` when only the local time is known (no
    GPS time, no offset): the time zone must then be entered by hand."""

    utc: datetime | None
    local: datetime | None
    offset_minutes: int | None  # local - UTC, written or implied by the GPS time
    source: str  # "GPS", "OFFSET" or "LOCAL"
    clock_mismatch: bool = False  # GPS time and camera clock disagree


def capture_time(local, offset, gps) -> CaptureTime | None:
    """GPS time first (UTC from the satellites; when the camera clock agrees
    with it, the camera clock to the second), else the camera clock with its
    written offset, else the bare local time. Never guesses the zone from the
    longitude (daylight saving time breaks it).

    When the GPS time and a complete camera clock (time + offset) disagree, the
    clock wins: phones write the time of the last GPS fix, which can be hours or
    days old. Without an offset the GPS time is the only UTC there is."""
    if gps is not None:
        if local is None:
            shown = (gps + timedelta(minutes=offset)).replace(tzinfo=None) if offset is not None else None
            return CaptureTime(gps, shown, offset, "GPS")
        minutes = (local - gps.replace(tzinfo=None)).total_seconds() / 60.0
        zone = 15 * round(minutes / 15.0)
        agrees = abs(minutes - zone) <= CLOCK_TOLERANCE_MIN and _is_zone(zone)
        if agrees and offset in (None, zone):
            # Phones write the time of the last GPS fix, seconds before the shot:
            # the camera clock gives the instant, the GPS time only its zone.
            utc = local.replace(tzinfo=timezone(timedelta(minutes=zone))).astimezone(UTC)
            return CaptureTime(utc, local, int(zone), "GPS")
        if offset is not None:
            utc = local.replace(tzinfo=timezone(timedelta(minutes=offset))).astimezone(UTC)
            return CaptureTime(utc, local, offset, "OFFSET", clock_mismatch=True)
        return CaptureTime(gps, local, None, "GPS", clock_mismatch=True)
    if local is None:
        return None
    if offset is not None:
        utc = local.replace(tzinfo=timezone(timedelta(minutes=offset))).astimezone(UTC)
        return CaptureTime(utc, local, offset, "OFFSET")
    return CaptureTime(None, local, None, "LOCAL")


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        if data[:2] == b"II":
            self.endian = "<"
        elif data[:2] == b"MM":
            self.endian = ">"
        else:
            raise ValueError("not a TIFF header")
        if self.unpack("H", 2) != 42:
            raise ValueError("bad TIFF magic")

    def unpack(self, fmt: str, offset: int):
        size = struct.calcsize(self.endian + fmt)
        if offset < 0 or offset + size > len(self.data):
            raise ValueError("offset out of range")
        return struct.unpack_from(self.endian + fmt, self.data, offset)[0]

    def ifd(self, offset: int) -> dict[int, object]:
        entries: dict[int, object] = {}
        count = self.unpack("H", offset)
        if count > _MAX_ENTRIES:
            raise ValueError("implausible IFD size")
        for k in range(count):
            base = offset + 2 + 12 * k
            try:
                tag = self.unpack("H", base)
                kind = self.unpack("H", base + 2)
                n = self.unpack("I", base + 4)
                entries[tag] = self.value(kind, n, base + 8)
            except (ValueError, struct.error, ZeroDivisionError):
                continue
        return entries

    def value(self, kind: int, count: int, field_offset: int):
        size = _TYPE_SIZES.get(kind)
        if size is None:
            raise ValueError("unknown type")
        total = size * count
        offset = field_offset if total <= 4 else self.unpack("I", field_offset)
        if offset + total > len(self.data):
            raise ValueError("value out of range")
        raw = self.data[offset : offset + total]
        if kind == 2:
            return raw.split(b"\0", 1)[0].decode("utf-8", "replace").strip() or None
        if kind in (1, 6, 7):
            values = list(raw)
        elif kind in (3, 8):
            values = [self.unpack("h" if kind == 8 else "H", offset + 2 * i) for i in range(count)]
        elif kind in (4, 9):
            values = [self.unpack("i" if kind == 9 else "I", offset + 4 * i) for i in range(count)]
        elif kind in (5, 10):
            fmt = "i" if kind == 10 else "I"
            values = []
            for i in range(count):
                num = self.unpack(fmt, offset + 8 * i)
                den = self.unpack(fmt, offset + 8 * i + 4)
                values.append(num / den if den else None)
        elif kind == 11:
            values = [self.unpack("f", offset + 4 * i) for i in range(count)]
        else:
            values = [self.unpack("d", offset + 8 * i) for i in range(count)]
        return values[0] if count == 1 else values


def _first_number(value) -> float | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
        return float(value)
    return None


def _bearing(value) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value) and 0.0 <= value <= 360.0:
        return float(value) % 360.0
    return None


def _dms(value, ref, negative: str) -> float | None:
    if not isinstance(value, list) or len(value) != 3 or any(v is None for v in value):
        return None
    degrees = value[0] + value[1] / 60.0 + value[2] / 3600.0
    if not math.isfinite(degrees) or not 0.0 <= degrees <= 180.0:
        return None
    return -degrees if isinstance(ref, str) and ref.upper().startswith(negative) else degrees


def _datetime(value) -> datetime | None:
    """EXIF ``YYYY:MM:DD HH:MM:SS`` (blank or garbled fields -> ``None``)."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip()[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _offset(value) -> int | None:
    """EXIF ``+HH:MM`` / ``-HH:MM`` -> minutes."""
    if not isinstance(value, str) or len(value) < 6 or value[0] not in "+-" or value[3] != ":":
        return None
    try:
        hours, minutes = int(value[1:3]), int(value[4:6])
    except ValueError:
        return None
    total = hours * 60 + minutes
    total = -total if value[0] == "-" else total
    return total if minutes < 60 and _is_zone(total) else None


def _gps_datetime(date, time) -> datetime | None:
    """GPSDateStamp ``YYYY:MM:DD`` + GPSTimeStamp (h, m, s) -> aware UTC."""
    if not isinstance(date, str) or not isinstance(time, list) or len(time) != 3:
        return None
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in time):
        return None
    try:
        day = datetime.strptime(date.strip()[:10], "%Y:%m:%d")
    except ValueError:
        return None
    h, m, sec = time
    if h > 24 or m >= 60 or sec >= 61:
        return None
    try:
        return (day + timedelta(hours=h, minutes=m, seconds=sec)).replace(tzinfo=UTC)
    except OverflowError:
        return None


# Plausible focal lengths (mm): anything else is a corrupt tag.
FOCAL_RANGE_MM = (0.5, 5000.0)


def _in_range(value, low, high):
    return value if value is not None and low <= value <= high else None


def parse_tiff(data: bytes) -> ExifData:
    """Parse a TIFF/EXIF block."""
    reader = _Reader(data)
    ifd0 = reader.ifd(reader.unpack("I", 4))

    def sub_ifd(tag):
        # A broken sub-IFD must not lose what IFD0 holds (make, model, orientation).
        if not isinstance(ifd0.get(tag), int):
            return {}
        try:
            return reader.ifd(ifd0[tag])
        except (struct.error, IndexError, ValueError, OverflowError, TypeError, KeyError):
            return {}

    exif = sub_ifd(TAG_EXIF_IFD)
    gps = sub_ifd(TAG_GPS_IFD)

    def text(d, tag):
        v = d.get(tag)
        return v if isinstance(v, str) and v else None

    def integer(d, tag):
        v = d.get(tag)
        if isinstance(v, list):
            v = v[0] if v else None
        return int(v) if isinstance(v, int) and v > 0 else None

    result = ExifData(
        make=text(ifd0, TAG_MAKE),
        model=text(ifd0, TAG_MODEL),
        lens_make=text(exif, TAG_LENS_MAKE),
        lens_model=text(exif, TAG_LENS_MODEL),
        focal_mm=_in_range(_first_number(exif.get(TAG_FOCAL_LENGTH)), *FOCAL_RANGE_MM),
        focal_35mm=_in_range(_first_number(exif.get(TAG_FOCAL_35MM)), *FOCAL_RANGE_MM),
        pixel_x=integer(exif, TAG_PIXEL_X),
        pixel_y=integer(exif, TAG_PIXEL_Y),
        focal_plane_x_res=_first_number(exif.get(TAG_FOCAL_PLANE_X_RES)),
        focal_plane_y_res=_first_number(exif.get(TAG_FOCAL_PLANE_Y_RES)),
        focal_plane_unit=integer(exif, TAG_FOCAL_PLANE_UNIT),
        orientation=_in_range(integer(ifd0, TAG_ORIENTATION), 1, 8),
        gps_latitude=_in_range(_dms(gps.get(GPS_LAT), gps.get(GPS_LAT_REF), "S"), -90.0, 90.0),
        gps_longitude=_dms(gps.get(GPS_LON), gps.get(GPS_LON_REF), "W"),
        gps_direction=_bearing(gps.get(GPS_DIRECTION)),
        gps_direction_ref=text(gps, GPS_DIRECTION_REF),
        datetime_original=_datetime(exif.get(TAG_DATETIME_ORIGINAL)),
        offset_minutes=_offset(exif.get(TAG_OFFSET_TIME_ORIGINAL)),
        gps_datetime=_gps_datetime(gps.get(GPS_DATE), gps.get(GPS_TIME)),
    )
    alt = gps.get(GPS_ALT)
    if isinstance(alt, (int, float)):
        below = gps.get(GPS_ALT_REF) == 1
        result.gps_altitude = -float(alt) if below else float(alt)
    return result


def _jpeg_exif(f) -> bytes | None:
    f.seek(2)
    while True:
        marker = f.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        if marker[1] in (0xD9, 0xDA):  # end of image / start of scan
            return None
        if 0xD0 <= marker[1] <= 0xD7 or marker[1] == 0x01:
            continue
        length = struct.unpack(">H", f.read(2))[0]
        payload = f.read(length - 2)
        if marker[1] == 0xE1 and payload.startswith(b"Exif\0\0"):
            return payload[6:]


def _png_exif(f) -> bytes | None:
    f.seek(8)
    while True:
        head = f.read(8)
        if len(head) < 8:
            return None
        length, kind = struct.unpack(">I4s", head)
        if kind == b"eXIf":
            return f.read(length)
        if kind == b"IEND":
            return None
        f.seek(length + 4, io.SEEK_CUR)


def _webp_exif(f) -> bytes | None:
    f.seek(12)
    while True:
        head = f.read(8)
        if len(head) < 8:
            return None
        kind, length = struct.unpack("<4sI", head)
        if kind == b"EXIF":
            data = f.read(length)
            return data[6:] if data.startswith(b"Exif\0\0") else data
        f.seek(length + (length & 1), io.SEEK_CUR)


def read_exif(source) -> ExifData:
    """Read EXIF from a file path, bytes or binary file object.

    Returns an empty ``ExifData`` for unsupported files or files without EXIF.
    """
    if isinstance(source, (bytes, bytearray, memoryview)):
        return _read(io.BytesIO(bytes(source)))
    if hasattr(source, "read"):
        return _read(source)
    try:
        with open(source, "rb") as f:
            return _read(f)
    except OSError:
        return ExifData()


def _read(f) -> ExifData:
    try:
        head = f.read(16)
        block = None
        if head[:2] == b"\xff\xd8":
            block = _jpeg_exif(f)
        elif head[:8] == b"\x89PNG\r\n\x1a\n":
            block = _png_exif(f)
        elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            block = _webp_exif(f)
        elif head[:4] in (b"II*\0", b"MM\0*"):
            f.seek(0)
            block = f.read()
        if block is None:
            return ExifData()
        return parse_tiff(block)
    except (ValueError, struct.error, OSError, KeyError, TypeError, OverflowError):
        return ExifData()
