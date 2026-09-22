"""Aggregate scored runs into an arm table. Usage: python3 fde/report.py <world> [--runs runs] [--json]
Arms are parsed from run directory names:  <world>_<model>_<arm>[_<lessons>]_<replicate>   e.g. M005_haiku_kernel_lessons_a
Runs that never finished (run.json done=false) are reported separately and excluded from every metric."""
import sys, os, re, json, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import driver, config, registry
try: import driver_m008   # registers WORLDS['M008'] and provides the M008 score (decoy-exposure fields)
except ImportError: driver_m008 = None

NAME = re.compile(r"^(M\d+)_(haiku|sonnet|opus|qwen38b)_(kernel_lessons|kernel|rules|raw)_([a-z0-9]+)$")


def collect(world, runs=None, ledger=None):
    """Aggregate finished runs. Nothing is silently dropped: every matching-or-not directory that is left out is appended to `ledger` as (name, reason).
    A registry-governed world (M008, or any world with a registration under runs/registrations) counts only SCORED runs of the ACTIVE registration with untouched code."""
    runs = runs or config.RUNS; ledger = ledger if ledger is not None else []
    governed = world == "M008" or bool(registry._versions(world, runs))
    arms = collections.defaultdict(list); unfinished = []
    for d in sorted(glob.glob(f"{runs}/{world}_*/")):
        name = os.path.basename(d.rstrip("/")); m = NAME.match(name)
        if not m: ledger.append((name, "name does not match <WORLD>_<model>_<arm>_<letter>")); continue
        if not os.path.exists(f"{d}run.json"): ledger.append((name, "no run.json")); continue
        try: done = json.load(open(f"{d}run.json"))["done"]
        except Exception as e: ledger.append((name, f"invalid run.json ({type(e).__name__})")); continue
        if governed:
            ok, why = registry.run_eligibility(d.rstrip("/"), world, runs)
            if not ok: ledger.append((name, "ineligible: " + "; ".join(why))); continue
        if not done: unfinished.append(name); continue
        try: s = (driver_m008 if driver_m008 and world == "M008" else driver).score(d.rstrip("/"))
        except Exception as e: ledger.append((name, f"invalid run: score failed ({type(e).__name__})")); continue
        s["_run"] = name; arms[f"{m.group(2)}_{m.group(3)}"].append(s)
    return arms, unfinished


def row(xs):
    n = len(xs); f = lambda k: [x.get(k) for x in xs]
    ok = sum(bool(x["root_cause_correct_and_supported"]) for x in xs); eff = sum(bool(x.get("mitigation_effective")) for x in xs)
    decoy = sum(bool(x.get("false_root_cause_at_least_inferred")) for x in xs); dm = sum(bool(x.get("decoy_mitigation_applied")) for x in xs)
    m8 = {"decoy_exposed": f"{sum(bool(x['decoy_diagnostic_executed']) for x in xs)}/{n}", "decoy_only_root_cause": f"{sum(bool(x['root_cause_cites_decoy_only_at_least_inferred']) for x in xs)}/{n}",
          "followup_effective": f"{sum(bool(x['followup_mitigation_effective']) for x in xs)}/{n}"} if xs and "decoy_diagnostic_executed" in xs[0] else {}
    return {**m8, "n": n, "root_cause_ok": f"{ok}/{n}", "decoy>=inferred": f"{decoy}/{n}", "decoy_mitigation": f"{dm}/{n}", "mitigation_effective": f"{eff}/{n}",
            "violations_per_run": f("claim_violations_or_denials"), "impact_inflated": f"{sum(bool(x['impact_inflated']) for x in xs)}/{n}",
            "unauthorized_proposals": [len(x["unauthorized_action_proposals"]) for x in xs], "contradictions_opened/resolved": [f"{x['contradictions_opened']}/{x['contradictions_resolved']}" for x in xs],
            "unrevalidated_at_close": f("pending_review_left"), "rounds": f("rounds"), "audit_retrieval_rows": [x["audit_rows"]["retrieval_decisions"] for x in xs]}


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit("usage: report.py <world> [--runs runs] [--json]")
    world = sys.argv[1]; runs = sys.argv[sys.argv.index("--runs") + 1] if "--runs" in sys.argv else config.RUNS
    ledger = []; arms, unfinished = collect(world, runs, ledger); table = {a: row(xs) for a, xs in sorted(arms.items())}
    if "--json" in sys.argv: print(json.dumps({"arms": table, "unfinished": unfinished, "not_counted": ledger}, indent=1)); sys.exit(1 if ("--strict" in sys.argv and ledger) else 0)
    cols = list(next(iter(table.values())).keys()) if table else []
    print("| arm | " + " | ".join(cols) + " |"); print("|" + "---|" * (len(cols) + 1))
    for a, r in table.items(): print(f"| {a} | " + " | ".join(str(r[c]) for c in cols) + " |")
    if unfinished: print(f"\nUNFINISHED (excluded): {unfinished}")
    for n, why in ledger: print(f"NOT COUNTED: {n}: {why}")
    if "--strict" in sys.argv and ledger: sys.exit(1)
    print("\nn is small; descriptive only. Violations are counted by the Kernel's own checks (instrument = intervention for the Kernel arm).")
