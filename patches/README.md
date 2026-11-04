# Patches

`python hmap.py patch` rebuilds `main.dol` from the untouched original
(`build/hmap/main.orig.dol`) plus every enabled patch in this folder, then you run
`python hmap.py recompile && python hmap.py build`.

* `*.toml`: native format, see `_template.toml`. Always fill in `original`, so a
  patch made for one region or revision fails loudly instead of corrupting another.
* `*.txt`: Gecko codes as Dolphin shows them. Only plain RAM writes (`00`/`02`/`04`/`06`)
  can be applied statically. Conditionals, `C2` assembly inserts and pointer codes are
  rejected with an explanation and have to be ported by hand.
* Use `game_ids` to limit a patch to `RBIEE9` (NTSC-U), `RBIP99` (PAL) or `RBIJ99` (NTSC-J).
* `python hmap.py patch --list` shows what will apply. `--reset` restores the original DOL.

Patches contain addresses and instruction words only, never game code or assets.
