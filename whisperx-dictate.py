#!/usr/bin/env python3
"""CLI entry: adds project root to sys.path so `python whisperx-dictate.py` works without install."""

import sys
from pathlib import Path

_root_m = Path(__file__).resolve().parent
if str(_root_m) not in sys.path:
    sys.path.insert(0, str(_root_m))

from whisperx_dictate.cli import cli_main

if __name__ == "__main__":
    cli_main()
