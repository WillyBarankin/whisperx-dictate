"""Runtime guard: WhisperX on PyPI supports Python 3.10–3.13 only."""

import platform
import sys

_WHISPERX_EXCLUSIVE_MAX = (3, 14)


def ensure_python_supported_for_whisperx() -> None:
    if sys.version_info < _WHISPERX_EXCLUSIVE_MAX:
        return
    if platform.system() == "Windows":
        venv_activate = ".venv\\Scripts\\activate"
        py_launch = "py -3.12 -m venv .venv"
    else:
        venv_activate = "source .venv/bin/activate"
        py_launch = "python3.12 -m venv .venv"
    sys.stderr.write(
        "WhisperX (PyPI) supports Python 3.10–3.13 only, not %d.%d.\n"
        "Install Python 3.12 from https://www.python.org/downloads/, then for example:\n"
        "  %s\n"
        "  %s\n"
        "  pip install -r requirements.txt\n"
        % (
            sys.version_info.major,
            sys.version_info.minor,
            py_launch,
            venv_activate,
        )
    )
    raise SystemExit(1)
