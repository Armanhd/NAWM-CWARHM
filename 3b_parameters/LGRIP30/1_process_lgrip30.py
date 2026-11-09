#!/usr/bin/env python3
"""CAMELS-SPAT-compatible LGRIP30 attributes."""

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "CATEGORICAL")
)

from processing import main

if __name__ == "__main__":
    main("lgrip30")
