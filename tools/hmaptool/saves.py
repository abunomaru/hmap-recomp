"""Save import/export between Dolphin and this port.

Both keep a Wii NAND with the same layout: title/00010000/<game id in hex>/data/. Animal Parade
saves are data/save/s0000.sv ... s0002.sv plus banner.bin. RBIE (NTSC-U) = 52424945, CBIE (Pride
Parade) = 43424945, RBIP = 52424950, RBIJ = 52424A4A.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from . import project


def title_hex(game_id: str) -> str:
    return game_id[:4].encode("ascii").hex()


def dolphin_nand_candidates() -> list[Path]:
    home = Path.home()
    candidates = []
    if sys.platform == "win32" or os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        candidates += [appdata / "Dolphin Emulator" / "Wii", home / "Documents" / "Dolphin Emulator" / "Wii"]
    elif sys.platform == "darwin":
        candidates += [home / "Library" / "Application Support" / "Dolphin" / "Wii"]
    else:
        candidates += [home / ".local" / "share" / "dolphin-emu" / "Wii", home / ".dolphin-emu" / "Wii",
                       home / ".var" / "app" / "org.DolphinEmu.dolphin-emu" / "data" / "dolphin-emu" / "Wii"]
    return candidates


def save_dir(nand_root: Path, game_id: str) -> Path:
    return nand_root / "title" / "00010000" / title_hex(game_id) / "data"


def engine_nand() -> Path:
    return project.ENGINE_GAME / "nand"


def find_dolphin_save(game_id: str, nand: Path | None = None) -> Path | None:
    for root in ([nand] if nand else dolphin_nand_candidates()):
        folder = save_dir(Path(root), game_id)
        if folder.exists() and any(folder.rglob("*.sv")):
            return folder
    return None


def copy_save(source: Path, target: Path) -> Path | None:
    """Copies a save folder over another, keeping a timestamped backup of the old one."""
    backup = None
    if target.exists() and any(target.iterdir()):
        backup = target.parent / f"data.backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copytree(target, backup)
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return backup
