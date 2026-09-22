import sys, os, json, tempfile, shutil, glob
FDE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, FDE)
import unittest, config, driver, kernel as K, vault_sync as V

class Vault(unittest.TestCase):
    def setUp(self):
        self.v = tempfile.mkdtemp(); self.real = (config.VAULT, config.EXP_DIR, config.LESSONS_DIR)
        config.VAULT = self.v; config.EXP_DIR = os.path.join(self.v, "50_Experiments", "FDE-Kernel"); config.LESSONS_DIR = os.path.join(self.v, "40_Memory", "FDE-Lessons")
    def tearDown(self):
        config.VAULT, config.EXP_DIR, config.LESSONS_DIR = self.real; shutil.rmtree(self.v)
    def run_dir(self, world="M005", mode="kernel", name="M005_haiku_kernel_t", finish=True):
        d = os.path.join(tempfile.mkdtemp(), name); driver.init(d, world, mode)
        if finish:
            p = d + "/p0.json"; json.dump({"claims": [{"claim_id": "C1", "statement": "s", "kind": "observation", "status": "established", "sources": ["m5_e09"]}], "next_action": {"action": "none", "kind": "final_assessment"}}, open(p, "w")); driver.apply(d, p)
        return d
    def test_tests_never_touch_the_real_vault(self):
        self.assertTrue(config.LESSONS_DIR.startswith(self.v)); self.assertNotEqual(config.VAULT, self.real[0])
    def test_lessons_round_trip_through_the_vault(self):
        import seed_lessons; db = os.path.join(tempfile.mkdtemp(), "seed.db"); seed_lessons.seed(db)
        pushed = V.lessons_push_from_db(db) if hasattr(V, "lessons_push_from_db") else None
        run = tempfile.mkdtemp() + "/seedrun"; os.makedirs(run); shutil.copy(db, run + "/state.db"); json.dump({"world": "M005", "mode": "kernel", "enforce": True, "round": 0, "done": False, "denials": [], "log": []}, open(run + "/run.json", "w"))
        out = V.lessons_push(run); self.assertTrue(all(r == "created" for _, r in out), out)
        self.assertEqual(len(glob.glob(config.LESSONS_DIR + "/*.md")), 3); self.assertGreaterEqual(len(glob.glob(config.LESSONS_DIR + "/gaps/*.md")), 2); self.assertGreaterEqual(len(glob.glob(config.LESSONS_DIR + "/regressions/*.md")), 2)
        rebuilt = os.path.join(tempfile.mkdtemp(), "rebuilt.db"); n = V.lessons_build(rebuilt); self.assertEqual(n["lessons"], 3); self.assertEqual(n["regressions"], 2)
        k = K.Kernel(rebuilt); self.assertEqual({r["transferable"] for r in k.c.execute("SELECT transferable FROM lessons")}, {"structure", "none"})
    def test_non_transferable_lesson_survives_the_vault_but_not_the_next_mission(self):
        import seed_lessons; db = os.path.join(tempfile.mkdtemp(), "s.db"); seed_lessons.seed(db); run = tempfile.mkdtemp() + "/r"; os.makedirs(run); shutil.copy(db, run + "/state.db"); json.dump({"world": "M005", "mode": "kernel", "enforce": True, "round": 0, "done": False, "denials": [], "log": []}, open(run + "/run.json", "w")); V.lessons_push(run)
        rebuilt = os.path.join(tempfile.mkdtemp(), "b.db"); V.lessons_build(rebuilt); nxt = os.path.join(tempfile.mkdtemp(), "next"); driver.init(nxt, "M005", "kernel", lessons=True, src_db=rebuilt)
        ids = {l["lesson_id"] for l in json.load(open(nxt + "/ctx_r0.json"))["prior_mission_lessons"]}; self.assertEqual(ids, {"L_M003_1", "L_M003_2"})   # the adapter-specific lesson never leaves M003
    def test_push_never_overwrites_a_human_note(self):
        import seed_lessons; db = os.path.join(tempfile.mkdtemp(), "s.db"); seed_lessons.seed(db); run = tempfile.mkdtemp() + "/r"; os.makedirs(run); shutil.copy(db, run + "/state.db"); json.dump({"world": "M005", "mode": "kernel", "enforce": True, "round": 0, "done": False, "denials": [], "log": []}, open(run + "/run.json", "w"))
        os.makedirs(config.LESSONS_DIR); mine = os.path.join(config.LESSONS_DIR, "L_M003_1.md"); open(mine, "w").write("---\nid: L_M003_1\ntype: fde-lesson\n---\nMY EDIT\n")
        out = dict(V.lessons_push(run)); self.assertIn("skipped", out["L_M003_1"]); self.assertEqual(open(mine).read().count("MY EDIT"), 1)
        again = dict(V.lessons_push(run)); self.assertTrue(all("skipped" in r for r in again.values()))          # push is create-only
    def test_export_run_and_world(self):
        d = self.run_dir(); r = V.export_run(d); self.assertEqual(r, "created"); p = glob.glob(config.EXP_DIR + "/M005/runs/*.md")[0]; s = open(p).read()
        self.assertIn("fde_generated: true", s); self.assertIn("root_cause_correct_and_supported", s); self.assertIn("status: complete", s)
        self.assertEqual(V.export_run(d), "updated")                                                              # generated notes may be refreshed
        parent = os.path.dirname(d); self.assertIn(V.export_world("M005", parent), ("created", "updated")); self.assertIn("| arm |", open(config.EXP_DIR + "/M005/README.md").read())
    def test_unfinished_run_is_refused_and_writes_nothing(self):
        d = self.run_dir(name="M005_haiku_raw_z", mode="raw", finish=False)
        with self.assertRaises(V.RunNotFinished): V.export_run(d)
        self.assertEqual(glob.glob(self.v + "/**/*.md", recursive=True), [])
        st = V.status(); self.assertEqual(st["run_notes"], 0); self.assertTrue(st["vault_exists"])
    def test_cli_unfinished_run_json_error_nonzero_no_file(self):
        import subprocess
        d = self.run_dir(name="M005_haiku_raw_z", mode="raw", finish=False); vault = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, "-W", "ignore", os.path.join(FDE, "vault_sync.py"), "export", "run", d], capture_output=True, text=True, env=dict(os.environ, FDE_VAULT=vault))
        self.assertEqual(r.returncode, 3); self.assertNotIn("Traceback", r.stderr); lines = r.stdout.strip().splitlines(); self.assertEqual(len(lines), 1)
        o = json.loads(lines[0]); self.assertIs(o["ok"], False); self.assertEqual(o["error_code"], "RUN_NOT_FINISHED"); self.assertTrue(o["message"])
        self.assertEqual([f for _, _, fs in os.walk(vault) for f in fs], []); shutil.rmtree(vault)
if __name__ == "__main__": unittest.main(verbosity=1)
