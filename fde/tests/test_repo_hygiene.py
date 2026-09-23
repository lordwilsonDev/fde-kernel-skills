"""Repo-hygiene gate — the four Blueprint-shaped guarantees from palantir/blueprint:
an agent front door, a pinned runtime, a check-only pre-commit hook, and format/type
gates whose exemptions are EXACTLY the byte-pinned set.

Why here: FDE's meta-gate is `make check`; these tests make the missing automation
layer load-bearing instead of aspirational. Exemptions derive from the experiment's
own registrations + the M007 baseline, so no future edit can quietly widen one
(add a line only when a registration freezes a file).

Skip policy mirrors house precedent: IS_SOURCE (install.sh exists) guards tests that
RUN the gate; runs/registrations guards anything DERIVING the frozen set — installed
workspaces carry the code, not the experiment (same idea as test_m008.HAS_M007)."""

import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FDE = os.path.dirname(HERE)
ROOT = os.path.dirname(FDE)
sys.path.insert(0, FDE)
IS_SOURCE = os.path.exists(os.path.join(ROOT, "install.sh"))
HAS_REG = os.path.isdir(os.path.join(ROOT, "runs", "registrations"))
EXEMPT_FILE = os.path.join(ROOT, "frozen_format_exemptions.txt")


class AgentFrontDoor(unittest.TestCase):
    def test_agents_md_exists_and_names_the_load_bearing_things(self):
        p = os.path.join(ROOT, "AGENTS.md")
        self.assertTrue(
            os.path.exists(p),
            "AGENTS.md is the front door for any agent (Blueprint ships one)",
        )
        t = open(p).read()
        self.assertTrue(t.startswith("# "), "AGENTS.md opens with an H1")
        for needle in (
            "make check",
            "make precommit",
            "ABSTRACTIONS.md",
            "Frozen",
            "blind",
            "3.12",
        ):
            self.assertIn(needle, t, f"AGENTS.md must mention {needle!r}")

    def test_python_version_is_pinned_to_this_interpreter(self):
        p = os.path.join(ROOT, ".python-version")
        self.assertTrue(os.path.exists(p), ".python-version missing")
        self.assertEqual(
            open(p).read().strip(),
            "{}.{}".format(*sys.version_info[:2]),
            ".python-version must match the interpreter the gate runs on — the byte-pins assume it",
        )


class CheckOnlyHook(unittest.TestCase):
    ALLOWED = re.compile(
        r"^(#!/bin/sh|set -e(uo pipefail)?|cd \"\$\(git rev-parse --show-toplevel\)\"|make precommit)$"
    )

    def test_hook_is_executable_and_says_only_check_things(self):
        p = os.path.join(ROOT, "hooks", "pre-commit")
        self.assertTrue(os.path.exists(p), "versioned hook missing (hooks/pre-commit)")
        self.assertTrue(os.access(p, os.X_OK), "hook not executable")
        lines = [ln.rstrip("\n") for ln in open(p)]
        self.assertTrue(
            any(ln.strip() == "make precommit" for ln in lines),
            "hook must invoke the meta-gate",
        )
        for ln in lines:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            self.assertRegex(
                s,
                self.ALLOWED,
                "pre-commit must be CHECK-ONLY: every command line must be whitelisted",
            )

    @unittest.skipUnless(
        os.path.isdir(os.path.join(ROOT, ".git")), "no git here (installed workspace)"
    )
    def test_hook_forwarder_is_installed_in_this_checkout(self):
        fwd = os.path.join(ROOT, ".git", "hooks", "pre-commit")
        self.assertTrue(os.path.exists(fwd), "run `make hook` once after cloning")
        self.assertIn(
            "hooks/pre-commit",
            open(fwd).read(),
            "forwarder must exec the versioned hook",
        )


