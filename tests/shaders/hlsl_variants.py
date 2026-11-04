"""Extract the engine's TEV shader and write the general + sample specialised variants,
mirroring specialized_source() in gx_render.cpp (engine patch 0012).
Used by tests/shaders/validate.sh."""
import random
import sys
from pathlib import Path

src_file, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
s = src_file.read_text()
marker = 'const char* kShaderSource = R"HLSL('
start = s.index(marker) + len(marker)
body = s[start:s.index(')HLSL";', start)]


def early(b):
    return b.replace("PixelOutput pixel_main(", "[earlydepthstencil] PixelOutput pixel_main(", 1)


def vec(v):
    return "uint4(%s)" % ", ".join(f"{x}u" for x in v)


def special(stages, tevind, header, swaps, indirect, fog_mode, is_early):
    out = "#define SPECIALIZED\n"
    out += "static const uint4 cstage[16] = {" + ", ".join(vec(stages[i] if i < len(stages) else [0, 0, 0, 0]) for i in range(16)) + "};\n"
    out += "static const uint4 ctevind[16] = {" + ", ".join(vec([tevind[i] if i < len(tevind) else 0, 0, 0, 0]) for i in range(16)) + "};\n"
    out += f"static const uint4 cheader = {vec(header)};\nstatic const uint4 cswaps = {vec(swaps)};\nstatic const uint4 cindirect = {vec(indirect)};\n"
    out += f"static const int cfog_mode = {fog_mode};\n"
    return out + (early(body) if is_early else body)


out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "general.hlsl").write_text(body)
(out_dir / "general_early.hlsl").write_text(early(body))
swaps = [0xE4, 0xE4, 0xE4, 0xE4]
one = [[(15 << 12) | (8 << 8) | (10 << 4) | 15 | (1 << 19), (7 << 13) | (4 << 10) | (5 << 7) | (7 << 4) | (1 << 19), (1 << 6), 12 | (28 << 5)]]
(out_dir / "spec_1stage.hlsl").write_text(special(one, [0], [1, 0x00470000, 0, 0], swaps, [1 << 8, 0, 0, 0], 0, False))
random.seed(7)


def rnd_stage():
    return [random.getrandbits(24), random.getrandbits(24), random.getrandbits(10) | (1 << 6), random.getrandbits(10)]


three = [rnd_stage() for _ in range(3)]
(out_dir / "spec_3stage_fog.hlsl").write_text(special(three, [0, 0, 0], [3, 0x00C80080, 0x1FF, 2 | (1 << 2)], swaps, [2 << 8, 0, 0, 0], 2 | 16, True))
eight = [rnd_stage() for _ in range(8)]
tevind = [random.getrandbits(21) for _ in range(8)]
(out_dir / "spec_8stage_indirect.hlsl").write_text(
    special(eight, tevind, [8, 0x00FFFFFF, 0, 1], [0xE4, 0x1B, 0x00, 0xFF], [2 | (4 << 8), random.getrandbits(12), random.getrandbits(16), random.getrandbits(16)], 10, False))
print("written", sorted(p.name for p in out_dir.glob("*.hlsl")))
