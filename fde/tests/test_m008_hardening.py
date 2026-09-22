"""Pre-run qualification of the M008 control system (driver, guard, registry, report). Test names state the contract.
Origin: the 2026-09-21 bug hunt (vault 50_Experiments/FDE-Kernel/M008/preflight/). Nothing here launches a model."""
import sys, os, json, re, copy, random, shutil, hashlib, sqlite3, subprocess, tempfile, threading
HERE = os.path.dirname(os.path.abspath(__file__)); FDE = os.path.dirname(HERE); ROOT = os.path.dirname(FDE)
sys.path.insert(0, FDE)
import unittest, driver, driver_m008 as D8, registry, simulator as S

DECOY, OFFSETS = "audit_allocation_exceptions", "read_partition_offsets"
GUARD = os.path.join(FDE, "blind_guard.py"); DRV = os.path.join(FDE, "driver_m008.py")
NA = lambda a, k="diagnostic": {"next_action": {"action": a, "kind": k}}
VALID = NA(DECOY)


def fingerprint(run, ignore=()):
    out = {}
    for dp, dn, fn in os.walk(run):
        dn[:] = [x for x in dn if x != "rejected"]
        for f in fn:
            if f == ".apply.lock" or f in ignore or f.endswith(".tmp"): continue
            p = os.path.join(dp, f); rel = os.path.relpath(p, run)
            if f == "state.db":
                c = sqlite3.connect(f"file:{p}?mode=ro", uri=True); out[rel] = hashlib.sha256("\n".join(c.iterdump()).encode()).hexdigest(); c.close()
            else: out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out

def newrun(mode="kernel"):
    base = tempfile.mkdtemp(); d = os.path.join(base, "M008_haiku_kernel_a"); D8.init(d, "M008", mode); return d, base

def prop(base, obj, name="p.json", raw=None):
    p = os.path.join(base, name)
    with open(p, "wb") as f: f.write(raw if raw is not None else json.dumps(obj).encode())
    return p

def cli(*a, cwd=None): return subprocess.run([sys.executable, "-W", "ignore", DRV, *a], capture_output=True, text=True, cwd=cwd or ROOT)


class InitContract(unittest.TestCase):
    def test_init_rejects_unknown_mode_without_creating_run(self):
        base = tempfile.mkdtemp(); d = base + "/M008_haiku_kernel_a"
        with self.assertRaises(D8.ProtoError) as c: D8.init(d, "M008", "bogus")
        self.assertEqual(c.exception.code, "BAD_MODE"); self.assertFalse(os.path.exists(d))
        for bad in ("rules-only", "Kernel", "", None):
            with self.assertRaises(D8.ProtoError): D8.init(d, "M008", bad)
        self.assertFalse(os.path.exists(d))
    def test_init_rejects_unknown_world_without_creating_run(self):
        base = tempfile.mkdtemp(); d = base + "/r"
        for w in ("M999", "M007", "", None, "../M008"):
            with self.assertRaises(D8.ProtoError) as c: D8.init(d, w, "kernel")
            self.assertEqual(c.exception.code, "UNKNOWN_WORLD"); self.assertFalse(os.path.exists(d))
    def test_init_rejects_existing_run_without_mutating_existing_state(self):
        d, base = newrun()
        for i in range(2): D8.apply(d, prop(base, VALID, f"a{i}.json"))
        before = fingerprint(d)
        for mode in ("kernel", "raw", "rules"):
            with self.assertRaises(D8.ProtoError) as c: D8.init(d, "M008", mode)
            self.assertEqual(c.exception.code, "RUN_EXISTS")
        self.assertEqual(fingerprint(d), before)
    def test_init_validates_all_arguments_before_creating_files(self):
        base = tempfile.mkdtemp()
        for name in ("my run", "run.1", "ré", "a" * 81, "../x", ""):
            with self.assertRaises(D8.ProtoError):
                D8.init(os.path.join(base, name) if name else "", "M008", "kernel")
        self.assertEqual(os.listdir(base), [])
        r = cli("init", base + "/x", "M008"); self.assertEqual(r.returncode, 2); self.assertEqual(json.loads(r.stdout)["error_code"], "USAGE"); self.assertFalse(os.path.exists(base + "/x"))
        r = cli("init", base + "/x", "M008", "kernel", "extra"); self.assertEqual(r.returncode, 2); self.assertFalse(os.path.exists(base + "/x"))
        r = cli("init", base + "/x", "M008", "bogus"); self.assertEqual(r.returncode, 2); self.assertEqual(json.loads(r.stdout)["error_code"], "BAD_MODE")
    def test_init_cleans_up_after_a_failure(self):
        base = tempfile.mkdtemp(); d = base + "/r"; real = D8.D.init
        def boom(run, world, mode, **k): os.makedirs(run); raise RuntimeError("x")
        D8.D.init = boom
        try:
            with self.assertRaises(RuntimeError): D8.init(d, "M008", "kernel")
        finally: D8.D.init = real
        self.assertFalse(os.path.exists(d))
    def test_scored_init_needs_an_active_registration_and_a_registered_arm_name(self):
        base = tempfile.mkdtemp(); old = registry.config.RUNS; registry.config.RUNS = tempfile.mkdtemp()   # isolate from any real registration (M008 v2 may be ACTIVE in this repo)
        try:
            with self.assertRaises(D8.ProtoError) as c: D8.init(base + "/M008_haiku_kernel_a", "M008", "kernel", run_kind="scored")
            self.assertEqual(c.exception.code, "NO_ACTIVE_REGISTRATION"); self.assertFalse(os.path.exists(base + "/M008_haiku_kernel_a"))
        finally: registry.config.RUNS = old


