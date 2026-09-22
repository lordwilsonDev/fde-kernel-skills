"""Failure visibility: an audit or error-log write that fails must never be silent.
Origin: 2026-09-22 engineering audit (driver_m008.py _reject_audit / _log_internal had `except Exception: pass`)."""
import contextlib, io, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import driver_m008 as D8


class RejectAuditFailureIsVisible(unittest.TestCase):
    def test_unwritable_rejected_dir_warns_on_stderr_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = os.path.join(tmp, "M008_test_run")
            os.makedirs(run)
            # A *file* named "rejected" makes os.makedirs(run/rejected) fail.
            open(os.path.join(run, "rejected"), "w").close()
            err = D8.ProtoError("BAD_PROPOSAL", "test rejection")
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                D8._reject_audit(run, os.path.join(run, "proposal_r1.json"), err)
            self.assertIn("rejected-proposal audit write failed", buf.getvalue())
            log = os.path.join(tmp, ".driver_errors.log")
            self.assertTrue(os.path.exists(log), "failure must also land in .driver_errors.log")

    def test_unwritable_error_log_falls_back_to_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = os.path.join(tmp, "M008_test_run")
            os.makedirs(run)
            # A *directory* named .driver_errors.log makes open(..., "a") fail.
            os.makedirs(os.path.join(tmp, ".driver_errors.log"))
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                D8._log_internal(run, ValueError("original boom"))
            self.assertIn("could not write .driver_errors.log", buf.getvalue())
            self.assertIn("original boom", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
