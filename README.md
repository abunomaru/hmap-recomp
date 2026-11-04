# Harvest Moon: Animal Parade — Recomp

A static recompilation of **Harvest Moon: Animal Parade** (Wii, 2009) into a native PC
executable, aiming for **60 fps**, higher resolutions and PC controls.

> **Status: scaffolding / pre-alpha.** The pipeline runs from a disc image to a built
> executable, and it has been tested end to end on a *synthetic* DOL. It has **not yet been run
> on the real game**. That is the next step, on your own machine with your own disc.

No game files are in this repository, and none will ever be. You supply your own legally dumped
disc. Every tool reads it locally.

## How it works

```
your disc (ISO/WBFS/RVZ)
   │  nodtool              extract
   ▼
main.dol (+ .rel modules)
   │  decomp-toolkit       function boundaries
   │  sdk_finder.py        locate OSSaveContext, OSLoadContext, setjmp, longjmp, … by code pattern
   │  Dolphin map (opt.)   names
   ▼
games/hmap/analysis/*.csv + game.toml
   │  patches/             optional static patches (60 fps work goes here)
   │  engine recompiler    PowerPC → C++ (Wii Party Recomp's recompiler, unchanged)
   ▼
C++  ──CMake/Ninja──►  native executable on the Wii Party Recomp engine
                       (GX → OpenGL/D3D11, DSP audio, IOS, NAND saves, Wii Remote + Nunchuk)
```

The engine is [Wii Party Recomp](https://github.com/arelkair/wiiparty-recomp) (GPL-3.0),
pinned as a git submodule in `extern/wiiparty-recomp`. It was picked because it emulates the
Wii's hardware below the SDK (GPU FIFO, DSP, IPC/IOS, EXI, VI) instead of replacing
game-specific functions, so it is game-agnostic and only needs a small per-game plug-in.
This repo adds that plug-in (`games/hmap/`), the analysis tools, and engine patches
(`engine-patches/`, applied automatically). Patch `0002` adds the **Nunchuk**, which the
engine did not have and which Animal Parade needs for movement.

## Quick start (on your laptop)

Requirements: Python 3.11+, Git, CMake 3.24+, Ninja, GCC 13+ or Clang 17+
(MinGW-w64 GCC on Windows). On Linux, also the SDL3 build dependencies:

```bash
# Debian/Ubuntu
sudo apt install g++ cmake ninja-build python3 git curl libx11-dev libxext-dev libxrandr-dev \
  libxcursor-dev libxi-dev libxss-dev libxtst-dev libxkbcommon-dev libwayland-dev wayland-protocols \
  libdecor-0-dev libegl-dev libgl-dev libpulse-dev libasound2-dev libudev-dev libdbus-1-dev
```

```bash
git clone --recursive https://github.com/abunomaru/hmap-recomp
cd hmap-recomp
python hmap.py setup                       # links the game plug-in, downloads nodtool + dtk (checksummed)
python hmap.py extract ~/games/hmap.rvz    # RBIEE9 / RBIP99 / RBIJ99
python hmap.py analyze                     # function list + SDK addresses
python hmap.py recompile
python hmap.py build
python hmap.py run
python hmap.py doctor                      # shows what is missing at any point
```

Or run it all at once: `python hmap.py all ~/games/hmap.rvz`.

If `analyze` reports missing SDK functions, export a Dolphin symbol map
(`Symbols > Generate Symbols From > Signature Database`, then `Symbols > Save Symbol Map`) and run
`python hmap.py analyze --dolphin-map path/to/RBIEE9.map`. You can also add `address,name` lines to
`games/hmap/analysis/manual_symbols.csv`.

For a headless home server (build only, no window), see [docs/LOCAL_SERVER.md](docs/LOCAL_SERVER.md).

## Controls (defaults)

| Wii | Keyboard / mouse | Gamepad |
|---|---|---|
| Nunchuk stick | W A S D | left stick |
| Nunchuk C / Z | C / X | L / ZL (left trigger) |
| A / B | Enter, Space, left click / Backspace, right click | per engine mapping |
| D-pad | arrow keys | D-pad |
| Pointer | mouse | gyro (if the pad has one) |
| + / − / 1 / 2 / Home | + / − / 1 / 2 / H | |
| **Fast-forward** (hold) | Tab | |

Set `input.nunchuk=0` in `games/hmap/settings.ini` (or `WP_NUNCHUK=0`) to unplug the Nunchuk.
Keys can be rebound in the same file.

## Settings worth knowing

`games/hmap/settings.ini` (in the engine folder, created on first run) or **F10** in game:

| Setting | Values | Notes |
|---|---|---|
| `video.scale` | 1–6 | internal resolution multiplier (1 = Wii's 640×480) |
| `video.efb_to_ram` | 2 auto (default), 1 always, 0 never | how GPU-rendered copies reach game memory. `1` is exact but slow in this game (it renders ~20 copies per frame); `0` is fastest but may break photo-album thumbnails, as in Dolphin |
| `input.nunchuk` | 1 / 0 | Nunchuk plugged in |
| `system.fast_forward` | 2–16 (default 4) | speed while holding the fast-forward key (Tab). Speeds up the game clock and screen refresh; parts limited by audio or disc timing speed up less |

## 60 fps

The game runs at 30 fps (25 on PAL). A recompiled build will run at the game's own rate,
without the slowdowns the real Wii has. Getting **60** takes extra work, described in
[docs/60FPS.md](docs/60FPS.md). `python hmap.py fps-scan` is the first step: it lists where the
frame lock most likely lives.

## Repository layout

| Path | What |
|---|---|
| `hmap.py` | the pipeline CLI |
| `tools/hmaptool/` | DOL reader, SDK pattern finder, symbol import, patcher, fps scanner, DSP finder, decompressors |
| `games/hmap/` | engine plug-in: `game.toml`, `CMakeLists.txt`, `game.cpp`, `analysis/` |
| `engine-patches/` | changes to the engine, as reviewable patch files |
| `patches/` | static patches for the game's `main.dol` |
| `extern/wiiparty-recomp/` | engine + recompiler (submodule, pinned) |
| `tests/` | `python -m unittest discover -s tests` (no game data needed) and `tests/engine/run.sh` |
| `docs/` | [ROADMAP](docs/ROADMAP.md), [PIPELINE](docs/PIPELINE.md), [60FPS](docs/60FPS.md), [LOCAL_SERVER](docs/LOCAL_SERVER.md) |

## Legal

An independent project, not affiliated with Nintendo, Marvelous or Natsume. Bring your own
legally obtained copy of the game. Licensed GPL-3.0-or-later (same as the engine).
