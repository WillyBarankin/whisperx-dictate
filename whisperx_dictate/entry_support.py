"""Lightweight helpers for repo-root launchers (see whisperx-dictate*.py)."""

import sys


def require_pynput() -> None:
    """Exit with a helpful message when dependencies are missing (venv not active / wrong interpreter)."""
    try:
        import pynput  # noqa: F401
    except ModuleNotFoundError:
        sys.stderr.write(
            "Missing dependency: pynput (and likely the rest of requirements.txt).\n"
            "This usually means the virtual environment is not active or `py` picked Python without your installs.\n"
            "From the project folder run:  setup-venv.bat   or   bash setup-venv.sh\n"
            "Then in Git Bash:  source .venv/Scripts/activate\n"
            "Then:              python whisperx-dictate-gui.py\n"
        )
        raise SystemExit(1)
