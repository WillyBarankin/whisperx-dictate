import argparse
import os
import re
import time
import threading
from datetime import datetime
try:
    import pyaudiowpatch as pyaudio  # Windows loopback-capable build
except ImportError:
    import pyaudio
import numpy as np
from pynput import keyboard
import platform

try:
    import pyperclip
    _HAS_PYPERCLIP = True
except ImportError:
    _HAS_PYPERCLIP = False

# Windows: pynput often sends modifiers as KeyCode(vk=...) instead of Key.ctrl/Key.alt
def _is_modifier_key(key, modifier_name):
    """Return True if key is the given modifier or key (ctrl, alt, space, etc.)."""
    name = modifier_name.lower()
    if hasattr(key, "vk") and key.vk is not None:  # KeyCode on Windows
        vk = key.vk
        if name in ("ctrl", "control"):
            return vk in (0x11, 0xA2, 0xA3)  # VK_CONTROL, VK_LCONTROL, VK_RCONTROL
        if name == "alt":
            return vk in (0x12, 0xA4, 0xA5)  # VK_MENU, VK_LMENU, VK_RMENU
        if name == "space":
            return vk == 0x20  # VK_SPACE
    try:
        attr = getattr(keyboard.Key, name, None)
        if attr is not None and key == attr:
            return True
    except (AttributeError, TypeError):
        pass
    # e.g. cmd_l, ctrl_l, alt_r
    for variant in (name, name.replace("_l", "").replace("_r", "")):
        attr = getattr(keyboard.Key, variant, None)
        if attr is not None and key == attr:
            return True
    return False


_GLOSSARY_HEADER_RE = re.compile(
    r"^(?P<a>from|wrong|misheard|source)(?:\t|\s{2,})(?P<b>to|correct|right|target)\s*$",
    re.IGNORECASE,
)


def load_glossary_tsv(path):
    """Load UTF-8 glossary: column 1 = text the model may emit, column 2 = replacement.

    Separator: tab, or two-or-more spaces (single space inside a phrase is unchanged).
    Lines starting with # are comments.
    """
    pairs = []
    with open(path, encoding="utf-8") as f:
        for i, raw in enumerate(f):
            line = raw.rstrip("\n\r")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if i == 0 and _GLOSSARY_HEADER_RE.match(stripped):
                continue
            if "\t" in line:
                wrong, right = line.split("\t", 1)
            else:
                parts = re.split(r"\s{2,}", stripped, maxsplit=1)
                if len(parts) < 2:
                    continue
                wrong, right = parts[0], parts[1]
            wrong, right = wrong.strip(), right.strip()
            if not wrong:
                continue
            pairs.append((wrong, right))
    return pairs


def _glossary_replacement_order(pairs):
    """Apply longest wrong-string first so phrases win over shared substrings."""
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def apply_glossary(text, pairs):
    if not text or not pairs:
        return text
    for wrong, right in _glossary_replacement_order(pairs):
        if wrong and wrong in text:
            text = text.replace(wrong, right)
    return text


