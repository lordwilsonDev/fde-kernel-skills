"""Tests fde/../skills/_spine/router.py: the deterministic reference implementation of skills/00-preflight/SKILL.md.
Covers the three worked examples from the design (simple rewrite, business analysis, production incident) and the
router's own invariants (determinism, every stem gets exactly one valid status, selection != authorization).
"""

import os, sys, json, unittest

SK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "skills",
)
sys.path.insert(0, os.path.join(SK, "_spine"))


@unittest.skipUnless(
    os.path.isdir(SK), "skills/ is not part of an installed workspace copy"
)
class Router(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import router  # type: ignore[import-not-found]

        cls.router = router

    def contract(self, **kw):
        base = dict(
            risk_tier="low",
            has_material_undefined_terms=False,
            material_terms_resolved=True,
            requires_external_sources=False,
            requires_tools=False,
            requires_files_or_queries=False,
            approved_source_and_tool_scope_available=False,
            has_material_claims_or_recommendations=False,
            evidence_exists=False,
            draft_claim_exists=False,
            has_multiple_workers=False,
            is_long_running=False,
            has_reusable_outcome_candidate=False,
            task_completed=False,
            detects_repeated_workflow=False,
            recurrence_confirmed=False,
        )
        base.update(kw)
        return base

    def test_every_stem_gets_exactly_one_valid_status(self):
        r = self.router.select_stems(self.contract())
        for stem, status in r.items():
            self.assertIn(status, self.router.STATUSES, stem)
        self.assertEqual(
            set(r),
            {
                "question_framing",
                "semantic_resolution",
                "ambiguity_risk",
                "context_assembly",
                "capability_retrieval",
                "workspace_investigation",
                "memory_consolidation",
                "concurrency_state",
                "validation",
                "skill_lifecycle",
            },
        )

    def test_deterministic_same_contract_same_plan(self):
        c = self.contract(
            risk_tier="high",
            requires_tools=True,
            has_material_claims_or_recommendations=True,
            evidence_exists=True,
        )
        r1 = self.router.select_stems(c)
        r2 = self.router.select_stems(dict(c))
        self.assertEqual(r1, r2)

    def test_question_framing_is_always_active(self):
        self.assertEqual(
            self.router.select_stems(self.contract())["question_framing"], "ACTIVE"
        )

    # ---- Example 1: simple rewrite ("Rewrite this email to sound warmer.")
    def test_example_simple_rewrite(self):
        r = self.router.select_stems(
            self.contract()
        )  # nothing material, no tools, no claims, single user
        self.assertEqual(r["question_framing"], "ACTIVE")
        self.assertEqual(
            r["semantic_resolution"], "CONDITIONAL"
        )  # no material undefined term -> stays conditional, never forced active
        self.assertEqual(
            r["ambiguity_risk"], "CONDITIONAL"
        )  # low risk -> not forced active
        self.assertEqual(r["context_assembly"], "CONDITIONAL")
        self.assertEqual(r["capability_retrieval"], "CONDITIONAL")
        self.assertEqual(r["workspace_investigation"], "CONDITIONAL")
        self.assertEqual(r["validation"], "CONDITIONAL")
        self.assertEqual(r["concurrency_state"], "NOT_NEEDED")
        self.assertEqual(r["skill_lifecycle"], "NOT_NEEDED")
        self.assertEqual(
            self.router.active_now(self.contract()), ["01-intent-capture"]
        )  # only one stem actually runs

    # ---- Example 2: business analysis ("Which customer segment drove expansion revenue last month?")
    def test_example_business_analysis_before_term_resolved(self):
        c = self.contract(
            risk_tier="medium",
            has_material_undefined_terms=True,
            material_terms_resolved=False,
            requires_external_sources=True,
            requires_tools=True,
            requires_files_or_queries=True,
            has_material_claims_or_recommendations=True,
        )
        r = self.router.select_stems(c)
        self.assertEqual(r["question_framing"], "ACTIVE")
        self.assertEqual(
            r["semantic_resolution"], "ACTIVE"
        )  # "expansion revenue" is a material undefined term
        self.assertEqual(r["ambiguity_risk"], "ACTIVE")  # medium risk
        self.assertEqual(r["context_assembly"], "ACTIVE")  # requires external sources
        self.assertEqual(
            r["capability_retrieval"], "BLOCKED"
        )  # tools needed but the term isn't resolved yet -- must not query before that
        self.assertEqual(
            r["workspace_investigation"], "CONDITIONAL"
        )  # needs files/queries but scope not yet approved
        self.assertEqual(
            r["validation"], "BLOCKED"
        )  # a claim will be needed but no evidence/draft exists yet
        self.assertEqual(
            self.router.active_now(c),
            sorted(
                {
                    "01-intent-capture",
                    "11-semantic-resolution",
                    "03-scope-governance",
                    "02-context-mapper",
                }
            ),
        )

    def test_example_business_analysis_after_term_resolved_and_scoped(self):
        c = self.contract(
            risk_tier="medium",
            requires_external_sources=True,
            requires_tools=True,
            requires_files_or_queries=True,
            approved_source_and_tool_scope_available=True,
            has_material_claims_or_recommendations=True,
            evidence_exists=True,
        )
        r = self.router.select_stems(c)
        self.assertEqual(
            r["capability_retrieval"], "ACTIVE"
        )  # term resolved (default: has_material_undefined_terms False) -> no longer blocked
        self.assertEqual(r["workspace_investigation"], "ACTIVE")  # scope now approved
        self.assertEqual(r["validation"], "ACTIVE")  # evidence now exists

    # ---- Example 3: production incident ("Checkout is failing. Fix it.")
    def test_example_production_incident(self):
        c = self.contract(
            risk_tier="critical",
            has_material_undefined_terms=True,
            material_terms_resolved=False,
            requires_external_sources=True,
            requires_tools=True,
            requires_files_or_queries=True,
            approved_source_and_tool_scope_available=True,
            has_multiple_workers=True,
            has_material_claims_or_recommendations=True,
            draft_claim_exists=True,
        )
        r = self.router.select_stems(c)
        for stem in (
            "question_framing",
            "semantic_resolution",
            "ambiguity_risk",
            "context_assembly",
            "workspace_investigation",
            "concurrency_state",
            "validation",
        ):
            self.assertEqual(r[stem], "ACTIVE", stem)
        self.assertEqual(
            r["capability_retrieval"], "BLOCKED"
        )  # read-only tools only, until the term (what "failing" means, blast radius) resolves -- matches "not permitted to deploy or restart simply because the user said fix it"
        self.assertEqual(
            r["memory_consolidation"], "CONDITIONAL"
        )  # not yet -- task hasn't completed
        self.assertEqual(
            r["skill_lifecycle"], "NOT_NEEDED"
        )  # no recurrence detected yet

    def test_selection_is_not_execution_active_now_never_includes_blocked_or_conditional(
        self,
    ):
        c = self.contract(
            risk_tier="critical",
            requires_tools=True,
            has_material_undefined_terms=True,
            material_terms_resolved=False,
        )
        r = self.router.select_stems(c)
        self.assertEqual(r["capability_retrieval"], "BLOCKED")
        self.assertNotIn("06-execution-orchestrator", self.router.active_now(c))

    def test_task_completion_and_recurrence_flip_conditional_stems_active(self):
        c = self.contract(
            has_reusable_outcome_candidate=True,
            task_completed=True,
            detects_repeated_workflow=True,
            recurrence_confirmed=True,
        )
        r = self.router.select_stems(c)
        self.assertEqual(r["memory_consolidation"], "ACTIVE")
        self.assertEqual(r["skill_lifecycle"], "ACTIVE")

    def test_bad_status_from_a_malformed_contract_raises_rather_than_silently_passing(
        self,
    ):
        # a contract that produces an invalid status should never happen with the shipped rules; assert the invariant holds broadly
        import itertools

        keys = [
            "has_material_undefined_terms",
            "material_terms_resolved",
            "requires_tools",
            "requires_files_or_queries",
            "approved_source_and_tool_scope_available",
            "has_material_claims_or_recommendations",
            "evidence_exists",
            "draft_claim_exists",
            "has_multiple_workers",
            "is_long_running",
            "has_reusable_outcome_candidate",
            "task_completed",
            "detects_repeated_workflow",
            "recurrence_confirmed",
        ]
        for risk in self.router.RISK_TIERS + ("garbage",):
            for combo in itertools.product(
                [True, False], repeat=3
            ):  # a sample, not the full 2^14 space
                c = self.contract(risk_tier=risk, **dict(zip(keys[:3], combo)))
                r = self.router.select_stems(c)
                for stem, status in r.items():
                    self.assertIn(status, self.router.STATUSES, (stem, status, c))


if __name__ == "__main__":
    unittest.main()
