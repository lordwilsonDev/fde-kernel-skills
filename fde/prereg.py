"""Write a pre-registration BEFORE any run: hashes of the frozen code plus your predictions.
  python3 fde/prereg.py new <WORLD> --arms "haiku:kernel,rules,raw x3; sonnet:kernel,rules,raw x1" --predictions predictions.md
  python3 fde/prereg.py addendum <WORLD> "text of the change / deviation"
  python3 fde/prereg.py verify <WORLD>        # re-hash the code and compare to the registered hashes
Refuses to overwrite an existing registration; deviations go in an addendum (append-only)."""

import sys, os, hashlib, datetime, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config
import registry  # coverage of closed-family drift by newer registry families (covered_drift)

RUNS = config.RUNS
FILES = ["kernel.py", "driver.py", "simulator.py", "schema.sql"]
# A family may freeze more than the four core files. M007 (and earlier) keep FILES exactly, so `verify M007` is unaffected.
# M008 also freezes its own simulator/driver, the linter and blind guard, the hook config, the M008 runner and the M008 test.
FILES_BY_WORLD = {
    "M008": FILES
    + [
        "simulator_m008.py",
        "driver_m008.py",
        "lint_scenario.py",
        "blind_guard.py",
        "manifest.py",
        "run_blind_m008.sh",
        "report.py",
        "inspect_run.py",
        "tests/test_m008.py",
        "../.claude/settings.json",
    ]
}
files = lambda world: FILES_BY_WORLD.get(world, FILES)


def h(p):
    fp = os.path.join(HERE, p)
    return hashlib.sha256(open(fp, "rb").read()).hexdigest() if os.path.isfile(fp) else "MISSING"


NAME_OK = re.compile(r"^[A-Za-z0-9_]{1,40}$", re.ASCII)


def safe_world(w):
    if not isinstance(w, str) or not NAME_OK.fullmatch(w):
        sys.exit(f"invalid world name {w!r} (letters, digits, underscore only)")
    return w


now = lambda: datetime.datetime.now(datetime.UTC).isoformat()
path = lambda w: os.path.join(RUNS, f"PREREG_{safe_world(w)}.md")


def _latest_freeze(world):
    """(frozen-hashes, source label): the last addendum's full hashes if any, else the original registration."""
    s = open(path(world)).read()
    adds = re.findall(r"Frozen-hashes \(full\) at addendum: (.*)", s)
    if adds:
        return dict(kv.split("=", 1) for kv in adds[-1].split()), f"addendum #{len(adds)}"
    return {f: (re.search(rf"- {re.escape(f)}: ([0-9a-f]{{64}})", s) or [None, None])[1] for f in files(world)}, "original registration"


def _registered_at(world):
    """ISO registration time; '' if unparseable = older than every registry record
    (true by construction: the registry replaced prereg from M008 onward)."""
    try:
        return re.search(r"Registered ([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.+-]+)", open(path(world)).read()).group(1)
    except (AttributeError, OSError):
        return ""


def _advanced_under(world, changed):
    """Drift re-frozen VERBATIM by a NEWER registry family: {file: 'WORLD vN'}.
    Closed families stay verifiable while the next family evolves shared code;
    without such a registration every changed file stays a mismatch (red)."""
    if not changed:
        return {}
    return registry.covered_drift(_registered_at(world), changed, {f: h(f) for f in changed}, runs=RUNS)


def new(world, arms, predictions):
    p = path(world)
    if os.path.exists(p):
        sys.exit(f"{p} exists; use 'addendum'")
    if [f for f in files(world) if h(f) == "MISSING"]:
        sys.exit(f"frozen files missing: {[f for f in files(world) if h(f) == 'MISSING']}")
    os.makedirs(RUNS, exist_ok=True)
    body = (
        f"# Pre-registration - {world}\nRegistered {now()} BEFORE any run.\n\n## Frozen code (sha256)\n"
        + "\n".join(f"- {f}: {h(f)}" for f in files(world))
    )
    body += f"\n\n## Arms\n{arms}\n\n## Primary metrics (deterministic, from DB + ground truth)\nroot_cause_correct_and_supported; false_root_cause_at_least_inferred; decoy_mitigation_applied and its gate decision; mitigation_effective; unauthorized_action_proposals; claim_violations_or_denials (+kinds); impact_inflated / impact_correct_established; contradictions opened/resolved; pending_review_left at close; rounds; audit rows.\n"
    body += f"\n## Predictions (write the ones AGAINST your own system too)\n{predictions}\n\n## Analysis rule\nReport every cell and every miss. No post-hoc metric redefinition. No significance claims at small n. Any code change after this point is a new version and must be run on a NEW scenario family.\n"
    open(p, "w").write(body)
    print(f"wrote {p}")


