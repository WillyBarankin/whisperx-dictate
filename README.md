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

## Default Hotkeys

- **Dictation toggle:** `Ctrl+Space` (Windows), `Cmd+Alt` (macOS)
- **Save last dictation to note:** `Ctrl+Alt+N` (when `--save-dir` is set, or in client mode)

You can customize hotkeys with:

- `-k`, `--key_combination` for dictation toggle
- `--save-hotkey` for note saving

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
- `--k_double_cmd`: macOS right-command double-click mode

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

# Server mode
python whisperx-dictate.py --server -l ru --save-dir ./notes --host 0.0.0.0 --port 8765

# Client mode
python whisperx-dictate.py --server-url http://127.0.0.1:8765 -l ru
python whisperx-dictate.py --server-url http://192.168.1.10:8765 -l ru
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
curl -X POST -F "file=@speech.wav" "http://127.0.0.1:8765/transcribe?language=ru"
curl -X POST --data-binary @recording.raw "http://127.0.0.1:8765/transcribe?language=ru"
curl -X POST "http://127.0.0.1:8765/save"
```

## Startup

- On Windows, use Task Scheduler or Startup folder shortcut if you want the app to start with the system

## Permissions

- Microphone access is required
- For global hotkeys on Windows, run terminal as Administrator if hotkeys are not detected
