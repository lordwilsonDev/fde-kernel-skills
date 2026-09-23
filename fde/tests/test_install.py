import os, subprocess, tempfile, shutil, unittest, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sh(*a, cwd=None, env=None):
    return subprocess.run(list(a), capture_output=True, text=True, cwd=cwd, env=env)


@unittest.skipUnless(
    os.path.exists(os.path.join(ROOT, "install.sh")),
    "installer tests only run in the source checkout, not inside an installed workspace",
)
class Install(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.home = tempfile.mkdtemp()
        self.env = dict(os.environ, HOME=self.home)

    def tearDown(self):
        shutil.rmtree(self.t)
        shutil.rmtree(self.home)

    def test_copy_install_is_self_contained_and_runs_its_own_tests(self):
        ws = os.path.join(self.t, "elsewhere", "ws")
        r = sh(os.path.join(ROOT, "install.sh"), ws, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        for f in (
            "fde/kernel.py",
            "fde/simulator.py",
            "fde/vault_sync.py",
            ".claude/settings.json",
            ".claude/skills/fde-mission/SKILL.md",
            "runs",
        ):
            self.assertTrue(os.path.exists(os.path.join(ws, f)), f)
        self.assertFalse(
            os.path.exists(os.path.join(self.home, ".claude"))
        )  # nothing global without --global-skills
        env = dict(self.env, FDE_VAULT=os.path.join(self.t, "vault"))
        t = sh(
            sys.executable,
            "-W",
            "ignore",
            "-m",
            "unittest",
            "discover",
            "-s",
            "fde/tests",
            cwd=ws,
            env=env,
        )
        self.assertEqual(
            t.returncode, 0, t.stderr[-1500:]
        )  # portable: full suite passes from the copy
        self.assertEqual(
            sh(sys.executable, "fde/lint_scenario.py", "M007", cwd=ws).returncode, 0
        )
        self.assertFalse(
            os.path.exists(os.path.join(self.t, "vault"))
            and os.listdir(os.path.join(self.t, "vault"))
        )  # tests wrote nothing to the configured vault

    def test_refuses_to_overwrite_without_force(self):
        ws = os.path.join(self.t, "ws")
        sh(os.path.join(ROOT, "install.sh"), ws, env=self.env)
        r = sh(os.path.join(ROOT, "install.sh"), ws, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stdout)
        self.assertEqual(
            sh(
                os.path.join(ROOT, "install.sh"), ws, "--force", env=self.env
            ).returncode,
            0,
        )

    def test_symlink_mode_points_at_source(self):
        ws = os.path.join(self.t, "ws")
        self.assertEqual(
            sh(
                os.path.join(ROOT, "install.sh"), ws, "--symlink", env=self.env
            ).returncode,
            0,
        )
        self.assertTrue(os.path.islink(os.path.join(ws, "fde")))

    def test_global_skills_only_with_flag_and_only_into_home(self):
        ws = os.path.join(self.t, "ws")
        self.assertEqual(
            sh(
                os.path.join(ROOT, "install.sh"), ws, "--global-skills", env=self.env
            ).returncode,
            0,
        )
        for s in ("fde-kernel", "fde-mission", "fde-eval"):
            self.assertTrue(
                os.path.exists(
                    os.path.join(self.home, ".claude", "skills", s, "SKILL.md")
                ),
                s,
            )
        self.assertFalse(
            os.path.exists(os.path.join(self.home, ".claude", "settings.json"))
        )  # the hook is never installed globally

    def test_no_hardcoded_absolute_paths_in_shipped_code(self):
        bad = subprocess.run(
            "grep -rIln -e '/tmp/fde' -e '/Users/' -e '/private/tmp' fde .claude install.sh README.md AGENTS.md hooks Makefile mypy.ini requirements-dev.txt frozen_format_exemptions.txt .python-version | grep -v '/tests/' || true",
            shell=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(bad, "", bad)


if __name__ == "__main__":
    unittest.main(verbosity=1)
