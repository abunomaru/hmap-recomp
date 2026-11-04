"""Decompressors for the formats Wii games use for code modules and archives.

* Yaz0 (Nintendo's run-length LZ, "Yaz0" magic)
* LZ10 / LZ11 (the GBA/DS/Wii BIOS-style LZ77 variants, first byte 0x10 / 0x11)

`detect` recognises the format from the header; `decompress` dispatches.
"""

from __future__ import annotations

import struct


def detect(data: bytes) -> str | None:
    if data[:4] == b"Yaz0":
        return "yaz0"
    if len(data) >= 4 and data[0] == 0x11:
        return "lz11"
    if len(data) >= 4 and data[0] == 0x10:
        return "lz10"
    return None


def decompress(data: bytes) -> bytes:
    kind = detect(data)
    if kind == "yaz0":
        return yaz0(data)
    if kind == "lz11":
        return lz11(data)
    if kind == "lz10":
        return lz10(data)
    raise ValueError("unknown compression format")


def _copy(out: bytearray, distance: int, length: int) -> None:
    if distance > len(out):
        raise ValueError(f"back-reference distance {distance} before start of output")
    start = len(out) - distance
    for i in range(length):
        out.append(out[start + i])


def yaz0(data: bytes) -> bytes:
    if data[:4] != b"Yaz0":
        raise ValueError("missing Yaz0 magic")
    size = struct.unpack_from(">I", data, 4)[0]
    out = bytearray()
    pos = 16
    while len(out) < size:
        flags = data[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                out.append(data[pos])
                pos += 1
            else:
                b0, b1 = data[pos], data[pos + 1]
                pos += 2
                distance = ((b0 & 0x0F) << 8 | b1) + 1
                count = b0 >> 4
                if count == 0:
                    length = data[pos] + 0x12
                    pos += 1
                else:
                    length = count + 2
                _copy(out, distance, length)
    return bytes(out[:size])


def _lz_header(data: bytes, magic: int) -> tuple[int, int]:
    if data[0] != magic:
        raise ValueError(f"expected LZ header byte {magic:#x}")
    size = data[1] | data[2] << 8 | data[3] << 16
    pos = 4
    if size == 0:
        size = struct.unpack_from("<I", data, 4)[0]
        pos = 8
    return size, pos


def lz10(data: bytes) -> bytes:
    size, pos = _lz_header(data, 0x10)
    out = bytearray()
    while len(out) < size:
        flags = data[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                b0, b1 = data[pos], data[pos + 1]
                pos += 2
                _copy(out, ((b0 & 0x0F) << 8 | b1) + 1, (b0 >> 4) + 3)
            else:
                out.append(data[pos])
                pos += 1
    return bytes(out[:size])


def lz11(data: bytes) -> bytes:
    size, pos = _lz_header(data, 0x11)
    out = bytearray()
    while len(out) < size:
        flags = data[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if not flags & (1 << bit):
                out.append(data[pos])
                pos += 1
                continue
            b0 = data[pos]
            indicator = b0 >> 4
            if indicator == 0:
                b1, b2 = data[pos + 1], data[pos + 2]
                pos += 3
                length = ((b0 & 0x0F) << 4 | b1 >> 4) + 0x11
                distance = ((b1 & 0x0F) << 8 | b2) + 1
            elif indicator == 1:
                b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
                pos += 4
                length = ((b0 & 0x0F) << 12 | b1 << 4 | b2 >> 4) + 0x111
                distance = ((b2 & 0x0F) << 8 | b3) + 1
            else:
                b1 = data[pos + 1]
                pos += 2
                length = indicator + 1
                distance = ((b0 & 0x0F) << 8 | b1) + 1
            _copy(out, distance, length)
    return bytes(out[:size])


# ---------------------------------------------------------------- encoders (tests)


def yaz0_store(data: bytes) -> bytes:
    """Literal-only Yaz0 stream (valid, uncompressed). Used by the tests."""
    out = bytearray(b"Yaz0" + struct.pack(">I", len(data)) + bytes(8))
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        out.append(0xFF)
        out += chunk
    return bytes(out)


def lz_store(data: bytes, magic: int) -> bytes:
    """Literal-only LZ10/LZ11 stream. Used by the tests."""
    out = bytearray([magic, len(data) & 0xFF, len(data) >> 8 & 0xFF, len(data) >> 16 & 0xFF])
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        out.append(0x00)
        out += chunk
    return bytes(out)
