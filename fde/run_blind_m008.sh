#!/usr/bin/env bash
# M008 blinded model arm, one command: verify the registration, init the mission, switch the RUN-SCOPED guard on, run one headless Claude Code session
# as the reasoning layer, switch the guard off, score. The orchestrating session only ever runs this script; its own tools are unrestricted before and after.
#   fde/run_blind_m008.sh <kernel|rules|raw> <run_name> [haiku|sonnet]     e.g.  fde/run_blind_m008.sh kernel M008_haiku_kernel_a haiku
# Refuses to run without an intact active registry entry (registry.py verify M008) (hard failure, unlike run_blind.sh) and never reuses a run name.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE=${1:?mode kernel|rules|raw}; RUN=${2:?run name}; MODEL=${3:-haiku}
[ -e "runs/$RUN" ] && { echo "runs/$RUN exists; pick a new name (no silent reruns)"; exit 1; }
python3 -W ignore fde/registry.py verify M008 || { echo "no intact, active M008 registration; refusing to run"; exit 1; }
python3 -W ignore fde/driver_m008.py init "runs/$RUN" M008 "$MODE" --scored >/dev/null
trap 'python3 -W ignore fde/driver_m008.py blind off >/dev/null' EXIT
python3 -W ignore fde/driver_m008.py blind on "runs/$RUN" >/dev/null
claude -p "Use the fde-mission skill to run the mission in runs/$RUN to completion. Mode: $MODE. This mission's driver is fde/driver_m008.py: wherever the skill says fde/driver.py, run fde/driver_m008.py instead, with the same arguments. Propose exactly ONE action name per round." \
  --model "$MODEL" --max-turns 60 --permission-mode acceptEdits \
  --allowedTools "Read,Write,Skill,Bash(python3 -W ignore fde/driver_m008.py:*),Bash(python3 fde/driver_m008.py:*)"
python3 -W ignore fde/driver_m008.py blind off >/dev/null
python3 -W ignore fde/driver_m008.py score "runs/$RUN"
