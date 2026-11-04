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


def _patch_targets(patch: Path) -> tuple[set[str], set[str]]:
    """Files a patch modifies, and files it creates."""
    modified, created = set(), set()
    previous = ""
    for line in patch.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            (created if previous == "--- /dev/null" else modified).add(path)
        previous = line.strip()
    return modified, created


def _engine_git_path(name: str) -> Path:
    path = subprocess.run(["git", "rev-parse", "--git-path", name], cwd=ENGINE,
                          check=True, capture_output=True, text=True).stdout.strip()
    return Path(path) if Path(path).is_absolute() else ENGINE / path


def apply_engine_patches(verbose: bool = False) -> list[str]:
    """Apply engine-patches/*.patch, in order, to the submodule's working tree.

    The engine stays a pristine pinned upstream commit in git; our fixes live as
    reviewable patch files. A stamp (inside the submodule's git dir) records which
    patch contents were applied. When the set changes, every file the patches touch
    is restored to the pinned commit and the whole series is applied again, so later
    patches can build on earlier ones (0004 on top of 0002) without confusing the
    "already applied?" check."""
    import hashlib

    patches = sorted(ENGINE_PATCHES.glob("*.patch"))
    digest = hashlib.sha256()
    for patch in patches:
        digest.update(patch.name.encode() + b"\0" + patch.read_bytes())
    wanted = digest.hexdigest()
    stamp = _engine_git_path("hmap-engine-patches.stamp")
    if stamp.exists() and stamp.read_text().strip() == wanted:
        if verbose:
            print("engine patches up to date")
        return []

    modified, created = set(), set()
    for patch in patches:
        m, c = _patch_targets(patch)
        modified |= m
        created |= c
    tracked = sorted(modified - created)
    if tracked:
        subprocess.run(["git", "checkout", "--", *tracked], cwd=ENGINE, check=True, capture_output=True)
    for path in created:
        (ENGINE / path).unlink(missing_ok=True)

    applied = []
    for patch in patches:
        args = ["git", "apply", str(patch)]
        result = subprocess.run(args, cwd=ENGINE, capture_output=True, text=True)
        if result.returncode != 0:
            # Windows checkouts with core.autocrlf=true have CRLF files.
            result = subprocess.run(["git", "apply", "--ignore-whitespace", str(patch)], cwd=ENGINE, capture_output=True, text=True)
        if result.returncode != 0:
            stamp.unlink(missing_ok=True)
            raise SystemExit(f"engine patch {patch.name} does not apply:\n{result.stderr}\n"
                             "On Windows, clone with: git -c core.autocrlf=false clone --recursive ...")
        applied.append(patch.name)
        print(f"engine patch applied: {patch.name}")
    stamp.write_text(wanted + "\n")
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
