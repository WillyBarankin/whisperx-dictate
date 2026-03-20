import time
import threading

import numpy as np

from whisperx_dictate.devices import SAMPLE_RATE, normalize_device_name, get_pyaudio_module


class Recorder:
    def __init__(self, transcriber, input_devices=None, on_message=None):
        self.recording = False
        self.transcriber = transcriber
        self.input_devices = input_devices or []
        self.on_message = on_message

    def _msg(self, *parts):
        if self.on_message:
            self.on_message(" ".join(str(p) for p in parts))
        else:
            print(*parts)

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
        pyaudio = get_pyaudio_module()
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
                    name = normalize_device_name(info.get("name"))

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
                        self._msg(f"(failed to open device {device_idx}: {e})")
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
                    self._msg("Recording from selected devices:")
                    for item in opened:
                        self._msg("  - " + item)
                if not streams:
                    self._msg("(no selected devices could be opened)")
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
            self._msg("(audio input open failed:", e, ")")
            for s in streams:
                try:
                    s["stream"].close()
                except Exception:
                    pass
            p.terminate()
            self.recording = False
            return

        t0 = time.time()

        def _read_one_stream(s):
            while self.recording:
                try:
                    raw = s["stream"].read(s["chunk_frames"], exception_on_overflow=False)
                    s["frames"].append(raw)
                except Exception:
                    break

        if len(streams) > 1:
            workers = [threading.Thread(target=_read_one_stream, args=(s,), daemon=True) for s in streams]
            for w in workers:
                w.start()
            try:
                while self.recording:
                    if max_time is not None and max_time > 0 and (time.time() - t0) >= max_time:
                        self._msg("(max recording time {:.0f}s reached — stopping)".format(max_time))
                        self.recording = False
                        break
                    time.sleep(0.05)
            finally:
                for s in streams:
                    try:
                        s["stream"].stop_stream()
                    except Exception:
                        pass
                self.recording = False
                for w in workers:
                    w.join(timeout=5.0)
        else:
            while self.recording:
                if max_time is not None and max_time > 0 and (time.time() - t0) >= max_time:
                    self._msg("(max recording time {:.0f}s reached — stopping)".format(max_time))
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
                track = track[:usable].reshape(-1, ch)[:, 0]
            track = track.astype(np.float32) / 32768.0
            track = self._resample_mono(track, s["rate"], target_rate)
            if track.size > 0:
                tracks.append(track)

        if not tracks:
            self._msg("(no audio captured)")
            return

        normalized = []
        for t in tracks:
            rms = float(np.sqrt(np.mean(np.square(t), dtype=np.float64))) if t.size else 0.0
            if rms > 1e-6:
                gain = min(0.05 / rms, 4.0)
                normalized.append((t * gain).astype(np.float32))
            else:
                normalized.append(t.astype(np.float32))

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
