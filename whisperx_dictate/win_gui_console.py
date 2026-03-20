"""Windows: optionally allocate a console when the GUI is run with pythonw (no console by default)."""

from __future__ import annotations

import os
import sys

_applied = False


def apply_gui_console_preference() -> None:
    """If ``--console`` or WHISPERX_DICTATE_GUI_CONSOLE is set, attach a console when none exists (pythonw / .pyw).

    Strips ``--console`` from ``sys.argv``. Safe to call multiple times: only the first call runs.
    """
    global _applied
    if _applied:
        return
    _applied = True

    if sys.platform != "win32":
        return

    env_console = (os.environ.get("WHISPERX_DICTATE_GUI_CONSOLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    want_attach = "--console" in sys.argv or env_console

    if "--console" in sys.argv:
        sys.argv.remove("--console")

    if want_attach:
        _ensure_attached_console()


def _ensure_attached_console() -> None:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow():
            return
        if not kernel32.AllocConsole():
            return
        conout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
        conin = open("CONIN$", "r", encoding="utf-8", errors="replace")
        sys.stdout = conout
        sys.stderr = conout
        sys.stdin = conin
    except Exception:
        pass
