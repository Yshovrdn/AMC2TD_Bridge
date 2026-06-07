#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

echo "Serving visualizer at:"
echo "  http://127.0.0.1:8000/web/point_visualizer.html"
echo
echo "Sample load:"
echo "  http://127.0.0.1:8000/web/point_visualizer.html?src=../01_08.csv"
echo
echo "Press Control+C to stop the server."
echo

python3 -m http.server 8000
