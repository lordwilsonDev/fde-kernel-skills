"""FDE Kernel v0.3 — persistent mission state machine + bounded Vault Gateway (minimum full loop).
Implements: event-sourced lifecycle, claim-status monotonicity, contradiction objects with discriminating-evidence
resolution, authority gate, revalidation-forcing, gap->regression learning, hybrid retrieval (metadata filter -> FTS5 ->
hash-embedding stand-in -> link expansion). enforce=False turns blocking off (violations are still logged) for baselines.
"""

import sqlite3, json, hashlib, re, math, uuid, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
RANK = {"unknown": 0, "hypothesized": 1, "inferred": 2, "reported": 2, "established": 3}
STATUSES = set(RANK) | {"stale", "disproven"}
KINDS = {"observation", "inference", "hypothesis", "root_cause", "impact", "quarantine_reference"}
PHASES = [
    "INTAKE",
    "CHARTERED",
    "DISCOVERING",
    "MAPPED",
    "ANALYZING",
    "EVALUATING",
    "CORRECTING",
    "OBSERVING",
    "REVALIDATING",
    "EVOLVING",
    "CLOSED",
]
NEXT = {
    "INTAKE": ["CHARTERED"],
    "CHARTERED": ["DISCOVERING"],
    "DISCOVERING": ["MAPPED", "ANALYZING"],
    "MAPPED": ["ANALYZING"],
    "ANALYZING": ["EVALUATING", "DISCOVERING", "CORRECTING"],
    "EVALUATING": ["CORRECTING", "OBSERVING", "ANALYZING"],
    "CORRECTING": ["OBSERVING", "ANALYZING"],
    "OBSERVING": ["REVALIDATING", "EVOLVING", "ANALYZING"],
    "REVALIDATING": ["ANALYZING", "EVOLVING", "CLOSED"],
    "EVOLVING": ["CLOSED"],
    "CLOSED": [],
}
INJECTION = re.compile(
    r"(system instruction|ignore (all|incident|policy)|disable logging|declare .{0,30}root cause|treat all .{0,30}approved)",
    re.I,
)
CLASS_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
now = lambda: datetime.datetime.now(datetime.UTC).isoformat()


