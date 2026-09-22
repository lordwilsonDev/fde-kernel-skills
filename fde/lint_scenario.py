"""Scenario leak linter. Born from the M006 failure: the true diagnostic was named in the action catalogue and pointed to by
the stale runbook, so no run ever visited the decoy and the red-team tested nothing.

Heuristic and deliberately noisy: it reports WARNINGS to fix or consciously accept before a scenario family is pre-registered.
Usage: python3 fde/lint_scenario.py <WORLD> [--json] [--path-checks]        exit 1 if any HIGH finding.

M008 additions (born from the M007 finding "decoy not reached"): L7 and L8 check that the decoy is on the critical path. They run for worlds whose truth
declares requires_decoy_on_path, or for any world with --path-checks (M003-M007 keep their existing lint result without the flag).
  L7-decoy-on-path  HIGH if a valid run can reach gate eligibility (obtain a discriminating artifact) without executing a decoy diagnostic.
  L8               HIGH if a true diagnostic can execute without receiving the declared prerequisite output of the decoy diagnostic.
"""

import sys, os, re, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulator as S

try:
    import simulator_m008  # noqa: F401  registers WORLDS['M008']
except ImportError:
    pass

GENERIC = {
    "check",
    "compare",
    "review",
    "query",
    "status",
    "report",
    "analysis",
    "log",
    "config",
    "metrics",
    "request",
    "run",
    "get",
    "show",
    "list",
    "by",
    "the",
    "of",
    "to",
    "and",
    "for",
    "in",
    "on",
    "a",
    "an",
    "is",
    "are",
    "was",
    "not",
    "or",
    "with",
    "from",
    "that",
    "this",
    "it",
    "its",
    "at",
    "as",
    "be",
    "no",
    "all",
    "any",
    "only",
    "after",
    "before",
    "which",
    "has",
    "have",
    "had",
    "than",
    "then",
    "when",
    "if",
    "so",
    "we",
    "you",
    "our",
    "your",
    "can",
    "may",
    "must",
    "will",
    "does",
    "did",
    "do",
    "one",
    "two",
    "each",
    "per",
    "new",
    "old",
    "now",
    "since",
    "into",
    "out",
    "up",
    "down",
    "over",
    "under",
    "between",
    "about",
    "also",
    "more",
    "most",
    "less",
    "least",
    "there",
    "their",
    "them",
    "they",
    "these",
    "those",
}
tok = lambda s: [t for t in re.findall(r"[a-z0-9]{3,}", s.lower()) if t not in GENERIC]


def _attach(world):
    """Orchestrator side only: M008's answer key lives in evaluator_m008 (private), not in the world the arm-facing driver imports."""
    w = S.WORLDS[world]
    if "truth" not in w and world.startswith("M008"):
        import evaluator_m008

        evaluator_m008.attach(w)
    return w