class ProposalRejection(unittest.TestCase):
    """Every rejection: structured error, non-zero exit, and NO state change."""
    def reject(self, obj=None, raw=None, code="INVALID_PROPOSAL", where=None):
        d, base = newrun(); D8.apply(d, prop(base, VALID, "warm.json")); before = fingerprint(d)
        p = prop(base, obj, raw=raw)
        with self.assertRaises(D8.ProtoError) as c: D8.apply(d, p)
        self.assertEqual(c.exception.code, code, (obj, raw)); self.assertEqual(fingerprint(d), before, (obj, raw))
        st = json.load(open(d + "/run.json")); self.assertEqual(st["round"], 1)
        r = cli("apply", d, p); self.assertEqual(r.returncode, 2); out = json.loads(r.stdout); self.assertFalse(out["ok"]); self.assertNotIn("Traceback", r.stdout + r.stderr); self.assertEqual(fingerprint(d), before)
        if where: self.assertEqual(c.exception.path, where)
    def test_apply_rejects_empty_file_without_state_change(self): self.reject(raw=b"")
    def test_apply_rejects_invalid_utf8_without_state_change(self): self.reject(raw=b"\xff\xfe{\x00")
    def test_apply_rejects_binary_without_state_change(self): self.reject(raw=os.urandom(2048))
    def test_apply_rejects_invalid_json_without_state_change(self): self.reject(raw=b'{"next_action": ')
    def test_apply_rejects_non_object_json_without_state_change(self):
        for raw in (b"[1,2]", b"null", b'"hi"', b"5", b"true"): self.reject(raw=raw, where="$")
    def test_apply_rejects_deeply_nested_json_without_state_change(self): self.reject(raw=b"[" * 100000 + b"]" * 100000)
    def test_apply_rejects_missing_next_action_without_state_change(self): self.reject({"claims": []}, where="$.next_action")
    def test_apply_rejects_non_object_next_action_without_state_change(self):
        for v in ("x", ["x"], None, 5): self.reject({"next_action": v}, where="$.next_action")
    def test_apply_rejects_invalid_action_type_without_state_change(self):
        for v in (["a"], 7, None, {"a": 1}): self.reject({"next_action": {"action": v, "kind": "diagnostic"}})
    def test_apply_rejects_invalid_kind_type_without_state_change(self):
        for v in (7, ["diagnostic"], "bogus", None): self.reject({"next_action": {"action": DECOY, "kind": v}}, where="$.next_action.kind")
    def test_apply_rejects_several_actions_in_one_string(self):
        self.reject({"next_action": {"action": f"{DECOY},{OFFSETS}", "kind": "diagnostic"}}); self.reject({"next_action": {"action": f"{DECOY} {OFFSETS}", "kind": "diagnostic"}})
    def test_apply_rejects_actions_outside_the_authority_list(self): self.reject({"next_action": {"action": "format_disk", "kind": "mitigation"}})
    def test_apply_rejects_incompatible_action_kind_pairing(self):
        self.reject({"next_action": {"action": DECOY, "kind": "mitigation"}}); self.reject({"next_action": {"action": "apply_slot_correction", "kind": "diagnostic"}}); self.reject({"next_action": {"action": DECOY, "kind": "final_assessment"}})
    def test_apply_rejects_non_list_claims_without_state_change(self):
        for v in ("abc", {"a": 1}, 5, None): self.reject({"claims": v, **VALID}, where="$.claims")
    def test_apply_rejects_non_object_claim_entries_without_state_change(self):
        for v in ([1], ["x"], [None], [[]]): self.reject({"claims": v, **VALID})
    def test_apply_rejects_oversized_proposal_without_state_change(self):
        self.reject(raw=json.dumps({**VALID, "notes": "x" * 300000}).encode(), code="PROPOSAL_TOO_LARGE")
        self.reject({**VALID, "notes": "x" * 5000}); self.reject({"claims": [{"claim_id": f"C{i}", "kind": "hypothesis"} for i in range(33)], **VALID})
    def test_apply_rejects_unknown_top_level_fields(self): self.reject({**VALID, "final_assessment": {"x": 1}})
    def test_apply_rejects_missing_proposal_file_without_state_change(self):
        d, base = newrun(); before = fingerprint(d)
        with self.assertRaises(D8.ProtoError) as c: D8.apply(d, base + "/nope.json")
        self.assertEqual(c.exception.code, "PROPOSAL_NOT_FOUND"); self.assertEqual(fingerprint(d), before)
    def test_apply_reports_structured_error_without_traceback_for_bad_cli_use(self):
        base = tempfile.mkdtemp()
        for args in (("apply",), ("apply", base + "/missing", base + "/p.json"), ("status", base + "/missing"), ("score", base + "/missing"), ("bogus",), ()):
            r = cli(*args); self.assertNotEqual(r.returncode, 0, args); self.assertNotIn("Traceback", r.stdout + r.stderr, args); self.assertFalse(json.loads(r.stdout)["ok"])
    def test_rejected_proposal_inside_the_run_is_kept_for_audit_and_its_filename_is_freed(self):
        d, base = newrun(); p = d + "/proposal_r0.json"; json.dump({"claims": "abc", **VALID}, open(p, "w"))
        with self.assertRaises(D8.ProtoError): D8.apply(d, p)
        self.assertFalse(os.path.exists(p)); self.assertEqual(len([f for f in os.listdir(d + "/rejected") if f.endswith(".json") and f != "log.jsonl"]), 1)
        json.dump(VALID, open(p, "w")); D8.apply(d, p); self.assertEqual(json.load(open(d + "/run.json"))["round"], 1)


class EvidenceAndClaims(unittest.TestCase):
    def claim(self, **kw): return dict({"claim_id": "C1", "statement": "s", "kind": "hypothesis", "status": "hypothesized", "sources": [], "limitation": "l"}, **kw)
    def reject(self, claims, code="INVALID_PROPOSAL"):
        d, base = newrun(); before = fingerprint(d)
        with self.assertRaises(D8.ProtoError) as c: D8.apply(d, prop(base, {"claims": claims, **VALID}))
        self.assertEqual(c.exception.code, code); self.assertEqual(fingerprint(d), before)
    def test_claim_rejects_unknown_artifact_id(self): self.reject([self.claim(kind="root_cause", status="inferred", mechanism_tag="carrier_feed_lag", sources=["ghost_1", "ghost_2"])], "UNKNOWN_SOURCE")
    def test_root_cause_claim_rejects_empty_sources(self):
        for k in ("root_cause", "inference", "impact", "observation"): self.reject([self.claim(kind=k, status="inferred", sources=[])])
    def test_claim_rejects_duplicate_source_ids(self): self.reject([self.claim(kind="observation", sources=["m8_e01", "m8_e01"])])
    def test_claim_rejects_too_many_sources(self): self.reject([self.claim(kind="observation", sources=[f"m8_e{i:02d}" for i in range(1, 10)])])
    def test_claim_rejects_unreleased_artifact(self): self.reject([self.claim(kind="observation", sources=["m8_r_offsets"])], "UNKNOWN_SOURCE")
    def test_claim_rejects_invalid_kind_status_and_tag(self):
        self.reject([self.claim(kind="rumour")]); self.reject([self.claim(status="certain")]); self.reject([self.claim(mechanism_tag="aliens")]); self.reject([self.claim(claim_id="bad id")]); self.reject([self.claim(statement=5)])
    def test_duplicate_claim_id_in_one_proposal_is_rejected_atomically(self): self.reject([self.claim(), self.claim(statement="other")])
    def test_a_released_artifact_becomes_citable(self):
        d, base = newrun(); D8.apply(d, prop(base, VALID, "a.json"))
        D8.apply(d, prop(base, {"claims": [self.claim(kind="observation", sources=["m8_r_exceptions"])], **NA("review_rule_history")}, "b.json")); k, _ = driver.load(d)
        self.assertEqual([r[0] for r in k.c.execute("SELECT artifact_id FROM claim_sources")], ["m8_r_exceptions"])
    def test_claim_id_reuse_across_rounds_is_the_kernel_revision_protocol_and_stays_audited(self):
        d, base = newrun(); D8.apply(d, prop(base, {"claims": [self.claim(statement="first")], **VALID}, "a.json"))
        D8.apply(d, prop(base, {"claims": [self.claim(statement="second")], **NA("check_dock_capacity")}, "b.json")); k, _ = driver.load(d)
        self.assertGreaterEqual(k.c.execute("SELECT COUNT(*) FROM claim_status_transitions WHERE claim_id='C1'").fetchone()[0], 2)     # both submissions are in the audit trail
    def test_dispositions_must_name_known_claims(self): self.reject_disp = None; d, base = newrun(); \
        self.assertRaises(D8.ProtoError, D8.apply, d, prop(base, {"dispositions": [{"claim_id": "ghost", "action": "preserve"}], **VALID}))


class Lifecycle(unittest.TestCase):
    def test_apply_rejects_completed_run_without_state_change(self):
        d, base = newrun()
        D8.apply(d, prop(base, {"next_action": {"action": "none", "kind": "final_assessment"}}, "f.json")); self.assertTrue(json.load(open(d + "/run.json"))["done"]); before = fingerprint(d)
        with self.assertRaises(D8.ProtoError) as c: D8.apply(d, prop(base, VALID, "x.json"))
        self.assertEqual(c.exception.code, "RUN_COMPLETE"); self.assertEqual(fingerprint(d), before); self.assertIsNone(D8.status(d)["next_context"])
    def test_round_cap_yields_one_terminal_semantic(self):
        d, base = newrun()
        for i in range(9): D8.apply(d, prop(base, NA("check_dock_capacity"), f"{i}.json"))
        st = json.load(open(d + "/run.json")); self.assertEqual((st["round"], st["done"]), (9, True)); self.assertFalse(os.path.exists(d + "/ctx_r9.json")); before = fingerprint(d)
        for i in range(5):
            with self.assertRaises(D8.ProtoError) as c: D8.apply(d, prop(base, VALID, f"y{i}.json"))
            self.assertEqual(c.exception.code, "RUN_COMPLETE")
        k, _ = driver.load(d); self.assertEqual(k.c.execute("SELECT COUNT(*) FROM scenario_actions").fetchone()[0], 9); self.assertEqual(fingerprint(d), before)
    def test_apply_exception_rolls_back_database_and_manifest(self):
        d, base = newrun(); D8.apply(d, prop(base, VALID, "a.json")); before = fingerprint(d); real = D8.D.apply
        def half(run, path):
            real(run, path); k, _ = driver.load(run); k.c.execute("INSERT INTO gaps(mission_id,capability,reason,layer,status) VALUES('M008','x','y','L5','open')"); k.c.commit(); raise RuntimeError("secret internals")
        D8.D.apply = half
        try:
            with self.assertRaises(D8.ProtoError) as c: D8.apply(d, prop(base, NA("check_dock_capacity"), "b.json"))
        finally: D8.D.apply = real
        self.assertEqual(c.exception.code, "INTERNAL_ERROR"); self.assertNotIn("secret", json.dumps(c.exception.as_dict())); self.assertEqual(fingerprint(d), before)
        D8.apply(d, prop(base, NA("check_dock_capacity"), "c.json")); self.assertEqual(json.load(open(d + "/run.json"))["round"], 2)      # and the run is still usable
    def test_repeated_diagnostic_has_explicit_idempotency_behavior(self):
        """Documented decision: allowed, idempotent (same artifact), costs a round."""
        d, base = newrun()
        for i in range(2): D8.apply(d, prop(base, NA("check_dock_capacity"), f"{i}.json"))
        k, _ = driver.load(d); self.assertEqual([r[0] for r in k.c.execute("SELECT result FROM scenario_actions")], ["m8_r_dock", "m8_r_dock"]); self.assertEqual(json.load(open(d + "/run.json"))["round"], 2)
    def test_run_json_is_never_half_written(self):
        d, base = newrun(); stop = threading.Event(); bad = []
        def reader():
            while not stop.is_set():
                try: json.load(open(d + "/run.json"))
                except Exception as e: bad.append(repr(e))
        t = threading.Thread(target=reader); t.start()
        try:
            for i in range(9): D8.apply(d, prop(base, NA("check_dock_capacity"), f"{i}.json"))
        finally: stop.set(); t.join()
        self.assertEqual(bad, [])


