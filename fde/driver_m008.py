"""M008 run controller. Wraps the frozen M007 driver (driver.py, untouched) and adds the control-system properties driver.py lacks.
ARM-FACING (apply / status): imports NO answer key (evaluator_m008 is loaded only by init/score, which are orchestrator-side).
Invariants (each pinned by tests/test_m008_hardening.py):
  I1  Validate everything (CLI args, world, mode, run name, proposal bytes/JSON/schema/limits/evidence ids) BEFORE creating or mutating anything.
  I2  A rejected apply changes NOTHING in run.json, state.db, ctx files, round, phase, log, artifacts. The only write is an audit copy of the rejected proposal under <run>/rejected/.
  I3  At most one apply/status runs per run at a time (exclusive flock on <run>/.apply.lock, held across the whole transaction; state is re-read under the lock).
  I4  Any failure after the lock is taken restores the run directory from a snapshot (rollback) and returns a structured error; no traceback reaches the caller.
  I5  A finished run is terminal: further apply -> RUN_COMPLETE, no simulator call, no ctx. Cap: rounds 0..8 are executable (9 rounds); the 9th apply sets done.
  I6  init never touches an existing run and cleans up after itself on failure. Modes are exactly kernel|rules|raw; there is no reset command.
  I7  run.json is replaced atomically (temp file + os.replace); readers never see a half-written file.
Decisions (Wilson to overrule): repeated diagnostics are ALLOWED and idempotent (same artifact re-released, costs a round). Reusing an existing claim_id in a LATER proposal is allowed
because it is the Kernel's status-revision protocol (audited in claim_status_transitions and by the retained proposal_r<N>.json files); duplicates WITHIN one proposal are rejected.
Errors are one JSON line: {"ok": false, "error_code": ..., "message": ..., "path": ...}; exit 2 = rejected input, 3 = state error (exists/complete/not found), 1 = internal.
CLI: init <run> <world> <mode> [--scored] | apply <run> <proposal> | status <run> | score <run> | blind on <run> | blind off
"""

import sys, os, re, json, gc, time, fcntl, shutil, tempfile, hashlib, datetime, contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulator as S, simulator_m008  # noqa: F401  (registers the PUBLIC world; no answer key is imported here)
import driver as D, kernel as K, lint_scenario, registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = os.path.join(ROOT, ".fde_blind")
MODES = ("kernel", "rules", "raw")
RUN_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,80}$", re.ASCII)
ARM_NAME = re.compile(
    r"^(M[0-9]{3})_(haiku|sonnet|opus|qwen38b)_(kernel|rules|raw)_([a-z0-9]+)$", re.ASCII
)
LOCAL_MODELS = {
    "qwen38b": "qwen3:8b"
}  # run-name model slug (ASCII, no colon) -> the real Ollama model tag, for fde/run_local_llm.py callers
ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$", re.ASCII)
ACTION_RE = re.compile(r"^[a-z0-9_]{1,80}$", re.ASCII)
KIND_OK = ("diagnostic", "mitigation", "escalation", "none", "final_assessment")
TOP_KEYS = {
    "claims",
    "contradictions",
    "resolutions",
    "dispositions",
    "capability_gaps",
    "next_action",
    "notes",
    "summary",
}
LIM = dict(bytes=256 * 1024, claims=32, sources=8, text=4096, lst=32, ids=100)


class ProtoError(Exception):
    def __init__(self, code, message, path=None, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.exit_code = exit_code

    def as_dict(self):
        return {"ok": False, "error_code": self.code, "message": self.message, "path": self.path}


# ---------------------------------------------------------------- small helpers
def _run_dir(run, must_exist=True):
    if not isinstance(run, str) or not run or "\x00" in run:
        raise ProtoError("BAD_ARGUMENT", "run path must be a non-empty string")
    name = os.path.basename(os.path.normpath(run))
    if not RUN_NAME.fullmatch(name):
        raise ProtoError("BAD_RUN_NAME", f"run name must match {RUN_NAME.pattern}")
    if must_exist and not (
        os.path.isdir(run)
        and os.path.isfile(os.path.join(run, "run.json"))
        and os.path.isfile(os.path.join(run, "state.db"))
    ):
        raise ProtoError("RUN_NOT_FOUND", "run directory missing or not initialised", exit_code=3)
    return run


def _atomic_save(run, st):
    tmp = os.path.join(run, f".run.json.{os.getpid()}.tmp")
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(run, "run.json"))


