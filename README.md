# Harvest Moon: Animal Parade — Recomp

A static recompilation of **Harvest Moon: Animal Parade** (Wii, 2009) into a native PC
executable, aiming for **60 fps**, higher resolutions and PC controls.

> **Status: alpha.** Boots and plays on the NTSC-U disc (Windows, Ryzen laptop): the opening
> cutscene and early game run, the Nunchuk works. Light scenes reach ~30 fps; heavy scenes are
> still slow with the built-in renderer, which is why the [aurora](https://github.com/encounter/aurora)
> renderer (the one behind WiiCompiled / Super Paper Mario PC) is being integrated: it builds and
> starts on Linux and in CI; try it with `play.bat --aurora`.

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

## Playing (Windows)

1. **Once:** install the tools (PowerShell):
   ```powershell
   winget install --id Git.Git -e
   winget install --id Python.Python.3.12 -e
   winget install --id MSYS2.MSYS2 -e
   C:\msys64\usr\bin\bash.exe -lc "pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-clang mingw-w64-ucrt-x86_64-lld mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-abseil-cpp"
   [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";C:\msys64\ucrt64\bin", "User")
   ```
   Close and reopen PowerShell, then:
   ```powershell
   cd $HOME\Desktop
   git -c core.autocrlf=false clone --recursive https://github.com/abunomaru/hmap-recomp hmap
   ```
2. **Put your files in `hmap\assets\`** (see [assets/README.md](assets/README.md)): your disc image
   (`.iso`, `.rvz`, `.wbfs`...), optionally `.xdelta` patches in `assets\patches\` (e.g.
   *Harvest Moon: Pride Parade*) and texture packs in `assets\textures\`.
3. **Double-click `play.bat`.** The first run extracts, translates and compiles the game (20-40
   minutes); later runs start in seconds and redo only what changed (new patch, new version).
   `play.bat --aurora` uses the aurora renderer (D3D12/Vulkan).

In game: **Tab** fast-forward, **F10** settings, **F11** fullscreen (aurora renderer).

**Dolphin saves:** `py hmap.py import-save` copies your Dolphin save of the game into the port
(found automatically; the port's previous save is backed up), and `py hmap.py export-save` copies
it back. Pride Parade saves use the `CBIEE9` ID: add `--game-id CBIEE9` if needed.

## Building by hand / Linux

Requirements: Python 3.11+, Git, CMake 3.24+, Ninja, GCC 13+ or Clang 17+ (MinGW-w64 on
Windows; clang for the aurora renderer). On Linux, also the SDL3 build dependencies:

```bash
# Debian/Ubuntu
sudo apt install g++ clang cmake ninja-build python3 git curl xdelta3 libx11-dev libxext-dev libxrandr-dev \
  libxcursor-dev libxi-dev libxss-dev libxtst-dev libxkbcommon-dev libwayland-dev wayland-protocols \
  libdecor-0-dev libegl-dev libgl-dev libpulse-dev libasound2-dev libudev-dev libdbus-1-dev libvulkan-dev
```

```bash
./play.sh                                  # same as play.bat: assets/ -> running game
python hmap.py doctor                      # shows what is missing at any point
# the individual steps, if you need them:
python hmap.py setup                       # links the game plug-in, downloads nodtool + dtk (checksummed)
python hmap.py extract ~/games/hmap.rvz    # RBIEE9 / RBIP99 / RBIJ99 / CBIEE9 (Pride Parade)
python hmap.py analyze --skip-dtk          # function list + SDK addresses
python hmap.py recompile
python hmap.py build [--aurora]
python hmap.py run [--log perf.txt] [--scale 2]
```

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
| `video.specialized_shaders` | 1 (default) / 0 | a shader compiled for each TEV setup the game uses (Direct3D 11), built in the background; 0 = always the general shader |
| `video.vertex_threads` | 0 auto (default), 1 off, N | CPU threads for vertex processing (the engine transforms and lights vertices on the CPU; auto = cores − 2, max 8). Set 1 if geometry looks wrong |
| `video.interpolation` | 0 (default), 120, 180, 240 | aurora renderer only: in-between frames for smoother motion (experimental) |
| `input.nunchuk` | 1 / 0 | Nunchuk plugged in |
| `system.fast_forward` | 2–16 (default 4) | speed while holding the fast-forward key (Tab). Speeds up the game clock and screen refresh; parts limited by audio or disc timing speed up less |

## Harvest Moon: Pride Parade

The fan patch by frogglegged (same-sex marriage, swapped player models) is an `.xdelta` for the
clean NTSC-U ISO. Put it in `assets/patches/` and its optional texture pack in
`assets/textures/`; `play.bat` converts your disc to ISO if needed, applies the patch, checks the
result is a valid disc (it becomes `CBIEE9`) and builds from it. Saves are kept separately from the
unpatched game (the disc ID differs).

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
| `docs/` | [ROADMAP](docs/ROADMAP.md), [PIPELINE](docs/PIPELINE.md), [60FPS](docs/60FPS.md), [RESEARCH](docs/RESEARCH.md), [LOCAL_SERVER](docs/LOCAL_SERVER.md) |

## Legal

An independent project, not affiliated with Nintendo, Marvelous or Natsume. Bring your own
legally obtained copy of the game. Licensed GPL-3.0-or-later (same as the engine).
