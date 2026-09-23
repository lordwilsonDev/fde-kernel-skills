import sys, os, json, subprocess, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
FDE = os.path.dirname(HERE)
ROOT = os.path.dirname(FDE)
sys.path.insert(0, FDE)
import unittest, driver, lint_scenario, report

GUARD = os.path.join(FDE, "blind_guard.py")


def guard(tool, inp, blind=True):
    proj = tempfile.mkdtemp()
    if blind:
        open(os.path.join(proj, ".fde_blind"), "w").write("x")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proj)
    r = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": tool, "tool_input": inp}),
        capture_output=True,
        text=True,
        env=env,
    )
    shutil.rmtree(proj)
    return r.returncode, r.stderr


class Guard(unittest.TestCase):
    """The blind guard was rewritten (canonical-path capability authorization, run-scoped, create-once proposals). The old regex-era expectations here (any run's ctx readable,
    legacy marker, driver.py commands, absolute-suffix paths) encoded the defects found in the 2026-09-21 bug hunt and were replaced; the full boundary tests live in
    test_m008_hardening.py::BlindGuard."""

    def test_inactive_without_marker(self):
        self.assertEqual(
            guard("Read", {"file_path": "fde/simulator.py"}, blind=False)[0], 0
        )
        self.assertEqual(
            guard("Bash", {"command": "cat fde/kernel.py"}, blind=False)[0], 0
        )

    def test_a_marker_without_a_run_denies_everything_including_the_old_allowed_routes(
        self,
    ):
        for tool, inp in (
            ("Read", {"file_path": "runs/M005_haiku_kernel_a/ctx_r3.json"}),
            ("Bash", {"command": "python3 fde/driver.py status runs/M005_a"}),
            (
                "Write",
                {
                    "file_path": "runs/M005_haiku_kernel_a/proposal_r3.json",
                    "content": "{}",
                },
            ),
            ("Grep", {"pattern": "x"}),
        ):
            self.assertEqual(guard(tool, inp)[0], 2, tool)


class Lint(unittest.TestCase):
    def codes(self, w):
        return {
            f["code"]
            for f in lint_scenario.lint(w)["findings"]
            if f["severity"] == "HIGH"
        }

    def test_m006_leak_is_caught(self):  # the failure that made M006 invalid
        c = self.codes("M006")
        self.assertIn("L1-name-leak", c)
        self.assertIn("L2-doc-pointer", c)
        self.assertTrue(
            any(
                f["code"] == "L2-doc-pointer" and "m6_e05" in f["message"]
                for f in lint_scenario.lint("M006")["findings"]
            )
        )

    def test_no_decoy_diagnostic_is_caught(self):
        for w in ("M003", "M004", "M005"):
            self.assertIn("L3-no-decoy-diagnostic", self.codes(w), w)

    def test_m006_has_a_decoy_diagnostic_and_gate_eligible_decoy_mitigation(self):
        r = lint_scenario.lint("M006")
        self.assertEqual(r["decoy_diagnostics"], ["auth_log_group_analysis"])
        self.assertFalse([f for f in r["findings"] if f["code"].startswith("L6")])

    def test_cli_exit_codes(self):
        self.assertEqual(
            subprocess.run(
                [sys.executable, os.path.join(FDE, "lint_scenario.py"), "M006"],
                capture_output=True,
            ).returncode,
            1,
        )