D.save = (
    _atomic_save  # driver.py's non-atomic save is replaced for every caller in this process (I7)
)


def _state(run):
    try:
        st = json.load(open(os.path.join(run, "run.json")))
    except Exception:
        raise ProtoError("RUN_CORRUPT", "run.json unreadable", exit_code=3)
    if not isinstance(st, dict) or not all(
        k in st for k in ("world", "mode", "round", "done", "log")
    ):
        raise ProtoError("RUN_CORRUPT", "run.json missing required fields", exit_code=3)
    return st


@contextlib.contextmanager
def _locked(run, timeout=30.0):
    fd = os.open(os.path.join(run, ".apply.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    end = time.time() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.time() > end:
                os.close(fd)
                raise ProtoError("LOCK_TIMEOUT", "another operation holds this run", exit_code=3)
            time.sleep(0.01)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


_KEEP = (".apply.lock", "rejected")


def _snapshot(run):
    snap = tempfile.mkdtemp(prefix="fde_snap_")
    shutil.copytree(run, os.path.join(snap, "s"), ignore=shutil.ignore_patterns(*_KEEP))
    return snap


def _restore(run, snap):
    gc.collect()
    for e in os.listdir(run):
        if e in _KEEP:
            continue
        p = os.path.join(run, e)
        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
    for e in os.listdir(os.path.join(snap, "s")):
        src = os.path.join(snap, "s", e)
        dst = os.path.join(run, e)
        shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy2(src, dst)


def _reject_audit(run, proposal_path, err):
    """The only write a rejected apply makes: keep the rejected proposal and the reason, outside every scored file. Also frees the round's proposal filename for the corrected file."""
    try:
        d = os.path.join(run, "rejected")
        os.makedirs(d, exist_ok=True)
        n = len([x for x in os.listdir(d) if x.endswith(".json") and x != "log.jsonl"]) + 1
        real = os.path.realpath(proposal_path)
        if (
            real.startswith(os.path.realpath(run) + os.sep)
            and os.path.isfile(real)
            and not os.path.islink(proposal_path)
        ):
            os.replace(real, os.path.join(d, f"{n:04d}_{os.path.basename(real)}.json"))
        with open(os.path.join(d, "log.jsonl"), "a") as f:
            f.write(
                json.dumps(
                    dict(err.as_dict(), n=n, at=datetime.datetime.now(datetime.UTC).isoformat())
                )
                + "\n"
            )
    except Exception as audit_err:
        # The rejection itself still stands; only its audit record failed. Never silent:
        # record the failure in .driver_errors.log and say so on stderr (stdout stays JSON).
        _log_internal(run, audit_err)
        print(
            f"[driver_m008] WARNING: rejected-proposal audit write failed: "
            f"{type(audit_err).__name__}: {audit_err}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------- proposal validation (pure: no state is touched)
def _s(v, path, maxlen=None, nonempty=False):
    if not isinstance(v, str):
        raise ProtoError("INVALID_PROPOSAL", f"{path} must be a string", path)
    if nonempty and not v.strip():
        raise ProtoError("INVALID_PROPOSAL", f"{path} must not be empty", path)
    if len(v) > (maxlen or LIM["text"]):
        raise ProtoError(
            "INVALID_PROPOSAL", f"{path} exceeds {maxlen or LIM['text']} characters", path
        )
    return v


def _list(v, path, cap=None):
    if not isinstance(v, list):
        raise ProtoError("INVALID_PROPOSAL", f"{path} must be a list", path)
    if len(v) > (cap or LIM["lst"]):
        raise ProtoError(
            "INVALID_PROPOSAL", f"{path} has more than {cap or LIM['lst']} entries", path
        )
    return v


def _obj(v, path):
    if not isinstance(v, dict):
        raise ProtoError("INVALID_PROPOSAL", f"{path} must be an object", path)
    return v


def validate_proposal(p, world, mode, art_exists, claim_ids):
    """Returns nothing; raises ProtoError. `art_exists(id)`/`claim_ids` come from the run's persisted state."""
    w = S.WORLDS[world]
    p = _obj(p, "$")
    unknown = sorted(set(p) - TOP_KEYS)
    if unknown:
        raise ProtoError("INVALID_PROPOSAL", f"unknown top-level field(s) {unknown}", "$")
    if "next_action" not in p:
        raise ProtoError("INVALID_PROPOSAL", "next_action is required", "$.next_action")
    seen = set()
    claims = _list(p.get("claims", []), "$.claims", LIM["claims"])
    for i, c in enumerate(claims):
        pa = f"$.claims[{i}]"
        c = _obj(c, pa)
        cid = c.get("claim_id")
        _s(cid, pa + ".claim_id", LIM["ids"], True)
        if not ID_RE.fullmatch(cid):
            raise ProtoError(
                "INVALID_PROPOSAL",
                "claim_id must be ASCII letters, digits, _ . -",
                pa + ".claim_id",
            )
        if cid in seen:
            raise ProtoError(
                "INVALID_PROPOSAL",
                f"duplicate claim_id {cid!r} within one proposal",
                pa + ".claim_id",
            )
        seen.add(cid)
        kind = c.get("kind", "hypothesis")
        status = c.get("status", "hypothesized")
        if not isinstance(kind, str) or not isinstance(status, str):
            raise ProtoError("INVALID_PROPOSAL", "kind and status must be strings", pa)
        if kind not in K.KINDS:
            raise ProtoError(
                "INVALID_PROPOSAL", f"kind must be one of {sorted(K.KINDS)}", pa + ".kind"
            )
        if status not in K.STATUSES:
            raise ProtoError(
                "INVALID_PROPOSAL", f"status must be one of {sorted(K.STATUSES)}", pa + ".status"
            )
        (
            _s(c.get("statement", ""), pa + ".statement", None, nonempty=True)
            if "statement" in c
            else None
        )
        if "mechanism_tag" in c:
            tag = _s(c["mechanism_tag"], pa + ".mechanism_tag", 100)
            if tag and w.get("vocab") and tag not in w["vocab"]:
                raise ProtoError(
                    "INVALID_PROPOSAL",
                    f"mechanism_tag must be one of {w['vocab']}",
                    pa + ".mechanism_tag",
                )
        for f in ("limitation", "corroboration"):
            if f in c:
                _s(c[f], f"{pa}.{f}")
        src = _list(c.get("sources", []), pa + ".sources", LIM["sources"])
        if len(set(map(str, src))) != len(src):
            raise ProtoError("INVALID_PROPOSAL", "duplicate source ids", pa + ".sources")
        for j, x in enumerate(src):
            _s(x, f"{pa}.sources[{j}]", LIM["ids"], True)
            if not art_exists(x):
                raise ProtoError(
                    "UNKNOWN_SOURCE",
                    f"source {x!r} is not an artifact in this run",
                    f"{pa}.sources[{j}]",
                )
        if kind in ("root_cause", "inference", "impact", "observation") and not src:
            raise ProtoError(
                "INVALID_PROPOSAL", f"a {kind} claim must cite at least one source", pa + ".sources"
            )
    for name in ("contradictions", "resolutions", "capability_gaps"):
        for i, o in enumerate(_list(p.get(name, []), f"$.{name}")):
            o = _obj(o, f"$.{name}[{i}]")
            for k, v in o.items():
                if isinstance(v, list):
                    for j, x in enumerate(_list(v, f"$.{name}[{i}].{k}")):
                        _s(x, f"$.{name}[{i}].{k}[{j}]", LIM["ids"])
                        if name == "resolutions" and k == "evidence_refs" and not art_exists(x):
                            raise ProtoError(
                                "UNKNOWN_SOURCE",
                                f"evidence ref {x!r} is not an artifact in this run",
                                f"$.{name}[{i}].{k}[{j}]",
                            )
                elif not isinstance(v, (str, int, float, bool)) and v is not None:
                    raise ProtoError(
                        "INVALID_PROPOSAL", "unsupported value type", f"$.{name}[{i}].{k}"
                    )
                elif isinstance(v, str):
                    _s(v, f"$.{name}[{i}].{k}")
    for i, d in enumerate(_list(p.get("dispositions", []), "$.dispositions")):
        pa = f"$.dispositions[{i}]"
        d = _obj(d, pa)
        cid = _s(d.get("claim_id"), pa + ".claim_id", LIM["ids"], True)
        if d.get("action") not in ("preserve", "downgrade", "refine"):
            raise ProtoError(
                "INVALID_PROPOSAL", "action must be preserve, downgrade or refine", pa + ".action"
            )
        if cid not in claim_ids and cid not in seen:
            raise ProtoError(
                "INVALID_PROPOSAL", f"disposition names unknown claim {cid!r}", pa + ".claim_id"
            )
    for f in ("notes", "summary"):
        if f in p:
            _s(p[f], f"$.{f}")
    na = _obj(p["next_action"], "$.next_action")
    if "action" not in na:
        raise ProtoError(
            "INVALID_PROPOSAL", "next_action.action is required", "$.next_action.action"
        )
    act = _s(na["action"], "$.next_action.action", 80, True)
    kind = na.get("kind", "none")
    if not isinstance(kind, str) or kind not in KIND_OK:
        raise ProtoError(
            "INVALID_PROPOSAL",
            f"next_action.kind must be one of {list(KIND_OK)}",
            "$.next_action.kind",
        )
    if not ACTION_RE.fullmatch(act):
        raise ProtoError(
            "INVALID_PROPOSAL",
            "next_action.action must be exactly one action name (lowercase letters, digits, _)",
            "$.next_action.action",
        )
    if act not in w["rules"] and act not in ("none", "other"):
        raise ProtoError(
            "INVALID_PROPOSAL",
            "next_action.action is not in the authority list",
            "$.next_action.action",
        )
    if kind == "final_assessment" and act not in ("none", "other"):
        raise ProtoError(
            "INVALID_PROPOSAL",
            "a final_assessment uses action 'none' or 'other'",
            "$.next_action.action",
        )
    if act in w["actions"] and kind != w["actions"][act][0]:
        raise ProtoError(
            "INVALID_PROPOSAL",
            f"action {act!r} is a {w['actions'][act][0]}; kind must match",
            "$.next_action.kind",
        )
    for f in ("rationale", "expected_information_gain"):
        if f in na:
            _s(na[f], f"$.next_action.{f}")


def _read_proposal(path):
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ProtoError("BAD_ARGUMENT", "proposal path must be a non-empty string")
    try:
        size = os.stat(path).st_size
    except OSError:
        raise ProtoError(
            "PROPOSAL_NOT_FOUND", "proposal file not found or unreadable", "proposal", exit_code=2
        )
    if not os.path.isfile(path):
        raise ProtoError("PROPOSAL_NOT_FOUND", "proposal is not a regular file", "proposal")
    if size == 0:
        raise ProtoError("INVALID_PROPOSAL", "proposal file is empty", "$")
    if size > LIM["bytes"]:
        raise ProtoError("PROPOSAL_TOO_LARGE", f"proposal exceeds {LIM['bytes']} bytes", "$")
    with open(path, "rb") as f:
        raw = f.read(LIM["bytes"] + 1)
    if len(raw) > LIM["bytes"]:
        raise ProtoError("PROPOSAL_TOO_LARGE", f"proposal exceeds {LIM['bytes']} bytes", "$")
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ProtoError("INVALID_PROPOSAL", "proposal is not valid UTF-8", "$")
    try:
        obj = json.loads(txt)
    except (ValueError, RecursionError):
        raise ProtoError(
            "INVALID_PROPOSAL", "proposal is not valid JSON (or nests too deeply)", "$"
        )
    return raw, obj


# ---------------------------------------------------------------- lifecycle
def init(run, world, mode, lessons=False, src_db=None, run_kind="qualification"):
    if lessons or src_db:
        raise ProtoError("BAD_ARGUMENT", "M008 has no lessons arm")
    if world not in S.WORLDS or not str(world).startswith("M008"):
        raise ProtoError("UNKNOWN_WORLD", "world must be a registered M008 world")
    if mode not in MODES:
        raise ProtoError("BAD_MODE", f"mode must be one of {list(MODES)}")
    if run_kind not in ("scored", "qualification"):
        raise ProtoError("BAD_ARGUMENT", "run_kind must be scored or qualification")
    _run_dir(run, must_exist=False)
    if os.path.lexists(run):
        raise ProtoError(
            "RUN_EXISTS", "run already exists; init never touches an existing run", exit_code=3
        )
    reg = None
    if run_kind == "scored":
        try:
            reg = registry.verify(world)
        except registry.RegistryError as e:
            raise ProtoError(
                "NO_ACTIVE_REGISTRATION",
                f"scored runs need an intact active registration: {e.code}",
                exit_code=3,
            )
        if not ARM_NAME.fullmatch(os.path.basename(os.path.normpath(run))) or not os.path.basename(
            os.path.normpath(run)
        ).startswith(world + "_"):
            raise ProtoError(
                "BAD_RUN_NAME",
                "a scored run must be named <WORLD>_<model>_<arm>_<letter>",
                exit_code=2,
            )
    high = [f["code"] for f in lint_scenario.lint(world)["findings"] if f["severity"] == "HIGH"]
    if high:
        raise ProtoError("LINT_HIGH", f"refusing to init {world}: lint HIGH findings {high}")
    name = os.path.basename(os.path.normpath(run))
    am = ARM_NAME.fullmatch(name)
    try:
        ctxp = D.init(run, world, mode)
        manifest = {
            "schema_version": 1,
            "experiment": f"{world}-v{reg['version']}" if reg else world,
            "run_id": name,
            "world": world,
            "arm": (
                {"model": am.group(2), "mode": am.group(3), "replicate": am.group(4)}
                if am
                else None
            ),
            "run_kind": run_kind,
            "registration_hash": reg["record_sha256"] if reg else None,
            "code_hashes": reg["files"] if reg else None,
            "initialized_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        _atomic_save_json(os.path.join(run, "run_manifest.json"), manifest)
    except BaseException:
        gc.collect()
        shutil.rmtree(run, ignore_errors=True)
        raise
    return ctxp


def _atomic_save_json(path, obj):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def apply(run, proposal_path):
    run = _run_dir(run)
    with _locked(run):
        st = _state(run)
        if st["done"]:
            raise ProtoError(
                "RUN_COMPLETE", "run is complete and cannot accept further proposals", exit_code=3
            )
        world = st["world"]
        if world not in S.WORLDS:
            raise ProtoError("UNKNOWN_WORLD", "run belongs to an unregistered world", exit_code=3)
        try:
            raw, obj = _read_proposal(proposal_path)
            k, _ = D.load(run)
            try:
                have = {r[0] for r in k.c.execute("SELECT artifact_id FROM artifacts")}
                cids = {r[0] for r in k.c.execute("SELECT claim_id FROM claims")}
            finally:
                k.c.close()
            try:
                validate_proposal(obj, world, st["mode"], have.__contains__, cids)
            except ProtoError:
                raise
            except (TypeError, KeyError, AttributeError, ValueError, IndexError, RecursionError):
                raise ProtoError(
                    "INVALID_PROPOSAL", "proposal failed validation", "$"
                )  # a validator gap must reject, never crash
        except ProtoError as e:
            if e.code in ("INVALID_PROPOSAL", "UNKNOWN_SOURCE", "PROPOSAL_TOO_LARGE"):
                _reject_audit(run, proposal_path, e)
            raise
        gated = gated_actions(world)
        na = obj["next_action"]
        action = na["action"]
        k, _ = D.load(run)
        try:
            prereq_met = action in gated and bool(k.art(gated[action][2]))
        finally:
            k.c.close()
        snap = _snapshot(run)
        pfile = os.path.join(snap, "proposal.json")
        n = st["round"]
        with open(pfile, "wb") as pf:
            pf.write(raw)
        try:
            report = D.apply(run, pfile)
            st2 = _state(run)
            if st2["round"] != n + 1 or len(st2["log"]) != len(st["log"]) + 1:
                raise ProtoError(
                    "INVARIANT_VIOLATION", "round did not advance by exactly one", exit_code=1
                )
            if action in gated:
                k, _ = D.load(run)
                try:
                    got = [
                        r["result"]
                        for r in k.c.execute(
                            "SELECT result FROM scenario_actions WHERE round=? AND action=?",
                            (n, action),
                        )
                    ]
                finally:
                    k.c.close()
                if got and got[-1] == gated[action][0] and not prereq_met:
                    raise ProtoError(
                        "INVARIANT_VIOLATION", "prerequisite invariant violated", exit_code=1
                    )
        except BaseException as e:
            _restore(run, snap)
            if isinstance(e, ProtoError):
                raise
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            _log_internal(run, e)
            raise ProtoError(
                "INTERNAL_ERROR",
                f"apply failed and was rolled back ({type(e).__name__})",
                exit_code=1,
            )
        finally:
            shutil.rmtree(snap, ignore_errors=True)
        return report


def _log_internal(run, e):
    try:
        import traceback

        with open(
            os.path.join(os.path.dirname(os.path.abspath(run)), ".driver_errors.log"), "a"
        ) as f:
            f.write(
                f"{datetime.datetime.now(datetime.UTC).isoformat()} {os.path.basename(run)}\n{traceback.format_exc()}\n"
            )
    except Exception as log_err:
        # Last resort: the error log itself is unwritable. Keep stdout JSON-clean; use stderr.
        print(
            f"[driver_m008] could not write .driver_errors.log ({type(log_err).__name__}); "
            f"original error: {type(e).__name__}: {e}",
            file=sys.stderr,
        )


def gated_actions(world):
    """{action: (real_artifact_id, waiting_artifact_id, prerequisite_artifact_id)} derived from the action specs alone (a diagnostic whose result waits on another artifact)."""
    out = {}
    for a, spec in S.WORLDS[world]["actions"].items():
        if spec[0] == "diagnostic" and len(spec) > 3 and spec[2]:
            out[a] = (spec[1]["aid"], spec[3]["aid"], spec[2][0])
    return out


def status(run):
    run = _run_dir(run)
    with _locked(run):
        st = _state(run)
        try:
            out = D.status(run)
        except Exception as e:
            _log_internal(run, e)
            raise ProtoError("INTERNAL_ERROR", f"status failed ({type(e).__name__})", exit_code=1)
    if st["done"]:
        out["next_context"] = None
    return out


def attach_truth(world):
    """Orchestrator side only (score/lint/report). The private modules are imported lazily HERE, never on the apply/status path."""
    import scorer_m008

    return scorer_m008.attach_truth(world)


def score(run):
    run = _run_dir(run)
    with _locked(run):
        st = _state(run)
        import scorer_m008

        return scorer_m008.score(run, st, gated_actions)


def blind(on, run=None):
    if on:
        if not run:
            raise ProtoError("BAD_ARGUMENT", "blind on requires the run directory")
        run = _run_dir(run)
        if not ARM_NAME.fullmatch(
            os.path.basename(os.path.normpath(run))
        ) and not RUN_NAME.fullmatch(os.path.basename(os.path.normpath(run))):
            raise ProtoError("BAD_RUN_NAME", "bad run name")
        _atomic_write(
            MARKER,
            f"blind mission run in progress\nrun={os.path.basename(os.path.normpath(run))}\n",
        )
        return "blind guard ON (run-isolated)"
    if os.path.exists(MARKER):
        os.remove(MARKER)
    return "blind guard OFF"


def _atomic_write(path, text):
    tmp = f"{path}.{os.getpid()}.tmp"
    open(tmp, "w").write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------- CLI (exact arity; structured errors; never a traceback)
def main(argv):
    a = argv[1:]
    c = a[0] if a else ""
    try:
        if c == "init" and len(a) in (4, 5) and (len(a) == 4 or a[4] == "--scored"):
            print(init(a[1], a[2], a[3], run_kind="scored" if len(a) == 5 else "qualification"))
        elif c == "apply" and len(a) == 3:
            print(json.dumps(apply(a[1], a[2]), indent=1)[:3000])
        elif c == "status" and len(a) == 2:
            print(json.dumps(status(a[1]), indent=1))
        elif c == "score" and len(a) == 2:
            print(json.dumps(score(a[1]), indent=1))
        elif c == "blind" and len(a) == 3 and a[1] == "on":
            print(blind(True, a[2]))
        elif c == "blind" and len(a) == 2 and a[1] == "off":
            print(blind(False))
        else:
            raise ProtoError(
                "USAGE",
                "usage: init <run> <world> <mode> [--scored] | apply <run> <proposal> | status <run> | score <run> | blind on <run> | blind off",
            )
        return 0
    except ProtoError as e:
        print(json.dumps(e.as_dict()))
        return e.exit_code
    except Exception as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "INTERNAL_ERROR",
                    "message": type(e).__name__,
                    "path": None,
                }
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
