"""Format gate whose exemptions EQUAL the byte-pinned set. Modes:
  python3 fde/hygiene.py frozen       list frozen .py paths (latest registration per world + M007 baseline)
  python3 fde/hygiene.py exemptions   list the exemption file
  python3 fde/hygiene.py validate     exit 1 unless exemptions == frozen
                                      (no runs/registrations -> warn to stderr, exit 0: installed copies
                                       ship the code, not the experiment)
  python3 fde/hygiene.py fmt-check    validate, then `black --check` every fde/**/*.py NOT exempt
                                      (the gate never writes)
  python3 fde/hygiene.py fmt-fix      validate, then `black` those same files (the ONLY safe
                                      auto-format: bare `black fde` would rewrite frozen files)
Why: FDE freezes files by hash (runs/registrations/*/v*/registration.json +
fde/tests/m007_baseline.json). Frozen files are UNFIXABLE — a formatter must never touch
them — and everything else must stay black-clean, so the exemption list can neither grow
(a free file dodging the gate) nor shrink (a frozen file handed to the formatter).
Enforced by fde/tests/test_repo_hygiene.py."""

import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXEMPT_FILE = os.path.join(ROOT, "frozen_format_exemptions.txt")
REG_DIR = os.path.join(ROOT, "runs", "registrations")
SKIP_DIRS = {"__pycache__", ".git", "runs"}


def frozen_py() -> set:
    """ROOT-relative paths of every byte-pinned .py file."""
    out: set = set()
    if os.path.isdir(REG_DIR):
        for world in sorted(os.listdir(REG_DIR)):
            for v in sorted(glob.glob(os.path.join(REG_DIR, world, "v*"))):
                rec = os.path.join(v, "registration.json")
                if os.path.exists(
                    os.path.join(v, "superseded_by.json")
                ) or not os.path.exists(rec):
                    continue
                files = json.load(open(rec)).get("files", {})
                for rel in files:
                    p = os.path.normpath(os.path.join("fde", rel)).replace("\\", "/")
                    if p.endswith(".py"):
                        out.add(p)
    base = os.path.join(HERE, "tests", "m007_baseline.json")
    if os.path.exists(base):
        out.update(p for p in json.load(open(base))["files"] if p.endswith(".py"))
    return out


def exemptions() -> set:
    if not os.path.exists(EXEMPT_FILE):
        return set()
    return {
        s
        for s in (ln.strip() for ln in open(EXEMPT_FILE))
        if s and not s.startswith("#")
    }


def coverage() -> list:
    """Every fde/**/*.py that the formatter OWNS (not exempt), ROOT-relative, sorted."""
    exempt = exemptions()
    out: list = []
    for dp, dn, fn in os.walk(os.path.join(ROOT, "fde")):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        for f in sorted(fn):
            if f.endswith(".py"):
                p = os.path.relpath(os.path.join(dp, f), ROOT).replace("\\", "/")
                if p not in exempt:
                    out.append(p)
    return sorted(out)


def validate() -> int:
    if not os.path.isdir(REG_DIR):
        print(
            "hygiene: no runs/registrations here — exemption validation skipped (installed copy)",
            file=sys.stderr,
        )
        return 0
    exp, fro = exemptions(), frozen_py()
    if exp == fro:
        return 0
    print(
        "hygiene: exemptions != frozen set\n  not frozen but exempt: %s\n  frozen but not exempt: %s"
        % (sorted(exp - fro), sorted(fro - exp)),
        file=sys.stderr,
    )
    return 1


def _black(write: bool) -> int:
    files = coverage()
    if not files:
        print("hygiene: no files to check", file=sys.stderr)
        return 2
    cmd = [sys.executable, "-m", "black"] + ([] if write else ["--check"]) + files
    return subprocess.run(cmd).returncode


def main(argv: list) -> int:
    mode = argv[1] if len(argv) > 1 else "fmt-check"
    if mode == "frozen":
        print("\n".join(sorted(frozen_py())))
        return 0
    if mode == "exemptions":
        print("\n".join(sorted(exemptions())))
        return 0
    if mode == "validate":
        return validate()
    if mode in ("fmt-check", "fmt-fix"):
        rc = validate()
        return rc if rc else _black(write=(mode == "fmt-fix"))
    print(
        "usage: hygiene.py frozen|exemptions|validate|fmt-check|fmt-fix",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
