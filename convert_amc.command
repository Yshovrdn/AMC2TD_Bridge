#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/amc_to_csv.py"

cd "$SCRIPT_DIR"

if [ $# -ge 1 ]; then
  python3 "$PYTHON_SCRIPT" "$1"
else
  python3 "$PYTHON_SCRIPT"
fi

echo
read -r "?Press Enter to close..."
