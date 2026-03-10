#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_EXE="${PYTHON_EXE:-python3}"
"$PYTHON_EXE" "$REPO_ROOT/app/local_ui_launcher.py" --host 127.0.0.1 --port 5050