class Prereg(unittest.TestCase):
    def setUp(self):
        self.w = "ZZTEST"
        self.runs = tempfile.mkdtemp()
        self.p = os.path.join(
            self.runs, f"PREREG_{self.w}.md"
        )  # private runs dir: honours FDE_RUNS in the CLI, never touches the real runs/

    def tearDown(self):
        shutil.rmtree(self.runs, ignore_errors=True)

    def run_cli(self, *a):
        return subprocess.run(
            [sys.executable, os.path.join(FDE, "prereg.py"), *a],
            capture_output=True,
            text=True,
            env=dict(os.environ, FDE_RUNS=self.runs),
        )

    def test_new_verify_addendum_and_no_overwrite(self):
        r = self.run_cli("new", self.w, "--arms", "haiku:kernel x3")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = open(self.p).read()
        self.assertIn("kernel.py:", s)
        self.assertIn("BEFORE any run", s)
        self.assertEqual(self.run_cli("verify", self.w).returncode, 0)
        self.assertNotEqual(self.run_cli("new", self.w).returncode, 0)  # append-only
        self.assertEqual(
            self.run_cli("addendum", self.w, "n reduced by cost").returncode, 0
        )
        self.assertIn("n reduced by cost", open(self.p).read())

    def test_verify_detects_changed_code(self):
        self.run_cli("new", self.w)
        s = open(self.p).read()
        import re

        open(self.p, "w").write(
            re.sub(r"(- kernel\.py: )[0-9a-f]{64}", r"\g<1>" + "0" * 64, s)
        )
        r = self.run_cli("verify", self.w)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CHANGED", r.stdout)

    def test_addendum_refreezes_latest_hashes_and_corruption_is_caught(self):
        import re

        self.run_cli("new", self.w)
        s = open(self.p).read()
        open(self.p, "w").write(
            re.sub(r"(- kernel\.py: )[0-9a-f]{64}", r"\g<1>" + "0" * 64, s)
        )
        self.assertEqual(
            self.run_cli("verify", self.w).returncode, 1
        )  # original hash is wrong
        self.assertNotEqual(
            self.run_cli("addendum", self.w, "driver fix before any run").returncode, 0
        )  # refuses: an addendum can no longer silently re-freeze changed code
        self.assertEqual(
            self.run_cli(
                "addendum", self.w, "driver fix before any run", "--refreeze"
            ).returncode,
            0,
        )
        r = self.run_cli("verify", self.w)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("addendum #1", r.stdout)  # latest freeze wins
        s = open(self.p).read()
        open(self.p, "w").write(
            re.sub(r"(kernel\.py=)[0-9a-f]{64}", r"\g<1>" + "1" * 64, s)
        )
        r = self.run_cli("verify", self.w)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CHANGED since addendum #1", r.stdout)


class PreregHonoursFdeRuns(unittest.TestCase):
    """Regression: the Prereg tests once hardcoded ROOT/runs and failed whenever FDE_RUNS was set. Re-run them in a subprocess with FDE_RUNS pointing at an empty dir and check nothing leaks."""

    def test_prereg_tests_pass_with_fde_runs_set_and_leave_no_files(self):
        outer = tempfile.mkdtemp()
        real = os.path.join(ROOT, "runs")
        before = sorted(os.listdir(real)) if os.path.isdir(real) else None
        try:
            env = dict(os.environ, FDE_RUNS=outer)
            r = subprocess.run(
                [
                    sys.executable,
                    "-W",
                    "ignore",
                    "-m",
                    "unittest",
                    "test_tooling.Prereg",
                ],
                capture_output=True,
                text=True,
                cwd=HERE,
                env=env,
            )
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            self.assertIn("Ran 3 tests", r.stderr)
            self.assertEqual(os.listdir(outer), [])  # nothing left in the FDE_RUNS dir
            self.assertEqual(
                sorted(os.listdir(real)) if os.path.isdir(real) else None, before
            )  # nothing left in the real runs dir
        finally:
            shutil.rmtree(outer, ignore_errors=True)


