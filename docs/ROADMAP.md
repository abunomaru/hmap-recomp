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
- [x] Tests: Python tools on synthetic DOLs; Nunchuk protocol test against the engine

## Phase 1: first boot (needs the real disc)

- [ ] `extract` + `analyze` on RBIEE9. Record which SDK names came from patterns, the map, or by hand
- [ ] Check whether the game uses REL modules (`hmap.py info`)
- [ ] `recompile`: note unsupported instructions and unresolved indirect jumps in the output
- [ ] `build` + `run`: reach the health-and-safety screen, then the title screen
- [ ] Run with `WP_LOG_WIIMOTE=1` and confirm the game initialises the Nunchuk unencrypted
      (writes 0x55 to 0xA400F0). If it asks for encryption, implement it (see Dolphin's
      `WiimoteEmu/Encryption.cpp`)
- [ ] Fix crashes. Likely areas: threads/context switches, cache ops, any `setjmp`/`longjmp` use

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
