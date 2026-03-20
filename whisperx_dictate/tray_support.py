"""System tray support (optional: pip install pystray pillow)."""

import threading

from whisperx_dictate import app_icon


def tray_available():
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def make_tray_image():
    from PIL import Image, ImageDraw
    w = 64
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    try:
        dr.rounded_rectangle((2, 2, w - 3, w - 3), radius=10, fill=(41, 98, 255, 255), outline=(255, 255, 255, 255), width=2)
    except AttributeError:
        dr.rectangle((2, 2, w - 3, w - 3), fill=(41, 98, 255, 255), outline=(255, 255, 255, 255), width=2)
    dr.text((22, 16), "W", fill=(255, 255, 255, 255))
    return img


def create_tray_icon(title, on_open, on_quit_after_stop):
    """Run pystray in a daemon thread. Returns Icon.

    on_open: callable () — schedule GUI on main thread with root.after.
    on_quit_after_stop: callable () — run on main thread after icon.stop() (unregister, destroy).
    """
    import pystray
    from pystray import MenuItem as item

    image = app_icon.load_pil_icon_for_tray() or make_tray_image()

    def open_handler(icon, menu_item):
        on_open()

    def quit_handler(icon, menu_item):
        icon.stop()
        on_quit_after_stop()

    menu = pystray.Menu(
        item("Open WhisperX Dictate", open_handler, default=True),
        item("Exit", quit_handler),
    )
    icon = pystray.Icon("whisperx_dictate", image, title, menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon
