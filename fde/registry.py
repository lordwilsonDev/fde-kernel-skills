#!/usr/bin/env python3
"""Tamper-evident experiment registry (replaces prereg.py for M008 onward; prereg.py stays only to verify closed families M003-M007).
Layout:  runs/registrations/<WORLD>/v<N>/{registration.json, PREREG.md, PREDICTIONS.md, addenda/0001.json, ..., superseded_by.json}
- A registration is created once (O_EXCL, read-only). It hashes: every frozen file, the full PREREG body, the predictions. record_sha256 covers the whole record.
- Addenda are hash-chained (each carries the previous record's hash) and can only CLARIFY or REPORT A DEVIATION. They never change the freeze:
  any change to a frozen file, the arms, thresholds, predictions, scoring, stopping rules or guard is a NEW version (register vN+1), which supersedes vN.
- verify checks: known world, contiguous versions, record hashes, chain, body/prediction hashes, every frozen file hash, and that the version is not superseded.
Usage:
  registry.py register <WORLD> <N> --body <md> --predictions <md> --files a,b,c [--supersedes-reason "text"]     (files relative to fde/)
  registry.py amend <WORLD> <N> clarification|deviation "text"
  registry.py verify <WORLD> [N]      exit 0 only if the (latest, or given) version is intact and not superseded
  registry.py status <WORLD>          prints the state, always exit 0"""
import os, sys, json, re, hashlib, datetime, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import config
REGISTERED_WORLDS = {"M003", "M004", "M005", "M006", "M007", "M008"}
WORLD_RE = re.compile(r"^M[0-9]{3}$", re.ASCII)
sha = lambda b: hashlib.sha256(b).hexdigest()
now = lambda: datetime.datetime.now(datetime.UTC).isoformat()
canon = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


