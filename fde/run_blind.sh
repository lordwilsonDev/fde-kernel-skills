#!/usr/bin/env bash
# One command: init a mission, turn the blind guard on, run Claude Code headless as the reasoning layer, turn the guard off, score.
#   fde/run_blind.sh <WORLD> <kernel|rules|raw> <run_name> [model]     e.g.  fde/run_blind.sh M005 kernel M005_haiku_kernel_x haiku
set -euo pipefail
cd "$(dirname "$0")/.."
WORLD=${1:?world}; MODE=${2:?mode kernel|rules|raw}; RUN=${3:?run name}; MODEL=${4:-haiku}
[ -e "runs/$RUN" ] && { echo "runs/$RUN exists; pick a new name (no silent reruns)"; exit 1; }
python3 -W ignore fde/prereg.py verify "$WORLD" 2>/dev/null || echo "WARNING: no matching pre-registration for $WORLD (run 'python3 fde/prereg.py new $WORLD ...' first)"
python3 -W ignore fde/driver.py init "runs/$RUN" "$WORLD" "$MODE" >/dev/null
trap 'python3 -W ignore fde/driver.py blind off >/dev/null' EXIT
python3 -W ignore fde/driver.py blind on >/dev/null
claude -p "Use the fde-mission skill to run the mission in runs/$RUN to completion. Mode: $MODE." \
  --model "$MODEL" --max-turns 60 --permission-mode acceptEdits \
  --allowedTools "Read,Write,Bash(python3 -W ignore fde/driver.py:*),Bash(python3 fde/driver.py:*)"
python3 -W ignore fde/driver.py blind off >/dev/null
python3 -W ignore fde/driver.py score "runs/$RUN"
