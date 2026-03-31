#!/usr/bin/env python3
"""GUI entry: adds project root to sys.path so `python whisperx-dictate-gui.py` works without install."""

import sys
from pathlib import Path

_root_g = Path(__file__).resolve().parent
if str(_root_g) not in sys.path:
    sys.path.insert(0, str(_root_g))

from whisperx_dictate.entry_support import require_pynput

require_pynput()

from whisperx_dictate.win_gui_console import apply_gui_console_preference

apply_gui_console_preference()

from whisperx_dictate.gui_app import gui_main

if __name__ == "__main__":
    gui_main()
