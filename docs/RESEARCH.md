# How other Wii ports solve our problems

Notes from reading the source of the other Wii static-recompilation projects, to decide
how to fix Animal Parade's frame rate and how to reach 60 fps. Measurements are from the
user's Ryzen 5 5500U (Vega 7 integrated graphics).

## Where we are

| Fix | Result |
|---|---|
| Patch 0006: per-frame EFB effect copies stay on the GPU | 299 → 0 copies/s written back, 6 → 12 fps |
| Patch 0010: present only new frames | presenting 90% → 0% of the GPU thread |
| Patch 0011: vertex processing on several cores | lighter scenes reach ~30 fps |
| Heavy scenes (hay cutscene, 140k vertices/frame) | still ~12–13 fps, GPU thread ~85% busy, ~600 ms/s in Direct3D draw submission |

The remaining cost is the graphics chip running the engine's pixel shader, and the CPU
doing all vertex work. The engine draws everything with one **ubershader** that reads every
TEV setting at run time, computes gradients for all 8 texture coordinates, and indexes its
TEV register arrays dynamically. AMD GPUs keep dynamically indexed arrays in slow scratch
memory, so integrated Radeons suffer most.

## The other projects

| Project | GX approach | Shaders | Vertex transform | Result |
|---|---|---|---|---|
| [Wii Party Recomp](https://github.com/arelkair/wiiparty-recomp) (our engine) | FIFO-level hardware emulation | one ubershader (D3D11 / GL 4.1) | CPU, one thread (now multi-core with patch 0011) | 60 fps on Wii Party, a light game |
| [wii-recomp](https://github.com/Zontex/wii-recomp) (GPL-2.0+) | FIFO-level hardware emulation, like ours | **a small shader per TEV setup** (`TevKey`, `gx_tev.c` / `gx_shader.c`), disk shader cache | **on the GPU**, a vertex shader per setup (`VertexKey`) | 60 fps at 1080p on a **Raspberry Pi 5** (Wii Fit Plus) |
| [aurora](https://github.com/encounter/aurora) (MIT), used by [WiiCompiled](https://github.com/patchzyy/wiicompiled), Metaforce, Dusklight | GX API level (the game's GX functions are replaced) | per `ShaderConfig` (TEV, texgen, lighting baked in), pipeline cache shippable with releases | on the GPU | Mario Kart Wii at 60 fps + interpolation |
| [WiiCompiled's aurora fork](https://github.com/patchzyy/aurora-wiicompiled) (MIT) | as aurora | as aurora | on the GPU | **frame interpolation** to 120/180/240 Hz (`lib/gx/frame_interpolation.cpp`) |

### Conclusions

1. **Specialised shaders are the standard answer.** Both fast ports generate a shader per
   TEV configuration and cache it (Dolphin does the same). With the settings compiled in,
   loops unroll, the register arrays become plain registers, and unused texture
   coordinates and gradients disappear.
2. **Vertex transform belongs on the GPU.** Both fast ports upload raw vertex data plus the
   XF matrices and transform in a vertex shader. That removes the CPU vertex work and
   shrinks what is uploaded per vertex (our `ScreenVertex` is 144 bytes, with all 8
   texture coordinates and both colours always sent).
3. **60 fps needs (2).** WiiCompiled's interpolation matches each draw with the previous
   frame's by a hash of pipeline + texture + geometry, interpolates the position, normal and
   projection matrices, and redraws in-between frames with them. That only works when
   matrices are uniforms that a vertex shader applies, not when vertices arrive already
   transformed, as they do in our engine today.
4. **Switching to aurora is not a small swap.** Its FIFO path carries host pointers through
   a custom command. WiiCompiled had to replace the game's GX functions with ~6,600 lines
   of HLE glue. Our engine emulates the GPU below the SDK, which is game-agnostic. Keeping
   that and borrowing the shader and vertex designs from wii-recomp (same architecture,
   GPL-compatible) is the shorter path.
5. **wii-recomp isn't an option on Windows yet** (macOS/Linux/Raspberry Pi, Vulkan), but its
   renderer is the best reference for our engine.

## Plan

1. **Specialised TEV pixel shaders** (engine patch), D3D11 first (the user's platform),
   then GL: key = TEV stage setup + indirect setup + texgen count + alpha test + fog +
   blend flags. Generate HLSL with the settings as literals, compile on a background
   thread, and keep drawing with the ubershader until the variant is ready, so it never
   stutters. Cache compiled shaders on disk.
2. **GPU vertex transform**: upload raw positions, normals, colours and texture
   coordinates plus the matrix palette, and do position, normal, lighting and texgen in a
   vertex shader generated per vertex setup. Keep the CPU path as a fallback.
3. **Frame interpolation for 60 fps**, following WiiCompiled: draw identity hashing,
   matrix pairing, in-between frames at the retrace that the 30 fps game does not use.
