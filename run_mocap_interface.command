#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

echo "MoCap interface:"
echo "  http://127.0.0.1:8765"
echo
echo "Press Control+C to stop the interface."
echo

python3 mocap_interface_server.py --host 127.0.0.1 --port 8765
