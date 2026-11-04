# Getting to 60 fps

Animal Parade renders at **30 fps** (25 on PAL at 50 Hz) and drops below that outdoors, at
night and in some cutscenes, even on a real Wii. A native build removes the slowdown but keeps
the 30 fps cap, because the cap is in the game's own code. There are two ways past it.

## Step 1: find the lock

```bash
python hmap.py analyze --dolphin-map RBIEE9.map   # names make the scan much better
python hmap.py fps-scan
```

The scanner reports three kinds of evidence (`tools/hmaptool/fps_scan.py`):

| Evidence | What it looks like | Typical meaning |
|---|---|---|
| `double-retrace-wait` | a function calls `VIWaitForRetrace` twice | renders every 2nd field |
| `retrace-wait-loop` | `VIWaitForRetrace` inside a backwards loop | waits N retraces |
| `retrace-count-compare` | `VIGetRetraceCount()` then `cmpwi …, 2` | "has a 2-field frame passed?" |
| constants | `30.0f`, `1/30`, `60.0f`, `2.0f`… in data | per-frame timesteps |

Confirm in Dolphin: put a breakpoint on each candidate, check it runs once per frame, and
change the compare value or loop count with the memory editor to see what happens. A good
sign is the whole game running at double speed, which means logic and rendering are locked
together.

## Option A: frame interpolation (recommended first)

WiiCompiled's aurora fork already ships this for Mario Kart Wii (`lib/gx/frame_interpolation.cpp`, MIT). See [RESEARCH.md](RESEARCH.md): it needs GPU-side vertex transform first.

Game logic stays at 30 Hz. The renderer draws an extra in-between frame, which is what
WiiCompiled does for Mario Kart Wii above 60 Hz and what N64 recomps (RT64) do.

How it would work in this engine, which sees GX command streams rather than a scene graph:

1. In `engine/src/gpu/gx.cpp`, record every frame's draws: vertex data references plus the
   position/normal/texture matrices loaded through XF (`GXLoadPosMtxImm`/indexed loads)
   and the projection.
2. Match draws between frame N-1 and frame N by their order and matrix slot, and hash the
   vertex array pointer and texture to reject mismatches.
3. At display time, present `lerp(N-1, N, 0.5)` matrices at the half step, then frame N.
   Anything that does not match (UI, particles, cuts) is drawn as in frame N, not interpolated.
4. Cut detection: a camera jump above a threshold turns interpolation off for that frame.

Pros: game logic is untouched, so no gameplay bugs. Cons: costs one frame of latency, may show
artifacts on skinned meshes if skinning is done on the CPU, and needs real work in the GX layer.

## Option B: run the game logic at 60 Hz

Patch the lock found in step 1 so the game advances every field, then halve every per-frame
timestep. In a farming sim that means auditing:

- the in-game clock (minutes per frame), crop/animal timers, NPC schedules
- animation playback rates, camera smoothing, physics/movement speeds
- menu and text speeds, and fixed-length waits counted in frames
- audio sync for cutscenes

Express each change as a TOML patch in `patches/` with `original` values, so it is
reviewable and region-checked. Gecko 60 fps codes from the community (if any appear) can
be dropped in as `.txt` when they only use RAM writes.

Pros: true 60 Hz input and simulation. Cons: easy to miss a frame-counted timer, which then
runs at double speed (crops growing twice as fast, NPCs arriving early). It needs long play
tests.

## PAL

PAL's 50 Hz mode runs at 25 fps with different timing constants. Prefer making the 60 Hz
(EuRGB60) path the default for PAL discs so all regions share one 60 fps implementation.
