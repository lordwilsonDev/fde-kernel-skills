"""Closed-family verify semantics (M009 design, open item 1).

A completed family stays verifiable while the NEXT family evolves shared code:
file drift is red until a NEWER active registration re-freezes the current hash
verbatim, then green with attribution (`tree advanced under W vN`). Older
records never cover (no retroactive whitewashing), no registration means no
window (FROZEN_FILE_CHANGED, exactly as before), and run eligibility for the
completed family's scored runs survives covered drift.

Ordering in `registry.covered_drift` is per-second: tests that need a coverer
sleep just over one second so created_utc differs.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FDE = os.path.dirname(HERE)
sys.path.insert(0, FDE)
import prereg
import registry


def _scratch():
    """(code-root, runs-root): both patchable via module HERE/RUNS, one freezable file."""
    code = tempfile.mkdtemp()
    runs = tempfile.mkdtemp()
    with open(os.path.join(code, "kernel.py"), "w") as fh:
        fh.write("kernel v1\n")
    return code, runs


def _beat_second():
    """registry.covered_drift orders per-second and conservatively ties -> wait it out."""
    time.sleep(1.05)


class CoveredDriftSemantics(unittest.TestCase):
    def setUp(self):
        self.code, self.runs = _scratch()
        self._saved = (registry.HERE, prereg.HERE, prereg.RUNS)
        registry.HERE = prereg.HERE = self.code
        prereg.RUNS = self.runs

    def tearDown(self):
        registry.HERE, prereg.HERE, prereg.RUNS = self._saved
        shutil.rmtree(self.code, ignore_errors=True)
        shutil.rmtree(self.runs, ignore_errors=True)

    def _register(self, world, files=("kernel.py",)):
        return registry.register(world, 1, "# body\n", "# predictions\n", list(files), runs=self.runs)

    def _drift(self, content="kernel v2\n"):
        with open(os.path.join(self.code, "kernel.py"), "w") as fh:
            fh.write(content)

    def _manifest(self, rec, run_id="M008_scratch_a"):
        run = os.path.join(self.runs, run_id)
        os.makedirs(run, exist_ok=True)
        with open(os.path.join(run, "run_manifest.json"), "w") as fh:
            json.dump(
                {
                    "schema_version": 1,
                    "run_kind": "scored",
                    "registration_hash": rec["record_sha256"],
                    "code_hashes": rec["files"],
                    "run_id": run_id,
                },
                fh,
            )
        return run

    def test_m009_is_known_but_unregistered(self):
        with self.assertRaises(registry.RegistryError) as cm:
            registry.verify("M009", runs=self.runs)
        self.assertEqual(cm.exception.code, "NO_REGISTRATION")  # not UNKNOWN_WORLD

    def test_no_drift_verifies_clean_without_coverage_cruft(self):
        self._register("M008")
        rec = registry.verify("M008", runs=self.runs)
        self.assertNotIn("covered_drift_by", rec)

    def test_uncovered_drift_stays_red_everywhere(self):
        rec = self._register("M008")
        run = self._manifest(rec)
        self.assertTrue(registry.run_eligibility(run, "M008", runs=self.runs)[0])
        self._drift()
        with self.assertRaises(registry.RegistryError) as cm:
            registry.verify("M008", runs=self.runs)
        self.assertEqual(cm.exception.code, "FROZEN_FILE_CHANGED")
        self.assertIn("kernel.py", cm.exception.msg)
        ok, reasons = registry.run_eligibility(run, "M008", runs=self.runs)
        self.assertFalse(ok)
        self.assertIn("FROZEN_FILE_CHANGED", reasons[0])  # no silent window for reports either

    def test_newer_family_freeze_covers_verify_and_report_eligibility(self):
        rec = self._register("M008")
        run = self._manifest(rec)
        self._drift()
        _beat_second()
        self._register("M009")  # captures the current hash: the legitimate re-freeze
        covered = registry.verify("M008", runs=self.runs)
        self.assertEqual(covered["covered_drift_by"], {"kernel.py": "M009 v1"})
        ok, reasons = registry.run_eligibility(run, "M008", runs=self.runs)
        self.assertTrue(ok, reasons)  # completed family's runs stay reportable

    def test_partial_coverage_names_only_the_uncovered(self):
        with open(os.path.join(self.code, "eval.py"), "w") as fh:
            fh.write("eval v1\n")
        self._register("M008", files=("kernel.py", "eval.py"))
        self._drift()
        with open(os.path.join(self.code, "eval.py"), "w") as fh:
            fh.write("eval v2\n")
        _beat_second()
        registry.register("M009", 1, "# b\n", "# p\n", ["kernel.py"], runs=self.runs)
        with self.assertRaises(registry.RegistryError) as cm:
            registry.verify("M008", runs=self.runs)
        self.assertIn("changed since registration: ['eval.py']", cm.exception.msg)
        self.assertIn("already re-frozen by a newer registration", cm.exception.msg)

    def test_older_registration_never_covers(self):
        # Reverting to content an OLDER record happens to hold must stay red:
        # only a freeze newer than the record under check can legitimize drift.
        self._register("M009")  # holds kernel v1, created first
        self._drift("kernel v2\n")
        _beat_second()
        target = self._register("M008")  # holds kernel v2, created later
        self._drift("kernel v1\n")  # revert to what M009 (older) recorded
        with self.assertRaises(registry.RegistryError) as cm:
            registry.verify("M008", runs=self.runs)
        self.assertEqual(cm.exception.code, "FROZEN_FILE_CHANGED")
        self.assertEqual(target["files"]["kernel.py"], registry.sha(b"kernel v2\n"))


class PreregClosedFamilyCoverage(unittest.TestCase):
    def setUp(self):
        self.code, self.runs = _scratch()
        self._saved = (registry.HERE, prereg.HERE, prereg.RUNS)
        registry.HERE = prereg.HERE = self.code
        prereg.RUNS = self.runs
        for name in prereg.FILES:
            if not os.path.exists(os.path.join(self.code, name)):
                with open(os.path.join(self.code, name), "w") as fh:
                    fh.write(f"{name} v1\n")
        body = (
            "# Pre-registration - M007\n"
            "Registered 2026-09-21T00:00:00+00:00 BEFORE any run.\n\n"
            "## Frozen code (sha256)\n"
            + "\n".join(f"- {f}: {prereg.h(f)}" for f in prereg.FILES)
        )
        with open(os.path.join(self.runs, "PREREG_M007.md"), "w") as fh:
            fh.write(body)

    def tearDown(self):
        registry.HERE, prereg.HERE, prereg.RUNS = self._saved
        shutil.rmtree(self.code, ignore_errors=True)
        shutil.rmtree(self.runs, ignore_errors=True)

    def _verify(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                prereg.verify("M007")
        return cm.exception.code, out.getvalue()

    def test_stays_red_without_coverage(self):
        with open(os.path.join(self.code, "kernel.py"), "w") as fh:
            fh.write("kernel v2\n")
        code, out = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("kernel.py: CHANGED since original registration", out)
        self.assertEqual(prereg._mismatches("M007"), ["kernel.py"])  # refreeze guard still bites

    def test_reports_advanced_under_when_covered(self):
        with open(os.path.join(self.code, "kernel.py"), "w") as fh:
            fh.write("kernel v2\n")
        registry.register("M009", 1, "# b\n", "# p\n", ["kernel.py"], runs=self.runs)  # now > 2026-09-21
        code, out = self._verify()
        self.assertEqual(code, 0, out)
        self.assertIn("tree advanced under M009 v1: kernel.py", out)
        self.assertEqual(prereg._mismatches("M007"), [])  # covered drift never forces --refreeze

    def test_uncovered_files_still_mismatch_alongside_covered_ones(self):
        with open(os.path.join(self.code, "kernel.py"), "w") as fh:
            fh.write("kernel v2\n")
        with open(os.path.join(self.code, "driver.py"), "w") as fh:
            fh.write("driver v2\n")
        registry.register("M009", 1, "# b\n", "# p\n", ["kernel.py"], runs=self.runs)
        code, out = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("driver.py: CHANGED", out)
        self.assertNotIn("kernel.py: CHANGED", out)


if __name__ == "__main__":
    unittest.main()
