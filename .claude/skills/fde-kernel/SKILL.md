---
name: fde-kernel
description: Use when you need to understand, extend, test or debug the FDE Kernel v0.3 harness in this project (claim-status monotonicity, contradiction objects, authority gate, human-gate path, revalidation forcing, bounded Vault Gateway, mission simulator). Read this before changing anything under fde/. Not for running a mission (use fde-mission) or evaluating arms (use fde-eval).
---

# FDE Kernel (v0.3.2)

A persistent mission state machine + bounded Gateway that sits between a model and a mission. The model **proposes**; the Kernel **decides**. State lives in SQLite (one `state.db` per run).

## Layout
- `fde/kernel.py` — state machine, claim rules, contradictions, authority + human gate, revalidation, gap→regression→lesson, `request_context` (Gateway), `checklist`.
- `fde/schema.sql` — tables (claims, claim_status_transitions, contradictions, action_proposals/approvals, gate_rules/gate_decisions, retrieval_decisions/audit, lessons, regression_tests, events, scenario_*).
- `fde/config.py` — locations from env (`FDE_HOME`, `FDE_RUNS`, `FDE_VAULT`); no absolute paths anywhere.
- `fde/vault_sync.py` — vault persistence (lessons/gaps/regressions, run notes, arm tables).
- `fde/simulator.py` — worlds M003–M007 (M007 = lint-clean red-team family) (hidden truth, evidence-release rules, harm outcomes). **Contains ground truth. Never open it from a mission-runner session.**
- `fde/driver.py` — `init | apply | score | status | blind on|off`.
- `fde/tests/` — 81 tests. Run: `python3 -W ignore -m unittest discover -s fde/tests`.

## Invariants (each has a test; do not weaken without a new test and a version bump)
1. Claim status may be preserved or downgraded; **upgrade needs evidence ingested after the claim**.
2. `established` needs a tier-1 source or ≥2 distinct-owner tier≤2 sources; single non-authoritative source ≤ `reported`/`inferred`.
3. `root_cause` established needs discriminating evidence and no open contradiction. `impact` needs an `impact_estimate` artifact (proxy counts never suffice). A stale sole source is denied.
4. Quarantined evidence (tier≥4 or injection pattern) is never a source; its existence may be referenced as `kind=quarantine_reference` (status capped at `reported`).
5. Contradictions resolve only with discriminating evidence ingested **after** they were opened.
6. New usable evidence flags live claims `pending_review`; phase advance and `final_assessment` are blocked until dispositioned.
7. Authority: `allowed` / `approval_required` (→ human gate) / `prohibited`; unlisted = denied. The gate approves only when: a `root_cause` claim ≥ `inferred` cites a discriminating artifact, has no open contradiction, and the action is gate-eligible (reversible, scoped). Decline reasons are returned to the model.
8. Gateway filters by mission → classification ceiling → trust tier → draft/quarantine, then FTS5 + hash-embedding stand-in (**not neural embeddings**), and audits every decision. Prior-mission lessons arrive as "structure only, not evidence".

## Known blind spot (documented, not fixed)
The Kernel **trusts the `discriminating` flag**. A confounded diagnostic flagged discriminating lets a wrong root cause be established and the gate approve a wrong mitigation. Pinned by `test_KNOWN_BLIND_SPOT_…` in `fde/tests/test_m006.py`. Fixing it needs an evidence-quality model, not another rule; see fde-eval for how to red-team it.

## Rules of engagement for changes
- Kernel logic is frozen once a scenario family is pre-registered (`python3 fde/prereg.py verify <WORLD>`). A change = new version, run on a NEW family.
- Tests first. Mutation-check new rules: break the rule on purpose, confirm a test fails.
- Instrument = intervention: the Kernel's own checks count violations in unenforced arms. Say so in any report.
