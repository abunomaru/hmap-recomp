# Pipeline reference

All commands run from the repo root as `python hmap.py <command>`.

| Command | Reads | Writes |
|---|---|---|
| `setup` | | `extern/wiiparty-recomp/games/hmap` link, applies `engine-patches/`, `tools/bin/{nodtool,dtk}` |
| `extract DISC` | disc image | `games/hmap/extracted/`, `build/hmap/main.orig.dol`, `build/hmap/inputs.json`, `extern/…/build/hmap/rel/*.rel` |
| `info` | original DOL | (prints sections, modules) |
| `analyze` | original DOL, optional Dolphin map, `analysis/manual_symbols.csv` | `analysis/dol_functions.csv`, `analysis/symbols.csv`, `analysis/sdk_report.txt`, `game.toml` |
| `patch` | original DOL, `patches/` | `games/hmap/extracted/sys/main.dol` |
| `fps-scan` | original DOL, analysis | `build/hmap/fps_scan.json` |
| `find-dsp [--dump F]` | DOL (+ dump) | `analysis/dsp_ucode.csv` |
| `recompile` | patched DOL, RELs, analysis | `extern/…/build/hmap/generated/{dol,modules,dsp}` |
| `build [--headless]` | generated code | `extern/…/build/out-hmap/hmap[.exe]` |
| `run [--dump-dsp DIR]` | executable, extracted disc | `games/hmap/nand/` (saves), `settings.ini` |

## Where each analysis input comes from

* **Function boundaries:** decomp-toolkit (`dtk dol split`) analyses the DOL. `--skip-dtk`
  falls back to a simple scan (entry point, `bl` targets, prologues). The engine's
  recompiler then finds more entries itself (branch targets, data pointers, jump tables).
* **SDK functions the engine needs** (`hle_functions.csv` + `OSSaveContext`, `setjmp`):
  `tools/hmaptool/sdk_finder.py` matches what each function does. For example,
  `OSLoadContext` is the only function with `lmw r13,0x34(r3)`, GQR restores, `mtsrr0` and
  `rfi`. A Dolphin map or `manual_symbols.csv` takes priority over the pattern finder, and
  conflicts are listed in `sdk_report.txt`.
* **DSP microcode:** run once with `python hmap.py run --dump-dsp dumps/`, then
  `python hmap.py find-dsp --dump dumps/dsp_<n>.bin`. Without it, audio uses the DSP
  interpreter (correct, but slower).

## Engine patches

`engine-patches/*.patch` are applied to the submodule's working tree on every command
(skipped if already applied). The submodule is set to `ignore = dirty`, so this does not show in
`git status`. To change the engine:

```bash
cd extern/wiiparty-recomp
# edit…
git diff -- <files of your change> > ../../engine-patches/000N-description.patch
git checkout -- . && cd ../.. && python hmap.py doctor   # re-applies all patches
```

When bumping the submodule, re-check that every patch still applies.

## Debugging switches (engine environment variables)

`WP_LOG_WIIMOTE=1` (Wii Remote traffic), `WP_LOG_INPUT=1`, `WP_DUMP_DSP_CODE=dir`,
`WP_NUNCHUK=0`, `WP_INPUT_SCRIPT=@file` (scripted input). Build with
`-DWP_TRACE_CALLS=ON` to log every guest function entry.