class InspectRunCli(unittest.TestCase):
    """inspect_run.py CLI: missing/unreadable run or transcript -> one JSON error line, exit 3, no traceback; valid runs unchanged."""

    SCRIPT = os.path.join(FDE, "inspect_run.py")

    def cli(self, *args):
        r = subprocess.run(
            [sys.executable, "-W", "ignore", self.SCRIPT, *args],
            capture_output=True,
            text=True,
        )
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        return r

    def assertErr(self, r, code):
        self.assertEqual(r.returncode, 3)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        o = json.loads(lines[0])
        self.assertIs(o["ok"], False)
        self.assertEqual(o["error_code"], code)
        self.assertTrue(o["message"])

    def newrun(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        d = os.path.join(base, "M006_kernel_a")
        driver.init(d, "M006", "kernel")
        return d

    def test_missing_run(self):
        self.assertErr(
            self.cli(os.path.join(tempfile.gettempdir(), "no_such_run_xyz")),
            "RUN_NOT_FOUND",
        )

    def test_missing_transcript_on_valid_run(self):
        d = self.newrun()
        self.assertErr(
            self.cli(d, "--transcript", d + "/nope.output"), "TRANSCRIPT_NOT_FOUND"
        )

    def test_transcript_flag_without_value(self):
        self.assertErr(self.cli(self.newrun(), "--transcript"), "BAD_ARGUMENT")

    def test_corrupt_run_json(self):
        d = self.newrun()
        open(d + "/run.json", "w").write("{not json")
        self.assertErr(self.cli(d), "RUN_CORRUPT")

    def test_missing_state_db_is_reported_and_not_created(self):
        d = self.newrun()
        os.remove(d + "/state.db")
        self.assertErr(self.cli(d), "RUN_NOT_FOUND")
        self.assertFalse(os.path.exists(d + "/state.db"))

    def test_valid_run_unchanged(self):
        import inspect_run

        d = self.newrun()
        r = self.cli(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            json.loads(r.stdout),
            json.loads(json.dumps(inspect_run.inspect(d), default=str)),
        )

    def test_valid_run_with_transcript(self):
        d = self.newrun()
        tp = d + "/t.output"
        open(tp, "w").write('{"file_path":"a.txt"}')
        r = self.cli(d, "--transcript", tp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["blindness"]["clean"])


class Report(unittest.TestCase):
    def test_table_groups_arms_and_excludes_unfinished(self):
        d = tempfile.mkdtemp()
        for name, mode, finish in (
            ("M005_haiku_kernel_a", "kernel", True),
            ("M005_haiku_raw_a", "raw", True),
            ("M005_haiku_raw_b", "raw", False),
        ):
            run = os.path.join(d, name)
            driver.init(run, "M005", mode)
            if finish:
                p = os.path.join(run, "p0.json")
                json.dump(
                    {"next_action": {"action": "none", "kind": "final_assessment"}},
                    open(p, "w"),
                )
                driver.apply(run, p)
        arms, unfinished = report.collect("M005", d)
        self.assertEqual(sorted(arms), ["haiku_kernel", "haiku_raw"])
        self.assertEqual(unfinished, ["M005_haiku_raw_b"])
        self.assertEqual(report.row(arms["haiku_raw"])["n"], 1)

    def test_status_works_after_claims_exist_and_flags_pending_review(
        self,
    ):  # regression: found by the Haiku smoke test (KeyError 'kind')
        d = tempfile.mkdtemp() + "/r"
        driver.init(d, "M007", "kernel")
        p = d + "/p0.json"
        json.dump(
            {
                "claims": [
                    {
                        "claim_id": "C1",
                        "statement": "s",
                        "kind": "observation",
                        "status": "inferred",
                        "sources": ["m7_e02"],
                    }
                ],
                "next_action": {"action": "pull_sampled_traces", "kind": "diagnostic"},
            },
            open(p, "w"),
        )
        driver.apply(d, p)
        s = driver.status(d)
        self.assertTrue(any(i.startswith("BLOCKING") for i in s["checklist"]))
        self.assertEqual(s["round"], 1)
        r = subprocess.run(
            [
                sys.executable,
                "-W",
                "ignore",
                os.path.join(FDE, "driver.py"),
                "status",
                d,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_status_is_truth_free(self):
        d = tempfile.mkdtemp()
        driver.init(d + "/r", "M006", "kernel")
        s = driver.status(d + "/r")
        self.assertEqual(
            set(s),
            {"world", "mode", "round", "done", "phase", "next_context", "checklist"},
        )
        self.assertNotIn("idp_cert_mismatch", json.dumps(s))


if __name__ == "__main__":
    unittest.main(verbosity=1)