def lint(world, path_checks=None):
    w = _attach(world)
    t = w["truth"]
    findings = []
    acts = w["actions"]

    def add(sev, code, msg):
        findings.append({"severity": sev, "code": code, "message": msg})

    true_diags = [
        a
        for a, spec in acts.items()
        if spec[0] == "diagnostic" and spec[1]["discriminating"] and _supports_truth(spec[1], t)
    ]
    decoy_diags = [
        a
        for a, spec in acts.items()
        if spec[0] == "diagnostic" and spec[1]["discriminating"] and a not in true_diags
    ]
    tag_tokens = set(tok(t["root_cause_tag"].replace("_", " ")))
    mit_tokens = set(tok(t["best_mitigation"].replace("_", " ")))
    initial_docs = {
        a["aid"]: (a["title"] + " " + a["body"], a["tier"], a["status"]) for a in w["artifacts"]
    }

    # L1: action name shares distinctive tokens with the root-cause tag or the mitigation name
    for a in true_diags:
        nt = set(tok(a.replace("_", " ")))
        shared = nt & (tag_tokens | mit_tokens)
        if shared:
            add(
                "HIGH",
                "L1-name-leak",
                f"true diagnostic '{a}' shares tokens {sorted(shared)} with the ground-truth tag/mitigation name; the action list telegraphs the answer",
            )

    # L2: an initial artifact points at the true diagnostic (runbook / owner doc / chat)
    for a in true_diags:
        nt = set(tok(a.replace("_", " ")))
        for aid, (text, tier, status) in initial_docs.items():
            hit = nt & set(tok(text))
            if len(hit) >= 2 or (len(hit) >= 1 and status == "stale"):
                add(
                    "HIGH" if len(hit) >= 2 else "MED",
                    "L2-doc-pointer",
                    f"initial artifact {aid} (tier {tier}, {status}) contains {sorted(hit)} from true diagnostic '{a}'; every arm can read the pointer",
                )

    # L3: the decoy must be genuinely attractive
    if not decoy_diags:
        add(
            "HIGH",
            "L3-no-decoy-diagnostic",
            "no flagged-discriminating diagnostic other than the true one; a red-team scenario needs a competing discriminating-looking artifact",
        )
    else:
        for a in decoy_diags:
            body = acts[a][1]["body"].lower()
            if not any(
                x in body for x in ("limitation", "cannot separate", "confound", "correlat")
            ):
                add(
                    "MED",
                    "L3b-decoy-unmarked",
                    f"decoy diagnostic '{a}' states no limitation; a careful reader has no way to see it is confounded",
                )

    # L4: catalogue balance
    diag = [a for a, spec in acts.items() if spec[0] == "diagnostic"]
    if len(diag) < 5:
        add(
            "MED",
            "L4-small-catalogue",
            f"only {len(diag)} diagnostics; picking the right one first is too likely",
        )
    if len(true_diags) and len(diag) and (len(true_diags) / len(diag)) > 0.4:
        add(
            "MED",
            "L4b-too-many-true",
            f"{len(true_diags)}/{len(diag)} diagnostics support the truth; nearly any first move succeeds",
        )

    # L5: initial evidence already contains the answer
    for aid, (text, tier, status) in initial_docs.items():
        if (
            tag_tokens
            and len(tag_tokens & set(tok(text))) >= max(1, len(tag_tokens) - 0)
            and status not in ("untrusted",)
        ):
            add(
                "MED",
                "L5-answer-in-packet",
                f"initial artifact {aid} contains all tokens of the ground-truth tag {sorted(tag_tokens)}",
            )

    # L6: a decoy mitigation only matters if the gate can approve it
    for dm in t.get("decoy_mitigations", []):
        if dm not in w.get("gate", {}):
            add(
                "MED",
                "L6-decoy-mitigation-ungated",
                f"decoy mitigation '{dm}' is not gate-eligible; the gate false-assurance path cannot fire",
            )
    if not t.get("decoy_mitigations"):
        add(
            "LOW",
            "L6b-no-decoy-mitigation",
            "no decoy mitigation defined; gate false assurance is untestable in this family",
        )

    if path_checks or (path_checks is None and t.get("requires_decoy_on_path")):
        _path_checks(w, true_diags, add)

    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    return {
        "world": world,
        "true_diagnostics": true_diags,
        "decoy_diagnostics": decoy_diags,
        "findings": findings,
    }


def _released(spec, present):
    """Mirror of driver.apply: an action spec's optional 3rd element lists artifact ids that must already exist; if any is missing the 4th element is released instead."""
    return spec[3] if len(spec) > 2 and not all(r in present for r in spec[2]) else spec[1]


def reachable_without_decoy(w):
    """Fixpoint over every diagnostic EXCEPT the decoy diagnostics: which artifacts can a run hold without ever executing a decoy diagnostic?
    Mitigations are excluded: they are gated, and the gate needs the discriminating evidence this function is looking for.
    """
    decoy_arts = set(w["truth"].get("decoy_diagnostics") or [])
    skip = {
        a
        for a, spec in w["actions"].items()
        if spec[0] == "diagnostic" and spec[1]["aid"] in decoy_arts
    }
    held = {a["aid"]: a for a in w["artifacts"]}
    while True:
        n = len(held)
        for a, spec in w["actions"].items():
            if spec[0] != "diagnostic" or a in skip:
                continue
            art = _released(spec, set(held))
            held[art["aid"]] = art
        if len(held) == n:
            return held


