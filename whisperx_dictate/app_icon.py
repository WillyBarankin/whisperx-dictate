"""Bundled GUI/tray icons: add ``app.ico`` and/or ``app.png`` under ``whisperx_dictate/assets/``."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
ASSETS_DIR = _PKG_DIR / "assets"


def _first_existing(*names: str) -> Path | None:
    for name in names:
        p = ASSETS_DIR / name
        if p.is_file():
            return p
    return None


def apply_tk_window_icon(root) -> None:
    """Set the Tk window/taskbar icon from bundled assets."""
    import tkinter as tk

    ico = _first_existing("app.ico")
    if ico and os.name == "nt":
        try:
            root.iconbitmap(default=str(ico))
            return
        except tk.TclError:
            pass

    path = _first_existing("app.png", "app.ico")
    if not path:
        return
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return
    try:
        im = Image.open(path)
        photo = ImageTk.PhotoImage(im)
        root.iconphoto(True, photo)
        root._whisperx_bundle_icon_photo = photo
    except Exception:
        pass


def load_pil_icon_for_tray():
    """Return a PIL image for the tray if a bundled file exists, else None."""
    path = _first_existing("app.png", "app.ico")
    if not path:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(path)
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        w, h = im.size
        if max(w, h) > 128:
            im = im.copy()
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            im.thumbnail((64, 64), resample)
        return im
    except Exception:
        return None