class GateWiring(unittest.TestCase):
    def test_makefile_wires_one_meta_gate(self):
        mk = open(os.path.join(ROOT, "Makefile")).read()
        m = re.search(r"^check:\s*(\S+(?:\s+\S+)*)\s*$", mk, re.M)
        self.assertIsNotNone(m, "check target missing")
        missing = {"test", "lint", "verify", "tree", "fmt-check", "typecheck"} - set(
            m.group(1).split()
        )
        self.assertEqual(missing, set(), "check must run every gate stage")
        self.assertIsNotNone(
            re.search(r"^precommit:\s*check\s*$", mk, re.M),
            "precommit is an alias for the full gate",
        )
        for t in ("fmt-check:", "typecheck:", "hook:"):
            self.assertIn(t, mk, f"missing `{t}` target")

    @unittest.skipUnless(
        HAS_REG, "frozen set needs registrations (not shipped to installed copies)"
    )
    def test_mypy_overrides_only_touch_frozen_modules(self):
        import hygiene

        ini = os.path.join(ROOT, "mypy.ini")
        self.assertTrue(os.path.exists(ini), "mypy.ini missing")
        frozen = hygiene.frozen_py()
        overrides = [
            o
            for o in re.findall(r"^\[mypy-([^\]]+)\]", open(ini).read(), re.M)
            if o != "mypy"
        ]
        self.assertTrue(
            overrides,
            "frozen modules with type debt must be scoped in mypy.ini, not edited in source",
        )
        for mod in overrides:
            mp = mod.replace(".", "/") + ".py"
            hits = [p for p in frozen if p == mp or p.endswith("/" + mp)]
            self.assertEqual(
                len(hits),
                1,
                f"override [{mod}] does not resolve to exactly one frozen file (got {hits})",
            )


class FrozenExemptions(unittest.TestCase):
    @unittest.skipUnless(
        HAS_REG and os.path.exists(EXEMPT_FILE),
        "needs registrations + the exemption file",
    )
    def test_exemptions_are_exactly_the_frozen_py_set(self):
        import hygiene

        self.assertEqual(
            hygiene.exemptions(),
            hygiene.frozen_py(),
            "exemptions == byte-pinned set: no FREE file may dodge the formatter, "
            "and no FROZEN file may ever be handed to it (the pin would break)",
        )


class ClaimsMatchReality(unittest.TestCase):
    def test_readme_test_count_is_current(self):
        rd = open(os.path.join(ROOT, "README.md")).read()
        claims = re.findall(r"(\d+)\s+tests", rd) + re.findall(
            r"tests only \((\d+)\)", rd
        )
        self.assertTrue(
            claims,
            "README stopped claiming a test count — update this test with the new claim style",
        )
        n = (
            unittest.TestLoader()
            .discover(os.path.join(ROOT, "fde", "tests"))
            .countTestCases()
        )
        for c in claims:
            self.assertEqual(
                int(c),
                n,
                f"README claims {c} tests; discovery counts {n} — update README.md",
            )


class GateRuns(unittest.TestCase):
    @unittest.skipUnless(
        IS_SOURCE,
        "the gate runs in the source checkout (needs experiment material + make)",
    )
    def test_new_gate_stages_pass(self):
        for stage in ("fmt-check", "typecheck"):
            r = subprocess.run(
                ["make", stage], cwd=ROOT, capture_output=True, text=True, timeout=300
            )
            self.assertEqual(
                r.returncode,
                0,
                f"make {stage}:\n{r.stdout[-2500:]}\n{r.stderr[-2500:]}",
            )

    @unittest.skipUnless(IS_SOURCE, "toolchain pins are enforced where the tools run")
    def test_toolchain_matches_requirements_dev_pins(self):
        req = os.path.join(ROOT, "requirements-dev.txt")
        self.assertTrue(os.path.exists(req), "requirements-dev.txt missing")
        pins = dict(
            ln.split("==") for ln in (s.strip() for s in open(req)) if "==" in ln
        )
        for tool in ("black", "mypy"):
            self.assertIn(tool, pins, f"{tool} must be pinned in requirements-dev.txt")
            out = subprocess.run(
                [sys.executable, "-m", tool, "--version"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            ver = out.stdout + out.stderr
            self.assertIn(
                pins[tool],
                ver,
                f"installed {tool} is {ver.strip()!r}, pinned {pins[tool]} — gate behavior would drift",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
