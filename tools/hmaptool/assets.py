"""The assets/ folder: where the player puts their own files.

    assets/
      <your disc image>        .iso .wbfs .rvz .wia .ciso .gcm  (exactly one)
      patches/*.xdelta         optional disc patches (e.g. Harvest Moon: Pride Parade), applied
                               in file-name order to the ISO before extraction
      textures/                optional texture packs (Dolphin format): folders or .zip files
      build/                   created by hmap.py: converted / patched ISO (git-ignored, deletable)

Nothing in assets/ is ever committed (see .gitignore).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import project, toolchain

DISC_SUFFIXES = (".iso", ".wbfs", ".rvz", ".wia", ".ciso", ".gcm")
PATCH_SUFFIXES = (".xdelta", ".vcdiff", ".xd3")


def assets_dir() -> Path:
    return project.ROOT / "assets"


def work_dir() -> Path:
    return assets_dir() / "build"


def find_disc() -> Path:
    root = assets_dir()
    discs = sorted(p for p in root.glob("*") if p.is_file() and p.suffix.lower() in DISC_SUFFIXES)
    if not discs:
        raise SystemExit(f"no disc image found: put your Harvest Moon: Animal Parade dump (.iso/.wbfs/.rvz) in {root}")
    if len(discs) > 1:
        names = ", ".join(p.name for p in discs)
        raise SystemExit(f"more than one disc image in {root} ({names}); keep only the one to play")
    return discs[0]


def find_patches() -> list[Path]:
    folder = assets_dir() / "patches"
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in PATCH_SUFFIXES)


def _fingerprint(paths: list[Path]) -> str:
    """Cheap identity of the inputs (name, size, mtime), to know when to rebuild."""
    digest = hashlib.sha256()
    for path in paths:
        stat = path.stat()
        digest.update(f"{path.name}|{stat.st_size}|{int(stat.st_mtime)}\n".encode())
    return digest.hexdigest()


def prepared_image() -> tuple[Path, str]:
    """The disc image to extract: the user's dump, or a patched ISO built from it.

    Returns (path, fingerprint). Patched ISOs are cached in assets/build/ and rebuilt only when the
    disc or a patch changes."""
    disc = find_disc()
    patches = find_patches()
    fingerprint = _fingerprint([disc, *patches])
    if not patches:
        return disc, fingerprint
    work = work_dir()
    work.mkdir(parents=True, exist_ok=True)
    patched = work / "patched.iso"
    stamp = work / "patched.json"
    if patched.exists() and stamp.exists() and json.loads(stamp.read_text()).get("fingerprint") == fingerprint:
        return patched, fingerprint

    # xdelta patches are made against a plain ISO: convert compressed formats first.
    if disc.suffix.lower() == ".iso":
        source = disc
    else:
        source = work / "source.iso"
        print(f"converting {disc.name} to ISO for patching (one time, needs ~4.7 GB free)")
        subprocess.run([str(toolchain.require("nodtool")), "convert", str(disc), str(source)], check=True)
    xdelta = toolchain.require("xdelta3")
    current = source
    for index, patch in enumerate(patches):
        target = work / f"step{index}.iso"
        print(f"applying {patch.name}")
        result = subprocess.run([str(xdelta), "-d", "-f", "-s", str(current), str(patch), str(target)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(
                f"{patch.name} does not apply to {disc.name}:\n{result.stderr.strip()}\n"
                "xdelta patches need the exact disc they were made from (usually a clean NTSC-U RBIEE9 ISO).")
        if current != source:
            current.unlink()
        current = target
    current.replace(patched)
    if source != disc:
        source.unlink(missing_ok=True)
    stamp.write_text(json.dumps({"fingerprint": fingerprint, "disc": disc.name,
                                 "patches": [p.name for p in patches]}, indent=2) + "\n")
    return patched, fingerprint


def install_textures() -> int:
    """Copies texture packs from assets/textures into the engine's load folder. Returns files copied."""
    source = assets_dir() / "textures"
    if not source.exists():
        return 0
    target = project.ENGINE_GAME / "textures" / "load"
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in sorted(source.iterdir()):
        if item.is_dir():
            for file in item.rglob("*"):
                if file.is_file() and file.suffix.lower() in (".png", ".dds"):
                    shutil.copy2(file, target / file.name)
                    copied += 1
        elif item.suffix.lower() == ".zip":
            with zipfile.ZipFile(item) as archive:
                for member in archive.infolist():
                    name = Path(member.filename).name
                    if not member.is_dir() and Path(name).suffix.lower() in (".png", ".dds") and ".." not in member.filename:
                        (target / name).write_bytes(archive.read(member))
                        copied += 1
        elif item.suffix.lower() in (".png", ".dds"):
            shutil.copy2(item, target / item.name)
            copied += 1
    return copied
