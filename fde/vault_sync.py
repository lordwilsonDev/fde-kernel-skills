"""Persistence with the Obsidian vault. The vault holds the human-readable memory (lessons, gap records, regression tests, run notes);
SQLite stays the live projection. Nothing is ever deleted, and no note is overwritten unless it carries `fde_generated: true`.

  python3 fde/vault_sync.py status
  python3 fde/vault_sync.py lessons build <out.db>          # vault lessons -> seed DB usable as `driver.py init ... <out.db>`
  python3 fde/vault_sync.py lessons push <run_dir>          # lessons/gaps/regressions promoted in a run -> vault notes (create-only)
  python3 fde/vault_sync.py export run <run_dir>            # one run -> 50_Experiments/FDE-Kernel/<world>/runs/<run>.md
  python3 fde/vault_sync.py export world <WORLD>            # arm table for every finished run -> .../<WORLD>/README.md
Vault location: FDE_VAULT (default ~/Documents/Vault)."""
import sys, os, re, json, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, kernel as K, driver, report
try: import driver_m008   # M008 scoring needs the orchestrator-side private evaluator
except ImportError: driver_m008 = None  # type: ignore[assignment]  # optional M008 module

today = lambda: datetime.date.today().isoformat()


def parse(text):
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m: return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ": " in line: k, v = line.split(": ", 1); fm[k.strip()] = v.strip().strip('"')
    return fm, m.group(2).strip()


