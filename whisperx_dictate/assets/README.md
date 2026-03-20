# Bundled application icon

The repo includes default **`app.png`** and **`app.ico`** (AI-generated dictation-style icon, post-processed to square PNG + multi-size ICO). Replace them to customize.

Place **one or both** of these files here (same folder as this README):

| File | Purpose |
|------|---------|
| `app.ico` | **Windows:** taskbar and title bar via `iconbitmap` (recommended for crisp icons). |
| `app.png` | **Any OS:** window icon via Pillow + Tk; **tray:** used if `pystray` is installed (prefer square, at least 64×64; transparent PNG is fine). |

If neither file exists, the GUI uses the default Tk icon and the tray falls back to a built-in generated glyph.

### Rebuilding `app.ico` from `app.png` (Pillow)

Use **one** RGBA image resized to **256×256** and **`sizes=...` only**. Do **not** rely on `append_images` for ICO — some Pillow versions end up with a single 16×16 entry.

```python
from pathlib import Path
from PIL import Image

assets = Path("whisperx_dictate/assets")
img = Image.open(assets / "app.png").convert("RGBA")
# optional: square center crop if not square
try:
    resample = Image.Resampling.LANCZOS
except AttributeError:
    resample = Image.LANCZOS
base = img.resize((256, 256), resample)
sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
         (64, 64), (72, 72), (96, 96), (128, 128), (256, 256)]
base.save(assets / "app.ico", format="ICO", sizes=sizes)
```

Check: `Image.open("app.ico").info["sizes"]` should list every dimension.

Recommended: add **both** — `.ico` with multiple sizes (16, 32, 48, 256) for Windows, and `.png` for tray / non-Windows.
