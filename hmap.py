#!/usr/bin/env python3
"""Harvest Moon: Animal Parade recompilation pipeline. Run `python hmap.py --help`."""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is required")

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

if sys.platform == "win32":
    # Started from PowerShell / Explorer: find MSYS2's UCRT64 compilers without asking the user to edit PATH.
    import os
    import shutil

    if not shutil.which("cmake") or not shutil.which("g++"):
        for root in (os.environ.get("MSYS2_ROOT", ""), r"C:\msys64", r"C:\tools\msys64", os.path.expanduser(r"~\msys64")):
            bin_dir = Path(root) / "ucrt64" / "bin" if root else None
            if bin_dir and (bin_dir / "g++.exe").exists():
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                break

from hmaptool.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
