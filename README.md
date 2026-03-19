# WhisperX Dictate

Dictation tool based on WhisperX (faster-whisper backend) (faster-whisper backend) with global hotkeys, clipboard output, optional note saving, and server/client modes.

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
- `--api-token TOKEN`: bearer token to protect the server or to authenticate against a protected server; also read from `WHISPERX_API_TOKEN` env var
- `--k_double_cmd`: macOS right-command double-click mode

**API token:** Pass `--api-token` or set `WHISPERX_API_TOKEN` in the environment (preferred for remote deployments so the secret does not appear in `ps` output). The server skips auth only on `GET /health`; all other endpoints return `401` if the token is wrong or missing. The client sends `Authorization: Bearer <token>` automatically.

**Diarization token:** The token is only required when the diarization model is downloaded from the Hub for the first time. You can pass it via `--hf-token`, or set `HF_TOKEN` in the environment, or run `huggingface-cli login` (saves token to `~/.cache/huggingface/token` or `%USERPROFILE%\.cache\huggingface\token`). Once the model is cached locally, it loads from disk and no token is needed.

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