class RegistryError(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code = code; self.msg = msg


def _world(w):
    if not isinstance(w, str) or not WORLD_RE.fullmatch(w) or w not in REGISTERED_WORLDS: raise RegistryError("UNKNOWN_WORLD", f"world must be one of {sorted(REGISTERED_WORLDS)}")
    return w

def _base(world, runs=None): return os.path.join(runs or config.RUNS, "registrations", _world(world))
def _vdir(world, n, runs=None): return os.path.join(_base(world, runs), f"v{int(n)}")
def _versions(world, runs=None):
    b = _base(world, runs)
    return sorted(int(d[1:]) for d in os.listdir(b) if re.fullmatch(r"v[0-9]+", d)) if os.path.isdir(b) else []

def _fhash(rel):
    p = os.path.realpath(os.path.join(HERE, rel))
    if not os.path.isfile(p): return None
    return sha(open(p, "rb").read())

def file_hashes(files): return {f: _fhash(f) for f in sorted(files)}

def _write_once(path, data, mode=0o444):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try: os.write(fd, data)
    finally: os.close(fd)
    os.chmod(path, mode)

def _seal(rec):
    body = {k: v for k, v in rec.items() if k != "record_sha256"}; rec = dict(rec); rec["record_sha256"] = sha(canon(body)); return rec

def _record_ok(rec): return rec.get("record_sha256") == sha(canon({k: v for k, v in rec.items() if k != "record_sha256"}))


def register(world, n, body, predictions, files, runs=None, supersedes_reason=None):
    _world(world); n = int(n); vs = _versions(world, runs)
    if n != (vs[-1] + 1 if vs else 1): raise RegistryError("BAD_VERSION", f"next version for {world} must be {vs[-1] + 1 if vs else 1}, got {n}")
    for label, txt in (("body", body), ("predictions", predictions)):
        if not isinstance(txt, str) or not txt.strip(): raise RegistryError("EMPTY_FIELD", f"{label} is empty")
    if not files: raise RegistryError("EMPTY_FIELD", "no frozen files")
    fh = file_hashes(files); missing = [f for f, h in fh.items() if h is None]
    if missing: raise RegistryError("MISSING_FILE", f"frozen files missing: {missing}")
    prev = None
    if vs:
        old = _load(world, vs[-1], runs)
        prev = {"version": vs[-1], "record_sha256": old["record_sha256"]}
    d = _vdir(world, n, runs); os.makedirs(d)
    _write_once(os.path.join(d, "PREREG.md"), body.encode()); _write_once(os.path.join(d, "PREDICTIONS.md"), predictions.encode())
    rec = _seal({"schema": 1, "world": world, "version": n, "created_utc": now(), "supersedes": prev, "supersedes_reason": supersedes_reason, "files": fh,
                 "files_manifest_sha256": sha(canon(fh)), "body_sha256": sha(body.encode()), "predictions_sha256": sha(predictions.encode())})
    _write_once(os.path.join(d, "registration.json"), json.dumps(rec, indent=1, sort_keys=True).encode())
    if prev:   # supersede the old version with a forward pointer (also write-once)
        _write_once(os.path.join(_vdir(world, prev["version"], runs), "superseded_by.json"), json.dumps(_seal({"world": world, "version": prev["version"], "superseded_by": n, "new_record_sha256": rec["record_sha256"], "created_utc": now(), "reason": supersedes_reason}), indent=1, sort_keys=True).encode())
    return rec


def import_legacy(world, prereg_md_path, predictions_path, runs=None):
    """Record a pre-registry (prereg.py) registration as v1 WITHOUT re-freezing anything: the hashes are the ones the legacy file last froze (latest addendum, else original)."""
    _world(world)
    if _versions(world, runs): raise RegistryError("BAD_VERSION", "registry already has versions")
    body = open(prereg_md_path).read(); preds = open(predictions_path).read()
    adds = re.findall(r"Frozen-hashes \(full\) at addendum: (.*)", body)
    if adds: fh = dict(kv.split("=", 1) for kv in adds[-1].split())
    else: fh = {f: h for f, h in re.findall(r"^- (\S+): ([0-9a-f]{64})$", body, re.M)}
    if not fh: raise RegistryError("CORRUPT", "no frozen hashes found in the legacy registration")
    d = _vdir(world, 1, runs); os.makedirs(d); _write_once(os.path.join(d, "PREREG.md"), body.encode()); _write_once(os.path.join(d, "PREDICTIONS.md"), preds.encode())
    rec = _seal({"schema": 1, "world": world, "version": 1, "created_utc": now(), "supersedes": None, "supersedes_reason": None, "legacy_import": True, "files": dict(sorted(fh.items())),
                 "files_manifest_sha256": sha(canon(dict(sorted(fh.items())))), "body_sha256": sha(body.encode()), "predictions_sha256": sha(preds.encode())})
    _write_once(os.path.join(d, "registration.json"), json.dumps(rec, indent=1, sort_keys=True).encode()); return rec


def _load(world, n, runs=None):
    p = os.path.join(_vdir(world, n, runs), "registration.json")
    try: return json.load(open(p))
    except Exception as e: raise RegistryError("CORRUPT", f"cannot read {p}: {type(e).__name__}")

def _addenda(world, n, runs=None):
    d = os.path.join(_vdir(world, n, runs), "addenda")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def amend(world, n, kind, text, runs=None):
    if kind not in ("clarification", "deviation"): raise RegistryError("BAD_KIND", "addenda may only be 'clarification' or 'deviation'; a change to the freeze needs a new version")
    if not isinstance(text, str) or not text.strip(): raise RegistryError("EMPTY_FIELD", "addendum text is empty")
    verify(world, n, runs, allow_file_drift=(kind == "deviation"))
    rec = _load(world, n, runs); names = _addenda(world, n, runs); prev = rec["record_sha256"]
    if names: prev = json.load(open(os.path.join(_vdir(world, n, runs), "addenda", names[-1])))["record_sha256"]
    d = os.path.join(_vdir(world, n, runs), "addenda"); os.makedirs(d, exist_ok=True); seq = len(names) + 1
    a = _seal({"seq": seq, "kind": kind, "text": text, "created_utc": now(), "prev_record_sha256": prev, "files_seen": file_hashes(list(rec["files"]))})
    _write_once(os.path.join(d, f"{seq:04d}.json"), json.dumps(a, indent=1, sort_keys=True).encode()); return a


def verify(world, n=None, runs=None, allow_file_drift=False):
    _world(world); vs = _versions(world, runs)
    if not vs: raise RegistryError("NO_REGISTRATION", f"no registration for {world}")
    if [f"v{x}" for x in vs] != [f"v{i}" for i in range(1, len(vs) + 1)]: raise RegistryError("CORRUPT", f"non-contiguous versions {vs}")
    n = vs[-1] if n is None else int(n)
    if n not in vs: raise RegistryError("NO_REGISTRATION", f"no {world} v{n}")
    if os.path.exists(os.path.join(_vdir(world, n, runs), "superseded_by.json")): raise RegistryError("SUPERSEDED", f"{world} v{n} is superseded")
    rec = _load(world, n, runs); d = _vdir(world, n, runs)
    if not _record_ok(rec) or rec.get("world") != world or rec.get("version") != n: raise RegistryError("CORRUPT", "registration record hash mismatch")
    for fn, key in (("PREREG.md", "body_sha256"), ("PREDICTIONS.md", "predictions_sha256")):
        try: ok = sha(open(os.path.join(d, fn), "rb").read()) == rec[key]
        except Exception: ok = False
        if not ok: raise RegistryError("TAMPERED", f"{fn} does not match the registered hash")
    if n > 1:
        prev = _load(world, n - 1, runs)
        if not rec.get("supersedes") or rec["supersedes"].get("record_sha256") != prev.get("record_sha256"): raise RegistryError("CORRUPT", "supersedes link does not match the previous record")
    prev = rec["record_sha256"]
    for i, name in enumerate(_addenda(world, n, runs), 1):
        a = json.load(open(os.path.join(d, "addenda", name)))
        if name != f"{i:04d}.json" or a.get("seq") != i or not _record_ok(a) or a.get("prev_record_sha256") != prev: raise RegistryError("CORRUPT", f"addendum chain broken at {name}")
        prev = a["record_sha256"]
    if not allow_file_drift:
        cur = file_hashes(list(rec["files"])); bad = [f for f in rec["files"] if cur[f] != rec["files"][f]]
        if bad: raise RegistryError("FROZEN_FILE_CHANGED", f"changed since registration: {bad}. A change to the freeze needs a new version (register N+1), not an addendum.")
    return rec


def run_eligibility(run_dir, world, runs=None):
    """(ok, [reasons]). A run counts toward a report only if it is a scored run of the ACTIVE registration with untouched code."""
    reasons = []
    try: rec = verify(world, None, runs)
    except RegistryError as e: return False, [f"no active registration: {e.code}"]
    try: m = json.load(open(os.path.join(run_dir, "run_manifest.json")))
    except Exception: return False, ["missing or unreadable run_manifest.json"]
    if not isinstance(m, dict) or m.get("schema_version") != 1: reasons.append("bad manifest schema")
    else:
        if m.get("run_kind") != "scored": reasons.append(f"run_kind={m.get('run_kind')!r}")
        if m.get("registration_hash") != rec["record_sha256"]: reasons.append("registration_hash is not the active registration")
        if m.get("code_hashes") != rec["files"]: reasons.append("code hashes at init differ from the registration")
        if m.get("run_id") != os.path.basename(os.path.normpath(run_dir)): reasons.append("run_id does not match directory name")
    return (not reasons), reasons


def _cli(a):
    c = a[1] if len(a) > 1 else ""
    opt = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    try:
        if c == "register" and len(a) >= 4:
            rec = register(a[2], a[3], open(opt("--body")).read(), open(opt("--predictions")).read(), (opt("--files") or "").split(","), supersedes_reason=opt("--supersedes-reason"))
            print(json.dumps({"ok": True, "world": rec["world"], "version": rec["version"], "record_sha256": rec["record_sha256"]}))
        elif c == "amend" and len(a) == 6: r = amend(a[2], a[3], a[4], a[5]); print(json.dumps({"ok": True, "seq": r["seq"], "record_sha256": r["record_sha256"]}))
        elif c == "verify" and len(a) in (3, 4): r = verify(a[2], a[3] if len(a) == 4 else None); print(json.dumps({"ok": True, "world": r["world"], "version": r["version"], "record_sha256": r["record_sha256"]}))
        elif c == "status" and len(a) == 3:
            try: r = verify(a[2]); print(f"{a[2]} v{r['version']}: ACTIVE, intact ({r['record_sha256'][:12]})")
            except RegistryError as e: print(f"{a[2]}: NOT ACTIVE ({e.code}: {e.msg})")
        else: print(__doc__); return 2
        return 0
    except RegistryError as e: print(json.dumps({"ok": False, "error_code": e.code, "message": e.msg})); return 3
    except (OSError, ValueError, TypeError, IndexError) as e: print(json.dumps({"ok": False, "error_code": "USAGE", "message": type(e).__name__})); return 2


if __name__ == "__main__": sys.exit(_cli(sys.argv))
