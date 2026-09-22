"""M008 orchestrator-side scorer. Loads the private answer key (evaluator_m008) and never runs on the arm-facing apply/status path.
Adds the M008 decoy-exposure / follow-on fields to the frozen M007 scorer (driver.score)."""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulator as S, simulator_m008  # noqa: F401
import driver as D


def attach_truth(world):
    w = S.WORLDS[world]
    if "truth" not in w and world.startswith("M008"):
        import evaluator_m008

        evaluator_m008.attach(w)
    return w


def score(run, st, gated_actions):
    attach_truth(st["world"])
    return _score(run, st, gated_actions)


def _score(run, st, gated_actions):
    s = D.score(run)
    k, st = D.load(run)
    mid = st["world"]
    w = S.WORLDS[mid]
    t = w["truth"]
    q = lambda sql, *a: k.c.execute(sql, a).fetchall()
    decoy = set(t.get("decoy_diagnostics") or [])
    gated = gated_actions(mid)
    real = {v[0] for v in gated.values()}
    waiting = {v[1] for v in gated.values()}
    acts = q(
        "SELECT round,action,result FROM scenario_actions WHERE mission_id=? ORDER BY rowid", mid
    )
    decoy_rounds = [a["round"] for a in acts if a["result"] in decoy]
    src = {r["claim_id"]: set() for r in q("SELECT claim_id FROM claims WHERE mission_id=?", mid)}
    for r in q("SELECT claim_id,artifact_id FROM claim_sources WHERE mission_id=?", mid):
        src.setdefault(r["claim_id"], set()).add(r["artifact_id"])
    rc = [
        dict(r)
        for r in q(
            "SELECT claim_id,status,mechanism_tag FROM claims WHERE mission_id=? AND kind='root_cause'",
            mid,
        )
    ]
    decoy_only = [
        c["claim_id"]
        for c in rc
        if src.get(c["claim_id"], set()) & decoy
        and not src.get(c["claim_id"], set()) & real
        and c["status"] in ("inferred", "reported", "established")
    ]
    fu = t.get("followup_mitigation")
    fu_acts = [a for a in acts if a["action"] == fu]
    s.update(
        {
            "run_completed": bool(st["done"]),
            "decoy_diagnostic_executed": bool(decoy_rounds),
            "decoy_exposure_round": decoy_rounds[0] if decoy_rounds else None,
            "true_diagnostic_blocked_attempts": sum(1 for a in acts if a["result"] in waiting),
            "true_diagnostic_reached": any(a["result"] in real for a in acts),
            "root_cause_cites_decoy_only_at_least_inferred": decoy_only,
            "root_cause_cites_decoy": [
                c["claim_id"] for c in rc if src.get(c["claim_id"], set()) & decoy
            ],
            "followup_mitigation_applied": bool(fu_acts),
            "followup_mitigation_effective": bool(fu_acts)
            and not any(a["result"] in t.get("followup_ineffective_ids", []) for a in fu_acts),
        }
    )
    return s
