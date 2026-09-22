"""Deterministic preflight router: reference implementation of skills/00-preflight/SKILL.md.
Not a live enforcement mechanism - these are model instructions (skills), so nothing here runs automatically inside a real
conversation. This module exists so the router is auditable and testable, per the design's own rule: "The router should be
deterministic enough to audit."

STEM_MAP: the 10 canonical stem names (as used in preflight_input/preflight_result) mapped to their skill folder. Three stems
(semantic_resolution, concurrency_state, skill_lifecycle) had no equivalent in the original 01-10 chain and were added as 11-13.
Two of the original 10 skills (08-deliverable-composer, 09-proactive-guide) are not separately named stems here; they are folded
into validation's output path (the deliverable and the next questions are what validation's approval unlocks), so they are not
independently selectable — they always run once validation has produced approved output, which the router encodes as a fixed
rule rather than a selectable stem."""
STEM_MAP = {
    "question_framing": "01-intent-capture",
    "semantic_resolution": "11-semantic-resolution",
    "ambiguity_risk": "03-scope-governance",
    "context_assembly": "02-context-mapper",
    "capability_retrieval": "06-execution-orchestrator",
    "workspace_investigation": "06-execution-orchestrator",   # same skill; capability_retrieval = which tool, workspace_investigation = using it on files/queries
    "memory_consolidation": "10-feedback-learning-loop",
    "concurrency_state": "12-concurrency-state",
    "validation": "07-quality-safety-review",
    "skill_lifecycle": "13-skill-lifecycle",
}
ALWAYS_AFTER_VALIDATION = ("08-deliverable-composer", "09-proactive-guide")   # fixed follow-on, not independently routed

STATUSES = ("ACTIVE", "CONDITIONAL", "NOT_NEEDED", "BLOCKED")
RISK_TIERS = ("low", "medium", "high", "critical")


def select_stems(contract):
    """contract: an object/dict with the boolean/enum fields used below (see TaskContract in test_preflight_router.py for the shape).
    Returns {stem_name: status}. Every one of the 10 canonical stems gets exactly one status from STATUSES."""
    g = contract.get if isinstance(contract, dict) else lambda k, d=None: getattr(contract, k, d)

    stems = {
        "question_framing": "ACTIVE",
        "semantic_resolution": "CONDITIONAL",
        "ambiguity_risk": "CONDITIONAL",
        "context_assembly": "CONDITIONAL",
        "capability_retrieval": "CONDITIONAL",
        "workspace_investigation": "CONDITIONAL",
        "memory_consolidation": "CONDITIONAL",
        "concurrency_state": "NOT_NEEDED",
        "validation": "CONDITIONAL",
        "skill_lifecycle": "NOT_NEEDED",
    }

    if g("has_material_undefined_terms"):
        stems["semantic_resolution"] = "ACTIVE"

    risk = g("risk_tier", "low")
    if risk not in RISK_TIERS: risk = "low"
    if risk in ("medium", "high", "critical"):
        stems["ambiguity_risk"] = "ACTIVE"

    if g("requires_external_sources"):
        stems["context_assembly"] = "ACTIVE"

    if g("requires_tools"):
        # capability_retrieval needs a resolved scope first: BLOCKED (not ACTIVE) if a material term is still unresolved
        stems["capability_retrieval"] = "BLOCKED" if (g("has_material_undefined_terms") and not g("material_terms_resolved")) else "ACTIVE"

    if g("requires_files_or_queries"):
        stems["workspace_investigation"] = "CONDITIONAL" if not g("approved_source_and_tool_scope_available") else "ACTIVE"

    if g("has_material_claims_or_recommendations"):
        # validation needs evidence or a draft claim to exist yet; otherwise it's correctly BLOCKED, not silently ACTIVE on nothing
        stems["validation"] = "ACTIVE" if (g("evidence_exists") or g("draft_claim_exists")) else "BLOCKED"

    if g("has_multiple_workers") or g("is_long_running"):
        stems["concurrency_state"] = "ACTIVE"

    if g("has_reusable_outcome_candidate"):
        stems["memory_consolidation"] = "CONDITIONAL" if not g("task_completed") else "ACTIVE"

    if g("detects_repeated_workflow"):
        stems["skill_lifecycle"] = "CONDITIONAL" if not g("recurrence_confirmed") else "ACTIVE"

    for s in stems:
        assert stems[s] in STATUSES, f"{s}: invalid status {stems[s]!r}"
    return stems


def active_now(contract):
    """The stems actually permitted to run THIS pass — the ACTIVE-status subset, resolved to skill folder names."""
    return sorted({STEM_MAP[s] for s, status in select_stems(contract).items() if status == "ACTIVE"})
