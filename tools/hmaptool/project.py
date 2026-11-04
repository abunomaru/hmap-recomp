"""Project layout and the link between this repo and the engine submodule.

    hmap-recomp/
      games/hmap/                 game plug-in (tracked) + local data (git-ignored)
        game.toml CMakeLists.txt game.cpp analysis/
        extracted/ nand/ ...      <- your disc contents and saves, never committed
      extern/wiiparty-recomp/     engine + recompiler (git submodule, pinned)
        games/hmap -> ../../../games/hmap   (symlink; a synced copy on Windows)
        build/hmap/generated/     translated C++ (local)
        build/out-hmap/           CMake build tree (local)
      build/hmap/                 this repo's intermediates (dtk project, reports, original DOL)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME_KEY = "hmap"
REPO_GAME = ROOT / "games" / GAME_KEY
ENGINE = ROOT / "extern" / "wiiparty-recomp"
ENGINE_GAME = ENGINE / "games" / GAME_KEY
WORK = ROOT / "build" / GAME_KEY
PATCHES = ROOT / "patches"

TRACKED = ("game.toml", "CMakeLists.txt", "game.cpp", "analysis")


def engine_present() -> bool:
    return (ENGINE / "recompiler" / "recomp.py").exists()


def ensure_engine() -> None:
    if engine_present():
        return
    print("engine submodule missing; running git submodule update --init")
    subprocess.run(["git", "submodule", "update", "--init", "--recursive"], cwd=ROOT, check=True)
    if not engine_present():
        raise SystemExit("extern/wiiparty-recomp is still missing; clone with --recursive")


def _exclude_in_engine_git() -> None:
    try:
        path = subprocess.run(
            ["git", "rev-parse", "--git-path", "info/exclude"],
            cwd=ENGINE, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return
    exclude = (ENGINE / path) if not Path(path).is_absolute() else Path(path)
    exclude.parent.mkdir(parents=True, exist_ok=True)
    lines = exclude.read_text().splitlines() if exclude.exists() else []
    entry = f"/games/{GAME_KEY}"
    if entry not in lines:
        exclude.write_text("\n".join(lines + [entry]) + "\n")


ENGINE_PATCHES = ROOT / "engine-patches"


def apply_engine_patches(verbose: bool = False) -> list[str]:
    """Apply engine-patches/*.patch to the submodule (idempotent).

    The engine stays a pristine pinned upstream commit in git; our fixes and
    additions for this game live as reviewable patch files and are applied to the
    working tree. A patch that neither applies nor is already applied stops the
    pipeline (usually: the submodule was bumped and the patch needs a rebase)."""
    applied = []
    for patch in sorted(ENGINE_PATCHES.glob("*.patch")):
        def git_apply(*extra):
            return subprocess.run(["git", "apply", *extra, str(patch)], cwd=ENGINE, capture_output=True, text=True)

        if git_apply("--reverse", "--check").returncode == 0:
            if verbose:
                print(f"engine patch already applied: {patch.name}")
            continue
        # Windows checkouts with core.autocrlf=true have CRLF files; retry ignoring whitespace.
        extra = ()
        check = git_apply("--check")
        if check.returncode != 0:
            extra = ("--ignore-whitespace",)
            if git_apply("--reverse", "--check", *extra).returncode == 0:
                continue
            check = git_apply("--check", *extra)
        if check.returncode != 0:
            raise SystemExit(f"engine patch {patch.name} does not apply:\n{check.stderr}\n"
                             "On Windows, clone with: git -c core.autocrlf=false clone --recursive ...")
        git_apply(*extra)
        applied.append(patch.name)
        print(f"engine patch applied: {patch.name}")
    return applied


def link_mode() -> str:
    if ENGINE_GAME.is_symlink():
        return "symlink"
    if ENGINE_GAME.exists():
        return "copy"
    return "missing"


def link_game() -> str:
    """Make the game folder visible to the engine. Returns 'symlink' or 'copy'."""
    ensure_engine()
    _exclude_in_engine_git()
    apply_engine_patches()
    if ENGINE_GAME.is_symlink():
        return "symlink"
    if not ENGINE_GAME.exists():
        try:
            ENGINE_GAME.symlink_to(os.path.relpath(REPO_GAME, ENGINE_GAME.parent), target_is_directory=True)
            return "symlink"
        except OSError:
            ENGINE_GAME.mkdir(parents=True)
    sync_game()
    return "copy"


def sync_game() -> None:
    """Copy the tracked plug-in files into the engine when a symlink is not possible."""
    if ENGINE_GAME.is_symlink():
        return
    for name in TRACKED:
        source = REPO_GAME / name
        target = ENGINE_GAME / name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        elif source.exists():
            shutil.copy2(source, target)


# ------------------------------------------------------------------ data paths (always via the engine view)


def extracted() -> Path:
    return ENGINE_GAME / "extracted"


def boot_bin() -> Path:
    return extracted() / "sys" / "boot.bin"


def main_dol() -> Path:
    return extracted() / "sys" / "main.dol"


def original_dol() -> Path:
    return WORK / "main.orig.dol"


def analysis() -> Path:
    return REPO_GAME / "analysis"


def engine_build() -> Path:
    return ENGINE / "build" / GAME_KEY


def generated() -> Path:
    return engine_build() / "generated"


def modules_dir() -> Path:
    return engine_build() / "rel"


def cmake_dir() -> Path:
    return ENGINE / "build" / f"out-{GAME_KEY}"


def executable() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return cmake_dir() / f"{GAME_KEY}{suffix}"
