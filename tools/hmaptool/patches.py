"""Static patches applied to main.dol before it is recompiled.

Two input formats:

1. Native TOML (preferred), one file per patch in patches/:

    [patch]
    name = "Example"
    description = "What it does and why"
    game_ids = ["RBIEE9"]       # optional; empty = any region
    enabled = true

    [[patch.write]]
    address = 0x80012340
    original = 0x38600002       # optional but strongly recommended: verified first
    value = 0x38600001

    [[patch.write]]
    address = 0x80012344
    original_bytes = "4E800020"
    bytes = "60000000"

2. Gecko / Action Replay codes (.txt, as Dolphin shows them). RAM-write types
   00/02/04 (8/16/32-bit, with repeat counts) and 06 (byte string) are applied to the
   DOL image. Code types that need a runtime handler (conditionals, C2 assembly
   inserts, pointer codes) are rejected with an explanation instead of silently
   dropped; port those by hand to a TOML patch (or to a runtime hook).

A static patch is equivalent to the Gecko code for code addresses. For data
addresses it only sets the initial value (Gecko re-applies every frame), so the
tool warns about writes into data sections.
"""

from __future__ import annotations

import struct
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .dol import Dol


class PatchError(Exception):
    pass


@dataclass
class Write:
    address: int
    data: bytes
    original: bytes | None = None
    source: str = ""


@dataclass
class Patch:
    name: str
    path: Path | None = None
    description: str = ""
    game_ids: list[str] = field(default_factory=list)
    enabled: bool = True
    writes: list[Write] = field(default_factory=list)

    def applies_to(self, game_id: str) -> bool:
        return self.enabled and (not self.game_ids or game_id in self.game_ids)


def _hex_bytes(text: str) -> bytes:
    cleaned = "".join(text.split())
    if len(cleaned) % 2:
        raise PatchError(f"odd number of hex digits in {text!r}")
    return bytes.fromhex(cleaned)


def load_toml(path: Path) -> Patch:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if "patch" not in data:
        raise PatchError(f"{path}: missing [patch] table")
    table = data["patch"]
    patch = Patch(
        name=table.get("name", path.stem),
        path=path,
        description=table.get("description", ""),
        game_ids=list(table.get("game_ids", [])),
        enabled=bool(table.get("enabled", True)),
    )
    for index, entry in enumerate(table.get("write", [])):
        where = f"{path.name} write #{index + 1}"
        if "address" not in entry:
            raise PatchError(f"{where}: missing address")
        if "value" in entry:
            payload = struct.pack(">I", entry["value"] & 0xFFFFFFFF)
        elif "bytes" in entry:
            payload = _hex_bytes(entry["bytes"])
        else:
            raise PatchError(f"{where}: needs value or bytes")
        original = None
        if "original" in entry:
            original = struct.pack(">I", entry["original"] & 0xFFFFFFFF)
        elif "original_bytes" in entry:
            original = _hex_bytes(entry["original_bytes"])
        if original is not None and len(original) != len(payload):
            raise PatchError(f"{where}: original and new data differ in length")
        patch.writes.append(Write(entry["address"], payload, original, where))
    return patch


GECKO_UNSUPPORTED = {
    0x08: "serial write (08)",
    0x20: "conditional (20-2E)",
    0x40: "base address / pointer codes (40-4E)",
    0x60: "repeat / goto (60-6E)",
    0x80: "gecko register ops (80-8E)",
    0xC0: "execute / insert asm (C0-C6)",
    0xE0: "terminators (E0-F0) after a conditional",
    0xF2: "checksum / hook codes (F2-FE)",
}


def parse_gecko(text: str, name: str = "gecko") -> Patch:
    """Parse Gecko RAM-write codes into static writes."""
    words: list[tuple[int, int, int]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("$", "*", "[")):
            continue
        parts = line.split()
        if len(parts) != 2 or any(len(p) != 8 for p in parts):
            raise PatchError(f"{name}:{number}: expected two 8-digit hex words, got {raw!r}")
        words.append((number, int(parts[0], 16), int(parts[1], 16)))

    patch = Patch(name=name)
    index = 0
    while index < len(words):
        number, first, second = words[index]
        index += 1
        code_type = (first >> 24) & 0xFE
        address = 0x80000000 | (first & 0x01FFFFFF)
        where = f"{name}:{number}"
        if code_type == 0x00:
            count = (second >> 16) + 1
            patch.writes.append(Write(address, bytes([second & 0xFF]) * count, None, where))
        elif code_type == 0x02:
            count = (second >> 16) + 1
            patch.writes.append(Write(address, struct.pack(">H", second & 0xFFFF) * count, None, where))
        elif code_type == 0x04:
            patch.writes.append(Write(address, struct.pack(">I", second), None, where))
        elif code_type == 0x06:
            length = second
            payload = bytearray()
            while len(payload) < length:
                if index >= len(words):
                    raise PatchError(f"{where}: string write runs past the end of the code")
                _, a, b = words[index]
                index += 1
                payload += struct.pack(">II", a, b)
            patch.writes.append(Write(address, bytes(payload[:length]), None, where))
        elif first == 0xE0000000 and second == 0x80008000:
            continue  # full terminator, no effect on unconditional writes
        else:
            kind = next((label for base, label in sorted(GECKO_UNSUPPORTED.items(), reverse=True) if code_type >= base), "unknown")
            raise PatchError(
                f"{where}: code type {code_type:02X} ({kind}) needs runtime support and cannot be applied "
                "statically; port it to a TOML patch or a runtime hook"
            )
    return patch


def load(path: Path) -> Patch:
    if path.suffix == ".toml":
        return load_toml(path)
    return parse_gecko(path.read_text(encoding="utf-8"), path.stem)


def discover(directory: Path) -> list[Patch]:
    if not directory.exists():
        return []
    files = sorted(p for p in directory.rglob("*") if p.suffix in (".toml", ".txt") and p.is_file())
    return [load(path) for path in files if not path.name.startswith("_")]


@dataclass
class Report:
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def apply(dol: Dol, patches: list[Patch], game_id: str) -> Report:
    report = Report()
    # Validate everything first so a bad patch never leaves a half-patched image.
    planned: list[tuple[Patch, Write]] = []
    for patch in patches:
        if not patch.applies_to(game_id):
            report.skipped.append(f"{patch.name} (disabled or not for {game_id})")
            continue
        for write in patch.writes:
            section = dol.section_at(write.address, len(write.data))
            if section is None:
                raise PatchError(
                    f"{patch.name} {write.source}: {write.address:#010x} is not inside main.dol "
                    "(BSS, heap or a REL module) - it cannot be patched statically"
                )
            if write.original is not None:
                current = dol.read(write.address, len(write.original))
                if current != write.original and current != write.data:
                    raise PatchError(
                        f"{patch.name} {write.source}: expected {write.original.hex()} at "
                        f"{write.address:#010x} but found {current.hex()} - wrong region or revision?"
                    )
            if not section.executable:
                report.warnings.append(
                    f"{patch.name} {write.source}: {write.address:#010x} is in {section.name}; a static write "
                    "only sets the initial value (Gecko would rewrite it every frame)"
                )
            planned.append((patch, write))
    for patch, write in planned:
        dol.write(write.address, write.data)
    for patch in patches:
        if patch.applies_to(game_id):
            report.applied.append(f"{patch.name} ({len(patch.writes)} writes)")
    return report
