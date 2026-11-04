#!/usr/bin/env sh
# Validates the Direct3D TEV shader (general, early-depth and sample specialised variants,
# engine patch 0012) with Khronos glslangValidator's HLSL front end. Needs glslang-tools and
# the engine patches applied (any hmap.py command applies them). Skips if glslang is missing.
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
if ! command -v glslangValidator >/dev/null 2>&1; then
    echo "glslangValidator not installed; skipping shader validation"
    exit 0
fi
OUT="$ROOT/build/shaders"
python3 -I "$ROOT/tests/shaders/hlsl_variants.py" "$ROOT/extern/wiiparty-recomp/engine/src/gpu/gx_render.cpp" "$OUT"
status=0
for f in "$OUT"/*.hlsl; do
    if glslangValidator -D -S frag -e pixel_main -V "$f" -o /dev/null >"$f.log" 2>&1; then
        echo "ok   $(basename "$f")"
    else
        echo "FAIL $(basename "$f")"; cat "$f.log"; status=1
    fi
done
if glslangValidator -D -S vert -e vertex_main -V "$OUT/general.hlsl" -o /dev/null >"$OUT/vs.log" 2>&1; then
    echo "ok   vertex shader"
else
    echo "FAIL vertex shader"; cat "$OUT/vs.log"; status=1
fi
exit $status
