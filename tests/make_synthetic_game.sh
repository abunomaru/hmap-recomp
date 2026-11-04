#!/usr/bin/env sh
# Writes a SYNTHETIC disc layout (hand-assembled test code, no Nintendo files) into
# games/hmap/extracted so the pipeline can be built and tested anywhere (CI, servers).
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
python3 - <<'PY'
import struct, sys
sys.path[:0] = ["tests", "tools"]
import synthetic
from hmaptool import disc, project
project.link_game()  # symlink, or a synced copy where symlinks are unavailable (Windows)
root = project.extracted()
if root.exists() and not (root / ".synthetic").exists():
    sys.exit(f"{root} holds a real disc; refusing to overwrite it")
(root / "sys").mkdir(parents=True, exist_ok=True)
(root / "files").mkdir(exist_ok=True)
(root / ".synthetic").write_text("synthetic test data\n")
image, _, _ = synthetic.build()
(root / "sys" / "main.dol").write_bytes(image)
boot = bytearray(0x440)
boot[0:6] = b"RBIEE9"
boot[0x18:0x1C] = struct.pack(">I", disc.WII_MAGIC)
(root / "sys" / "boot.bin").write_bytes(bytes(boot))
project.original_dol().unlink(missing_ok=True)
print(f"synthetic game written to {root}")
PY
