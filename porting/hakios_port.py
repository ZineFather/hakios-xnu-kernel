#!/usr/bin/env python3
"""HakiOS porting tool for the caller-selected device (RAM-only workflow)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hakiosport.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