def write_note(path, fm, body, allow_update_generated=True):
    """Create-only for human notes; overwrite only notes this tool generated (fde_generated: true)."""
    if os.path.exists(path):
        old, _ = parse(open(path).read())
        if old.get("fde_generated") != "true": return "skipped (human note exists)"
        if not allow_update_generated: return "skipped (exists)"
        fm["created"] = old.get("created", fm.get("created"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fm = dict(fm, fde_generated="true", updated=today())
    fm.setdefault("created", today())
    text = "---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n" + body.rstrip() + "\n"
    existed = os.path.exists(path); open(path, "w").write(text); return "updated" if existed else "created"


# ---------------- lessons / gaps / regressions
def lessons_push(run_dir):
    k, st = driver.load(run_dir); out = []
    for r in k.c.execute("SELECT * FROM lessons"):
        fm = {"id": r["lesson_id"], "area": "memory", "area_code": 40, "type": "fde-lesson", "status": "active", "tags": f"[fde, lesson, {r['domain']}]", "source_mission": r["source_mission"], "domain": r["domain"], "transferable": r["transferable"], "regression_test": r["regression_test"] or "none"}
        body = f"# {r['lesson_id']}\n\n{r['lesson']}\n\n**Transferable:** `{r['transferable']}` (`structure` = procedure only, never evidence; `none` = domain fact, must not leave its mission).\n"
        out.append((r["lesson_id"], write_note(os.path.join(config.LESSONS_DIR, f"{r['lesson_id']}.md"), fm, body, allow_update_generated=False)))
    for r in k.c.execute("SELECT * FROM gaps"):
        gid = f"GAP_{r['mission_id']}_{r['gap_id']}_{re.sub(r'[^a-z0-9]+', '-', r['capability'].lower())[:40]}"
        fm = {"id": gid, "area": "memory", "area_code": 40, "type": "fde-gap", "status": r["status"], "tags": "[fde, gap]", "mission": r["mission_id"], "layer": r["layer"], "regression_test": r["regression_test"] or "none"}
        out.append((gid, write_note(os.path.join(config.LESSONS_DIR, "gaps", f"{gid}.md"), fm, f"# {gid}\n\n**Capability:** {r['capability']}\n\n**Reason:** {r['reason']}\n\n**Closed by regression test:** `{r['regression_test'] or 'none'}`\n", allow_update_generated=False)))
    for r in k.c.execute("SELECT * FROM regression_tests"):
        fm = {"id": r["name"], "area": "memory", "area_code": 40, "type": "fde-regression", "status": "active", "tags": "[fde, regression]", "gap_ref": r["gap_ref"] or "none"}
        out.append((r["name"], write_note(os.path.join(config.LESSONS_DIR, "regressions", f"{r['name']}.md"), fm, f"# {r['name']}\n\n{r['description']}\n", allow_update_generated=False)))
    return out


def lessons_build(out_db):
    if os.path.exists(out_db): os.remove(out_db)
    k = K.Kernel(out_db); n = {"lessons": 0, "regressions": 0}
    for p in sorted(glob.glob(os.path.join(config.LESSONS_DIR, "*.md"))):
        fm, body = parse(open(p).read())
        if fm.get("type") != "fde-lesson" or fm.get("status") != "active": continue
        text = re.sub(r"^# .*?\n+", "", body, count=1).split("\n\n**Transferable")[0].strip()
        k.promote_lesson(fm["id"], fm.get("source_mission", "?"), fm.get("domain", "?"), text, fm.get("transferable", "none"), None if fm.get("regression_test") in (None, "none") else fm["regression_test"]); n["lessons"] += 1
    for p in sorted(glob.glob(os.path.join(config.LESSONS_DIR, "regressions", "*.md"))):
        fm, body = parse(open(p).read())
        if fm.get("type") == "fde-regression": k.c.execute("INSERT OR REPLACE INTO regression_tests VALUES(?,?,?)", (fm["id"], re.sub(r"^# .*?\n+", "", body, count=1).strip(), fm.get("gap_ref"))); n["regressions"] += 1
    k.c.commit(); return n


# ---------------- run / world export
class RunNotFinished(Exception):
    pass


def export_run(run_dir):
    st = json.load(open(os.path.join(run_dir, "run.json")))
    if not st.get("done"): raise RunNotFinished(f"run {os.path.basename(run_dir.rstrip('/'))} is not finished (run.json done=false); nothing exported")
    s = (driver_m008 if driver_m008 and str(st["world"]).startswith("M008") else driver).score(run_dir); k, _ = driver.load(run_dir); name = os.path.basename(run_dir.rstrip("/")); world = st["world"]
    m = report.NAME.match(name); model, arm = (m.group(2), m.group(3)) if m else ("?", st["mode"])
    fm = {"id": f"fde-run-{name}", "area": "experiments", "area_code": 50, "type": "fde-run", "status": "complete", "tags": f"[fde, {world}, {arm}]", "world": world, "run": name, "mode": st["mode"], "model": model, "arm": arm}
    denials = [dict(r) for r in k.c.execute("SELECT claim_id,from_status,to_status,result,reason FROM claim_status_transitions WHERE result!='accepted'")]
    gates = [dict(r) for r in k.c.execute("SELECT action,decision,reason FROM gate_decisions")]
    actions = [f"{x['round']}. `{x['next_action'].get('action')}` ({x['next_action'].get('kind')}) -> {x.get('authority') or ''} {x.get('gate') or ''}" for x in st["log"]]
    body = f"# {name}\n\nWorld `{world}`, mode `{st['mode']}`, model `{model}`. Finished.\n\n## Score (deterministic, vs ground truth)\n```json\n{json.dumps(s, indent=1, default=str)}\n```\n\n## Actions\n" + "\n".join(actions) + "\n\n## Gate decisions\n" + ("\n".join(f"- {g['action']}: {g['decision']} - {g['reason']}" for g in gates) or "none") + "\n\n## Kernel denials / logged violations\n" + ("\n".join(f"- {d['claim_id']}: {d['from_status']}->{d['to_status']} {d['result']}: {d['reason']}" for d in denials) or "none") + "\n\n_Generated by fde/vault_sync.py. Scores are computed with the Kernel's own checks (instrument = intervention for the Kernel arm)._\n"
    return write_note(os.path.join(config.EXP_DIR, world, "runs", f"{name}.md"), fm, body)


def export_world(world, runs=None):
    arms, unfinished = report.collect(world, runs or config.RUNS); table = {a: report.row(xs) for a, xs in sorted(arms.items())}
    cols = list(next(iter(table.values())).keys()) if table else []
    md = "| arm | " + " | ".join(cols) + " |\n|" + "---|" * (len(cols) + 1) + "\n" + "\n".join(f"| {a} | " + " | ".join(str(r[c]) for c in cols) + " |" for a, r in table.items())
    if unfinished: md += f"\n\nUNFINISHED (excluded): {unfinished}"
    fm = {"id": f"fde-world-{world}", "area": "experiments", "area_code": 50, "type": "fde-world-report", "status": "generated", "tags": f"[fde, {world}]", "world": world}
    return write_note(os.path.join(config.EXP_DIR, world, "README.md"), fm, f"# {world} arm table (generated)\n\n{md}\n\nn is small; descriptive only. Interpretation and caveats live in the hand-written experiment notes, not here.\n")


def status():
    c = lambda pat: len(glob.glob(os.path.join(config.LESSONS_DIR, pat)))
    return {"vault": config.VAULT, "vault_exists": os.path.isdir(config.VAULT), "lessons": c("*.md"), "gaps": c("gaps/*.md"), "regressions": c("regressions/*.md"),
            "run_notes": len(glob.glob(os.path.join(config.EXP_DIR, "*", "runs", "*.md"))), "runs_dir": config.RUNS}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["status"]: print(json.dumps(status(), indent=1))
    elif a[:2] == ["lessons", "build"]: print(lessons_build(a[2]))
    elif a[:2] == ["lessons", "push"]: [print(f"{n}: {r}") for n, r in lessons_push(a[2])]
    elif a[:2] == ["export", "run"]:
        try: print(export_run(a[2].rstrip("/")))
        except RunNotFinished as e: print(json.dumps({"ok": False, "error_code": "RUN_NOT_FINISHED", "message": str(e)})); sys.exit(3)
    elif a[:2] == ["export", "world"]: print(export_world(a[2]))
    else: print(__doc__)