class Concurrency(unittest.TestCase):
    def test_concurrent_apply_serializes_to_unique_rounds(self):
        for trial in range(3):
            d, base = newrun(); p = prop(base, NA("check_dock_capacity")); procs = [subprocess.Popen([sys.executable, "-W", "ignore", DRV, "apply", d, p], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(6)]
            outs = [(x.communicate(), x.returncode) for x in procs]
            for (o, e), rc in outs: self.assertEqual(rc, 0, o + e); self.assertNotIn("Traceback", o + e)
            st = json.load(open(d + "/run.json")); self.assertEqual(st["round"], 6); self.assertEqual(len(st["log"]), 6); self.assertEqual([x["round"] for x in st["log"]], list(range(6)))
            k, _ = driver.load(d); self.assertEqual([r[0] for r in k.c.execute("SELECT round FROM scenario_actions ORDER BY rowid")], list(range(6)))
    def test_concurrent_apply_never_duplicates_scenario_action_round(self):
        d, base = newrun(); p = prop(base, NA("check_dock_capacity")); errs = []
        def go():
            try: D8.apply(d, p)
            except D8.ProtoError as e: errs.append(e.code)
        ts = [threading.Thread(target=go) for _ in range(8)]; [t.start() for t in ts]; [t.join() for t in ts]
        k, _ = driver.load(d); rounds = [r[0] for r in k.c.execute("SELECT round FROM scenario_actions")]
        self.assertEqual(len(rounds), len(set(rounds))); self.assertEqual(len(rounds), json.load(open(d + "/run.json"))["round"])
    def test_status_during_apply_sees_a_consistent_round(self):
        d, base = newrun(); p = prop(base, NA("check_dock_capacity")); procs = [subprocess.Popen([sys.executable, "-W", "ignore", DRV, "apply", d, p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(3)]
        rs = [cli("status", d) for _ in range(6)]; [x.wait() for x in procs]
        for r in rs: self.assertEqual(r.returncode, 0, r.stdout); self.assertNotIn("Traceback", r.stdout + r.stderr)


class Fuzz(unittest.TestCase):
    POOL: list = [None, 1, -1, 10 ** 12, True, "x", "", "a,b", "é日", "x" * 5000, [], [1], [None], {}, {"a": 1}, [[]], "M008", "diagnostic", "inferred"]
    def mutate(self, o, rng):
        o = copy.deepcopy(o); nodes = []
        def walk(x, path):
            nodes.append(path)
            if isinstance(x, dict): [walk(v, path + [k]) for k, v in x.items()]
            elif isinstance(x, list): [walk(v, path + [i]) for i, v in enumerate(x)]
        walk(o, []); path = rng.choice(nodes)
        if not path: return rng.choice(self.POOL)
        cur = o
        for k in path[:-1]: cur = cur[k]
        if rng.random() < 0.3 and isinstance(cur, dict): del cur[path[-1]]
        else: cur[path[-1]] = rng.choice(self.POOL)
        return o
    def test_any_proposal_either_advances_exactly_one_round_or_changes_nothing(self):
        rng = random.Random(20260921); base_prop = {"claims": [{"claim_id": "C1", "statement": "s", "kind": "observation", "status": "inferred", "sources": ["m8_e01"], "mechanism_tag": "unknown", "limitation": "l"}],
                                                   "dispositions": [{"claim_id": "C1", "action": "preserve"}], "notes": "n", **VALID}
        d, base = newrun(); n_ok = n_rej = 0
        for i in range(400):
            st = json.load(open(d + "/run.json"))
            if st["done"]: d, base = newrun()
            obj = base_prop
            for _ in range(rng.choice([1, 1, 2, 3])): obj = self.mutate(obj, rng)
            p = prop(base, obj, "f.json", raw=(json.dumps(obj).encode() if rng.random() < 0.97 else os.urandom(rng.randrange(0, 64)))); before = fingerprint(d); r0 = json.load(open(d + "/run.json"))["round"]
            try: D8.apply(d, p); ok = True
            except D8.ProtoError as e:
                ok = False; self.assertIn(e.exit_code, (2, 3)); self.assertEqual(fingerprint(d), before, (i, obj))
            r1 = json.load(open(d + "/run.json"))["round"]; self.assertEqual(r1, r0 + (1 if ok else 0), (i, obj)); n_ok += ok; n_rej += (not ok)
        self.assertGreater(n_ok, 10); self.assertGreater(n_rej, 100)


class TruthSeparation(unittest.TestCase):
    def test_public_world_module_holds_no_answer_key(self):
        r = subprocess.run([sys.executable, "-W", "ignore", "-c", "import sys; sys.path.insert(0, %r); import simulator_m008, simulator as S; w = S.WORLDS['M008']; print('truth' in w, 'prerequisites' in w)" % FDE], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "False False", r.stderr)      # fresh process: earlier tests in this process legitimately attach the key on the orchestrator side
        src = open(os.path.join(FDE, "simulator_m008.py")).read()
        for needle in ("decoy", "truth", "best_mitigation", "root_cause_tag", "requires_decoy", "false_tag", "answer key"): self.assertFalse(needle in src.lower(), needle)
    def test_arm_facing_paths_never_load_the_private_evaluator(self):
        d, base = newrun(); p = prop(base, VALID)
        code = ("import sys; sys.path.insert(0, %r); import driver_m008 as D, simulator as S; D.apply(%r, %r); D.status(%r); "
                "print(sorted(m for m in sys.modules if 'evaluator' in m), 'truth' in S.WORLDS['M008'], 'prerequisites' in S.WORLDS['M008'])") % (FDE, d, p, d)
        r = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stdout.strip(), "[] False False")
        r = cli("status", d); self.assertNotIn("carrier_feed_lag", r.stdout.replace('"vocab', "")); self.assertNotIn("EXC-0921", r.stdout)
    def test_answer_literals_are_absent_from_arm_facing_source(self):
        for f in ("blind_guard.py", "driver_m008.py", "simulator_m008.py", "registry.py"):
            src = open(os.path.join(FDE, f)).read(); self.assertNotIn("m8_r_offsets_wait_answer", src)
            for lit in ("root_cause_tag", "best_mitigation", "decoy_diagnostics", "followup_mitigation", "decoy"): self.assertFalse(lit in src.lower(), (f, lit))
    def test_scorer_and_linter_do_load_the_key_on_the_orchestrator_side(self):
        d, base = newrun(); D8.apply(d, prop(base, VALID)); s = D8.score(d); self.assertIn("scorer_m008", sys.modules); self.assertTrue(s["decoy_diagnostic_executed"]); self.assertIn("truth", S.WORLDS["M008"])


# ------------------------------------------------------------------ the blind guard, as capability authorization
class Proj:
    def __init__(self, run="M008_haiku_kernel_a", rnd=3, marker=None):
        self.root = os.path.realpath(tempfile.mkdtemp()); self.run = run; self.rnd = rnd
        os.makedirs(f"{self.root}/runs/{run}"); json.dump({"round": rnd, "done": False, "world": "M008", "mode": "kernel", "log": []}, open(f"{self.root}/runs/{run}/run.json", "w"))
        for n in (f"ctx_r{rnd}.json", f"ctx_r{rnd - 1}.json", "state.db"): open(f"{self.root}/runs/{run}/{n}", "w").write("{}")
        os.makedirs(f"{self.root}/runs/M008_haiku_raw_a"); open(f"{self.root}/runs/M008_haiku_raw_a/ctx_r3.json", "w").write("{}"); open(f"{self.root}/runs/M008_haiku_raw_a/proposal_r3.json", "w").write("{}")
        os.makedirs(f"{self.root}/fde"); open(f"{self.root}/fde/simulator_m008.py", "w").write("x"); os.makedirs(f"{self.root}/docs")
        open(f"{self.root}/.fde_blind", "w").write(marker if marker is not None else f"blind\nrun={run}\n")
    def call(self, tool, inp, raw=None, cwd=None):
        payload = raw if raw is not None else json.dumps(dict({"tool_name": tool, "tool_input": inp}, **({"cwd": cwd} if cwd else {})))
        return subprocess.run([sys.executable, GUARD], input=payload, capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=self.root)).returncode

class BlindGuard(unittest.TestCase):
    def setUp(self): self.p = Proj(); self.R = "runs/M008_haiku_kernel_a"
    def ok(self, tool, inp, **k): self.assertEqual(self.p.call(tool, inp, **k), 0, (tool, inp))
    def no(self, tool, inp, **k): self.assertEqual(self.p.call(tool, inp, **k), 2, (tool, inp))
    def test_the_arm_can_do_its_job(self):
        r = self.R; self.ok("Read", {"file_path": f"{r}/ctx_r3.json"}); self.ok("Read", {"file_path": f"{self.p.root}/{r}/ctx_r3.json"}); self.ok("Write", {"file_path": f"{r}/proposal_r3.json", "content": "{}"})
        self.ok("Write", {"file_path": f"{self.p.root}/{r}/proposal_r3.json", "content": "{}"}); self.ok("Skill", {"skill": "fde-mission"})
        for py in ("python3 ", "python3 -W ignore "):
            self.ok("Bash", {"command": f"{py}fde/driver_m008.py status {r}"}); self.ok("Bash", {"command": f"{py}fde/driver_m008.py apply {r} {r}/proposal_r3.json"}, cwd=self.p.root)
    def test_blind_agent_cannot_read_private_truth_or_source(self):
        for f in ("fde/simulator_m008.py", "fde/evaluator_m008.py", "fde/driver_m008.py", "fde/kernel.py", "docs/x.md", "README.md", ".claude/settings.json", "runs/PREREG_M008.md", "runs/registrations/M008/v2/PREREG.md", ".fde_blind"):
            self.no("Read", {"file_path": f}); self.no("Read", {"file_path": f"{self.p.root}/{f}"})
        self.no("Read", {"file_path": f"{os.path.expanduser('~')}/Documents/Vault/50_Experiments/FDE-Kernel/M007/M007-checkpoint-finding-2026-09-21.md"})
    def test_blind_agent_cannot_read_other_arm_context_or_proposal(self):
        for f in ("ctx_r3.json", "proposal_r3.json"): self.no("Read", {"file_path": f"runs/M008_haiku_raw_a/{f}"}); self.no("Read", {"file_path": f"{self.p.root}/runs/M008_haiku_raw_a/{f}"})
        self.no("Write", {"file_path": "runs/M008_haiku_raw_a/proposal_r3.json", "content": "x"})
    def test_blind_agent_cannot_read_own_state_or_stale_rounds(self):
        for f in ("run.json", "state.db", "ctx_r2.json", "ctx_r4.json", "proposal_r2.json", "run_manifest.json", "rejected/log.jsonl"): self.no("Read", {"file_path": f"{self.R}/{f}"})
    def test_path_authorization_is_canonical_not_a_suffix_match(self):
        r = self.R; other = Proj(); evil = tempfile.mkdtemp()
        for path in (f"/tmp/evil/{r}/ctx_r3.json", f"{evil}/{r}/ctx_r3.json", f"{other.root}/{r}/ctx_r3.json", f"{r}/ctx_r3.json\n", f"{r}/ctx_r٣.json", f"{r}/../M008_haiku_raw_a/ctx_r3.json", f"runs/OTHER/{r}/ctx_r3.json",
                     f"~/{r}/ctx_r3.json", f"{r}/ctx_r3.json\x00", f"{r}//..//ctx_r3.json", "", f"file://{self.p.root}/{r}/ctx_r3.json", f"{r}/ctx_r3.json ", f"{r}/nested/ctx_r3.json"):
            self.no("Read", {"file_path": path})
        os.symlink("/etc/hosts", f"{self.p.root}/{r}/proposal_r3.json"); self.no("Read", {"file_path": f"{r}/proposal_r3.json"})
        os.remove(f"{self.p.root}/{r}/proposal_r3.json"); os.symlink(f"{self.p.root}/{r}/ctx_r3.json", f"{self.p.root}/{r}/proposal_r3.json"); self.no("Read", {"file_path": f"{r}/proposal_r3.json"})
        for bad in (5, None, ["x"], {"a": 1}): self.no("Read", {"file_path": bad})
    def test_proposals_are_create_once_for_the_current_round_only(self):
        r = self.R; self.ok("Write", {"file_path": f"{r}/proposal_r3.json", "content": "{}"}); open(f"{self.p.root}/{r}/proposal_r3.json", "w").write("{}")
        self.no("Write", {"file_path": f"{r}/proposal_r3.json", "content": "again"}); self.no("Edit", {"file_path": f"{r}/proposal_r3.json"})
        for f in ("proposal_r4.json", "proposal_r2.json", "ctx_r3.json", "run.json", "x.json", "proposal_r3.json.bak", "../proposal_r3.json"): self.no("Write", {"file_path": f"{r}/{f}", "content": "x"})
        for f in ("fde/kernel.py", "runs/PREREG_M008.md", ".claude/settings.json", "notes.md", "/tmp/x.json"): self.no("Write", {"file_path": f, "content": "x"})
        self.no("NotebookEdit", {"notebook_path": f"{r}/proposal_r3.json"})
    def test_bash_is_four_literal_strings_and_nothing_else(self):
        r = self.R; base = f"fde/driver_m008.py apply {r} {r}/proposal_r3.json"
        for c in (f"python3.12 {base}", f"python3 {base}\r", f"python3 {base}\n", f"python3 {base}", f"python3\t{base}", f"python3  {base}", f"python3 {base} ", f"python3 {base} | cat", f"python3 {base}; ls", f"python3 {base} && ls",
                  f"python3 fde/driver_m008.py apply {r} {r}/proposal_r4.json", f"python3 fde/driver_m008.py apply {r} runs/M008_haiku_raw_a/proposal_r3.json", f"python3 fde/driver_m008.py status runs/M008_haiku_raw_a",
                  f"python3 fde/driver.py status {r}", f"python3 fde/driver_m008.py score {r}", "python3 fde/driver_m008.py blind off", "python3 fde/driver_m008.py init runs/x M008 kernel", "python3 -c 'import evaluator_m008'",
                  "cat fde/simulator_m008.py", "ls", f"cat {r}/run.json", f"python3 -W ignore -W error fde/driver_m008.py status {r}", f"PYTHONPATH=x python3 fde/driver_m008.py status {r}", "", None, 5, ["python3"]):
            self.no("Bash", {"command": c})
        self.no("Bash", {"command": f"python3 fde/driver_m008.py status {r}"}, cwd="/tmp")
    def test_blind_guard_covers_search_web_mcp_and_subagent_routes(self):
        for t, i in (("Grep", {"pattern": "x"}), ("Glob", {"pattern": "**/*"}), ("WebFetch", {"url": "https://example.com"}), ("WebSearch", {"query": "x"}), ("Agent", {"prompt": "x"}), ("ToolSearch", {"query": "x"}),
                     ("mcp__msb-v3__vault_read", {"path": "x"}), ("mcp__obsidian__read_notes", {"paths": []}), ("mcp__anything__else", {}), ("TodoWrite", {}), ("Task", {}), ("Skill", {"skill": "fde-eval"}), ("Skill", {"skill": "fde-kernel"}), ("Skill", {}), ("read", {"file_path": f"{self.R}/ctx_r3.json"}), ("", {})): self.no(t, i)
    def test_blind_guard_fails_closed_on_malformed_tool_input(self):
        for raw in ("[1]", "null", '"x"', "5", "true", "{}", '{"tool_name":"Bash"}', '{"tool_name":"Bash","tool_input":"x"}', '{"tool_name":"Bash","tool_input":["x"]}', '{"tool_name":"Bash","tool_input":null}', '{"tool_name":5,"tool_input":{}}',
                    '{"tool_name":null,"tool_input":{}}', "not json", "", '{"tool_name":"Read","tool_input":{"file_path":{"a":1}}}', '\xff'): self.no("", {}, raw=raw)
    def test_marker_misconfiguration_denies_everything(self):
        for marker in ("blind\n", "run=\n", "run=a.b\n", "run=a b\n", "run=..\n", "run=M008_haiku_kernel_a/../x\n", "run=M008_haiku_ghost_a\n", "run=١٢\n", "x"):
            p = Proj(marker=marker)
            for t, i in (("Read", {"file_path": "runs/M008_haiku_kernel_a/ctx_r3.json"}), ("Bash", {"command": "python3 fde/driver_m008.py status runs/M008_haiku_kernel_a"}), ("Skill", {"skill": "fde-mission"})): self.assertEqual(p.call(t, i), 2, (marker, t))
        p = Proj(); os.remove(f"{p.root}/runs/M008_haiku_kernel_a/run.json"); self.assertEqual(p.call("Skill", {"skill": "fde-mission"}), 2)
        p = Proj(); open(f"{p.root}/runs/M008_haiku_kernel_a/run.json", "w").write("{corrupt"); self.assertEqual(p.call("Skill", {"skill": "fde-mission"}), 2)
    def test_run_directory_must_be_a_plain_directory(self):
        p = Proj(); shutil.move(f"{p.root}/runs/M008_haiku_kernel_a", f"{p.root}/elsewhere"); os.symlink(f"{p.root}/elsewhere", f"{p.root}/runs/M008_haiku_kernel_a"); self.assertEqual(p.call("Skill", {"skill": "fde-mission"}), 2)
    def test_guard_is_inert_without_the_marker_for_the_orchestrator(self):
        p = Proj(); os.remove(f"{p.root}/.fde_blind")
        for t, i in (("Read", {"file_path": "fde/simulator_m008.py"}), ("Bash", {"command": "cat runs/PREREG_M008.md"}), ("Agent", {})): self.assertEqual(p.call(t, i), 0)
    def test_guard_never_exits_one(self):
        rc = {self.p.call("Read", {"file_path": x}) for x in (5, None, "\x00", "a" * 100000, "\ud800")} | {self.p.call("", {}, raw=r) for r in ("[", "{", "\x00", "[[[[[[[[[[")}
        self.assertTrue(rc <= {0, 2}, rc)
    def test_blind_on_writes_a_marker_the_guard_accepts(self):
        p = Proj(marker="x"); old = D8.MARKER; D8.MARKER = f"{p.root}/.fde_blind"
        try: D8.blind(True, f"{p.root}/runs/M008_haiku_kernel_a")
        finally: D8.MARKER = old
        self.assertEqual(p.call("Read", {"file_path": "runs/M008_haiku_kernel_a/ctx_r3.json"}), 0); self.assertEqual(p.call("Read", {"file_path": "runs/M008_haiku_raw_a/ctx_r3.json"}), 2)
        for bad in ("runs/M008_haiku_1.0_a", "runs/has space", "runs/../x"):
            with self.assertRaises(D8.ProtoError): D8.blind(True, bad)
    def test_hook_config_routes_every_closed_tool_through_the_guard(self):
        s = json.load(open(os.path.join(ROOT, ".claude", "settings.json"))); h = s["hooks"]["PreToolUse"][0]; self.assertIn("blind_guard.py", h["hooks"][0]["command"])
        for t in ("Read", "Write", "Edit", "Grep", "Glob", "Bash", "NotebookEdit", "Skill", "WebFetch", "WebSearch", "Agent", "ToolSearch", "mcp__msb-v3__vault_read", "mcp__obsidian__read_notes"): self.assertTrue(re.fullmatch(h["matcher"], t), t)


# ------------------------------------------------------------------ registry (tamper-evident, versioned)
class Registry(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(); self.f1 = os.path.join(self.base, "a.py"); self.f2 = os.path.join(self.base, "b.py"); open(self.f1, "w").write("A"); open(self.f2, "w").write("B")
        self.reg = lambda n=1, **k: registry.register("M008", n, "body text", "predictions text", [self.f1, self.f2], runs=self.base, **k)
    def code(self, fn, *a, **k):
        with self.assertRaises(registry.RegistryError) as c: fn(*a, **k)
        return c.exception.code
    def test_register_verify_and_immutability(self):
        rec = self.reg(); self.assertEqual(registry.verify("M008", runs=self.base)["record_sha256"], rec["record_sha256"])
        self.assertEqual(self.code(self.reg), "BAD_VERSION")                                       # cannot re-register v1
        d = registry._vdir("M008", 1, self.base)
        for f in ("registration.json", "PREREG.md", "PREDICTIONS.md"): self.assertFalse(os.access(os.path.join(d, f), os.W_OK), f)
    def test_editing_a_frozen_file_is_caught_and_an_addendum_cannot_refreeze_it(self):
        self.reg(); open(self.f1, "w").write("A-changed")
        self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "FROZEN_FILE_CHANGED")
        self.assertEqual(self.code(registry.amend, "M008", 1, "clarification", "harmless", runs=self.base), "FROZEN_FILE_CHANGED")
        registry.amend("M008", 1, "deviation", "reporting that a.py changed after freeze", runs=self.base)               # a deviation may be REPORTED, it never re-freezes
        self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "FROZEN_FILE_CHANGED")
    def test_a_frozen_file_deleted_is_a_mismatch_not_a_traceback(self):
        self.reg(); os.remove(self.f2); self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "FROZEN_FILE_CHANGED")
    def test_predictions_and_body_are_hash_protected(self):
        self.reg(); d = registry._vdir("M008", 1, self.base)
        for f in ("PREDICTIONS.md", "PREREG.md"):
            p = os.path.join(d, f); os.chmod(p, 0o644); orig = open(p).read(); open(p, "w").write(orig + " edited"); self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "TAMPERED"); open(p, "w").write(orig)
        registry.verify("M008", runs=self.base)
    def test_registration_record_and_addendum_chain_are_tamper_evident(self):
        self.reg(); registry.amend("M008", 1, "clarification", "one", runs=self.base); registry.amend("M008", 1, "clarification", "two", runs=self.base); d = registry._vdir("M008", 1, self.base)
        a1 = os.path.join(d, "addenda", "0001.json"); os.chmod(a1, 0o644); orig = open(a1).read(); open(a1, "w").write(orig.replace("one", "ONE")); self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "CORRUPT"); open(a1, "w").write(orig)
        registry.verify("M008", runs=self.base); os.chmod(a1, 0o644); os.rename(a1, os.path.join(d, "addenda", "0009.json")); self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "CORRUPT")
        os.rename(os.path.join(d, "addenda", "0009.json"), a1); rj = os.path.join(d, "registration.json"); os.chmod(rj, 0o644); rtxt = open(rj).read(); open(rj, "w").write(rtxt.replace('"version": 1', '"version": 1 '))
        registry.verify("M008", runs=self.base)                                                    # whitespace-only change keeps the canonical hash
        open(rj, "w").write(rtxt.replace("M008", "M007")); self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "CORRUPT")
    def test_addenda_can_only_clarify_or_report_deviation(self):
        self.reg()
        for kind in ("freeze", "change", "", None, "refreeze"): self.assertEqual(self.code(registry.amend, "M008", 1, kind, "x", runs=self.base), "BAD_KIND")
        for text in ("", "   ", None): self.assertEqual(self.code(registry.amend, "M008", 1, "clarification", text, runs=self.base), "EMPTY_FIELD")
        forged = registry.amend("M008", 1, "clarification", "Frozen-hashes (full) at addendum: kernel.py=abc", runs=self.base); registry.verify("M008", runs=self.base); self.assertEqual(forged["seq"], 1)
    def test_world_names_are_a_closed_registry(self):
        for w in ("../evil", "a b", "M999", "m008", "", None, "M008/../M007", "M8", "M٠٠٨"): self.assertEqual(self.code(registry.verify, w, runs=self.base), "UNKNOWN_WORLD", w)
        self.assertEqual(self.code(registry.register, "../evil", 1, "b", "p", [self.f1], runs=self.base), "UNKNOWN_WORLD")
    def test_empty_fields_and_missing_files_are_refused_and_create_nothing(self):
        self.assertEqual(self.code(registry.register, "M008", 1, "", "p", [self.f1], runs=self.base), "EMPTY_FIELD"); self.assertEqual(self.code(registry.register, "M008", 1, "b", "  ", [self.f1], runs=self.base), "EMPTY_FIELD")
        self.assertEqual(self.code(registry.register, "M008", 1, "b", "p", [], runs=self.base), "EMPTY_FIELD"); self.assertEqual(self.code(registry.register, "M008", 1, "b", "p", [self.base + "/nope"], runs=self.base), "MISSING_FILE")
        self.assertEqual(registry._versions("M008", self.base), [])
    def test_changing_the_freeze_requires_a_new_version_that_supersedes_the_old(self):
        self.reg(); open(self.f1, "w").write("A2"); self.assertEqual(self.code(self.reg, 3), "BAD_VERSION"); rec2 = self.reg(2, supersedes_reason="driver hardened before any data")
        self.assertEqual(registry.verify("M008", runs=self.base)["version"], 2); self.assertEqual(self.code(registry.verify, "M008", 1, runs=self.base), "SUPERSEDED"); self.assertEqual(rec2["supersedes"]["version"], 1)
    def test_legacy_registration_can_be_imported_without_refreezing(self):
        pre = os.path.join(self.base, "P.md"); pr = os.path.join(self.base, "Q.md"); open(pr, "w").write("preds")
        open(pre, "w").write("# x\n## Frozen code (sha256)\n- kernel.py: " + "a" * 64 + "\n- driver.py: " + "b" * 64 + "\n"); rec = registry.import_legacy("M008", pre, pr, runs=self.base)
        self.assertEqual(rec["files"], {"driver.py": "b" * 64, "kernel.py": "a" * 64}); self.assertEqual(self.code(registry.verify, "M008", runs=self.base), "FROZEN_FILE_CHANGED")
    def test_run_eligibility_requires_a_scored_run_of_the_active_registration(self):
        old = registry.config.RUNS; registry.config.RUNS = self.base
        try:
            registry.register("M008", 1, "b", "p", ["kernel.py", "simulator_m008.py"], runs=self.base); ok = os.path.join(self.base, "M008_haiku_kernel_a"); D8.init(ok, "M008", "kernel", run_kind="scored")
            self.assertEqual(registry.run_eligibility(ok, "M008", self.base), (True, []))
            q = os.path.join(self.base, "M008_haiku_kernel_b"); D8.init(q, "M008", "kernel"); self.assertFalse(registry.run_eligibility(q, "M008", self.base)[0])
            m = json.load(open(ok + "/run_manifest.json")); m["registration_hash"] = "0" * 64; json.dump(m, open(ok + "/run_manifest.json", "w")); self.assertIn("registration_hash", " ".join(registry.run_eligibility(ok, "M008", self.base)[1]))
            os.remove(ok + "/run_manifest.json"); self.assertFalse(registry.run_eligibility(ok, "M008", self.base)[0])
        finally: registry.config.RUNS = old
    def test_cli_returns_structured_errors_and_codes(self):
        r = subprocess.run([sys.executable, os.path.join(FDE, "registry.py"), "verify", "../evil"], capture_output=True, text=True); self.assertEqual(r.returncode, 3); self.assertEqual(json.loads(r.stdout)["error_code"], "UNKNOWN_WORLD")
        r = subprocess.run([sys.executable, os.path.join(FDE, "registry.py"), "bogus"], capture_output=True, text=True); self.assertEqual(r.returncode, 2); self.assertNotIn("Traceback", r.stdout + r.stderr)


