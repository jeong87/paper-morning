#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"
"$PYTHON_EXE" local_ui_launcher.py --host 127.0.0.1 --port 5050
