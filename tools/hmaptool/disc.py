"""Disc image identification (no extraction - that is nodtool's job)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

WII_MAGIC = 0x5D1C9EA3
GC_MAGIC = 0xC2339F3D


@dataclass(frozen=True)
class Release:
    game_id: str
    region: str
    title: str
    video: str  # native refresh rate the release targets


# The three retail releases (IDs from the Dolphin wiki / GameTDB).
KNOWN_RELEASES = {
    "RBIEE9": Release("RBIEE9", "NTSC-U", "Harvest Moon: Animal Parade", "60 Hz"),
    "RBIP99": Release("RBIP99", "PAL", "Harvest Moon: Animal Parade", "50 Hz (60 Hz optional)"),
    "RBIJ99": Release("RBIJ99", "NTSC-J", "Bokujou Monogatari: Waku Waku Animal March", "60 Hz"),
}


@dataclass
class DiscInfo:
    game_id: str
    revision: int
    title: str
    container: str
    is_wii: bool

    @property
    def release(self) -> Release | None:
        return KNOWN_RELEASES.get(self.game_id)


def parse_disc_header(raw: bytes, container: str) -> DiscInfo:
    if len(raw) < 0x80:
        raise ValueError("disc header is truncated")
    game_id = raw[0:6].decode("ascii", errors="replace")
    revision = raw[7]
    wii_magic = struct.unpack_from(">I", raw, 0x18)[0]
    gc_magic = struct.unpack_from(">I", raw, 0x1C)[0]
    title = raw[0x20:0x80].split(b"\0", 1)[0].decode("ascii", errors="replace")
    if wii_magic != WII_MAGIC and gc_magic != GC_MAGIC:
        raise ValueError(f"{container}: no Wii/GameCube disc magic in the header")
    return DiscInfo(game_id, revision, title, container, wii_magic == WII_MAGIC)


def identify(path: str | Path) -> DiscInfo:
    """Read the disc header from an ISO, WBFS, RVZ/WIA, CISO image or an extracted boot.bin."""
    path = Path(path)
    with open(path, "rb") as handle:
        head = handle.read(0x10000)
    if head[:4] == b"WBFS":
        sector = 1 << head[8]
        return parse_disc_header(head[sector:sector + 0x100], "wbfs")
    if head[:4] in (b"RVZ\x01", b"WIA\x01"):
        # wia_file_head_t is 0x48 bytes; wia_disc_t starts with 4 u32s, then the 0x80-byte disc header.
        return parse_disc_header(head[0x58:0x58 + 0x80], head[:3].decode().lower())
    if head[:4] == b"CISO":
        return parse_disc_header(head[0x8000:0x8100], "ciso")
    return parse_disc_header(head[:0x100], "iso" if path.suffix.lower() != ".bin" else "boot.bin")