def _path_checks(w, true_diags, add):
    acts, t = w["actions"], w["truth"]
    decoy_arts = set(t.get("decoy_diagnostics") or [])
    held = reachable_without_decoy(w)
    leaked = sorted(aid for aid, a in held.items() if a["discriminating"] and aid not in decoy_arts)
    if leaked:
        add(
            "HIGH",
            "L7-decoy-on-path",
            f"a run can reach gate eligibility without executing a decoy diagnostic: discriminating artifact(s) {leaked} are obtainable using only non-decoy diagnostics (the M007 failure)",
        )
    prereqs = w.get("prerequisites") or {}
    decoy_names = {
        a: spec
        for a, spec in acts.items()
        if spec[0] == "diagnostic" and spec[1]["aid"] in decoy_arts
    }
    initial = {a["aid"] for a in w["artifacts"]}
    for a in true_diags:
        spec = acts[a]
        pr = prereqs.get(a)
        if not pr:
            add(
                "HIGH",
                "L8",
                f"true diagnostic '{a}' declares no prerequisite output from a decoy diagnostic; it can execute without one",
            )
            continue
        d = pr.get("requires_output_of")
        need = pr.get("artifact")
        if d not in decoy_names or decoy_names[d][1]["aid"] != need:
            add(
                "HIGH",
                "L8",
                f"'{a}' declares prerequisite {d}/{need}, which is not the output of a declared decoy diagnostic",
            )
            continue
        if len(spec) < 4 or need not in spec[2]:
            add(
                "HIGH",
                "L8",
                f"'{a}' does not gate its real result on {need}; the driver would release it without the prerequisite",
            )
            continue
        if _released(spec, initial | (set(held) - decoy_arts))["aid"] == spec[1]["aid"]:
            add("HIGH", "L8", f"'{a}' releases its real result without {need}")
        if spec[3]["discriminating"]:
            add(
                "HIGH",
                "L8",
                f"the not-ready result of '{a}' ({spec[3]['aid']}) is flagged discriminating",
            )
        if _released(spec, {need})["aid"] != spec[1]["aid"]:
            add(
                "HIGH", "L8", f"'{a}' does not release its real result even when {need} is supplied"
            )
        producers = [
            x
            for x, sp in acts.items()
            if x != d and need in {sp[1]["aid"]} | ({sp[3]["aid"]} if len(sp) > 3 else set())
        ]
        if producers or need in initial:
            add(
                "HIGH",
                "L8",
                f"prerequisite {need} of '{a}' can be obtained without running {d}: also produced by {producers or 'the initial packet'}",
            )


def _supports_truth(art, truth):
    """A discriminating diagnostic 'supports the truth' if its text shares distinctive tokens with the mitigation outcome or truth tag, or if it is not one of the decoys.
    Decoys are declared via truth['decoy_diagnostics'] when present; otherwise fall back to: body mentions a limitation/confound => decoy.
    """
    decl = truth.get("decoy_diagnostics")
    body = art["body"].lower()
    if decl is not None:
        return art["aid"] not in decl
    return not any(x in body for x in ("limitation", "cannot separate", "confound"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in S.WORLDS:
        sys.exit(f"usage: lint_scenario.py <{'|'.join(S.WORLDS)}> [--json]")
    r = lint(sys.argv[1], path_checks=True if "--path-checks" in sys.argv else None)
    if "--json" in sys.argv:
        print(json.dumps(r, indent=1))
    else:
        print(
            f"{r['world']}: true diagnostics {r['true_diagnostics']}; decoy diagnostics {r['decoy_diagnostics']}"
        )
        for f in r["findings"]:
            print(f"  [{f['severity']}] {f['code']}: {f['message']}")
        if not r["findings"]:
            print("  no findings")
    sys.exit(1 if any(f["severity"] == "HIGH" for f in r["findings"]) else 0)
