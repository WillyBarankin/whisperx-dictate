"""Windows: register ``keyboard``-module hotkeys under US layout, then restore (fixes RU-at-start)."""

from __future__ import annotations

import contextlib
import os

# US English (QWERTY) — stable VK/scan mapping for ctrl+space, ctrl+alt+n, etc.
_US_KLID = "00000409"
_KLF_ACTIVATE = 1


@contextlib.contextmanager
def hotkey_registration_layout_fix():
    """Activate US keyboard layout in the current thread during ``add_hotkey`` calls, then restore."""
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    old_hkl = wintypes.HANDLE(user32.GetKeyboardLayout(0))
    try:
        us_hkl = user32.LoadKeyboardLayoutW(_US_KLID, _KLF_ACTIVATE)
        if us_hkl:
            user32.ActivateKeyboardLayout(us_hkl, 0)
        yield
    finally:
        if old_hkl:
            user32.ActivateKeyboardLayout(old_hkl, 0)
