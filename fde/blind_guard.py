#!/usr/bin/env python3
"""PreToolUse hook: enforced blindness for one blinded mission run.  Active ONLY while <project>/.fde_blind exists.
The marker is written by `python3 fde/driver_m008.py blind on runs/<run>` and MUST carry `run=<name>` (ASCII [A-Za-z0-9_-]+); a marker without a valid run is a
misconfiguration and denies every tool. This is capability authorization on CANONICAL objects, not pattern matching on strings:
  Read   : exactly runs/<run>/ctx_r<CURRENT>.json or proposal_r<CURRENT>.json, a regular non-symlink file whose resolved parent is the run directory
  Write  : exactly runs/<run>/proposal_r<CURRENT>.json, create-once (existing file, symlink, or any other target is denied); Edit is denied
  Bash   : one of exactly four literal command strings (status / apply for the current round; with or without `-W ignore`), cwd = project root if a cwd is supplied
  Skill  : fde-mission only
  every other tool (Grep, Glob, WebFetch, WebSearch, Agent, MCP, NotebookEdit, ...) : denied
CURRENT is read from the run's own run.json (which the arm cannot write). Paths must not contain control characters, `~`, `..`, or a URL scheme; absolute paths are accepted
only if they resolve to the same object; anything that resolves outside the run directory is denied. Output is exactly: exit 0 = explicitly allowed, exit 2 = denied
(including every internal error and every malformed payload: fail closed). Nothing here can exit 1."""
import sys, os, json, re
from pathlib import Path

RUN_RE = re.compile(r"[A-Za-z0-9_\-]{1,80}", re.ASCII)

def deny(why):
    print(f"BLIND GUARD: blocked. {why} This session is a blind mission run: read only this run's current ctx_r<N>.json, write only its proposal_r<N>.json (once), and use `python3 fde/driver_m008.py status|apply` exactly.", file=sys.stderr); sys.exit(2)

def bad_text(s): return (not isinstance(s, str)) or (not s) or any(ord(c) < 32 or ord(c) == 127 for c in s) or "~" in s or "://" in s or ".." in s.replace("\\", "/").split("/")

def main():
    root_env = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not os.path.exists(os.path.join(root_env, ".fde_blind")): sys.exit(0)          # guard inactive: orchestrator / normal session
    root = Path(root_env).resolve(strict=True)
    try: mtext = (root / ".fde_blind").read_text()
    except Exception: deny("marker unreadable.")
    m = re.search(r"^run=(.*)$", mtext, re.M)
    if not m or not RUN_RE.fullmatch(m.group(1)): deny("marker has no valid run=<name>; refusing every tool.")
    run = m.group(1); run_root = (root / "runs" / run)
    if run_root.is_symlink() or not run_root.is_dir() or run_root.resolve(strict=True) != root / "runs" / run: deny("active run directory is not a plain directory under runs/.")
    run_root = run_root.resolve(strict=True)
    try:
        st = json.loads((run_root / "run.json").read_text()); cur = st["round"]
        if not isinstance(cur, int) or isinstance(cur, bool) or cur < 0: raise ValueError
    except Exception: deny("run.json unreadable; cannot determine the current round.")
    try: data = json.load(sys.stdin)
    except Exception: deny("hook payload unreadable.")
    if not isinstance(data, dict): deny("hook payload must be an object.")
    tool, inp = data.get("tool_name"), data.get("tool_input")
    if not isinstance(tool, str): deny("tool_name must be a string.")
    if not isinstance(inp, dict): deny("tool_input must be an object.")
    cwd = data.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or Path(cwd).resolve() != root) and tool == "Bash": deny("working directory is not the project root.")
    ctx_name, prop_name = f"ctx_r{cur}.json", f"proposal_r{cur}.json"

    def cand(raw):
        if bad_text(raw): deny(f"path {str(raw)[:80]!r} is not an acceptable path.")
        p = Path(raw); return p if p.is_absolute() else root / p

    if tool == "Read":
        c = cand(inp.get("file_path"))
        if c.is_symlink(): deny("symlinks are not permitted.")
        try: real = c.resolve(strict=True)
        except Exception: deny("file does not exist.")
        if not real.is_file() or real.parent != run_root or real.name not in (ctx_name, prop_name) or c.name != real.name: deny("only this run's current context/proposal file is readable.")
    elif tool == "Write":
        c = cand(inp.get("file_path"))
        try: parent = c.parent.resolve(strict=True)
        except Exception: deny("write target directory does not exist.")
        if parent != run_root or c.name != prop_name: deny("only this run's proposal for the current round may be written.")
        if os.path.lexists(c): deny("that proposal file already exists; proposals are create-once.")
    elif tool == "Bash":
        cmd = inp.get("command")
        if not isinstance(cmd, str) or any(not (0x20 <= ord(ch) <= 0x7e) for ch in cmd): deny("command must be printable ASCII.")
        ok = set()
        for py in ("python3 ", "python3 -W ignore "): ok |= {f"{py}fde/driver_m008.py status runs/{run}", f"{py}fde/driver_m008.py apply runs/{run} runs/{run}/{prop_name}"}
        if cmd not in ok: deny(f"command not allowed: {cmd[:80]!r}")
    elif tool == "Skill":
        if inp.get("skill") != "fde-mission": deny("only the fde-mission skill is allowed.")
    else: deny(f"tool {tool!r} is not allowed in a blind mission run (search, web, MCP, sub-agents and edits are closed).")
    sys.exit(0)

if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except BaseException: deny("internal authorization error (denied fail-closed).")
