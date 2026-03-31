# WhisperX Dictate

Dictation tool based on WhisperX (faster-whisper backend) with global hotkeys, clipboard output, optional note saving, and server/client modes.

## Requirements

- **Full install (local model or you run `--server`):** Python **3.10–3.13** and `requirements.txt` (PyTorch **2.8.x** + **WhisperX**). **Python 3.14+** is not supported for that stack yet.
- **Client-only** (this PC only records and sends audio to another machine via **Server URL** / `--server-url`): you **do not** need PyTorch or WhisperX here. Use **`requirements-client.txt`** instead — lighter deps (mic, hotkeys, typing, GUI). That path can work on **newer Python** when wheels exist for those packages.
- Microphone
- **Windows:** `requirements.txt` uses **`pyaudiowpatch`** (prebuilt wheel, including loopback) instead of building **`pyaudio`**
- **Windows:** `keyboard` global hotkeys may require running terminal as Administrator
- **Windows system-audio loopback:** output indices are auto-mapped to loopback devices when using `pyaudiowpatch`
- **macOS/Linux:** PortAudio (for example `brew install portaudio`) for `pyaudio`
- **GPU:** install a CUDA build of PyTorch **2.8.x** if needed ([pytorch.org](https://pytorch.org/get-started/locally/)); `requirements.txt` pins the 2.8 line to match WhisperX

## Installation

**If your default `python` is 3.14** (common with a fresh Windows install), `pip install -r requirements.txt` will fail: PyPI has **no PyTorch 2.8 wheels for 3.14**, and WhisperX does not support 3.14 yet. Install **Python 3.12** (or any **3.10–3.13**), then bootstrap a venv (creates `.venv` in this folder):

| Shell | Command |
|--------|---------|
| **Command Prompt** (recommended on Windows) | `setup-venv.bat` |
| **Git Bash** | `bash setup-venv.sh` |

After that, activate the venv whenever you work in the project:

- **Git Bash:** `source .venv/Scripts/activate` (this path exists once the venv is created; if you see “No such file”, run `setup-venv.bat` or `bash setup-venv.sh` first).
- **Command Prompt:** `.venv\Scripts\activate.bat`

Then `python` / `pip` use that supported version inside the venv.

**Manual install** (if you already have 3.10–3.13 active):

```bash
python -m pip install -r requirements.txt
```

**Client-only install** (remote transcription server already running elsewhere):

```bash
python -m pip install -r requirements-client.txt
```

Do not use **Expose local HTTP API** or **Load model** locally on a client-only install unless you also install the full `requirements.txt`.

To list device indices (inputs and output loopback candidates), run:

```bash
python whisperx-dictate.py --list-devices
```

(or `python -m whisperx_dictate.cli --list-devices` from the project root)

## Project layout

Application code lives in the `whisperx_dictate/` package. Thin launchers in the repo root add the project directory to `sys.path`:

- `whisperx-dictate.py` → CLI (`cli_main`)
- `whisperx-dictate-gui.py` → desktop GUI (`gui_main`)
- `whisperx-dictate-gui.pyw` → same GUI, **Windows**: `pythonw` by default (no console; use `--console` if needed)

## Desktop GUI (tkinter)

Native window (no browser). From the project directory:

```bash
python whisperx-dictate-gui.py
```

On **Windows**, **`python.exe whisperx-dictate-gui.py`** uses a normal console. **`pythonw`** / **`.pyw`** avoids a console; if **Python Install Manager** or Explorer still starts **`python.exe`**, `whisperx-dictate-gui.pyw` **re-execs** via **`pythonw.exe`** next to that interpreter when possible. Use **`--console`** or **`WHISPERX_DICTATE_GUI_CONSOLE=1`** only when you want a console for logging or debugging.

Equivalent: `python -m whisperx_dictate.gui_app` (same rules when `gui_main` runs)

**Window / tray icon:** add your own `app.ico` and/or `app.png` under `whisperx_dictate/assets/` (see `whisperx_dictate/assets/README.md`). Windows benefits from a multi-size `.ico` for the taskbar; the tray uses the PNG if present (else `.ico` via Pillow), otherwise the built-in placeholder. On Windows the GUI also sets an **AppUserModelID** before creating the window and applies **`WM_SETICON` via Win32** (in addition to Tk) so the **taskbar** can use a **large** layer from `app.ico` instead of a blurry scaled‑up 16×16.

Configure language, model, optional remote server URL, glossary / initial-prompt files, save directory, and multi-select audio devices. Click **Load model / connect** (runs in a background thread so the window stays responsive). Optionally enable **Expose local HTTP API** to serve the same JSON endpoints as `--server` on the chosen host/port (default `127.0.0.1:8765`) in a background thread.

**Settings profile:** `gui_config.json` is stored under `%APPDATA%\WhisperXDictate\` on Windows, or `~/.config/whisperx-dictate/` on other platforms. The GUI saves on each successful **Load model / connect**.

The GUI has a **Translate speech to English** checkbox (Whisper `translate` task); leave it off to **transcribe** in the spoken language. Click **Load model / connect** after changing it.

By default the GUI matches the CLI after each dictation: **type into the focused window** and **copy to the clipboard** (disable either via the two checkboxes). Use **Start recording** / **Stop recording**, or enable **global hotkeys** (same `keyboard` library as the CLI; on Windows you may need to run the app as Administrator). Defaults: dictate `ctrl+space`, save last `ctrl+alt+n`, stop recording and save to file `ctrl+alt+space` — configurable in the form and stored in `gui_config.json`. For **multiple audio devices**, use **Ctrl/Shift-click** in the device list (extended selection); each source is captured in parallel so all are mixed for transcription.

**System tray (notification area):** with **Minimize to system tray** enabled (default), minimizing the window hides it from the taskbar and shows an icon near the clock; **Open** (double-click the icon on some setups) or the tray menu restores the window, **Exit** quits the app. Use **Hide to tray** to hide without using the taskbar minimize button. Requires `pystray` and `Pillow` (listed in `requirements.txt`). Closing the window with the title-bar **X** still exits fully (tray icon is removed).

**Copy last to clipboard** uses the last transcript; **Save last to note** uses save-directory semantics when set (local mode only for file saves; client mode still uses the server’s `/save`).

## Run Modes

| Mode | Command | Notes |
|------|---------|-------|
| Local hotkeys | `python whisperx-dictate.py -l ru` | `Ctrl+Space` to dictate, `Ctrl+Alt+N` to save last dictation |
| Enter-to-toggle | `python whisperx-dictate.py -l ru --enter-to-toggle` | Use Enter in terminal instead of global hotkeys |
| Server (API) | `python whisperx-dictate.py --server -l ru --save-dir ./notes` | Provides `/transcribe`, `/last`, `/save` |
| Client | `python whisperx-dictate.py --server-url http://127.0.0.1:8765 -l ru` | Keeps local hotkeys, transcribes on remote server |
| Protected server | `python whisperx-dictate.py --server --api-token mysecret --host 0.0.0.0` | Requires `Authorization: Bearer mysecret` on all endpoints |
| Client (token) | `python whisperx-dictate.py --server-url http://host:8765 --api-token mysecret` | Sends token automatically with every request |

## Default Hotkeys

- **Dictation toggle:** `Ctrl+Space` (Windows), `Cmd+Alt` (macOS)
- **Save last dictation to note:** `Ctrl+Alt+N` (when `--save-dir` is set, or in client mode)

You can customize hotkeys with:

- `-k`, `--key_combination` for dictation toggle
- `--save-hotkey` for note saving
- `--save-stop-hotkey` for stop-and-save-to-file (default `Ctrl+Alt+Space`)

## Key Arguments

- `-l`, `--language`: optional hint for the ASR decoder (`ru`, `en`, etc.). It does **not** mean “translate into this language”: with the default **transcribe** task, text stays in the **spoken** language; empty `-l` enables auto-detection (slower, better for mixed speech).
- `--translate`: Whisper **translate** task — write **English** text from non-English speech. Off by default (`transcribe`). Use a **multilingual** checkpoint (not `*.en`). In server mode, start the server with `--translate` if you want translated output.
- `-m`, `--model_name`: `tiny`, `base`, `small`, `medium`, `large`, `large-v2`, `large-v3` (also `.en` variants: `tiny.en`, `base.en`, `small.en`, `medium.en`)
- `--enter-to-toggle`: use Enter in terminal to start/stop recording
- `-t`, `--max_time`: optional cap on recording length in seconds; **default: no limit** (stop only via hotkey / Enter). If set, recording stops automatically when the duration elapses
- `--save-dir DIR`: directory for saved notes
- `--save-naming number|time`: file naming strategy
- `--save-hotkey KEYS`: save hotkey (default `ctrl+alt+n`)
- `--save-stop-hotkey KEYS`: stop recording + save to file, skipping typing (default `ctrl+alt+space`)
- `--server`: run HTTP server mode
- `--host`, `--port`: server bind address and port
- `--server-url URL`: use remote server for transcription (client mode)
- `--input-devices IDS`: comma-separated device indices to record and mix (inputs and/or output loopback), for example `13,36`
- `--list-devices`: print available device indices and exit
- `--diarize`: enable speaker diarization (`[SPEAKER_XX]` labels)
- `--diarize-model`: diarization model name (default `pyannote/speaker-diarization-community-1`)
- `--hf-token`: Hugging Face token for gated diarization models (if needed)
- `--initial-prompt TEXT`: Whisper [`initial_prompt`](https://github.com/SYSTRAN/faster-whisper) via WhisperX `asr_options`. Sets **context** for decoding (topic, register, language mix) — see **Steering recognition** below. Mutually exclusive with `--initial-prompt-file`.
- `--initial-prompt-file PATH`: same, but read from a UTF-8 file. See **Initial prompt example** below.
- `--glossary-file PATH`: UTF-8 table (tab or two-or-more spaces between columns). Column 1 = what the model prints, column 2 = what you want. Applied as **substring replacements** after each transcript, longest first. Without an explicit `--initial-prompt`, a short bias string is auto-built from column 2.
- `--no-glossary-prompt`: with `--glossary-file`, skip auto-building `initial_prompt` from column 2 (replacements only).
- `--api-token TOKEN`: bearer token for server auth; also read from `WHISPERX_API_TOKEN` env var
- `--k_double_cmd`: macOS right-command double-click mode

**API token:** Pass `--api-token` or set `WHISPERX_API_TOKEN` in the environment (preferred for remote deployments so the secret does not appear in `ps` output). The server skips auth only on `GET /health`; all other endpoints return `401` if the token is wrong or missing. The client sends `Authorization: Bearer <token>` automatically.

**Diarization token:** Only required when the model is downloaded from the Hub for the first time. Pass via `--hf-token`, or set `HF_TOKEN` in the environment, or run `huggingface-cli login`. Once cached locally, no token is needed.

**Steering recognition — `initial_prompt` vs `--glossary-file`:**

| | **`initial_prompt`** | **`--glossary-file`** |
|---|---|---|
| **Purpose** | Bias *what kind of text* you expect: topic, register, mixed RU/EN, domain jargon. | Replace wrong substrings with exact text after transcription. |
| **Think of it as** | "This is a standup / lecture / ticket notes…" | A deterministic find/replace table. |
| **Spellings** | Soft hint; not guaranteed. | Exact output for each row. |

Use both together when useful: prompt for overall context, glossary for corrections you can list.

## Examples

```bash
# Local dictation with note saving
python whisperx-dictate.py -l ru --save-dir ./notes

# Mix two input devices (mic + headset monitor)
python whisperx-dictate.py -l ru --input-devices 1,3

# Mix your mic and system audio
python whisperx-dictate.py -l ru --input-devices 13,36

# Enable diarization (speaker labels)
python whisperx-dictate.py -l ru --diarize

# Enter-to-toggle mode
python whisperx-dictate.py -l ru --enter-to-toggle --save-dir ./notes

# Larger model
python whisperx-dictate.py -m large-v3 -l ru

# Glossary: wrong → correct (see "Glossary" below)
python whisperx-dictate.py -l ru --glossary-file examples/glossary.sample.tsv

# Server mode
python whisperx-dictate.py --server -l ru --save-dir ./notes --host 0.0.0.0 --port 8765

# Server with bearer token
python whisperx-dictate.py --server -l ru --save-dir ./notes --host 0.0.0.0 --api-token mysecret
# or via env var
WHISPERX_API_TOKEN=mysecret python whisperx-dictate.py --server -l ru --save-dir ./notes --host 0.0.0.0

# Client mode
python whisperx-dictate.py --server-url http://127.0.0.1:8765 -l ru
# Client with token
python whisperx-dictate.py --server-url http://192.168.1.10:8765 -l ru --api-token mysecret
```

## HTTP API (Server Mode)

- `GET /health` — readiness check
- `GET /last` — last transcription text
- `POST /transcribe` — transcribe audio
  - raw body: s16le PCM, 16 kHz mono
  - or multipart form file: `file`/`audio` (for example WAV)
  - optional query: `?language=ru`, `?diarize=1`
- `POST /save` — save last transcription to `--save-dir` on the server

```bash
# Without token
curl -X POST -F "file=@speech.wav" "http://127.0.0.1:8765/transcribe?language=ru"
curl -X POST --data-binary @recording.raw "http://127.0.0.1:8765/transcribe?language=ru"
curl -X POST "http://127.0.0.1:8765/save"

# With token
curl -X POST -H "Authorization: Bearer mysecret" -F "file=@speech.wav" "http://host:8765/transcribe?language=ru"
curl -X POST -H "Authorization: Bearer mysecret" "http://host:8765/save"
```

## Startup

- On Windows, use Task Scheduler or Startup folder shortcut if you want the app to start with the system

## Permissions

- Microphone access is required
- For global hotkeys on Windows, run terminal as Administrator if hotkeys are not detected

## Initial prompt example

[`initial_prompt`](https://github.com/SYSTRAN/faster-whisper) is conditioning text the decoder reads **before** your audio, biasing it toward words and phrasing that fit the scenario. This is a **context** hint, not a spelling dictionary — for exact string fixes use the **glossary**.

**File** [`examples/initial_prompt.sample.txt`](examples/initial_prompt.sample.txt):

```text
Software engineering standup in English. Informal but technical: pull requests, issues, CI pipelines, APIs, deployment, repositories, code review.
```

**CLI:**

```bash
python whisperx-dictate.py -l en --initial-prompt "Engineering standup: GitHub, CI, APIs, deployment, informal technical English."
# or from file
python whisperx-dictate.py -l en --initial-prompt-file examples/initial_prompt.sample.txt
```

Other ideas: lecture notes in Russian with English IT terms; medical or legal dictation; customer call summary — keep it **short** (a few sentences).

Server mode loads the model once, so pass the prompt flags when starting the server. Client mode does not load the model; configure the prompt on the server side.

## Glossary (table wrong → correct)

Deterministic corrections (exact substrings) applied after each transcription. Complements `initial_prompt`, which only sets *context* — see **Steering recognition** above.

Edit a UTF-8 file with one row per mishearing. Between the two columns use a **tab** or **two-or-more spaces** (single spaces inside a phrase stay part of column 1).

- **Column 1:** text as Whisper printed it (add variants: different casing, Russian phonetic transcription of an English name, etc.).
- **Column 2:** exact text you want in the final output.
- Lines starting with `#` are comments. An optional header row (`wrong`/`correct` or `from`/`to`) is auto-skipped.
- Longer left-column strings are replaced first.

Example: [`examples/glossary.sample.tsv`](examples/glossary.sample.tsv).

```text
wrong	correct
wabbit	rabbit
the wabbit    the rabbit
```

The last data row uses multiple spaces as the separator instead of a tab.

Add rows as you notice errors — this is the main way to grow a correction dictionary. Use `--no-glossary-prompt` if you only want replacements without auto-building an `initial_prompt` from column 2.

**Client + server:** the glossary runs on whichever side you pass `--glossary-file`. For the auto-built `initial_prompt` to affect decoding, pass it on the **server** (or use an explicit `--initial-prompt` there).
