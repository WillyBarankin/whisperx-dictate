import platform

try:
    import pyaudiowpatch as pyaudio  # Windows loopback-capable build
except ImportError:
    import pyaudio

SAMPLE_RATE = 16000


def normalize_device_name(name):
    """Best-effort fix for mojibake device names on Windows."""
    text = str(name)
    if platform.system() != "Windows":
        return text
    if "Р" in text or "С" in text:
        try:
            fixed = text.encode("cp1251").decode("utf-8")
            if fixed:
                return fixed
        except Exception:
            pass
    return text


def list_input_devices():
    """Return list of dicts: index, name, role, max_input_channels, max_output_channels."""
    p = pyaudio.PyAudio()
    entries = []
    try:
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            max_in = int(info.get("maxInputChannels", 0))
            max_out = int(info.get("maxOutputChannels", 0))
            if max_in > 0 or max_out > 0:
                name = normalize_device_name(info.get("name"))
                if max_in > 0 and max_out > 0:
                    role = f"input+output (inputs: {max_in}, outputs: {max_out})"
                elif max_in > 0:
                    role = f"input (inputs: {max_in})"
                else:
                    role = f"output-only/loopback candidate (outputs: {max_out})"
                entries.append(
                    {
                        "index": i,
                        "name": name,
                        "role": role,
                        "max_input_channels": max_in,
                        "max_output_channels": max_out,
                    }
                )
    finally:
        p.terminate()
    return entries


def print_input_devices():
    """Print available audio devices (CLI)."""
    entries = list_input_devices()
    print("Available audio devices:")
    if not entries:
        print("  (no audio devices found)")
        return
    for e in entries:
        print(f"  {e['index']}: {e['name']} [{e['role']}]")


def get_pyaudio_module():
    """Return the active pyaudio module (pyaudiowpatch or pyaudio)."""
    return pyaudio
