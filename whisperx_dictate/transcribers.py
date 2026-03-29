import time

import numpy as np
from pynput import keyboard

try:
    import pyperclip
    _HAS_PYPERCLIP = True
except ImportError:
    _HAS_PYPERCLIP = False

from whisperx_dictate.glossary import apply_glossary

# TUIs (e.g. Claude Code in terminal) drop key events if injection is too fast; ~2.5ms/char loses spaces on long lines.
_INJECT_KEY_DELAY_SEC = 0.022


def _inject_type_text(controller: keyboard.Controller, text: str) -> None:
    started = False
    for element in text:
        if element == " " and not started:
            continue
        started = True
        try:
            controller.type(element)
            time.sleep(_INJECT_KEY_DELAY_SEC)
        except Exception:
            pass


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
        on_message=None,
        on_transcript=None,
        inject_typing=True,
        copy_to_clipboard=True,
    ):
        self.model = model
        self.glossary_pairs = glossary_pairs or []
        self.pykeyboard = keyboard.Controller()
        self.save_dir = save_dir
        self.save_naming = save_naming
        self.diarize = diarize
        self.hf_token = hf_token
        self.diarize_model = diarize_model
        self.device = device
        self._diarization_pipeline = None
        self._save_counter = 0
        self._last_text = None
        self._save_on_next = False
        self.save_note_hint = None
        self.on_message = on_message
        self.on_transcript = on_transcript
        self.inject_typing = inject_typing
        self.copy_to_clipboard = copy_to_clipboard

    def _msg(self, *parts):
        if self.on_message:
            self.on_message(" ".join(str(p) for p in parts))
        else:
            print(*parts)

    def _next_save_path(self):
        """Return path for next transcript file based on save_naming."""
        import os
        from datetime import datetime

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
        import os

        if not self.save_dir:
            return
        if not self._last_text:
            self._msg("(nothing to save — dictate first)")
            return
        path = self._next_save_path()
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._last_text)
                self._msg("(saved to {})".format(path))
            except Exception as e:
                self._msg("(save failed:", e, ")")

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
            self._msg("(failed to initialize diarization pipeline:", e, ")")
            self._diarization_pipeline = False
        return self._diarization_pipeline

    @staticmethod
    def _segments_to_text(segments):
        chunks = []
        last_speaker = None
        line_sep = "\n"
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
                    self._msg("(diarization failed:", e, ")")

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
            self._msg("(no speech detected)")
            return
        if self.on_transcript:
            self.on_transcript(text)
        else:
            self._msg("→", text)
        if save_mode and self.save_dir:
            path = self._next_save_path()
            if path:
                try:
                    import os
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                    self._msg("(saved to {})".format(path))
                except Exception as e:
                    self._msg("(save failed:", e, ")")
            return
        if self.copy_to_clipboard and _HAS_PYPERCLIP:
            try:
                pyperclip.copy(text)
                self._msg("(copied to clipboard — paste with Ctrl+V)")
            except Exception as e:
                self._msg("(clipboard copy failed:", e, ")")
        elif self.copy_to_clipboard:
            self._msg("(install pyperclip for clipboard: pip install pyperclip)")
        if self.inject_typing:
            _inject_type_text(self.pykeyboard, text)
        if self.save_note_hint:
            self._msg("(save to note: {})".format(self.save_note_hint))


class ClientTranscriber:
    """Transcriber that sends audio to a remote server."""

    def __init__(
        self,
        server_url,
        language=None,
        diarize=False,
        api_token=None,
        glossary_pairs=None,
        on_message=None,
        on_transcript=None,
        inject_typing=True,
        copy_to_clipboard=True,
    ):
        self.server_url = server_url.rstrip("/")
        self._language = language
        self._diarize = diarize
        self._api_token = api_token
        self.glossary_pairs = glossary_pairs or []
        self.pykeyboard = keyboard.Controller()
        self.save_dir = None
        self._last_text = None
        self._save_on_next = False
        self.save_note_hint = None
        self.on_message = on_message
        self.on_transcript = on_transcript
        self.inject_typing = inject_typing
        self.copy_to_clipboard = copy_to_clipboard
        try:
            import urllib.request
            with urllib.request.urlopen(self.server_url + "/health", timeout=5) as _:
                pass
        except Exception as e:
            self._msg("(warning: server not reachable at", self.server_url, "—", e, ")")

    def _msg(self, *parts):
        if self.on_message:
            self.on_message(" ".join(str(p) for p in parts))
        else:
            print(*parts)

    def _add_auth(self, req):
        if self._api_token:
            req.add_header("Authorization", "Bearer " + self._api_token)

    def _post_transcribe(self, audio_bytes, language=None):
        import json
        import urllib.request

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
            self._msg("(server error:", e, ")")
            return None

    def _post_save(self):
        import json
        import urllib.request

        req = urllib.request.Request(self.server_url + "/save", data=b"", method="POST")
        self._add_auth(req)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            self._msg("(save on server failed:", e, ")")
            return None

    def save_last_to_note(self):
        if not self._last_text:
            self._msg("(nothing to save — dictate first)")
            return
        out = self._post_save()
        if out and out.get("saved"):
            self._msg("(saved on server to {})".format(out.get("path", "?")))
        elif out and out.get("error"):
            self._msg("(save error:", out["error"], ")")

    def transcribe(self, audio_data, language=None):
        save_mode = self._save_on_next
        self._save_on_next = False
        if audio_data.dtype != np.int16:
            audio_bytes = (audio_data * 32768.0).astype(np.int16).tobytes()
        else:
            audio_bytes = audio_data.tobytes()
        out = self._post_transcribe(audio_bytes, language)
        if not out:
            return
        text = (out.get("text") or "").strip()
        if not text:
            self._msg("(no speech detected)")
            return
        if self.glossary_pairs:
            text = apply_glossary(text, self.glossary_pairs)
        self._last_text = text
        if self.on_transcript:
            self.on_transcript(text)
        else:
            self._msg("→", text)
        if save_mode:
            out2 = self._post_save()
            if out2 and out2.get("saved"):
                self._msg("(saved on server to {})".format(out2.get("path", "?")))
            elif out2 and out2.get("error"):
                self._msg("(save error:", out2["error"], ")")
            return
        if self.copy_to_clipboard and _HAS_PYPERCLIP:
            try:
                pyperclip.copy(text)
                self._msg("(copied to clipboard — paste with Ctrl+V)")
            except Exception as e:
                self._msg("(clipboard copy failed:", e, ")")
        elif self.copy_to_clipboard:
            self._msg("(install pyperclip for clipboard: pip install pyperclip)")
        if self.inject_typing:
            _inject_type_text(self.pykeyboard, text)
        if self.save_note_hint:
            self._msg("(save to note: {})".format(self.save_note_hint))
