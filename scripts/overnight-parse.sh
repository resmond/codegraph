#!/usr/bin/env bash
# Launch the full C++ extraction as a background user service that blocks sleep.
# Usage: scripts/overnight-parse.sh [run-dir] [workers]
#   Watch:  tail -f <run-dir>/progress.log      Status: systemctl --user status codegraph-parse
#   Stop:   systemctl --user stop codegraph-parse  (rerun the same command to resume)
# Needs you to stay logged in (user lingering is off), but survives closing terminals/VS Code.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REV=$(git -C "$HOME/src/FreeCAD" rev-parse --short=10 HEAD)
RUN="${1:-$HOME/.cache/codegraph/runs/$(date +%F)-freecad-$REV}"
WORKERS="${2:-6}"
systemd-run --user --unit=codegraph-parse --collect \
  --working-directory="$REPO" \
  -p Nice=10 -p MemoryHigh=12G \
  systemd-inhibit --what=sleep:idle --who=codegraph --why="FreeCAD code parse" \
  uv run cg-extract-cpp --out "$RUN" --workers "$WORKERS"
echo "started codegraph-parse -> $RUN"
echo "progress: tail -f $RUN/progress.log"
