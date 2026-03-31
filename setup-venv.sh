#!/usr/bin/env bash
# Create .venv with Python 3.10-3.13 and install dependencies (Git Bash / WSL / macOS / Linux).
set -euo pipefail
cd "$(dirname "$0")"

resolve_supported_python() {
  local v
  for v in 3.12 3.13 3.11 3.10; do
    if command -v py >/dev/null 2>&1; then
      if out=$(py -"${v}" -c "import sys; print(sys.executable)" 2>/dev/null); then
        echo "$out"
        return 0
      fi
    fi
  done
  for v in python3.12 python3.13 python3.11 python3.10; do
    if command -v "$v" >/dev/null 2>&1; then
      command -v "$v"
      return 0
    fi
  done
  return 1
}

if ! PY=$(resolve_supported_python); then
  echo "error: No Python 3.10-3.13 found." >&2
  echo "WhisperX on PyPI does not support Python 3.14+ yet; pip cannot install torch 2.8 there." >&2
  echo "Install 3.12 from https://www.python.org/downloads/ (on Windows, enable the py launcher)." >&2
  exit 1
fi

echo "Using interpreter: $PY"
"$PY" -m venv .venv

if [[ -f .venv/Scripts/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/Scripts/activate
else
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
echo
echo "Done. Activate later:  source .venv/Scripts/activate   (this shell)"
echo "Or Command Prompt:      .venv\\Scripts\\activate.bat"
