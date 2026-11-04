"""Bundles the DLLs a Windows build needs next to the executable.

An MSYS2 build links against DLLs in ucrt64/bin (libstdc++, libgcc, winpthread, abseil for the
aurora build) and aurora adds Dawn, SDL3 and the DXC DLLs Dawn loads at run time. Those are only
found while the MSYS2 bin directory is on PATH, so a game started from Explorer or a plain
PowerShell would fail with STATUS_DLL_NOT_FOUND (0xC0000135). This walks the PE import tables
(no external tool needed) and copies every DLL that is not part of Windows beside the game.
"""

from __future__ import annotations

import os
import shutil
import struct
from pathlib import Path

# Loaded with LoadLibrary rather than imported, so the import walk cannot see them.
DYNAMIC = ("dxcompiler.dll", "dxil.dll")


def imports(path: Path) -> list[str]:
    """Names of the DLLs a PE file imports (normal and delay-load import tables)."""
    data = path.read_bytes()
    if data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    sections_count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directories = optional + (112 if magic == 0x20B else 96)
    sections = []
    for i in range(sections_count):
        entry = optional + optional_size + 40 * i
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, entry + 8)
        sections.append((vaddr, max(vsize, rsize), raw))

    def offset(rva: int) -> int | None:
        for vaddr, size, raw in sections:
            if vaddr <= rva < vaddr + size:
                return rva - vaddr + raw
        return None

    def name_at(rva: int) -> str:
        start = offset(rva)
        if start is None:
            return ""
        end = data.index(b"\0", start)
        return data[start:end].decode("ascii", "replace")

    names: list[str] = []
    for index, stride, name_field in ((1, 20, 12), (13, 32, 4)):  # import, delay import
        rva, size = struct.unpack_from("<II", data, directories + 8 * index)
        position = offset(rva) if rva and size else None
        while position is not None and position + stride <= len(data):
            entry = data[position:position + stride]
            if not any(entry):
                break
            name_rva = struct.unpack_from("<I", entry, name_field)[0]
            if name_rva:
                name = name_at(name_rva)
                if name:
                    names.append(name)
            position += stride
    return names


def _search_dirs(exe: Path, extra: list[Path]) -> list[Path]:
    dirs: list[Path] = [exe.parent, *extra]
    for tool in ("clang++", "g++", "gcc", "cmake"):
        found = shutil.which(tool)
        if found:
            dirs.append(Path(found).resolve().parent)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            dirs.append(Path(entry))
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()
    unique: list[Path] = []
    for d in dirs:
        try:
            resolved = d.resolve()
        except OSError:
            continue
        # Never copy DLLs that belong to Windows itself.
        if resolved == windows or windows in resolved.parents:
            continue
        if resolved.is_dir() and resolved not in unique:
            unique.append(resolved)
    return unique


def bundle(exe: Path, build_dir: Path | None = None) -> list[str]:
    """Copies the non-system DLLs `exe` needs into its directory. Returns the names copied."""
    extra: list[Path] = []
    if build_dir is not None and build_dir.is_dir():
        # aurora's prebuilt Dawn and SDL3 live somewhere in the build tree's _deps.
        for dll in list(build_dir.rglob("webgpu_dawn.dll")) + list(build_dir.rglob("SDL3.dll")):
            extra.append(dll.parent)
    dirs = _search_dirs(exe, extra)
    target = exe.parent
    copied: list[str] = []
    seen: set[str] = set()
    pending: list[Path] = [exe]

    def locate(name: str) -> Path | None:
        for d in dirs:
            candidate = d / name
            if candidate.is_file():
                return candidate
        return None

    for name in DYNAMIC:
        source = locate(name)
        if source is not None:
            pending.append(source)

    while pending:
        current = pending.pop()
        if current.parent.resolve() != target.resolve():
            destination = target / current.name
            if not destination.exists() or destination.stat().st_size != current.stat().st_size \
                    or destination.stat().st_mtime < current.stat().st_mtime:
                shutil.copy2(current, destination)
                copied.append(current.name)
            current = destination
        for name in imports(current):
            key = name.lower()
            if key in seen or key.startswith(("api-ms-win-", "ext-ms-")):
                continue
            seen.add(key)
            source = locate(name)
            if source is not None:
                pending.append(source)
    return copied
