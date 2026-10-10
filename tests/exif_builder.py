# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds synthetic EXIF blocks for tests (no pytest dependency)."""

import struct

import exif

ASCII, SHORT, LONG, RATIONAL = 2, 3, 4, 5


def build_tiff(ifd0, exif_ifd=None, gps_ifd=None, endian="<"):
    """Serialise IFDs into a TIFF block. Each IFD is a list of (tag, type, values)."""
    mark = b"II" if endian == "<" else b"MM"
    ifd0 = list(ifd0)
    out = bytearray(mark + struct.pack(endian + "HI", 42, 8))

    def encode(kind, values):
        if kind == ASCII:
            raw = values.encode() + b"\0"
            return raw, len(raw)
        values = values if isinstance(values, list) else [values]
        if kind == SHORT:
            return b"".join(struct.pack(endian + "H", v) for v in values), len(values)
        if kind == LONG:
            return b"".join(struct.pack(endian + "I", v) for v in values), len(values)
        raw = b"".join(struct.pack(endian + "II", n, d) for n, d in values)
        return raw, len(values)

    def ifd_size(entries):
        return 2 + 12 * len(entries) + 4

    # Lay out IFD0, then the EXIF and GPS IFDs, then all out-of-line values.
    sub = [e for e in (exif_ifd, gps_ifd) if e is not None]
    if exif_ifd is not None:
        ifd0.append((exif.TAG_EXIF_IFD, LONG, 0))
    if gps_ifd is not None:
        ifd0.append((exif.TAG_GPS_IFD, LONG, 0))
    offsets = [8]
    for entries in [ifd0, *sub]:
        offsets.append(offsets[-1] + ifd_size(entries))
    data_offset = offsets[-1]
    pointer_values = {}
    k = 1
    if exif_ifd is not None:
        pointer_values[exif.TAG_EXIF_IFD] = offsets[k]
        k += 1
    if gps_ifd is not None:
        pointer_values[exif.TAG_GPS_IFD] = offsets[k]

    blobs = bytearray()
    for entries in [ifd0, *sub]:
        out += struct.pack(endian + "H", len(entries))
        for tag, kind, values in sorted(entries, key=lambda e: e[0]):
            if tag in pointer_values:
                values = pointer_values[tag]
            raw, count = encode(kind, values)
            out += struct.pack(endian + "HHI", tag, kind, count)
            if len(raw) <= 4:
                out += raw.ljust(4, b"\0")
            else:
                out += struct.pack(endian + "I", data_offset + len(blobs))
                blobs += raw
        out += struct.pack(endian + "I", 0)
    return bytes(out + blobs)
