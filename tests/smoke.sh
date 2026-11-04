#!/usr/bin/env sh
# End-to-end smoke test with a SYNTHETIC disc layout (no game data):
# analyze -> recompile -> headless build -> engine Nunchuk test.
# It overwrites games/hmap/extracted and the analysis outputs, so run it in CI or a
# throwaway checkout, not next to your real extracted disc.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
sh tests/make_synthetic_game.sh
python3 hmap.py analyze --skip-dtk
python3 hmap.py recompile
python3 hmap.py build --headless
sh tests/engine/run.sh
sh tests/shaders/validate.sh
