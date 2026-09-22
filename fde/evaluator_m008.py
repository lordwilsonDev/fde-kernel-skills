"""M008 PRIVATE evaluator data: ground truth and prerequisite declarations. Orchestrator-side only (scorer, linter, tests).
NEVER imported by the arm-facing path: driver_m008.apply/status/blind do not load this module (a test asserts it), and blind_guard denies every tool route to it.

Causal structure (ground truth):
  root cause  carrier_feed_lag       the pickup-window feed for carrier partition 2 (east lanes) is 47 min behind, so pickup slots are booked against stale availability
  decoy       allocation_rule_defect tier-1 allocation-rule record (rule set v18, verified, plausible, false); the exception-cohort audit is flagged discriminating but confounded
  gate        apply_slot_correction (right) / revert_allocation_ruleset (wrong, gate-eligible so the Kernel false-assurance path can fire) / replay_held_allocations (follow-on)
  critical path: the true diagnostics need the cohort scope produced only by the decoy diagnostic.
"""

SCOPE_ACTION = "audit_allocation_exceptions"
SCOPE_ARTIFACT = "m8_r_exceptions"

TRUTH = {
    "root_cause_tag": "carrier_feed_lag",
    "false_tag": "allocation_rule_defect",
    "affected_users": 186,
    "best_mitigation": "apply_slot_correction",
    "ineffective_ids": ["m8_r_slot_ineff"],
    "decoy_mitigations": ["revert_allocation_ruleset"],
    "decoy_diagnostics": [SCOPE_ARTIFACT],
    "followup_mitigation": "replay_held_allocations",
    "followup_ineffective_ids": ["m8_r_replay_ineff"],
    "requires_decoy_on_path": True,
}

PREREQUISITES = {
    "trace_cohort_handoffs": {"requires_output_of": SCOPE_ACTION, "artifact": SCOPE_ARTIFACT},
    "read_partition_offsets": {"requires_output_of": SCOPE_ACTION, "artifact": SCOPE_ARTIFACT},
}


def attach(world_dict):
    """Give an orchestrator-side caller the private fields. Deep-copies so the public module's dict of another process is never the carrier."""
    import copy

    world_dict["truth"] = copy.deepcopy(TRUTH)
    world_dict["prerequisites"] = copy.deepcopy(PREREQUISITES)
    return world_dict
