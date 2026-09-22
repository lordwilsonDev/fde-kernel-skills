"""Deterministic artifact manifest: sorted relative paths + sha256, and one tree hash over them.
The repository may not be a git repository, so this is the provenance record.
  python3 fde/manifest.py tree [--json]     manifest of the harness (fde/*.py, schema, skills, hook config, docs); excludes runs/, caches, marker files
  python3 fde/manifest.py m007              hashes of everything M007 owns (frozen code, prereg, predictions, run dirs)
  python3 fde/manifest.py files a b ...     manifest of the named files"""
import os, sys, json, hashlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"__pycache__", ".git", "runs"}
SKIP_FILES = {".fde_blind", ".DS_Store"}
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

def walk(rel_dirs, root=ROOT):
    out = {}
    for rd in rel_dirs:
        base = os.path.join(root, rd)
        if os.path.isfile(base): out[rd] = sha(base); continue
        for dp, dn, fn in os.walk(base):
            dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
            for f in sorted(fn):
                if f in SKIP_FILES or f.endswith(".pyc"): continue
                p = os.path.join(dp, f); out[os.path.relpath(p, root)] = sha(p)
    return dict(sorted(out.items()))

def tree_hash(m): return hashlib.sha256("\n".join(f"{k}  {v}" for k, v in sorted(m.items())).encode()).hexdigest()

def harness(root=ROOT): return walk(["fde", ".claude", "docs", "README.md", "install.sh"], root)

def m007(root=ROOT):
    m = walk(["fde/kernel.py", "fde/driver.py", "fde/simulator.py", "fde/schema.sql", "runs/PREREG_M007.md", "runs/PREDICTIONS_M007.md"], root)
    rd = os.path.join(root, "runs")
    for d in sorted(os.listdir(rd)):
        if d.startswith("M007_") and os.path.isdir(os.path.join(rd, d)): m.update(walk([os.path.join("runs", d)], root))
    return dict(sorted(m.items()))

if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "tree"
    m = harness() if c == "tree" else m007() if c == "m007" else walk(sys.argv[2:])
    if "--json" in sys.argv or c == "m007": print(json.dumps({"tree_sha256": tree_hash(m), "files": m}, indent=1))
    else:
        for k, v in m.items(): print(f"{v}  {k}")
        print(f"TREE {tree_hash(m)}  ({len(m)} files)")
