"""Reader/writer for the DOL executable format (GameCube/Wii main.dol)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

TEXT_SECTIONS = 7
DATA_SECTIONS = 11
SECTION_COUNT = TEXT_SECTIONS + DATA_SECTIONS
HEADER_SIZE = 0x100


@dataclass
class Section:
    index: int
    offset: int
    address: int
    size: int

    @property
    def executable(self) -> bool:
        return self.index < TEXT_SECTIONS

    @property
    def name(self) -> str:
        return f"text{self.index}" if self.executable else f"data{self.index - TEXT_SECTIONS}"

    def contains(self, address: int, length: int = 1) -> bool:
        return self.address <= address and address + length <= self.address + self.size


class Dol:
    def __init__(self, data: bytes):
        if len(data) < HEADER_SIZE:
            raise ValueError("file is too small to be a DOL")
        self.data = bytearray(data)
        header = struct.unpack_from(">" + "I" * 0x39, self.data, 0)
        offsets = header[0:18]
        addresses = header[18:36]
        sizes = header[36:54]
        self.bss_address, self.bss_size, self.entry = header[54], header[55], header[56]
        self.sections = [
            Section(i, offsets[i], addresses[i], sizes[i])
            for i in range(SECTION_COUNT)
            if sizes[i] and offsets[i]
        ]
        for section in self.sections:
            if section.offset + section.size > len(self.data):
                raise ValueError(f"{section.name} runs past the end of the file")
            if not 0x80000000 <= section.address < 0x81800000:
                raise ValueError(f"{section.name} has an unexpected load address {section.address:#x}")

    @classmethod
    def load(cls, path: str | Path) -> "Dol":
        return cls(Path(path).read_bytes())

    # ------------------------------------------------------------------ lookup

    def section_at(self, address: int, length: int = 1) -> Section | None:
        for section in self.sections:
            if section.contains(address, length):
                return section
        return None

    def file_offset(self, address: int, length: int = 1) -> int | None:
        section = self.section_at(address, length)
        if section is None:
            return None
        return section.offset + (address - section.address)

    def is_code(self, address: int) -> bool:
        section = self.section_at(address, 4)
        return section is not None and section.executable and address % 4 == 0

    def read(self, address: int, length: int) -> bytes | None:
        offset = self.file_offset(address, length)
        if offset is None:
            return None
        return bytes(self.data[offset:offset + length])

    def word(self, address: int) -> int | None:
        raw = self.read(address, 4)
        return None if raw is None else struct.unpack(">I", raw)[0]

    def words(self, start: int, end: int) -> list[int]:
        out = []
        for address in range(start, end, 4):
            value = self.word(address)
            if value is None:
                break
            out.append(value)
        return out

    def code_ranges(self) -> list[tuple[int, int]]:
        return [(s.address, s.address + s.size) for s in self.sections if s.executable]

    def data_ranges(self) -> list[tuple[int, int]]:
        return [(s.address, s.address + s.size) for s in self.sections if not s.executable]

    def find_bytes(self, needle: bytes) -> list[int]:
        """Every address (in loaded sections) at which `needle` occurs."""
        found = []
        for section in self.sections:
            blob = bytes(self.data[section.offset:section.offset + section.size])
            start = 0
            while True:
                index = blob.find(needle, start)
                if index < 0:
                    break
                found.append(section.address + index)
                start = index + 1
        return found

    # ------------------------------------------------------------------ writes

    def write(self, address: int, raw: bytes) -> None:
        offset = self.file_offset(address, len(raw))
        if offset is None:
            raise ValueError(f"{address:#010x}+{len(raw):#x} is not inside a loaded DOL section")
        self.data[offset:offset + len(raw)] = raw

    def write_word(self, address: int, value: int) -> None:
        self.write(address, struct.pack(">I", value & 0xFFFFFFFF))

    def to_bytes(self) -> bytes:
        return bytes(self.data)


def build(sections: list[tuple[int, bytes, bool]], entry: int, bss: tuple[int, int] = (0, 0)) -> bytes:
    """Build a DOL from (address, contents, executable) tuples. Used by the tests."""
    offsets = [0] * SECTION_COUNT
    addresses = [0] * SECTION_COUNT
    sizes = [0] * SECTION_COUNT
    body = bytearray()
    text_index, data_index = 0, TEXT_SECTIONS
    for address, contents, executable in sections:
        if executable:
            index, text_index = text_index, text_index + 1
        else:
            index, data_index = data_index, data_index + 1
        while len(body) % 32:
            body.append(0)
        offsets[index] = HEADER_SIZE + len(body)
        addresses[index] = address
        sizes[index] = len(contents)
        body += contents
    header = struct.pack(">" + "I" * 0x39, *offsets, *addresses, *sizes, bss[0], bss[1], entry)
    header += bytes(HEADER_SIZE - len(header))
    return header + bytes(body)
