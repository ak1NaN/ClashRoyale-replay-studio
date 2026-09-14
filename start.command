#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if [ "$(uname -s)" = Darwin ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then
  set -- arch -arm64
else
  set --
fi
if [ ! -x .venv/bin/python ]; then
  "$@" python3 -m venv .venv || exit 1
fi
"$@" .venv/bin/python -c 'import PySide6, frida' 2>/dev/null || "$@" .venv/bin/python -m pip install -r requirements.txt || exit 1
exec "$@" .venv/bin/python run_desktop.py
