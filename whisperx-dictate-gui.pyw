#!/usr/bin/env python3
"""Same as whisperx-dictate-gui.py; use pythonw/this file so Explorer does not open a console."""

import os
import sys
from pathlib import Path

# GUI: avoid an extra console when the launcher uses python.exe (Python Install Manager, py, venv).
if sys.platform == "win32":
    _script = Path(__file__).resolve()
    _exe = Path(sys.executable).resolve()
    if _exe.name.lower() == "python.exe":
        _pyw = _exe.with_name("pythonw.exe")
        if _pyw.is_file():
            os.environ["WHISPERX_DICTATE_GUI_DISABLE_CONSOLE"] = "1"
            argv = [str(_pyw), str(_script)] + sys.argv[1:]
            os.execv(str(_pyw), argv)

# If we are already pythonw.exe (or no pythonw next to this interpreter), continue normally.
os.environ.setdefault("WHISPERX_DICTATE_GUI_DISABLE_CONSOLE", "1")

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
