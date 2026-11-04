#!/usr/bin/env python3
"""Harvest Moon: Animal Parade recompilation pipeline. Run `python hmap.py --help`."""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is required")

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from hmaptool.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
