#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/asf_amc_to_xyz_csv.py"

cd "$SCRIPT_DIR"

if [ $# -ge 3 ]; then
  python3 "$PYTHON_SCRIPT" "$1" "$2" "$3"
elif [ $# -ge 2 ]; then
  python3 "$PYTHON_SCRIPT" "$1" "$2"
else
  python3 "$PYTHON_SCRIPT"
fi

echo
read -r "?Press Enter to close..."
