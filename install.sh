#!/usr/bin/env bash
# Portable installer. Creates an FDE workspace anywhere (a folder holding fde/, .claude/ and runs/), optionally installs the skills globally.
#   ./install.sh <workspace-dir> [--symlink] [--global-skills] [--force]
#     (default)        copy fde/, .claude/, README into <workspace-dir>  -> fully self-contained, relocatable
#     --symlink        link fde/ and .claude/ back to this checkout      -> one source of truth, updates propagate
#     --global-skills  ALSO copy the three skills into ~/.claude/skills  -> /fde-kernel, /fde-mission, /fde-eval anywhere (run them from a workspace)
#     --force          overwrite an existing fde/ or .claude/ in the workspace
# Nothing outside <workspace-dir> is touched unless --global-skills is given. Env: FDE_VAULT (default ~/Documents/Vault), FDE_RUNS, FDE_HOME.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:?usage: install.sh <workspace-dir> [--symlink] [--global-skills] [--force]}"; shift || true
LINK=0; GLOBAL=0; FORCE=0
for a in "$@"; do case "$a" in --symlink) LINK=1;; --global-skills) GLOBAL=1;; --force) FORCE=1;; *) echo "unknown option $a"; exit 2;; esac; done
mkdir -p "$DEST/runs"; DEST="$(cd "$DEST" && pwd)"
[ "$DEST" = "$SRC" ] && { echo "workspace is the source checkout; nothing to install"; exit 0; }
for part in fde .claude hooks; do
  if [ -e "$DEST/$part" ] || [ -L "$DEST/$part" ]; then
    [ "$FORCE" = 1 ] || { echo "$DEST/$part exists (use --force)"; exit 1; }
    rm -rf "$DEST/$part"
  fi
  if [ "$LINK" = 1 ]; then ln -s "$SRC/$part" "$DEST/$part"; else cp -R "$SRC/$part" "$DEST/$part"; fi
done
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
cp "$SRC/README.md" "$DEST/README.md" 2>/dev/null || true
for f in AGENTS.md Makefile mypy.ini requirements-dev.txt frozen_format_exemptions.txt .python-version; do cp "$SRC/$f" "$DEST/$f" 2>/dev/null || true; done
printf 'runs/*/state.db\nruns/*/ctx_r*.json\n__pycache__/\n.fde_blind\n' > "$DEST/.gitignore"
chmod +x "$DEST/fde/run_blind.sh" "$DEST/fde/blind_guard.py" "$DEST/hooks/pre-commit" 2>/dev/null || true
if [ "$GLOBAL" = 1 ]; then
  mkdir -p "$HOME/.claude/skills"
  for s in fde-kernel fde-mission fde-eval; do rm -rf "$HOME/.claude/skills/$s"; cp -R "$SRC/.claude/skills/$s" "$HOME/.claude/skills/$s"; done
  echo "skills installed to $HOME/.claude/skills (fde-kernel, fde-mission, fde-eval). The blind guard hook is per-workspace (.claude/settings.json); it is NOT installed globally."
fi
echo "workspace ready: $DEST   ($( [ "$LINK" = 1 ] && echo symlinked || echo copied ))"
echo "next: cd \"$DEST\" && python3 -W ignore -m unittest discover -s fde/tests && python3 fde/lint_scenario.py M007"
