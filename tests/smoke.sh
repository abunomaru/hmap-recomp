#!/usr/bin/env sh
# End-to-end smoke test with a SYNTHETIC disc layout (no game data):
# analyze -> recompile -> headless build -> engine Nunchuk test.
# It overwrites games/hmap/extracted and the analysis outputs, so run it in CI or a
# throwaway checkout, not next to your real extracted disc.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
if [ -e games/hmap/extracted ] && [ ! -e games/hmap/extracted/.synthetic ]; then
    echo "games/hmap/extracted holds a real disc; refusing to overwrite it" >&2
    exit 1
fi
python3 - <<'PY'
import struct, sys
from pathlib import Path
sys.path[:0] = ["tests", "tools"]
import synthetic
from hmaptool import disc
root = Path("games/hmap/extracted")
(root / "sys").mkdir(parents=True, exist_ok=True)
(root / "files").mkdir(exist_ok=True)
(root / ".synthetic").write_text("synthetic test data\n")
image, _, _ = synthetic.build()
(root / "sys" / "main.dol").write_bytes(image)
boot = bytearray(0x440)
boot[0:6] = b"RBIEE9"
boot[0x18:0x1C] = struct.pack(">I", disc.WII_MAGIC)
(root / "sys" / "boot.bin").write_bytes(bytes(boot))
PY
rm -f build/hmap/main.orig.dol
python3 hmap.py analyze --skip-dtk
python3 hmap.py recompile
python3 hmap.py build --headless
sh tests/engine/run.sh
