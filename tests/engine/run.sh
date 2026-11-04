#!/usr/bin/env sh
# Build the engine headless (python hmap.py build --headless) first; then:
#   sh tests/engine/run.sh
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
ENGINE="$ROOT/extern/wiiparty-recomp"
OUT="$ENGINE/build/out-hmap"
BIN="$ROOT/build/tests"
mkdir -p "$BIN"
c++ -std=c++17 -O1 -Wall -Wextra -I"$ENGINE/engine/include" "$ROOT/tests/engine/test_nunchuk.cpp" \
    -Wl,--start-group "$OUT/games/hmap/libhmap_code.a" "$OUT/engine/libwp_engine.a" -Wl,--end-group \
    "$OUT/third_party/libwp_dolphin_dsp.a" -lpthread -o "$BIN/test_nunchuk"
c++ -std=c++17 -O1 -Wall -Wextra -I"$ENGINE/engine/include" -I"$ENGINE/engine/src/gpu" "$ROOT/tests/engine/test_efb_policy.cpp" \
    -Wl,--start-group "$OUT/games/hmap/libhmap_code.a" "$OUT/engine/libwp_engine.a" -Wl,--end-group \
    "$OUT/third_party/libwp_dolphin_dsp.a" -lpthread -o "$BIN/test_efb_policy"
c++ -std=c++17 -O1 -Wall -Wextra -I"$ENGINE/engine/include" "$ROOT/tests/engine/test_speed.cpp" \
    -Wl,--start-group "$OUT/games/hmap/libhmap_code.a" "$OUT/engine/libwp_engine.a" -Wl,--end-group \
    "$OUT/third_party/libwp_dolphin_dsp.a" -lpthread -o "$BIN/test_speed"
c++ -std=c++17 -O1 -Wall -Wextra -I"$ENGINE/engine/include" "$ROOT/tests/engine/test_present.cpp" \
    -Wl,--start-group "$OUT/games/hmap/libhmap_code.a" "$OUT/engine/libwp_engine.a" -Wl,--end-group \
    "$OUT/third_party/libwp_dolphin_dsp.a" -lpthread -o "$BIN/test_present"
cd "$ENGINE" && "$BIN/test_nunchuk" && "$BIN/test_efb_policy" && "$BIN/test_speed" && "$BIN/test_present"
