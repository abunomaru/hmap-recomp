# Roadmap

Rough order. Each phase ends with something you can check.

## Phase 0: scaffolding (done)

- [x] Engine chosen and pinned (Wii Party Recomp, `extern/wiiparty-recomp`)
- [x] `games/hmap` plug-in (game description, CMake, analysis seeds)
- [x] `hmap.py` pipeline: setup → extract → analyze → patch → recompile → build → run
- [x] SDK function finder (OSSaveContext, OSLoadContext, setjmp, longjmp, OSSwitchFiber,
      OSRealModeCall/RealMode, OSPanic) by code pattern, with Dolphin-map and manual fallbacks
- [x] Static patcher (TOML + Gecko RAM writes), with original-bytes verification
- [x] 30 fps lock scanner (`fps-scan`)
- [x] DSP microcode locator (`find-dsp`)
- [x] Engine patch 0001: headless build links
- [x] Engine patch 0002: Nunchuk extension (stick, C/Z, calibration), keyboard + gamepad mapping
- [x] Engine patch 0003: GCC 16 link fix (unused Dolphin DSP logger)
- [x] Engine patch 0004: extension encryption (Dolphin's KeyGen1stParty)
- [x] Tests: Python tools on synthetic DOLs; Nunchuk protocol test against the engine

## Phase 1: first boot (done on RBIEE9, Windows)

- [x] `extract` + `analyze` on RBIEE9: no REL modules; all SDK names found by pattern
      (OSPanic by caller count; setjmp/longjmp not linked in this game; OSSelectThread
      found as the caller of both OSSaveContext and OSLoadContext)
- [x] `recompile`: 19,825 functions, 891,703 instructions, 37 `rfi` + 14 data words +
      143 indirect calls (same profile as Wii Party)
- [x] Boots, creates the save, plays the opening cutscene into the first dialogue
- [x] The game uses the **encrypted** extension protocol: engine patch 0004 ports Dolphin's
      first-party key generation and encryption
- [ ] Frame rate: 6 fps in the opening cutscene. Profile with `hmap.py run --log`
      (CPU vs GPU thread load), then translate the DSP microcode ahead of time

## Phase 1b: performance (Ryzen 5 5500U / Vega 7 reference)

- [x] 0006 EFB copies: per-frame effects stay on the GPU (6 → 12 fps)
- [x] 0010 present only new frames (presenting 90% → 0% of the GPU thread)
- [x] 0011 vertex processing on several cores (light scenes ~30 fps)
- [x] 0012 specialised TEV pixel shaders, compiled in the background (Direct3D 11)
- [ ] Measure 0012 on the hay cutscene; disk cache for compiled variants
- [ ] OpenGL (Linux/macOS) specialisation
- [ ] GPU vertex transform (see RESEARCH.md), then frame interpolation

## Phase 1c: aurora renderer (in progress)

- [x] aurora (WiiCompiled fork, MIT) added as `extern/aurora`; builds on Linux with clang and its prebuilt Dawn
- [x] GX → aurora FIFO bridge (`bridge/`): array bases, textures, palettes, EFB copies, display lists; unit tested
- [ ] Engine integration behind a build option: aurora owns the window; VI retrace → aurora frames;
      aurora draw-done → PE finish interrupt; input from aurora's SDL window
- [ ] EFB copies the CPU reads (photo album) via aurora readback
- [ ] Windows build (Dawn D3D12) tested on the reference laptop; then frame interpolation

## Phase 2: playable at 30 fps

- [ ] New save, play through the first in-game day
- [ ] Photo album (EFB copy to RAM), which Dolphin needed special settings for
- [ ] Night lighting and the watery cave (known Dolphin trouble spots)
- [ ] Audio: `find-dsp --dump`, ahead-of-time DSP translation
- [ ] Save/load through emulated NAND, and save backups
- [ ] Classic Controller support (the game supports it; engine patch similar to 0002)

## Phase 3: PC features

- [ ] Widescreen without stretching (the game has a 16:9 mode; check the projection)
- [ ] Internal resolution scaling (the engine supports up to 6×)
- [ ] Controls page / launcher entries for the Nunchuk actions
- [ ] Packaging: launcher that builds from the user's disc, like Wii Party Recomp's

## Phase 4: 60 fps (see 60FPS.md)

- [ ] Find the frame lock (`fps-scan` + breakpoints)
- [ ] Prototype A: frame interpolation in the GX layer (game logic stays at 30 Hz)
- [ ] Prototype B: logic at 60 Hz (halve timesteps). Audit timers, animation, in-game clock, NPC schedules
- [ ] Pick one and make it a settings toggle, default off until it is stable
- [ ] PAL: run the 60 Hz mode (the game offers EuRGB60) so PAL and NTSC behave the same

## Upstreaming

Engine patches that are not game-specific (0001, the Nunchuk/extension model) should go
upstream to Wii Party Recomp once they are proven in a real game.
