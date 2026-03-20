"""Bundled GUI/tray icon helpers."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
ASSETS_DIR = _PKG_DIR / "assets"
_WINDOWS_APP_ID = "WhisperXDictate.Desktop.GUI.1"


def prepare_windows_taskbar_identity() -> None:
    """Set explicit AppUserModelID so taskbar icon is not tied to python.exe."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_WINDOWS_APP_ID)
    except Exception:
        pass


def _first_existing(*names: str) -> Path | None:
    for name in names:
        path = ASSETS_DIR / name
        if path.is_file():
            return path
    return None


def _lanczos():
    from PIL import Image

    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def _square_rgba(path: Path, edge: int):
    from PIL import Image

    im = Image.open(path).convert("RGBA")
    w, h = im.size
    if w != h:
        s = min(w, h)
        left, top = (w - s) // 2, (h - s) // 2
        im = im.crop((left, top, left + s, top + s))
    if max(im.size) != edge:
        im = im.resize((edge, edge), _lanczos())
    return im


def _windows_hwnd_chain(wid: int):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    out: list[int] = []
    seen: set[int] = set()
    hwnd = int(wid)
    for _ in range(8):
        if hwnd and hwnd not in seen:
            seen.add(hwnd)
            out.append(hwnd)
        parent = int(user32.GetParent(wintypes.HWND(hwnd)))
        if not parent or parent == hwnd:
            break
        hwnd = parent
    return out


def _apply_windows_native_icons(root, ico: Path) -> None:
    """Force big/small icons via WM_SETICON for all relevant HWNDs."""
    import ctypes
    from ctypes import wintypes

    try:
        root.update_idletasks()
        wid = int(root.winfo_id())
    except Exception:
        return

    user32 = ctypes.windll.user32
    path = str(ico.resolve())

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1

    load_image = user32.LoadImageW
    load_image.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        wintypes.INT,
        wintypes.INT,
        wintypes.UINT,
    ]
    load_image.restype = wintypes.HANDLE

    send_message = user32.SendMessageW
    send_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    send_message.restype = wintypes.LPARAM

    def load_icon(candidates: tuple[int, ...]):
        for sz in candidates:
            h = load_image(None, path, IMAGE_ICON, sz, sz, LR_LOADFROMFILE)
            if h:
                return h
        return None

    h_big = load_icon((256, 128, 64, 48, 32))
    h_small = load_icon((32, 24, 16))
    if not h_big and not h_small:
        return

    for hwnd in _windows_hwnd_chain(wid):
        if h_big:
            send_message(wintypes.HWND(hwnd), WM_SETICON, ICON_BIG, h_big)
        if h_small:
            send_message(wintypes.HWND(hwnd), WM_SETICON, ICON_SMALL, h_small)


def apply_tk_window_icon(root) -> None:
    """Set Tk window icon, including a native Windows fallback for taskbar quality."""
    import tkinter as tk

    ico = _first_existing("app.ico")
    photo_source = _first_existing("app.png", "app.ico")

    if ico and os.name == "nt":
        try:
            root.iconbitmap(default=str(ico.resolve()))
        except tk.TclError:
            pass

        # Some Tk builds keep a blurry taskbar icon unless WM_SETICON is pushed explicitly.
        root.after_idle(lambda: _apply_windows_native_icons(root, ico))
        root.after(250, lambda: _apply_windows_native_icons(root, ico))

    if not photo_source:
        return
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return
    try:
        raw = Image.open(photo_source)
        edge = 512 if max(raw.size) >= 400 else 256
        photo = ImageTk.PhotoImage(_square_rgba(photo_source, edge))
        root._whisperx_bundle_icon_photo = photo
        root.iconphoto(True, photo)
    except Exception:
        pass


def load_pil_icon_for_tray():
    """Return a PIL image for the tray if bundled assets exist."""
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
        if max(im.size) > 128:
            im = im.copy()
            im.thumbnail((64, 64), _lanczos())
        return im
    except Exception:
        return None