def glossary_initial_prompt(pairs, max_chars=480):
    """Short ASR bias string built only from unique correct (second) column values."""
    if not pairs:
        return None
    seen = set()
    terms = []
    for _, correct in pairs:
        c = (correct or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        terms.append(c)
    if not terms:
        return None
    body = ", ".join(terms)
    prefix = "Proper names and terms: "
    blob = prefix + body
    if len(blob) > max_chars:
        blob = blob[: max_chars - 3].rstrip(", ") + "..."
    return blob


class SpeechTranscriber:
    def __init__(
        self,
        model,
        save_dir=None,
        save_naming="number",
        diarize=False,
        hf_token=None,
        diarize_model="pyannote/speaker-diarization-community-1",
        device="cpu",
        glossary_pairs=None,
    ):
        self.model = model
        self.glossary_pairs = glossary_pairs or []
        self.pykeyboard = keyboard.Controller()
        self.save_dir = save_dir
        self.save_naming = save_naming  # "number" or "time"
        self.diarize = diarize
        self.hf_token = hf_token
        self.diarize_model = diarize_model
        self.device = device
        self._diarization_pipeline = None
        self._save_counter = 0
        self._last_text = None
        self._save_on_next = False  # when True, next transcription goes to file instead of typing
        self.save_note_hint = None  # if set, printed after each normal transcription

    def _next_save_path(self):
        """Return path for next transcript file based on save_naming."""
        if not self.save_dir:
            return None
        os.makedirs(self.save_dir, exist_ok=True)
        if self.save_naming == "time":
            name = "transcript_{}.txt".format(datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        else:
            self._save_counter += 1
            name = "transcript_{:03d}.txt".format(self._save_counter)
        return os.path.join(self.save_dir, name)

    def save_last_to_note(self):
        """Save last transcription to a file (call from save hotkey)."""
        if not self.save_dir:
            return
        if not self._last_text:
            print("(nothing to save — dictate first)")
            return
        path = self._next_save_path()
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._last_text)
                print("(saved to {})".format(path))
            except Exception as e:
                print("(save failed:", e, ")")

    def _ensure_diarizer(self):
        if self._diarization_pipeline is not None:
            return self._diarization_pipeline
        try:
            import whisperx
            self._diarization_pipeline = whisperx.diarize.DiarizationPipeline(
                model_name=self.diarize_model,
                token=self.hf_token,
                device=self.device,
            )
        except Exception as e:
            print("(failed to initialize diarization pipeline:", e, ")")
            self._diarization_pipeline = False
        return self._diarization_pipeline

    @staticmethod
    def _segments_to_text(segments):
        chunks = []
        last_speaker = None
        line_sep = "\n"  # when diarization is used, one line per speaker turn
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            speaker = seg.get("speaker")
            if speaker:
                if speaker != last_speaker:
                    chunks.append((line_sep if chunks else "") + f"[{speaker}] {text}")
                else:
                    chunks.append(" " + text)
                last_speaker = speaker
            else:
                chunks.append((" " if chunks else "") + text)
        return "".join(chunks).strip()

    def transcribe_to_text(self, audio_data, language=None, diarize_override=None):
        """Transcribe audio to text only; returns text or None. Updates _last_text for /save."""
        import whisperx
        result = self.model.transcribe(audio_data, batch_size=4)

        use_diarization = self.diarize if diarize_override is None else bool(diarize_override)
        if use_diarization:
            diarizer = self._ensure_diarizer()
            if diarizer:
                try:
                    diarize_df = diarizer(audio_data)
                    result = whisperx.assign_word_speakers(diarize_df, result)
                except Exception as e:
                    print("(diarization failed:", e, ")")

        text = self._segments_to_text(result["segments"])
        if text and self.glossary_pairs:
            text = apply_glossary(text, self.glossary_pairs)
        if text:
            self._last_text = text
        return text if text else None

    def transcribe(self, audio_data, language=None):
        save_mode = self._save_on_next
        self._save_on_next = False
        text = self.transcribe_to_text(audio_data, language)
        if not text:
            print("(no speech detected)")
            return
        print("→", text)
        if save_mode and self.save_dir:
            path = self._next_save_path()
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                    print("(saved to {})".format(path))
                except Exception as e:
                    print("(save failed:", e, ")")
            return
        if _HAS_PYPERCLIP:
            try:
                pyperclip.copy(text)
                print("(copied to clipboard — paste with Ctrl+V)")
            except Exception as e:
                print("(clipboard copy failed:", e, ")")
        else:
            print("(install pyperclip for clipboard: pip install pyperclip)")
        started = False
        for element in text:
            if element == " " and not started:
                continue
            started = True
            try:
                self.pykeyboard.type(element)
                time.sleep(0.0025)
            except Exception:
                pass
        if self.save_note_hint:
            print("(save to note: {})".format(self.save_note_hint))


class ClientTranscriber:
    """Transcriber that sends audio to a remote server (same hotkeys/clipboard/typing, no local model)."""
    def __init__(self, server_url, language=None, diarize=False, api_token=None, glossary_pairs=None):
        self.server_url = server_url.rstrip("/")
        self._language = language
        self._diarize = diarize
        self._api_token = api_token
        self.glossary_pairs = glossary_pairs or []
        self.pykeyboard = keyboard.Controller()
        self.save_dir = None  # save is done on server via POST /save
        self._last_text = None
        self._save_on_next = False
        self.save_note_hint = None
        try:
            import urllib.request
            with urllib.request.urlopen(self.server_url + "/health", timeout=5) as _:
                pass
        except Exception as e:
            print("(warning: server not reachable at", self.server_url, "—", e, ")")

    def _add_auth(self, req):
        if self._api_token:
            req.add_header("Authorization", "Bearer " + self._api_token)

    def _post_transcribe(self, audio_bytes, language=None):
        import urllib.request
        import json
        lang = language or self._language
        params = []
        if lang:
            params.append("language=" + lang)
        if self._diarize:
            params.append("diarize=1")
        url = self.server_url + "/transcribe" + (("?" + "&".join(params)) if params else "")
        req = urllib.request.Request(url, data=audio_bytes, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        self._add_auth(req)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print("(server error:", e, ")")
            return None

    def _post_save(self):
        import urllib.request
        import json
        req = urllib.request.Request(self.server_url + "/save", data=b"", method="POST")
        self._add_auth(req)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print("(save on server failed:", e, ")")
            return None

    def save_last_to_note(self):
        if not self._last_text:
            print("(nothing to save — dictate first)")
            return
        out = self._post_save()
        if out and out.get("saved"):
            print("(saved on server to {})".format(out.get("path", "?")))
        elif out and out.get("error"):
            print("(save error:", out["error"], ")")

    def transcribe(self, audio_data, language=None):
        save_mode = self._save_on_next
        self._save_on_next = False
        # s16le 16 kHz mono for server
        if audio_data.dtype != np.int16:
            audio_bytes = (audio_data * 32768.0).astype(np.int16).tobytes()
        else:
            audio_bytes = audio_data.tobytes()
        out = self._post_transcribe(audio_bytes, language)
        if not out:
            return
        text = (out.get("text") or "").strip()
        if not text:
            print("(no speech detected)")
            return
        if self.glossary_pairs:
            text = apply_glossary(text, self.glossary_pairs)
        self._last_text = text
        print("→", text)
        if save_mode:
            out2 = self._post_save()
            if out2 and out2.get("saved"):
                print("(saved on server to {})".format(out2.get("path", "?")))
            elif out2 and out2.get("error"):
                print("(save error:", out2["error"], ")")
            return
        if _HAS_PYPERCLIP:
            try:
                pyperclip.copy(text)
                print("(copied to clipboard — paste with Ctrl+V)")
            except Exception as e:
                print("(clipboard copy failed:", e, ")")
        else:
            print("(install pyperclip for clipboard: pip install pyperclip)")
        started = False
        for element in text:
            if element == " " and not started:
                continue
            started = True
            try:
                self.pykeyboard.type(element)
                time.sleep(0.0025)
            except Exception:
                pass
        if self.save_note_hint:
            print("(save to note: {})".format(self.save_note_hint))


class Recorder:
    def __init__(self, transcriber, input_devices=None):
        self.recording = False
        self.transcriber = transcriber
        self.input_devices = input_devices or []

    def start(self, language=None, max_time=None):
        thread = threading.Thread(target=self._record_impl, args=(language, max_time))
        thread.start()

    def stop(self):
        self.recording = False

    @staticmethod
    def _resample_mono(audio, src_rate, dst_rate):
        if src_rate == dst_rate or audio.size == 0:
            return audio
        src_len = audio.shape[0]
        dst_len = int(round(src_len * (dst_rate / float(src_rate))))
        if dst_len <= 1:
            return np.array([], dtype=np.float32)
        x_old = np.linspace(0.0, 1.0, num=src_len, endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=dst_len, endpoint=False)
        return np.interp(x_new, x_old, audio).astype(np.float32)

    def _record_impl(self, language, max_time=None):
        self.recording = True
        target_rate = SAMPLE_RATE
        base_frames = 1024
        p = pyaudio.PyAudio()
        streams = []

        def _open_stream(device_index, preferred_channels=1):
            info = p.get_device_info_by_index(device_index)
            max_in = int(info.get("maxInputChannels", 0))
            if max_in <= 0:
                raise RuntimeError(f"device {device_index} has no input channels")

            rate_candidates = [target_rate, int(round(float(info.get("defaultSampleRate", target_rate))))]
            channel_candidates = []
            for ch in (preferred_channels, max_in, 2, 1):
                if ch > 0 and ch <= max_in and ch not in channel_candidates:
                    channel_candidates.append(ch)

            for channels in channel_candidates:
                for rate in rate_candidates:
                    try:
                        stream = p.open(
                            format=pyaudio.paInt16,
                            channels=channels,
                            rate=rate,
                            frames_per_buffer=base_frames,
                            input=True,
                            input_device_index=device_index,
                        )
                        return stream, rate, channels, info
                    except Exception:
                        continue
            raise RuntimeError(f"cannot open device {device_index} with supported sample rate/channels")

        try:
            if self.input_devices:
                opened = []
                for device_idx in self.input_devices:
                    info = p.get_device_info_by_index(device_idx)
                    max_in = int(info.get("maxInputChannels", 0))
                    max_out = int(info.get("maxOutputChannels", 0))
                    name = _normalize_device_name(info.get("name"))

                    open_idx = device_idx
                    mode = "input"
                    if max_in <= 0 and max_out > 0 and hasattr(p, "get_wasapi_loopback_analogue_by_index"):
                        loopback_info = p.get_wasapi_loopback_analogue_by_index(device_idx)
                        if isinstance(loopback_info, dict):
                            open_idx = int(loopback_info.get("index", device_idx))
                            mode = f"loopback->{open_idx}"

                    preferred_channels = 1
                    if mode.startswith("loopback"):
                        loop_info = p.get_device_info_by_index(open_idx)
                        preferred_channels = int(loop_info.get("maxInputChannels", 1)) or 1

                    try:
                        stream, stream_rate, stream_channels, _ = _open_stream(open_idx, preferred_channels=preferred_channels)
                    except Exception as e:
                        print(f"(failed to open device {device_idx}: {e})")
                        continue

                    chunk_frames = max(1, int(round(base_frames * (stream_rate / target_rate))))
                    streams.append(
                        {
                            "stream": stream,
                            "rate": stream_rate,
                            "channels": stream_channels,
                            "chunk_frames": chunk_frames,
                            "frames": [],
                        }
                    )
                    opened.append(f"{device_idx} ({mode} @ {stream_rate}Hz, ch={stream_channels}): {name}")

                if opened:
                    print("Recording from selected devices:")
                    for item in opened:
                        print("  -", item)
                if not streams:
                    print("(no selected devices could be opened)")
                    p.terminate()
                    self.recording = False
                    return
            else:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=target_rate,
                    frames_per_buffer=base_frames,
                    input=True,
                )
                streams.append(
                    {
                        "stream": stream,
                        "rate": target_rate,
                        "channels": 1,
                        "chunk_frames": base_frames,
                        "frames": [],
                    }
                )
        except Exception as e:
            print("(audio input open failed:", e, ")")
            for s in streams:
                try:
                    s["stream"].close()
                except Exception:
                    pass
            p.terminate()
            self.recording = False
            return

        t0 = time.time()
        while self.recording:
            if max_time is not None and max_time > 0 and (time.time() - t0) >= max_time:
                print("(max recording time {:.0f}s reached — stopping)".format(max_time))
                self.recording = False
                break
            for s in streams:
                raw = s["stream"].read(s["chunk_frames"], exception_on_overflow=False)
                s["frames"].append(raw)

        for s in streams:
            s["stream"].stop_stream()
            s["stream"].close()
        p.terminate()

        tracks = []
        for s in streams:
            raw = b"".join(s["frames"])
            if not raw:
                continue
            track = np.frombuffer(raw, dtype=np.int16)
            ch = int(s.get("channels", 1))
            if ch > 1:
                usable = (track.size // ch) * ch
                if usable <= 0:
                    continue
                # For multichannel loopback sources, channel averaging can cancel signal.
                # Use the first channel as a stable mono source.
                track = track[:usable].reshape(-1, ch)[:, 0]
            track = track.astype(np.float32) / 32768.0
            track = self._resample_mono(track, s["rate"], target_rate)
            if track.size > 0:
                tracks.append(track)

        if not tracks:
            print("(no audio captured)")
            return

        # Light per-track RMS normalization to keep one source from drowning out others.
        normalized = []
        for t in tracks:
            rms = float(np.sqrt(np.mean(np.square(t), dtype=np.float64))) if t.size else 0.0
            if rms > 1e-6:
                gain = min(0.05 / rms, 4.0)
                normalized.append((t * gain).astype(np.float32))
            else:
                normalized.append(t.astype(np.float32))

        # Keep full conversation: do not trim to shortest track.
        max_len = max(t.shape[0] for t in normalized)
        mix_sum = np.zeros(max_len, dtype=np.float32)
        mix_weight = np.zeros(max_len, dtype=np.float32)
        for t in normalized:
            n = t.shape[0]
            if n == 0:
                continue
            mix_sum[:n] += t
            mix_weight[:n] += 1.0
        mixed = (mix_sum / np.maximum(mix_weight, 1.0)).astype(np.float32)
        self.transcriber.transcribe(mixed, language)


class GlobalKeyListener:
    def __init__(self, app, key_combination):
        self.app = app
        self.key1_name, self.key2_name = key_combination.split('+')
        self.key1_pressed = False
        self.key2_pressed = False

    def on_key_press(self, key):
        if _is_modifier_key(key, self.key1_name):
            self.key1_pressed = True
        elif _is_modifier_key(key, self.key2_name):
            self.key2_pressed = True

        if self.key1_pressed and self.key2_pressed:
            self.app.toggle()

    def on_key_release(self, key):
        if _is_modifier_key(key, self.key1_name):
            self.key1_pressed = False
        elif _is_modifier_key(key, self.key2_name):
            self.key2_pressed = False

class DoubleCommandKeyListener:
    def __init__(self, app):
        self.app = app
        self.key = keyboard.Key.cmd_r
        self.pressed = 0
        self.last_press_time = 0

    def on_key_press(self, key):
        is_listening = self.app.started
        if key == self.key:
            current_time = time.time()
            if not is_listening and current_time - self.last_press_time < 0.5:  # Double click to start listening
                self.app.toggle()
            elif is_listening:  # Single click to stop listening
                self.app.toggle()
            self.last_press_time = current_time

    def on_key_release(self, key):
        pass

class CLIApp:
    def __init__(self, recorder, languages=None, max_time=None):
        self.recorder = recorder
        self.languages = languages
        self.max_time = max_time
        self.started = False

    def toggle(self):
        if self.started:
            print("Stopping...")
            self.recorder.stop()
            self.started = False
        else:
            print("Starting...")
            self.recorder.start(self.languages[0] if self.languages else None, self.max_time)
            self.started = True

    def run(self):
        print("CLI dictation running. Use your key combination to toggle recording.")
        while True:
            time.sleep(1)  # Keep main thread alive

    def stop_and_save(self):
        """Stop current recording and save the transcription to file (skip typing)."""
        if not self.started:
            return
        print("Stopping (save to file)...")
        self.recorder.transcriber._save_on_next = True
        self.recorder.stop()
        self.started = False

    def save_last_note(self):
        """Save last transcription to file (called by save hotkey)."""
        self.recorder.transcriber.save_last_to_note()


class CLIAppEnter:
    """Use Enter in the terminal to start/stop recording (no global hotkey; works without admin)."""
    def __init__(self, recorder, languages=None, max_time=None):
        self.recorder = recorder
        self.languages = languages
        self.max_time = max_time
        self.started = False

    def toggle(self):
        if self.started:
            print("Stopping...")
            self.recorder.stop()
            self.started = False
        else:
            print("Starting...")
            self.recorder.start(self.languages[0] if self.languages else None, self.max_time)
            self.started = True

    def run(self):
        print("Enter-to-toggle mode: focus this window and press Enter to start, Enter again to stop.")
        while True:
            try:
                input()
                self.toggle()
            except (EOFError, KeyboardInterrupt):
                break

    def stop_and_save(self):
        """Stop current recording and save the transcription to file (skip typing)."""
        if not self.started:
            return
        print("Stopping (save to file)...")
        self.recorder.transcriber._save_on_next = True
        self.recorder.stop()
        self.started = False

    def save_last_note(self):
        """Save last transcription to file (called by save hotkey)."""
        self.recorder.transcriber.save_last_to_note()


SAMPLE_RATE = 16000


def _normalize_device_name(name):
    """Best-effort fix for mojibake device names on Windows."""
    text = str(name)
    if platform.system() != "Windows":
        return text
    # Common mojibake pattern for UTF-8 bytes decoded as cp1251 (e.g. "РњРёРє...")
    if "Р" in text or "С" in text:
        try:
            fixed = text.encode("cp1251").decode("utf-8")
            if fixed:
                return fixed
        except Exception:
            pass
    return text


def _list_input_devices():
    """Print available audio devices and how they can be used."""
    p = pyaudio.PyAudio()
    try:
        print("Available audio devices:")
        found = 0
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            max_in = int(info.get("maxInputChannels", 0))
            max_out = int(info.get("maxOutputChannels", 0))
            if max_in > 0 or max_out > 0:
                name = _normalize_device_name(info.get("name"))
                if max_in > 0 and max_out > 0:
                    role = f"input+output (inputs: {max_in}, outputs: {max_out})"
                elif max_in > 0:
                    role = f"input (inputs: {max_in})"
                else:
                    role = f"output-only/loopback candidate (outputs: {max_out})"
                print(f"  {i}: {name} [{role}]")
                found += 1
        if found == 0:
            print("  (no audio devices found)")
    finally:
        p.terminate()


def _run_server(transcriber, args):
    """Run HTTP API server for transcription and save."""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print("Install Flask for server mode: pip install flask")
        return
    import whisperx
    app = Flask(__name__)
    _transcriber = transcriber
    _lang = args.language[0] if getattr(args, "language", None) else None
    _api_token = getattr(args, "api_token", None)

    if _api_token:
        @app.before_request
        def _check_auth():
            if request.endpoint == "health":
                return None
            auth = request.headers.get("Authorization", "")
            if not (auth.startswith("Bearer ") and auth[7:] == _api_token):
                return jsonify({"error": "unauthorized"}), 401

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/last", methods=["GET"])
    def last():
        text = getattr(_transcriber, "_last_text", None)
        return jsonify({"text": text or ""})

    @app.route("/transcribe", methods=["POST"])
    def transcribe():
        lang = request.args.get("language") or _lang
        diarize_q = request.args.get("diarize")
        diarize_override = None
        if diarize_q is not None:
            diarize_override = diarize_q.lower() in ("1", "true", "yes", "on")
        audio_data = None
        if request.content_type and "multipart/form-data" in request.content_type:
            f = request.files.get("file") or request.files.get("audio")
            if f:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    f.save(tmp.name)
                    try:
                        audio_data = whisperx.load_audio(tmp.name, sr=SAMPLE_RATE)
                    finally:
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
        if audio_data is None:
            raw = request.get_data()
            if not raw:
                return jsonify({"error": "no audio data"}), 400
            # assume s16le 16kHz mono
            audio_data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        text = _transcriber.transcribe_to_text(audio_data, language=lang, diarize_override=diarize_override)
        return jsonify({"text": text or "", "language": lang or "auto"})

    @app.route("/save", methods=["POST"])
    def save():
        if not _transcriber.save_dir:
            return jsonify({"error": "save_dir not configured"}), 400
        if not getattr(_transcriber, "_last_text", None):
            return jsonify({"error": "nothing to save"}), 400
        path = _transcriber._next_save_path()
        if not path:
            return jsonify({"error": "save path error"}), 500
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(_transcriber._last_text)
            return jsonify({"saved": True, "path": path})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    print("Server: http://{}:{}/  (GET /health, /last; POST /transcribe, /save)".format(host, port))
    if _api_token:
        print("Auth: Bearer token required on all endpoints except /health.")
    elif host != "127.0.0.1":
        print("WARNING: server is exposed without --api-token. Anyone who can reach this address can transcribe audio.")
    app.run(host=host, port=port, threaded=True, use_reloader=False)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Dictation app using WhisperX (faster-whisper) ASR. By default the keyboard shortcut cmd+option '
        '(macOS) or ctrl+alt (others) starts and stops dictation.')
    parser.add_argument('-m', '--model_name', type=str,
                        choices=['tiny', 'tiny.en', 'base', 'base.en', 'small', 'small.en', 'medium', 'medium.en', 'large', 'large-v2', 'large-v3'],
                        default='base',
                        help='WhisperX/faster-whisper model: tiny, base, small, medium, large, large-v2, large-v3. '
                        'To see the  most up to date list of models along with model size, memory footprint, and estimated '
                        'transcription speed check out this [link](https://github.com/openai/whisper#available-models-and-languages). '
                        'Note that the models ending in .en are trained only on English speech and will perform better on English '
                        'language. Note that the small, medium, and large models may be slow to transcribe and are only recommended '
                        'if you find the base model to be insufficient. Default: base.')
    parser.add_argument('-k', '--key_combination', type=str,
                        default='cmd_l+alt' if platform.system() == 'Darwin' else 'ctrl+space',
                        help='Hotkey to start/stop recording. Examples: ctrl+space, alt+space (Windows); cmd_l+alt (macOS). Default: ctrl+space (Windows), cmd+alt (macOS).')
    parser.add_argument('--k_double_cmd', action='store_true',
                            help='If set, use double Right Command key press on macOS to toggle the app (double click to begin recording, single click to stop recording). '
                                 'Ignores the --key_combination argument.')
    parser.add_argument('-l', '--language', type=str, default=None,
                        help='Specify the two-letter language code (e.g., "en" for English) to improve recognition accuracy. '
                        'This can be especially helpful for smaller model sizes.  To see the full list of supported languages, '
                        'check out the official list [here](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py).')
    parser.add_argument('-t', '--max_time', type=float, default=None,
                        help='Optional maximum recording duration in seconds; omit for no limit (default). '
                        'Recording stops when this elapses or when you toggle stop, whichever comes first.')
    parser.add_argument('--enter-to-toggle', action='store_true',
                        help='Use Enter in the terminal to start/stop recording (no global hotkey). '
                        'Transcription is printed and copied to clipboard for pasting in Cursor.')
    parser.add_argument('--save-dir', type=str, default=None, metavar='DIR',
                        help='Directory for saving notes. Use the save hotkey (default Ctrl+Alt+N) to write the last transcription to a file.')
    parser.add_argument('--save-naming', type=str, choices=['number', 'time'], default='number',
                        help='When using --save-dir: "number" (transcript_001.txt, ...) or "time" (transcript_2026-03-13_14-30-45.txt). Default: number.')
    parser.add_argument('--save-hotkey', type=str, default='ctrl+alt+n', metavar='KEYS',
                        help='Hotkey to save the last (already finished) transcription to a note in --save-dir. Default: ctrl+alt+n.')
    parser.add_argument('--save-stop-hotkey', type=str, default='ctrl+alt+space', metavar='KEYS',
                        help='Hotkey that stops the current recording and saves the result directly to a file in --save-dir, without typing into the focused window. Default: ctrl+alt+space.')
    parser.add_argument('--server', action='store_true',
                        help='Run as HTTP API server instead of desktop app (transcribe, last, save).')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Server bind address (only with --server). Default: 127.0.0.1. Use 0.0.0.0 for LAN.')
    parser.add_argument('--port', type=int, default=8765,
                        help='Server port (only with --server). Default: 8765.')
    parser.add_argument('--server-url', type=str, default=None, metavar='URL',
                        help='Use remote server for transcription: same hotkeys/clipboard/save, but audio is sent to URL (e.g. http://127.0.0.1:8765). No local model load.')
    parser.add_argument('--input-devices', type=str, default=None, metavar='IDS',
                        help='Optional comma-separated device indices to record and mix together, e.g. "13,36". Can include input devices and output loopback devices.')
    parser.add_argument('--list-devices', action='store_true',
                        help='List available audio device indices (inputs and output-loopback candidates) and exit.')
    parser.add_argument('--diarize', action='store_true',
                        help='Enable optional speaker diarization (labels like [SPEAKER_00]). Can be slower.')
    parser.add_argument('--diarize-model', type=str, default='pyannote/speaker-diarization-community-1',
                        help='Diarization model name for WhisperX pyannote pipeline.')
    parser.add_argument('--hf-token', type=str, default=None,
                        help='Hugging Face token for gated diarization models, if required.')
    parser.add_argument('--initial-prompt', type=str, default=None, metavar='TEXT',
                        help='Optional ASR initial_prompt: sets decoding context (topic, setting, register, RU/EN mix). '
                        'For exact string fixes after transcription use --glossary-file. See README. '
                        'Mutually exclusive with --initial-prompt-file.')
    parser.add_argument('--initial-prompt-file', type=str, default=None, metavar='PATH',
                        help='UTF-8 file used as initial_prompt (multi-line context). Not for TSV corrections; '
                        'use --glossary-file. Mutually exclusive with --initial-prompt.')
    parser.add_argument('--glossary-file', type=str, default=None, metavar='PATH',
                        help='UTF-8 glossary table: column 1 = wrong text, column 2 = replacement. '
                        'Separator: tab, or two-or-more spaces between columns. Applied after each transcription. '
                        'If you do not pass --initial-prompt / --initial-prompt-file, '
                        'a short initial_prompt is built from unique values in column 2 (see --no-glossary-prompt).')
    parser.add_argument('--no-glossary-prompt', action='store_true',
                        help='With --glossary-file, skip building initial_prompt from column 2 (replacements only).')
    parser.add_argument('--api-token', type=str, default=None, metavar='TOKEN',
                        help='Secret bearer token to protect the HTTP API (server mode) or authenticate against a protected server (client mode). '
                        'Can also be set via the WHISPERX_API_TOKEN environment variable. '
                        'When set on the server, all endpoints except /health require "Authorization: Bearer <token>".')

    args = parser.parse_args()

    if not args.api_token:
        args.api_token = os.environ.get("WHISPERX_API_TOKEN") or None

    if args.language is not None:
        args.language = args.language.split(',')

    if args.model_name.endswith('.en') and args.language is not None and any(lang != 'en' for lang in args.language):
        raise ValueError('If using a model ending in .en, you cannot specify a language other than English.')
    if args.input_devices is not None:
        try:
            args.input_devices = [int(x.strip()) for x in args.input_devices.split(",") if x.strip()]
        except ValueError as e:
            raise ValueError("Invalid --input-devices format. Use comma-separated integer indices, e.g. 1,3") from e
    if args.initial_prompt and args.initial_prompt_file:
        raise ValueError("Use either --initial-prompt or --initial-prompt-file, not both.")
    if args.glossary_file and not os.path.isfile(args.glossary_file):
        raise ValueError("Glossary file not found: {}".format(args.glossary_file))
    return args


def _resolve_initial_prompt(args):
    """Return stripped initial_prompt string for whisperx load_model asr_options, or None."""
    if getattr(args, "initial_prompt_file", None):
        with open(args.initial_prompt_file, encoding="utf-8") as f:
            s = f.read().strip()
        return s if s else None
    if getattr(args, "initial_prompt", None):
        s = args.initial_prompt.strip()
        return s if s else None
    return None


if __name__ == "__main__":
    args = parse_args()

    if getattr(args, "list_devices", False):
        _list_input_devices()
        raise SystemExit(0)

    lang = args.language[0] if args.language else None
    server_url = getattr(args, "server_url", None)

    glossary_pairs = []
    if getattr(args, "glossary_file", None):
        glossary_pairs = load_glossary_tsv(args.glossary_file)
        print("(glossary: {} replacement rows)".format(len(glossary_pairs)))

    user_prompt = _resolve_initial_prompt(args)
    use_glossary_prompt = glossary_pairs and not getattr(args, "no_glossary_prompt", False)
    auto_from_glossary = glossary_initial_prompt(glossary_pairs) if use_glossary_prompt else None
    initial_prompt = user_prompt or auto_from_glossary

    if server_url:
        print("Client mode: using server", server_url, "(no local model)")
        if auto_from_glossary and not user_prompt:
            print("(note: ASR initial_prompt from glossary applies only on the server; "
                  "pass the same --glossary-file there, or use --initial-prompt on the server)")
        transcriber = ClientTranscriber(
            server_url,
            language=lang,
            diarize=getattr(args, "diarize", False),
            api_token=getattr(args, "api_token", None),
            glossary_pairs=glossary_pairs,
        )
    else:
        import torch
        import whisperx
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_name = args.model_name
        if model_name == "large":
            model_name = "large-v2"
        print(f"Loading model ({model_name}) on {device}...")
        asr_options = {"initial_prompt": initial_prompt} if initial_prompt else None
        if initial_prompt:
            src = "glossary (compact)" if not user_prompt and auto_from_glossary else "explicit"
            print("(using ASR initial_prompt [{}], {} chars)".format(src, len(initial_prompt)))
        model = whisperx.load_model(model_name, device, language=lang, asr_options=asr_options)
        print(f"{model_name} model loaded")
        transcriber = SpeechTranscriber(
            model,
            save_dir=getattr(args, "save_dir", None),
            save_naming=getattr(args, "save_naming", "number"),
            diarize=getattr(args, "diarize", False),
            hf_token=getattr(args, "hf_token", None),
            diarize_model=getattr(args, "diarize_model", "pyannote/speaker-diarization-community-1"),
            device=device,
            glossary_pairs=glossary_pairs,
        )
    recorder = Recorder(transcriber, input_devices=getattr(args, "input_devices", None))

    if getattr(args, "server", False):
        if server_url:
            print("Cannot use --server and --server-url together.")
            raise SystemExit(1)
        _run_server(transcriber, args)
        raise SystemExit(0)

#    app = StatusBarApp(recorder, args.language, args.max_time)
    if getattr(args, "enter_to_toggle", False):
        app = CLIAppEnter(recorder, args.language, args.max_time)
        print("Enter-to-toggle: press Enter to start recording, Enter again to stop. Result is printed and copied to clipboard.")
        if (getattr(args, "save_dir", None) or getattr(args, "server_url", None)) and platform.system() == "Windows":
            try:
                import keyboard as kb
                save_hk = getattr(args, "save_hotkey", "ctrl+alt+n").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                kb.add_hotkey(save_hk, app.save_last_note, suppress=False)
                transcriber.save_note_hint = save_hk
                save_stop_hk = getattr(args, "save_stop_hotkey", "ctrl+alt+space").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                kb.add_hotkey(save_stop_hk, app.stop_and_save, suppress=False)
                print("Stop recording + save to file: {}".format(save_stop_hk))
            except Exception:
                pass
        app.run()
    else:
        app = CLIApp(recorder, args.language, args.max_time)
        key_combo = args.key_combination
        # On Windows, use 'keyboard' library for global hotkey if available (more reliable than pynput)
        use_keyboard_lib = False
        if platform.system() == "Windows":
            try:
                import keyboard as kb
                # Normalize: ctrl+space, alt+space, ctrl+alt+space all valid
                hotkey_str = key_combo.replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                if hotkey_str in ("ctrl+alt", "control+alt"):
                    hotkey_str = "ctrl+alt+space"
                kb.add_hotkey(hotkey_str, app.toggle, suppress=False)
                if getattr(args, "save_dir", None) or getattr(args, "server_url", None):
                    save_hk = getattr(args, "save_hotkey", "ctrl+alt+n").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                    kb.add_hotkey(save_hk, app.save_last_note, suppress=False)
                    transcriber.save_note_hint = save_hk
                    save_stop_hk = getattr(args, "save_stop_hotkey", "ctrl+alt+space").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                    kb.add_hotkey(save_stop_hk, app.stop_and_save, suppress=False)
                use_keyboard_lib = True
                key_combo = hotkey_str  # show user the actual combo
            except ImportError:
                pass
            except Exception as e:
                print("(keyboard lib failed:", e, "- using pynput)")

        if use_keyboard_lib:
            print("Running... (hotkey: {} — press Ctrl+C to quit)".format(key_combo))
            if getattr(args, "save_dir", None) or getattr(args, "server_url", None):
                save_stop_hk = getattr(args, "save_stop_hotkey", "ctrl+alt+space").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                print("Stop recording + save to file: {}".format(save_stop_hk))
            print("If hotkey does not work, run this terminal as Administrator or use --enter-to-toggle.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nQuit.")
        else:
            if args.k_double_cmd:
                key_listener = DoubleCommandKeyListener(app)
            else:
                key_listener = GlobalKeyListener(app, key_combo)
            listener = keyboard.Listener(on_press=key_listener.on_key_press, on_release=key_listener.on_key_release)
            listener.start()
            print("Running... (hotkey: {})".format(key_combo))
            if getattr(args, "save_dir", None) or getattr(args, "server_url", None):
                save_stop_combo = getattr(args, "save_stop_hotkey", "ctrl+alt+space")
                save_stop_listener_obj = GlobalKeyListener(app, save_stop_combo)
                save_stop_listener_obj.app = type("_ShimApp", (), {"toggle": app.stop_and_save})()
                save_stop_listener = keyboard.Listener(
                    on_press=save_stop_listener_obj.on_key_press,
                    on_release=save_stop_listener_obj.on_key_release,
                )
                save_stop_listener.start()
                print("Stop recording + save to file: {}".format(save_stop_combo))
            app.run()