def addendum(world, text, refreeze=False):
    """LEGACY registry (closed families). An addendum can no longer turn a code change into an accepted freeze: if any frozen file differs from the latest freeze, this refuses
    unless --refreeze is given (which is then recorded in the addendum text). New families use fde/registry.py, where a change to the freeze is a new version.
    """
    p = path(world)
    if not os.path.exists(p):
        sys.exit(f"no registration for {world}")
    if not isinstance(text, str) or not text.strip():
        sys.exit("addendum text is empty")
    text = text.replace("Frozen-hashes", "Frozen_hashes").replace(
        "Code hashes at addendum time", "Code_hashes_at_addendum_time"
    )
    if not refreeze and _mismatches(world):
        sys.exit(
            f"REFUSED: frozen files changed since the latest freeze {_mismatches(world)}; an addendum would silently re-freeze them. Re-run with --refreeze (recorded), or start a new family."
        )
    if refreeze:
        text = "[REFREEZE requested explicitly] " + text
    frozen = " ".join(f"{f}={h(f)}" for f in files(world))
    open(p, "a").write(
        f"\n\n## ADDENDUM (registered {now()}, append-only)\n{text}\nCode hashes at addendum time: "
        + "; ".join(f"{f} {h(f)[:12]}" for f in files(world))
        + f"\nFrozen-hashes (full) at addendum: {frozen}\n"
    )
    print("addendum appended (code re-frozen at the hashes above)")


def _mismatches(world):
    """Files not matching the latest freeze, MINUS drift covered by a newer registry family."""
    frozen, _ = _latest_freeze(world)
    changed = [f for f in files(world) if frozen.get(f) != h(f)]
    cov = _advanced_under(world, changed)
    return [f for f in changed if f not in cov]


def verify(world):
    """Checks the code against the LATEST freeze: the last addendum's full hashes if any, else the original registration.
    Drift whose current hash is re-frozen by a NEWER registry family prints as advanced-under and exits 0; everything else still exits 1."""
    if not os.path.exists(path(world)):
        sys.exit(f"no registration for {world}")
    frozen, src = _latest_freeze(world)
    unknown = [f for f in files(world) if not frozen.get(f)]
    changed = [f for f in files(world) if frozen.get(f) and frozen[f] != h(f)]
    cov = _advanced_under(world, changed)
    bad = [f"{f}: not registered" for f in unknown] + [
        f"{f}: CHANGED since {src}" for f in changed if f not in cov
    ]
    if bad:
        print("MISMATCH:\n  " + "\n  ".join(bad))
        sys.exit(1)
    via = (
        f" (tree advanced under {', '.join(sorted(set(cov.values())))}: {', '.join(sorted(cov))})"
        if cov
        else ""
    )
    print(f"OK: code matches {src}{via}")
    sys.exit(0)


if __name__ == "__main__":
    a = sys.argv
    if len(a) >= 3 and a[1] == "new":
        arms = a[a.index("--arms") + 1] if "--arms" in a else "(specify)"
        pred = (
            open(a[a.index("--predictions") + 1]).read()
            if "--predictions" in a
            else "(specify before running)"
        )
        new(a[2], arms, pred)
    elif len(a) >= 4 and a[1] == "addendum":
        rf = "--refreeze" in a
        addendum(a[2], " ".join(x for x in a[3:] if x != "--refreeze"), refreeze=rf)
    elif len(a) >= 3 and a[1] == "verify":
        verify(a[2])
    else:
        print(__doc__)