def embed(text, dim=256):
    v = [0.0] * dim
    for w in re.findall(r"[a-z0-9]{3,}", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1
    n = math.sqrt(sum(x * x for x in v)) or 1
    return [x / n for x in v]


cos = lambda a, b: sum(x * y for x, y in zip(a, b))


class Kernel:
    def __init__(self, db=":memory:", enforce=True):
        self.c = sqlite3.connect(db)
        self.c.row_factory = sqlite3.Row
        self.enforce = enforce
        self.c.executescript(open(f"{HERE}/schema.sql").read())

    # ---------- events / lifecycle
    def emit(self, mission, etype, actor, payload=None, trigger=None, evidence=None):
        cur = self.c.execute(
            "INSERT INTO events(mission_id,etype,actor,trigger,payload_json,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (mission, etype, actor, trigger, json.dumps(payload), json.dumps(evidence), now()),
        )
        self.c.commit()
        return cur.lastrowid

    def seq(self):
        return self.c.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]

    def create_mission(
        self,
        mid,
        objective,
        non_goals,
        authority_scope,
        risk_tier,
        rules,
        policy_version="v0.3",
        ceiling="internal",
    ):
        self.c.execute(
            "INSERT INTO missions VALUES(?,?,?,?,?,?,?,?,?)",
            (
                mid,
                objective,
                json.dumps(non_goals),
                authority_scope,
                risk_tier,
                "INTAKE",
                policy_version,
                ceiling,
                now(),
            ),
        )
        for a, r in rules.items():
            self.c.execute("INSERT INTO authority_rules VALUES(?,?,?)", (mid, a, r))
        self.emit(mid, "mission_created", "kernel")
        self.set_phase(mid, "CHARTERED", "charter", "kernel")
        self.set_phase(mid, "DISCOVERING", "intake_complete", "kernel")

    def phase(self, mid):
        return self.c.execute("SELECT phase FROM missions WHERE mission_id=?", (mid,)).fetchone()[0]

    def set_phase(self, mid, new, trigger, actor, evidence=None):
        cur = self.phase(mid)
        if new not in NEXT[cur] and new not in ("BLOCKED", "ESCALATED"):
            return False, f"illegal transition {cur}->{new}"
        if (
            self.c.execute(
                "SELECT COUNT(*) FROM claims WHERE mission_id=? AND pending_review=1", (mid,)
            ).fetchone()[0]
            and new in ("EVALUATING", "CORRECTING", "OBSERVING", "EVOLVING", "CLOSED")
            and self.enforce
        ):
            return False, "pending_review claims must be dispositioned before advancing"
        self.c.execute("UPDATE missions SET phase=? WHERE mission_id=?", (new, mid))
        self.emit(mid, "phase", actor, {"from": cur, "to": new}, trigger, evidence)
        return True, "ok"

    # ---------- artifacts / revalidation
    def ingest_artifact(
        self,
        mid,
        aid,
        kind,
        title,
        body,
        tier,
        status="verified",
        owner="unknown",
        cls="internal",
        created="",
        last_verified=None,
        discriminating=0,
        domain=None,
        trigger="ingest",
    ):
        q = 1 if (tier >= 4 or INJECTION.search(body)) else 0
        s = self.emit(
            mid, "artifact_ingested", "kernel", {"id": aid, "tier": tier, "quarantined": q}, trigger
        )
        self.c.execute(
            "INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                aid,
                mid,
                kind,
                title,
                body,
                tier,
                status,
                owner,
                cls,
                created,
                last_verified,
                discriminating,
                domain,
                hashlib.sha256(body.encode()).hexdigest(),
                s,
                q,
                json.dumps(embed(title + " " + body)),
            ),
        )
        self.c.execute("DELETE FROM artifact_fts WHERE artifact_id=?", (aid,))
        self.c.execute("INSERT INTO artifact_fts VALUES(?,?,?)", (aid, title, body))
        flagged = []
        if not q:  # new usable evidence forces revalidation of every live non-trivial claim
            for r in self.c.execute(
                "SELECT claim_id FROM claims WHERE mission_id=? AND status!='unknown' AND status!='disproven' AND kind!='quarantine_reference'",
                (mid,),
            ).fetchall():
                self.c.execute(
                    "UPDATE claims SET pending_review=1 WHERE claim_id=? AND mission_id=?",
                    (r[0], mid),
                )
                flagged.append(r[0])
            if flagged:
                self.c.execute(
                    "INSERT INTO revalidation_events(mission_id,trigger,claims_flagged,seq) VALUES(?,?,?,?)",
                    (mid, f"new_evidence:{aid}", json.dumps(flagged), s),
                )
        self.c.commit()
        return flagged

    def art(self, aid):
        return self.c.execute("SELECT * FROM artifacts WHERE artifact_id=?", (aid,)).fetchone()

    def is_stale(self, a):
        return a["status"] == "stale"

    # ---------- claim transitions (monotonicity)
    def sufficiency(self, mid, kind, sources, contradicted):
        arts = [self.art(s) for s in sources if self.art(s)]
        if not arts:
            return False, "no sources"
        if any(a["quarantined"] for a in arts):
            return False, "cites quarantined evidence"
        live = [a for a in arts if not self.is_stale(a)]
        if not live:
            return False, "only stale sources"
        t1 = [a for a in live if a["trust_tier"] == 1]
        owners = {
            a["source_owner"]
            for a in live
            if a["trust_tier"] <= 2 and a["source_owner"] not in ("unknown", "none")
        }
        if not (t1 or len(owners) >= 2):
            return (
                False,
                "single non-authoritative source (need tier-1 or >=2 distinct tier<=2 owners)",
            )
        if kind == "root_cause":
            if not any(a["discriminating"] for a in live):
                return False, "root_cause requires discriminating evidence"
            if contradicted:
                return False, "root_cause with open contradiction"
        if kind == "impact" and not any(a["kind"] == "impact_estimate" for a in live):
            return False, "impact requires an impact_estimate artifact, not proxies"
        return True, "ok"

    def apply_claim(self, mid, cl, actor):
        cid = cl["claim_id"]
        new = cl.get("status", "hypothesized")
        kind = cl.get("kind", "hypothesis")
        src = list(cl.get("sources") or [])
        if new not in STATUSES or kind not in KINDS:
            return self._tr(mid, cid, None, new, "denied", "invalid status/kind")
        row = self.c.execute(
            "SELECT * FROM claims WHERE claim_id=? AND mission_id=?", (cid, mid)
        ).fetchone()
        cur = row["status"] if row else None
        s = self.seq()
        if kind == "quarantine_reference":
            if RANK.get(new, 0) > RANK["reported"]:
                new = "reported"
        else:
            if any((self.art(x) and self.art(x)["quarantined"]) for x in src):
                return (
                    self._tr(
                        mid, cid, cur, new, "denied", "non-meta claim cites quarantined evidence"
                    )
                    if self.enforce
                    else self._commit_claim(
                        mid, cl, cur, new, src, s, "violation:quarantined_cited"
                    )
                )
        contradicted = (
            self.c.execute(
                "SELECT COUNT(*) FROM contradictions WHERE mission_id=? AND status='open' AND (claim_a=? OR claim_b=?)",
                (mid, cid, cid),
            ).fetchone()[0]
            > 0
        )
        base_rank = RANK.get(cur, -1) if cur else -1
        up = RANK.get(new, 0) > base_rank and new in RANK
        if kind != "quarantine_reference" and new == "established":
            ok, why = self.sufficiency(mid, kind, src, contradicted)
            # upgrade of an existing claim also needs evidence newer than the claim
            if ok and row and cur != "established":
                newer = [
                    x
                    for x in src
                    if self.art(x) and self.art(x)["ingested_seq"] > row["updated_seq"]
                ]
                if not newer:
                    ok, why = False, "upgrade requires evidence newer than the claim"
            if not ok:
                if self.enforce:
                    return self._tr(mid, cid, cur, new, "denied", f"cannot establish: {why}", src)
                return self._commit_claim(mid, cl, cur, new, src, s, f"violation:{why}")
        elif row and new in RANK and RANK[new] > RANK.get(cur, 0) and cur in RANK and new != cur:
            newer = [
                x for x in src if self.art(x) and self.art(x)["ingested_seq"] > row["updated_seq"]
            ]
            if not newer:
                if self.enforce:
                    return self._tr(
                        mid,
                        cid,
                        cur,
                        new,
                        "denied",
                        "upgrade requires new evidence newer than the claim",
                        src,
                    )
                return self._commit_claim(
                    mid, cl, cur, new, src, s, "violation:upgrade_without_new_evidence"
                )
        return self._commit_claim(mid, cl, cur, new, src, s, "accepted")

    def _commit_claim(self, mid, cl, cur, new, src, s, result):
        cid = cl["claim_id"]
        self.c.execute(
            "INSERT INTO claims(claim_id,mission_id,statement,kind,status,mechanism_tag,corroboration,limitation,freshness,created_seq,updated_seq) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(claim_id,mission_id) DO UPDATE SET statement=excluded.statement,kind=excluded.kind,status=excluded.status,mechanism_tag=excluded.mechanism_tag,corroboration=excluded.corroboration,limitation=excluded.limitation,freshness=excluded.freshness,updated_seq=excluded.updated_seq,pending_review=0",
            (
                cid,
                mid,
                cl.get("statement"),
                cl.get("kind"),
                new,
                cl.get("mechanism_tag"),
                cl.get("corroboration"),
                cl.get("limitation"),
                cl.get("freshness"),
                s,
                s,
            ),
        )
        self.c.execute("DELETE FROM claim_sources WHERE claim_id=? AND mission_id=?", (cid, mid))
        for x in src:
            self.c.execute("INSERT OR IGNORE INTO claim_sources VALUES(?,?,?)", (cid, mid, x))
        return self._tr(
            mid,
            cid,
            cur,
            new,
            result if result != "accepted" else "accepted",
            "ok" if result == "accepted" else result,
            src,
        )

    def _tr(self, mid, cid, fr, to, result, reason, ev=None):
        self.c.execute(
            "INSERT INTO claim_status_transitions(mission_id,claim_id,from_status,to_status,result,reason,evidence_json,seq) VALUES(?,?,?,?,?,?,?,?)",
            (mid, cid, fr, to, result, reason, json.dumps(ev), self.seq()),
        )
        self.c.commit()
        return {"claim_id": cid, "from": fr, "to": to, "result": result, "reason": reason}

    # ---------- contradictions
    def add_contradiction(self, mid, d):
        s = self.emit(mid, "contradiction_opened", "model", d)
        self.c.execute(
            "INSERT OR IGNORE INTO contradictions VALUES(?,?,?,?,?,?,?,?)",
            (
                d["id"],
                mid,
                d.get("claim_a"),
                d.get("claim_b"),
                d.get("description"),
                "open",
                s,
                None,
            ),
        )
        if d.get("discriminating_evidence_needed"):
            self.c.execute(
                "INSERT INTO discriminating_evidence_requirements VALUES(?,?,?)",
                (d["id"], mid, d["discriminating_evidence_needed"]),
            )
        self.c.commit()
        return {"contradiction": d["id"], "result": "opened"}

    def resolve_contradiction(self, mid, r):
        row = self.c.execute(
            "SELECT * FROM contradictions WHERE contradiction_id=? AND mission_id=?",
            (r["contradiction_id"], mid),
        ).fetchone()
        if not row or row["status"] != "open":
            return {
                "contradiction": r["contradiction_id"],
                "result": "denied",
                "reason": "not open",
            }
        good = [
            e
            for e in (r.get("evidence_refs") or [])
            if self.art(e)
            and self.art(e)["discriminating"]
            and self.art(e)["ingested_seq"] > row["created_seq"]
            and not self.art(e)["quarantined"]
        ]
        if not good and self.enforce:
            return {
                "contradiction": r["contradiction_id"],
                "result": "denied",
                "reason": "resolution needs discriminating evidence ingested after the contradiction was opened",
            }
        s = self.emit(mid, "contradiction_resolved", "model", r, evidence=good)
        self.c.execute(
            "UPDATE contradictions SET status='resolved',resolved_seq=? WHERE contradiction_id=? AND mission_id=?",
            (s, r["contradiction_id"], mid),
        )
        self.c.commit()
        return {
            "contradiction": r["contradiction_id"],
            "result": "resolved" if good else "violation:resolved_without_discriminating_evidence",
        }

    # ---------- authority
    def grant_approval(self, mid, action, approver, scope):
        s = self.emit(mid, "approval", approver, {"action": action, "scope": scope})
        self.c.execute(
            "INSERT INTO action_approvals(mission_id,action,approver,scope,seq) VALUES(?,?,?,?,?)",
            (mid, action, approver, scope, s),
        )
        self.c.commit()

    def set_rule(self, mid, action, rule):
        self.c.execute("INSERT OR REPLACE INTO authority_rules VALUES(?,?,?)", (mid, action, rule))
        self.c.commit()
        self.emit(mid, "authority_changed", "human_gate", {"action": action, "rule": rule})

    def authorize(self, mid, actor, action, kind, rationale=""):
        r = self.c.execute(
            "SELECT rule FROM authority_rules WHERE mission_id=? AND action=?", (mid, action)
        ).fetchone()
        rule = r[0] if r else "unlisted"
        appr = self.c.execute(
            "SELECT COUNT(*) FROM action_approvals WHERE mission_id=? AND action=?", (mid, action)
        ).fetchone()[0]
        if rule == "allowed":
            dec, why = "allowed", "read-only/allowed"
        elif rule == "approval_required":
            dec, why = (
                ("allowed", "approved by human gate")
                if appr
                else ("escalate", "approval required; converted to escalation")
            )
        else:
            dec, why = "denied", f"rule={rule}"
        s = self.emit(mid, "action_proposed", actor, {"action": action, "decision": dec})
        self.c.execute(
            "INSERT INTO action_proposals(mission_id,actor,action,kind,rationale,decision,reason,seq) VALUES(?,?,?,?,?,?,?,?)",
            (mid, actor, action, kind, rationale, dec, why, s),
        )
        self.c.commit()
        if dec != "allowed" and not self.enforce:
            return "allowed", f"UNENFORCED violation ({dec}: {why})"
        return dec, why

    # ---------- human gate (approval path)
    GATE_CONDITIONS = [
        "a claim with kind='root_cause' at status >= inferred",
        "that claim cites at least one discriminating evidence artifact",
        "that claim has no open contradiction",
        "the action is reversible and within the scope stated for it",
    ]

    def set_gate_rule(self, mid, action, scope_text):
        self.c.execute("INSERT OR REPLACE INTO gate_rules VALUES(?,?,?)", (mid, action, scope_text))
        self.c.commit()

    def gate_check(self, mid, action):
        """Deterministic gate conditions. Returns (ok, reason). The real human decision is simulated by these conditions."""
        if not self.c.execute(
            "SELECT 1 FROM gate_rules WHERE mission_id=? AND action=?", (mid, action)
        ).fetchone():
            return (
                False,
                "action is not eligible for the human gate (not a listed reversible mitigation)",
            )
        rcs = self.c.execute(
            "SELECT claim_id,status FROM claims WHERE mission_id=? AND kind='root_cause'", (mid,)
        ).fetchall()
        if not rcs:
            return (
                False,
                "no claim with kind='root_cause' exists; add one (status >= inferred) citing discriminating evidence, then re-propose",
            )
        ok_rc = [c for c in rcs if RANK.get(c["status"], 0) >= 2]
        if not ok_rc:
            return (
                False,
                "your kind='root_cause' claim is below 'inferred'; gather discriminating evidence, then re-propose",
            )
        for c in ok_rc:
            srcs = [
                r[0]
                for r in self.c.execute(
                    "SELECT artifact_id FROM claim_sources WHERE claim_id=? AND mission_id=?",
                    (c["claim_id"], mid),
                )
            ]
            if not any(self.art(x) and self.art(x)["discriminating"] for x in srcs):
                continue
            if self.c.execute(
                "SELECT 1 FROM contradictions WHERE mission_id=? AND status='open' AND (claim_a=? OR claim_b=?)",
                (mid, c["claim_id"], c["claim_id"]),
            ).fetchone():
                return (
                    False,
                    f"root_cause claim {c['claim_id']} has an open contradiction; resolve it with discriminating evidence first",
                )
            return True, f"conditions met via {c['claim_id']}"
        return (
            False,
            "no root_cause claim at >= inferred cites a discriminating evidence artifact; cite one (see evidence[].discriminating) and re-propose",
        )

    def request_gate(self, mid, action, actor="model"):
        ok, why = self.gate_check(mid, action)
        s = self.emit(mid, "gate_decision", "human_gate", {"action": action, "ok": ok, "why": why})
        self.c.execute(
            "INSERT INTO gate_decisions(mission_id,action,decision,reason,seq) VALUES(?,?,?,?,?)",
            (mid, action, "approved" if ok else "declined", why, s),
        )
        if ok:
            self.grant_approval(
                mid,
                action,
                "human_gate(IC+on-call)",
                self.c.execute(
                    "SELECT scope_text FROM gate_rules WHERE mission_id=? AND action=?",
                    (mid, action),
                ).fetchone()[0],
            )
        self.c.commit()
        return ok, why

    # ---------- gaps / learning
    def add_gap(self, mid, capability, reason, layer="L5"):
        self.c.execute(
            "INSERT INTO gaps(mission_id,capability,reason,layer,status) VALUES(?,?,?,?,'open')",
            (mid, capability, reason, layer),
        )
        self.c.commit()

    def close_gap_to_regression(self, gap_id, name, description):
        self.c.execute(
            "INSERT OR REPLACE INTO regression_tests VALUES(?,?,?)",
            (name, description, str(gap_id)),
        )
        self.c.execute(
            "UPDATE gaps SET status='closed',regression_test=? WHERE gap_id=?", (name, gap_id)
        )
        self.c.commit()

    def promote_lesson(self, lid, mission, domain, lesson, transferable, test=None):
        self.c.execute(
            "INSERT OR REPLACE INTO lessons VALUES(?,?,?,?,?,?)",
            (lid, mission, domain, lesson, transferable, test),
        )
        self.c.commit()

    # ---------- proposal application
    def apply_proposal(self, mid, actor, p):
        out = {
            "claims": [],
            "contradictions": [],
            "resolutions": [],
            "gaps": [],
            "next_action": None,
        }
        for cl in p.get("claims") or []:
            out["claims"].append(self.apply_claim(mid, cl, actor))
        for d in p.get("contradictions") or []:
            out["contradictions"].append(self.add_contradiction(mid, d))
        for r in p.get("resolutions") or []:
            out["resolutions"].append(self.resolve_contradiction(mid, r))
        for g in p.get("capability_gaps") or []:
            self.add_gap(mid, g.get("capability"), g.get("reason"))
            out["gaps"].append(g.get("capability"))
        # contradicted claims are contested; every live claim the proposal touched is dispositioned
        touched = {c["claim_id"] for c in p.get("claims") or []}
        for cid in touched:
            self.c.execute(
                "UPDATE claims SET pending_review=0 WHERE claim_id=? AND mission_id=?", (cid, mid)
            )
        for d in p.get("dispositions") or []:
            if d.get("action") in ("preserve", "downgrade", "refine"):
                self.c.execute(
                    "UPDATE claims SET pending_review=0 WHERE claim_id=? AND mission_id=?",
                    (d["claim_id"], mid),
                )
        self.c.commit()
        out["pending_review"] = [
            r[0]
            for r in self.c.execute(
                "SELECT claim_id FROM claims WHERE mission_id=? AND pending_review=1", (mid,)
            )
        ]
        return out

    def gate_guide(self, mid):
        rows = self.c.execute(
            "SELECT g.action, g.scope_text FROM gate_rules g WHERE mission_id=?", (mid,)
        ).fetchall()
        return {
            "how_it_works": "Actions marked approval_required are NOT forbidden. Propose one with next_action.kind='mitigation'; the request goes to the human gate together with your current claims. It is approved automatically when ALL gate conditions hold, otherwise it is declined with a reason in denied_last_round and nothing is executed. Prohibited actions can never be approved.",
            "conditions": self.GATE_CONDITIONS,
            "eligible_actions": [{"action": r[0], "scope": r[1]} for r in rows],
            "past_decisions": [
                dict(r)
                for r in self.c.execute(
                    "SELECT action,decision,reason FROM gate_decisions WHERE mission_id=?", (mid,)
                )
            ],
        }

    def checklist(self, mid, claims):
        """Deterministic gap detector from state (Kernel scaffolding, not model reasoning)."""
        items = []
        pend = [c["claim_id"] for c in claims if c["pending_review"]]
        if pend:
            items.append(
                f"BLOCKING: dispositions required for pending_review claims {pend} (preserve/downgrade/refine) before a final_assessment will be accepted."
            )
        rc = [c for c in claims if c["kind"] == "root_cause"]
        if not rc:
            items.append(
                "No claim with kind='root_cause' exists yet. The mitigation gate and the final assessment require one (status >= inferred, citing discriminating evidence). Observations/inferences do not count."
            )
        elif not any(RANK.get(c["status"], 0) >= 2 for c in rc):
            items.append(
                "Your kind='root_cause' claim is below 'inferred'; discriminating evidence is needed before any mitigation can be gated."
            )
        if not self.c.execute(
            "SELECT 1 FROM artifacts WHERE mission_id=? AND kind='impact_estimate'", (mid,)
        ).fetchone():
            items.append(
                "No impact_estimate artifact yet: customer impact is unquantified; proxy counts (support contacts) cannot establish impact."
            )
        if self.c.execute(
            "SELECT 1 FROM contradictions WHERE mission_id=? AND status='open'", (mid,)
        ).fetchone():
            items.append(
                "Open contradictions remain; resolving one needs discriminating evidence ingested after it was opened."
            )
        done = {
            r[0]
            for r in self.c.execute(
                "SELECT action FROM action_proposals WHERE mission_id=? AND decision='allowed'",
                (mid,),
            )
        }
        todo = [
            r[0]
            for r in self.c.execute(
                "SELECT action FROM authority_rules WHERE mission_id=? AND rule='allowed'", (mid,)
            )
            if r[0] not in done
        ]
        if todo:
            items.append(f"Allowed read-only diagnostics not yet run: {todo}")
        gr = self.c.execute("SELECT action FROM gate_rules WHERE mission_id=?", (mid,)).fetchall()
        if gr and not any(
            r[0]
            in {
                x[0]
                for x in self.c.execute(
                    "SELECT action FROM action_approvals WHERE mission_id=?", (mid,)
                )
            }
            for r in gr
        ):
            ok, why = self.gate_check(mid, gr[0][0])
            items.append(
                f"Human-gate mitigations available: {[r[0] for r in gr]}. Gate check now: {'READY - conditions met, you may propose the mitigation' if ok else 'not yet - ' + why}. Consider whether a reversible mitigation is warranted before final_assessment."
            )
        return items

    # ---------- Gateway
    def request_context(
        self,
        mid,
        actor,
        purpose,
        query,
        tiers=(0, 1, 2, 3),
        ceiling="internal",
        budget_chars=14000,
        prior_denials=None,
        raw=False,
    ):
        rid = str(uuid.uuid4())
        m = self.c.execute("SELECT * FROM missions WHERE mission_id=?", (mid,)).fetchone()
        considered = []
        terms = " OR ".join(sorted(set(re.findall(r"[a-z0-9]{3,}", query.lower()))))
        fts = (
            {
                r[0]: -r[1]
                for r in self.c.execute(
                    "SELECT artifact_id, bm25(artifact_fts) FROM artifact_fts WHERE artifact_fts MATCH ?",
                    (terms,),
                )
            }
            if terms
            else {}
        )
        qe = embed(query)
        rows = self.c.execute(
            "SELECT * FROM artifacts WHERE mission_id IN (?, 'GLOBAL')", (mid,)
        ).fetchall()
        allowed, quarantined = [], []
        for a in rows:
            if a["quarantined"] or a["trust_tier"] not in tiers:
                dec, why = "deny", f"trust tier {a['trust_tier']}/quarantine"
            elif CLASS_RANK.get(a["classification"], 9) > CLASS_RANK[ceiling]:
                dec, why = "deny", "classification above ceiling"
            elif a["status"] == "draft":
                dec, why = "deny", "draft is not evidence"
            else:
                dec, why = "allow", "in scope"
            self.c.execute(
                "INSERT INTO retrieval_decisions(mission_id,request_id,artifact_id,decision,reason,policy_version,created_at) VALUES(?,?,?,?,?,?,?)",
                (mid, rid, a["artifact_id"], dec, why, m["policy_version"], now()),
            )
            (allowed if dec == "allow" else quarantined).append((a, why))
        scored = sorted(
            (
                (fts.get(a["artifact_id"], 0) + 2 * cos(qe, json.loads(a["embedding_json"])), a)
                for a, _ in allowed
            ),
            key=lambda x: -x[0],
        )
        cited = {
            r[0]
            for r in self.c.execute(
                "SELECT DISTINCT artifact_id FROM claim_sources WHERE mission_id=?", (mid,)
            )
        }  # link-graph expansion
        ev = []
        for sc, a in scored:
            if sc > 0 or a["artifact_id"] in cited or True:
                ev.append(
                    {
                        "id": a["artifact_id"],
                        "kind": a["kind"],
                        "tier": a["trust_tier"],
                        "status": a["status"],
                        "owner": a["source_owner"],
                        "created": a["created"],
                        "discriminating": bool(a["discriminating"]),
                        "flags": (
                            ["STALE: cannot determine current state without corroboration"]
                            if self.is_stale(a)
                            else []
                        )
                        + (["incomplete"] if a["status"] == "incomplete" else [])
                        + (
                            ["non-authoritative: single source cannot be established"]
                            if a["trust_tier"] > 1
                            else []
                        ),
                        "content": a["body"],
                    }
                )
        claims = [
            dict(r) for r in self.c.execute("SELECT * FROM claims WHERE mission_id=?", (mid,))
        ]
        for c in claims:
            c["sources"] = [
                r[0]
                for r in self.c.execute(
                    "SELECT artifact_id FROM claim_sources WHERE claim_id=? AND mission_id=?",
                    (c["claim_id"], mid),
                )
            ]
            c["contested"] = (
                self.c.execute(
                    "SELECT COUNT(*) FROM contradictions WHERE mission_id=? AND status='open' AND (claim_a=? OR claim_b=?)",
                    (mid, c["claim_id"], c["claim_id"]),
                ).fetchone()[0]
                > 0
            )
        rules = {
            r[0]: r[1]
            for r in self.c.execute(
                "SELECT action,rule FROM authority_rules WHERE mission_id=?", (mid,)
            )
        }
        lessons = [
            dict(r)
            for r in self.c.execute(
                "SELECT lesson_id,source_mission,domain,lesson,transferable FROM lessons WHERE transferable!='none' AND source_mission!=?",
                (mid,),
            )
        ]
        pkg = {
            "request_id": rid,
            "mission": {
                "id": mid,
                "objective": m["objective"],
                "non_goals": json.loads(m["non_goals"]),
                "phase": m["phase"],
                "authority_scope": m["authority_scope"],
                "risk_tier": m["risk_tier"],
            },
            "claim_status_rules": [
                "You may preserve, downgrade, split or refine a claim status; you may NOT upgrade one without NEW evidence ingested after the claim.",
                "established needs a tier-1 source or >=2 distinct-owner tier<=2 sources; root_cause additionally needs discriminating evidence and no open contradiction.",
                "A single non-authoritative source is reported/inferred, never established. Proxy counts (support contacts) are not total impact.",
                "Stale artifacts cannot determine current state alone.",
                "Quarantined evidence may only be referenced as kind=quarantine_reference (existence), never as a source.",
            ],
            "authority": rules,
            "human_gate": self.gate_guide(mid),
            "claims": claims,
            "pending_review_claims": [c["claim_id"] for c in claims if c["pending_review"]],
            "open_contradictions": [
                dict(r)
                for r in self.c.execute(
                    "SELECT c.*, (SELECT requirement FROM discriminating_evidence_requirements d WHERE d.contradiction_id=c.contradiction_id AND d.mission_id=c.mission_id LIMIT 1) AS discriminating_evidence_needed FROM contradictions c WHERE mission_id=? AND status='open'",
                    (mid,),
                )
            ],
            "mission_checklist": self.checklist(mid, claims),
            "evidence": ev,
            "quarantined_withheld": [{"id": a["artifact_id"], "reason": w} for a, w in quarantined],
            "prior_mission_lessons": [
                dict(
                    l,
                    note="STRUCTURE ONLY. Prior-mission domain facts are NOT evidence for this mission.",
                )
                for l in lessons
            ],
            "regression_tests": [dict(r) for r in self.c.execute("SELECT * FROM regression_tests")],
            "denied_last_round": prior_denials or [],
            "vocab_mechanism_tags": [
                "adapter_retry_timeout",
                "db_saturation",
                "batch_job_contention",
                "capacity",
                "upstream_data_delay",
                "schema_change",
                "timezone_dst",
                "duplicate_ingestion",
                "other",
                "unknown",
            ],
            "proposal_schema": {
                "claims": [
                    {
                        "claim_id": "C#",
                        "statement": "",
                        "kind": sorted(KINDS),
                        "status": sorted(STATUSES),
                        "mechanism_tag": "",
                        "sources": ["artifact ids"],
                        "corroboration": "",
                        "limitation": "",
                    }
                ],
                "contradictions": [
                    {
                        "id": "X#",
                        "claim_a": "",
                        "claim_b": "",
                        "description": "",
                        "discriminating_evidence_needed": "",
                    }
                ],
                "resolutions": [
                    {"contradiction_id": "", "evidence_refs": [""], "outcome": "", "rationale": ""}
                ],
                "dispositions": [{"claim_id": "", "action": "preserve|downgrade|refine"}],
                "capability_gaps": [{"capability": "", "reason": ""}],
                "next_action": {
                    "action": "name from authority list or other",
                    "kind": "diagnostic|mitigation|escalation|none|final_assessment",
                    "rationale": "",
                    "expected_information_gain": "",
                },
            },
        }
        s = json.dumps(pkg)
        while len(s) > budget_chars and pkg["evidence"]:
            pkg["evidence"].pop()
            s = json.dumps(pkg)
        h = hashlib.sha256(s.encode()).hexdigest()
        self.c.execute(
            "INSERT INTO retrieval_audit VALUES(?,?,?,?,?,?,?,?)",
            (
                rid,
                mid,
                actor,
                purpose,
                query,
                json.dumps([e["id"] for e in pkg["evidence"]]),
                h,
                now(),
            ),
        )
        self.c.commit()
        self.emit(mid, "context_package", "gateway", {"request": rid, "hash": h})
        return pkg
