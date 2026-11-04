"""Locate the DSP (audio) microcode embedded in main.dol.

The engine can run the AX microcode through its DSP interpreter, or - much faster -
as code translated ahead of time by recompiler/dsp/recomp_dsp.py, which needs
games/hmap/analysis/dsp_ucode.csv (name, DOL file offset, size, checksum).

Two ways to fill it in:

1. `from_dump`: run the game once with WP_DUMP_DSP_CODE=<dir>; the engine writes
   dsp_<checksum>.bin for every microcode it uploads. This searches the DOL for
   that exact image. Always correct.
2. `scan`: heuristic search for the DSP exception-vector table a microcode starts
   with (eight 2-word slots, mostly `jmp` = 0x029F or `rti` = 0x02FF). Only a
   starting point; confirm with method 1.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .dol import Dol

JMP = 0x029F
RTI = 0x02FF
HALT = 0x0021
NOP = 0x0000


def checksum(data: bytes) -> int:
    """Same function as recompiler/dsp/recomp_dsp.py and engine/src/audio/dsp.cpp."""
    value = 0
    for byte in data:
        value = ((value * 31) ^ byte) & 0xFFFFFFFF
    return value


@dataclass
class Candidate:
    dol_offset: int
    size: int
    checksum: int
    score: int


def from_dump(dol: Dol, image: bytes) -> Candidate | None:
    offset = bytes(dol.data).find(image)
    if offset < 0:
        return None
    return Candidate(offset, len(image), checksum(image), 100)


def _vector_score(blob: bytes, offset: int) -> int:
    score = 0
    for slot in range(8):
        word = struct.unpack_from(">H", blob, offset + slot * 4)[0]
        if word == JMP:
            score += 2
        elif word in (RTI, HALT):
            score += 1
        elif word != NOP:
            return 0
    return score


def scan(dol: Dol, sizes=(0x2000, 0x1000, 0x1800)) -> list[Candidate]:
    blob = bytes(dol.data)
    found = []
    for section in dol.sections:
        if section.executable:
            continue
        start, end = section.offset, section.offset + section.size
        for offset in range(start - start % 32 + 32 if start % 32 else start, end - 32, 32):
            score = _vector_score(blob, offset)
            if score < 12:
                continue
            for size in sizes:
                if offset + size <= end:
                    found.append(Candidate(offset, size, checksum(blob[offset:offset + size]), score))
                    break
    return sorted(found, key=lambda c: -c.score)


def write_csv(path, name: str, candidate: Candidate) -> None:
    path.write_text(
        "name,dol_offset,size,checksum\n"
        f"{name},{candidate.dol_offset:x},{candidate.size:x},{candidate.checksum:08x}\n",
        encoding="utf-8",
    )
