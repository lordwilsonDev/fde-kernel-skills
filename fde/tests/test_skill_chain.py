import os, re, json, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SK = os.path.join(ROOT, "skills")
CORE = [
    "intent-capture",
    "context-mapper",
    "scope-governance",
    "evidence-builder",
    "plan-generator",
    "execution-orchestrator",
    "quality-safety-review",
    "deliverable-composer",
    "proactive-guide",
    "feedback-learning-loop",
]
EXTENSIONS = [
    "semantic-resolution",
    "concurrency-state",
    "skill-lifecycle",
]  # 11-13: added when the stem vocabulary (00-preflight) turned out not to map 1:1 onto the original 10
ALL_NAMED = (
    ["preflight"] + CORE + EXTENSIONS
)  # 00 + 01-10 + 11-13 = 14 skill folders total
STEM_NAMES = {
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
}  # canonical preflight vocabulary (10, not 14: capability_retrieval+workspace_investigation share one skill; 08/09 aren't independently routed)


def front(path):
    t = open(path).read()
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    assert m, path
    return {
        k.strip(): v.strip()
        for k, v in (l.split(":", 1) for l in m.group(1).splitlines() if ":" in l)
    }, t


def validate_event(e, schema):
    errs = []
    for k in schema["required"]:
        if k not in e:
            errs.append(f"missing {k}")
    if e.get("skill") not in schema["properties"]["skill"]["enum"]:
        errs.append("bad skill")
    if e.get("status") not in schema["properties"]["status"]["enum"]:
        errs.append("bad status")
    for c in e.get("claims", []):
        if (
            c.get("status")
            not in schema["properties"]["claims"]["items"]["properties"]["status"][
                "enum"
            ]
        ):
            errs.append("bad claim status")
    for a in e.get("approvals_required", []):
        if (
            a.get("action_class")
            not in schema["properties"]["approvals_required"]["items"]["properties"][
                "action_class"
            ]["enum"]
        ):
            errs.append("bad action_class")
    return errs


@unittest.skipUnless(
    os.path.isdir(SK), "skills/ is not part of an installed workspace copy"
)
class SkillChain(unittest.TestCase):
    def test_fourteen_skill_folders_numbered_00_through_13_with_valid_frontmatter(self):
        dirs = sorted(d for d in os.listdir(SK) if re.match(r"\d\d-", d))
        self.assertEqual([d[3:] for d in dirs], ALL_NAMED)
        for i, d in enumerate(dirs):
            fm, t = front(os.path.join(SK, d, "SKILL.md"))
            self.assertEqual(fm["name"], ALL_NAMED[i])
            self.assertEqual(int(fm["order"]), i)
            self.assertEqual(fm["model_neutral"], "true")
            self.assertIn("## Model instruction", t)
            self.assertIn("```text", t)
            self.assertIn("## Observability", t)
            self.assertIn(ALL_NAMED[i], t)
            self.assertIn("## Handoff", t)

    def test_core_chain_1_to_10_hands_off_in_strict_order_looping_back_to_1(self):
        for i, name in enumerate(CORE, 1):
            t = open(os.path.join(SK, f"{i:02d}-{name}", "SKILL.md")).read()
            self.assertIn(
                "back to skill 01" if i == 10 else f"skill {i+1:02d}-{CORE[i]}", t
            )

    def test_preflight_selects_before_anything_else_runs(self):
        t = open(os.path.join(SK, "00-preflight", "SKILL.md")).read()
        self.assertIn(
            "Preflight selects systems; the Task Contract authorizes actions; stems execute only when their preconditions are met",
            t,
        )
        for status in ("ACTIVE", "CONDITIONAL", "NOT_NEEDED", "BLOCKED"):
            self.assertIn(status, t)
        for checkpoint in (
            "task start",
            "new tool category",
            "new data source",
            "external action",
            "user correction",
            "major failure",
            "skill promotion",
            "task closure",
        ):
            self.assertIn(checkpoint, t)

    def test_preflight_stem_matrix_covers_all_ten_canonical_stem_names(self):
        t = open(os.path.join(SK, "00-preflight", "SKILL.md")).read()
        for stem in STEM_NAMES:
            self.assertIn(f"`{stem}`", t, stem)

    def test_extension_stems_have_a_narrow_activation_condition_not_always_on(self):
        for name in EXTENSIONS:
            t = open(
                os.path.join(
                    SK, [d for d in os.listdir(SK) if d.endswith(name)][0], "SKILL.md"
                )
            ).read()
            self.assertRegex(t, r"[Aa]ctivates only when")

    def test_no_skill_exposes_chain_of_thought_or_names_a_vendor(self):
        for d in os.listdir(SK):
            p = os.path.join(SK, d, "SKILL.md")
            if os.path.isfile(p):
                t = open(p).read().lower()
                body = (
                    t.split("## what it covers")[1] if "## what it covers" in t else t
                )
                self.assertFalse(
                    re.search(r"\b(claude|gpt|gemini|openai|anthropic)\b", body), d
                )
        self.assertIn(
            "decision record",
            open(os.path.join(SK, "08-deliverable-composer", "SKILL.md")).read(),
        )
        self.assertIn(
            "Do not expose private chain-of-thought",
            open(os.path.join(SK, "MASTER_PROMPT.md")).read(),
        )

    def test_master_prompt_has_rule_zero_through_ten_and_the_closing_requirements(self):
        t = open(os.path.join(SK, "MASTER_PROMPT.md")).read()
        self.assertEqual(
            sorted(int(x) for x in re.findall(r"^(\d+)\. ", t, re.M)),
            list(range(0, 11)),
        )
        self.assertIn("See decision record", t)
        self.assertIn("Preflight selects which stems run", t)

    def test_governance_defaults_ask_before_consequential_actions(self):
        t = open(os.path.join(SK, "03-scope-governance", "SKILL.md")).read()
        for w in (
            "modify",
            "communicate",
            "publish",
            "transact",
            "delete",
            "remember",
            "untrusted document text",
        ):
            self.assertIn(w, t)

    def test_feedback_skill_never_saves_memory_silently(self):
        t = open(os.path.join(SK, "10-feedback-learning-loop", "SKILL.md")).read()
        self.assertIn("Never silently convert", t)
        self.assertIn("lesson (save only after review/approval)", t)

    def test_skill_lifecycle_promotion_needs_recurrence_not_one_success(self):
        t = open(os.path.join(SK, "13-skill-lifecycle", "SKILL.md")).read()
        self.assertIn("recurrence", t.lower())
        self.assertIn("not a single good run", t)

    def test_event_schema_accepts_the_example_and_rejects_bad_events(self):
        s = json.load(open(os.path.join(SK, "_spine", "event.schema.json")))
        e = json.load(open(os.path.join(SK, "_spine", "example_event.json")))
        self.assertEqual(validate_event(e, s), [])
        for bad in (
            {k: v for k, v in e.items() if k != "run_id"},
            dict(e, skill="not-a-skill"),
            dict(e, status="maybe"),
            dict(e, claims=[{"id": "c", "statement": "s", "status": "certain"}]),
            dict(
                e,
                approvals_required=[
                    {"action_class": "yolo", "target": "t", "proposed_change": "p"}
                ],
            ),
        ):
            self.assertTrue(validate_event(bad, s), bad)
        self.assertEqual(set(s["properties"]["skill"]["enum"]), set(ALL_NAMED))


if __name__ == "__main__":
    unittest.main()
