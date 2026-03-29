"""HTTP API server for transcription (Flask)."""

import os
import threading

import numpy as np

from whisperx_dictate.devices import SAMPLE_RATE


def create_flask_app(transcriber_holder, language=None, api_token=None):
    """Build Flask app instance; does not run it.

    ``transcriber_holder`` must be a mutable one-element list ``[transcriber]`` (or ``[None]``).
    Replace ``holder[0]`` when reloading the model so the same server thread keeps serving.
    """
    from flask import Flask, request, jsonify
    import whisperx

    if not isinstance(transcriber_holder, list) or not transcriber_holder:
        raise TypeError("transcriber_holder must be a non-empty list")

    app = Flask(__name__)
    _holder = transcriber_holder
    _lang = language
    _api_token = api_token

    def _current():
        return _holder[0]

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
        tr = _current()
        if tr is None:
            return jsonify({"text": "", "error": "model not loaded"}), 503
        text = getattr(tr, "_last_text", None)
        return jsonify({"text": text or ""})

    @app.route("/transcribe", methods=["POST"])
    def transcribe():
        tr = _current()
        if tr is None:
            return jsonify({"error": "model not loaded"}), 503
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
            audio_data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        text = tr.transcribe_to_text(audio_data, language=lang, diarize_override=diarize_override)
        return jsonify({"text": text or "", "language": lang or "auto"})

    @app.route("/save", methods=["POST"])
    def save():
        tr = _current()
        if tr is None:
            return jsonify({"error": "model not loaded"}), 503
        if not tr.save_dir:
            return jsonify({"error": "save_dir not configured"}), 400
        if not getattr(tr, "_last_text", None):
            return jsonify({"error": "nothing to save"}), 400
        path = tr._next_save_path()
        if not path:
            return jsonify({"error": "save path error"}), 500
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(tr._last_text)
            return jsonify({"saved": True, "path": path})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def run_server(transcriber, host, port, language=None, api_token=None):
    """Run Flask server in the current thread (blocking)."""
    try:
        from flask import Flask  # noqa: F401
    except ImportError:
        print("Install Flask for server mode: pip install flask")
        return
    holder = [transcriber]
    app = create_flask_app(holder, language=language, api_token=api_token)
    print("Server: http://{}:{}/  (GET /health, /last; POST /transcribe, /save)".format(host, port))
    if api_token:
        print("Auth: Bearer token required on all endpoints except /health.")
    elif host != "127.0.0.1":
        print("WARNING: server is exposed without --api-token. Anyone who can reach this address can transcribe audio.")
    app.run(host=host, port=port, threaded=True, use_reloader=False)


def run_server_in_thread(transcriber_holder, host, port, language=None, api_token=None):
    """Start Flask in a daemon background thread; returns the Thread.

    ``transcriber_holder`` is a one-element list shared with the GUI so ``holder[0]`` can be swapped on reload.
    """
    app = create_flask_app(transcriber_holder, language=language, api_token=api_token)

    def _run():
        app.run(host=host, port=port, threaded=True, use_reloader=False)

    t = threading.Thread(target=_run, name="whisperx-dictate-flask", daemon=True)
    t.start()
    return t
