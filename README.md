# WhisperX Dictate

Dictation tool based on WhisperX (faster-whisper backend) with global hotkeys, clipboard output, optional note saving, and server/client modes.

## Requirements

- Python 3.10+
- Microphone
- WhisperX environment (including `torch`, `numpy`, CUDA support if needed)
- **Windows:** `keyboard` global hotkeys may require running terminal as Administrator
- **Windows system-audio loopback:** install `pyaudiowpatch` (`pip install pyaudiowpatch`) so output device capture works (output indices are auto-mapped to loopback devices)
- **macOS/Linux:** PortAudio (for example `brew install portaudio`)

## Installation

From the project directory:

```bash
pip install -r requirements.txt
```

To list device indices (inputs and output loopback candidates), run:

```bash
python whisperx-dictate.py --list-devices
```

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

- `-l`, `--language`: language code (`ru`, `en`, etc.)
- `-m`, `--model_name`: `tiny`, `base`, `small`, `medium`, `large`, `large-v2`, `large-v3`
- `--enter-to-toggle`: use Enter in terminal to start/stop recording
- `--save-dir DIR`: directory for saved notes
- `--save-naming number|time`: file naming strategy
- `--save-hotkey KEYS`: save hotkey (default `ctrl+alt+n`)
- `--server`: run HTTP server mode
- `--host`, `--port`: server bind address and port
- `--server-url URL`: use remote server for transcription (client mode)
- `--input-devices IDS`: optional comma-separated device indices to record and mix (inputs and/or output loopback), for example `13,36`
- `--list-devices`: print available device indices and exit
- `--diarize`: enable speaker diarization (`[SPEAKER_XX]` labels)
- `--diarize-model`: diarization model name (default `pyannote/speaker-diarization-community-1`)
- `--hf-token`: Hugging Face token for gated diarization models (if needed)
- `--initial-prompt TEXT`: optional [Whisper `initial_prompt`](https://github.com/SYSTRAN/faster-whisper) via WhisperX `asr_options`. Sets **context** for decoding (topic, situation, language/register mix)—see **Steering recognition** below. **Not** a replacement for the glossary when you need exact spellings. Keep it short. Mutually exclusive with `--initial-prompt-file`.
- `--initial-prompt-file PATH`: same, but read from a UTF-8 file (multi-line context). See **Initial prompt example** below.
- `--glossary-file PATH`: UTF-8 **TSV** table: column 1 = what the model often prints, column 2 = what you want. Rows are applied as **substring replacements** after each transcript (longer phrases first). If you do **not** use `--initial-prompt` / `--initial-prompt-file`, a **short** `initial_prompt` is auto-built from unique values in column 2 (capped in length) so the context does not turn into a long essay.
- `--no-glossary-prompt`: use with `--glossary-file` to **only** run replacements and **not** feed column 2 into `initial_prompt` (useful for very large glossaries).
- `--api-token TOKEN`: bearer token to protect the server or to authenticate against a protected server; also read from `WHISPERX_API_TOKEN` env var
- `--k_double_cmd`: macOS right-command double-click mode

**API token:** Pass `--api-token` or set `WHISPERX_API_TOKEN` in the environment (preferred for remote deployments so the secret does not appear in `ps` output). The server skips auth only on `GET /health`; all other endpoints return `401` if the token is wrong or missing. The client sends `Authorization: Bearer <token>` automatically.

**Diarization token:** The token is only required when the diarization model is downloaded from the Hub for the first time. You can pass it via `--hf-token`, or set `HF_TOKEN` in the environment, or run `huggingface-cli login` (saves token to `~/.cache/huggingface/token` or `%USERPROFILE%\.cache\huggingface\token`). Once the model is cached locally, it loads from disk and no token is needed.

**Steering recognition — `initial_prompt` vs `--glossary-file`:**

| | **`initial_prompt`** | **`--glossary-file`** |
|---|----------------------|-------------------------|
| **Purpose** | Bias *what kind of text* you expect: setting, topic, technical vs casual, mixed RU/EN, domain jargon in prose. | **After** transcription: replace wrong *substrings* with the right text (brands, repeated ASR errors). |
| **Think of it as** | “This is a standup / lecture / ticket notes…” so token choices fit the scenario. | A deterministic find/replace table. |
| **Spellings** | Soft hint only; not guaranteed. | Exact output for each row you define. |

Use **both** together when useful: prompt for overall context, glossary for corrections you can list. For systematic typo fixes, prefer the glossary; use the prompt for everything that is not a simple string substitution.

## Examples

```bash
# Local dictation with note saving
python whisperx-dictate.py -l ru --save-dir ./notes

# Mix two input devices (for example mic + headset monitor)
python whisperx-dictate.py -l ru --input-devices 1,3

# Mix your mic and system audio
python whisperx-dictate.py -l ru --input-devices 13,36

# Enable diarization (speaker labels)
python whisperx-dictate.py -l ru --diarize

# Enter-to-toggle mode
python whisperx-dictate.py -l ru --enter-to-toggle --save-dir ./notes

# Larger model
python whisperx-dictate.py -m large-v3 -l ru

# TSV glossary: wrong → correct (see "Glossary" below)
python whisperx-dictate.py -l ru --glossary-file examples/glossary.sample.tsv

# Server mode (localhost only, no auth needed)
python whisperx-dictate.py --server -l ru --save-dir ./notes --host 0.0.0.0 --port 8765

# Server mode with bearer token (for remote/public exposure)
python whisperx-dictate.py --server -l ru --save-dir ./notes --host 0.0.0.0 --api-token mysecret
# or via env var (avoids token in shell history / ps output)
WHISPERX_API_TOKEN=mysecret python whisperx-dictate.py --server -l ru --save-dir ./notes --host 0.0.0.0

# Client mode (local server, no token)
python whisperx-dictate.py --server-url http://127.0.0.1:8765 -l ru
# Client mode (remote protected server)
python whisperx-dictate.py --server-url http://192.168.1.10:8765 -l ru --api-token mysecret
# or via env var
WHISPERX_API_TOKEN=mysecret python whisperx-dictate.py --server-url http://192.168.1.10:8765 -l ru
```

## HTTP API (Server Mode)

- `GET /health` — readiness check
- `GET /last` — last transcription text
- `POST /transcribe` — transcribe audio
  - raw body: s16le PCM, 16 kHz mono
  - or multipart form file: `file`/`audio` (for example WAV)
  - optional query: `?language=ru`
- `POST /save` — save last transcription to `--save-dir` on the server

```bash
# Without token
curl -X POST -F "file=@speech.wav" "http://127.0.0.1:8765/transcribe?language=ru"
curl -X POST --data-binary @recording.raw "http://127.0.0.1:8765/transcribe?language=ru"
curl -X POST "http://127.0.0.1:8765/save"

# With --api-token mysecret
curl -X POST -H "Authorization: Bearer mysecret" -F "file=@speech.wav" "http://host:8765/transcribe?language=ru"
curl -X POST -H "Authorization: Bearer mysecret" "http://host:8765/save"
```

## Startup

- On Windows, use Task Scheduler or Startup folder shortcut if you want the app to start with the system

## Permissions

- Microphone access is required
- For global hotkeys on Windows, run terminal as Administrator if hotkeys are not detected

## Initial prompt example

[`initial_prompt`](https://github.com/SYSTRAN/faster-whisper) is conditioning text read **before** your audio: the decoder favors words and phrasing that *fit* that scenario. Below is a **context** example (engineering standup), not a spelling checklist—for “always write X as Y” use the **glossary** instead.

**File** [`examples/initial_prompt.sample.txt`](examples/initial_prompt.sample.txt):

```text
Software engineering standup in English. Informal but technical: pull requests, issues, CI pipelines, APIs, deployment, repositories, code review.
```

**One-line CLI** (escape quotes on your shell if needed):

```bash
python whisperx-dictate.py -l en --initial-prompt "Engineering standup: GitHub, CI, APIs, deployment, informal technical English."
```

**With file:**

```bash
python whisperx-dictate.py -l en --initial-prompt-file examples/initial_prompt.sample.txt
```

Other ideas for `initial_prompt`: lecture notes in Russian with English IT terms; medical or legal dictation; customer call summary in a given industry vocabulary—still **short** (a few sentences).

Server mode loads the model once: pass the same flags when starting the server so `initial_prompt` applies to every request. Client-only mode does not load the model; configure the prompt on the machine that runs `--server`.

## Glossary (table wrong → correct)

This is the right tool for **deterministic** corrections (exact substrings). It complements an `initial_prompt` that only describes *context*; see **Steering recognition** above.

Edit a **tab-separated** file (UTF-8). One row per mishearing:

- **Column 1:** substring as Whisper printed it (include each common variant: different casing, Russian transcript of an English name, etc.).
- **Column 2:** exact text you want in the final transcript.
- Lines starting with `#` are comments. Optional header row `wrong<TAB>correct` (or `from` / `to`) is ignored.
- Replacements run **longest match first**, so a row `wabbits` → `rabbits` is applied before a shorter row `wabbit` → `rabbit` if you add both.

Example: [`examples/glossary.sample.tsv`](examples/glossary.sample.tsv).

```text
wrong	correct
wabbit	rabbit
```

This is the main way to grow a “dictionary” without bloating `initial_prompt`: add rows as you notice errors. Use `--no-glossary-prompt` if you only want deterministic fixes and rely on `-l`, model size, or a small `--initial-prompt` for ASR bias.

**Client + server:** Replacements run on the client too if you pass `--glossary-file` on the client (useful if the server was started without the glossary). For `initial_prompt` derived from the glossary, start the **server** with the same `--glossary-file` (or an explicit `--initial-prompt`).