class ExportRegression(unittest.TestCase):
    def test_inspect_run_of_an_m008_run_works_after_the_key_was_made_private(self):
        import inspect_run
        d, base = newrun(); D8.apply(d, prop(base, VALID)); self.assertTrue(inspect_run.inspect(d)["visited_decoy_diagnostic"])
    def test_vault_export_of_an_m008_run_works_after_the_key_was_made_private(self):
        """Regression from the evaluator split: vault_sync scored M008 runs with the old driver and crashed with KeyError 'truth'."""
        import vault_sync, config
        d, base = newrun(); D8.apply(d, prop(base, VALID)); old = config.EXP_DIR; config.EXP_DIR = os.path.join(base, "exp")
        rj = os.path.join(d, "run.json"); st = json.load(open(rj)); st["done"] = True; json.dump(st, open(rj, "w"))   # export refuses unfinished runs
        try: out = vault_sync.export_run(d)
        finally: config.EXP_DIR = old
        self.assertTrue(os.path.exists(out) if isinstance(out, str) and os.path.sep in out else True)


class LegacyPrereg(unittest.TestCase):
    """prereg.py still verifies the closed families; it must no longer be able to silently re-freeze."""
    def setUp(self): self.runs = tempfile.mkdtemp(); self.env = dict(os.environ, FDE_RUNS=self.runs)
    def cli(self, *a): return subprocess.run([sys.executable, "-W", "ignore", os.path.join(FDE, "prereg.py"), *a], capture_output=True, text=True, env=self.env)
    def test_world_names_paths_missing_registrations_and_empty_addenda(self):
        self.assertNotEqual(self.cli("new", "../evil").returncode, 0); self.assertNotIn("Traceback", self.cli("verify", "Nope").stderr); self.assertNotIn("Traceback", self.cli("verify", "a b").stderr)
        self.assertEqual(self.cli("new", "ZZ").returncode, 0); self.assertNotEqual(self.cli("addendum", "ZZ", "   ").returncode, 0)
    def test_an_addendum_cannot_silently_refreeze_changed_code_and_cannot_forge_a_freeze_line(self):
        self.cli("new", "ZZ"); text = open(self.runs + "/PREREG_ZZ.md").read(); open(self.runs + "/PREREG_ZZ.md", "w").write(re.sub(r"(- kernel\.py: )[0-9a-f]{64}", r"\g<1>" + "0" * 64, text))     # simulate 'code changed since freeze'
        r = self.cli("addendum", "ZZ", "harmless"); self.assertNotEqual(r.returncode, 0); self.assertIn("REFUSED", r.stdout + r.stderr); self.assertEqual(self.cli("verify", "ZZ").returncode, 1)
        self.assertEqual(self.cli("addendum", "ZZ", "--refreeze", "explicit", "Frozen-hashes", "(full)", "at", "addendum:", "kernel.py=abc").returncode, 0)
        body = open(self.runs + "/PREREG_ZZ.md").read(); self.assertIn("REFREEZE requested explicitly", body); self.assertEqual(len(re.findall(r"^Frozen-hashes \(full\) at addendum:", body, re.M)), 1)


if __name__ == "__main__": unittest.main(verbosity=1)
