"""Backtest Lab cockpit — a stdlib HTTP view on the data room (bck.mex-traders.com).

Reads $LAB_DIR/index.json + results/<run_id>/ and renders the runs in the MEX
house style. Lets you upload a raw platform export straight from the browser:
it streams to disk, normalizes to the canonical schema, and catalogs it — no scp.

No numpy/pandas: the dashboard reads JSON and the upload path uses the stdlib
normalizer/catalog. Run:  LAB_DIR=/data/lab python -m backtest.lab.lab_viewer
Env: LAB_PORT (8090), LAB_PASSWORD (owner gate; unset = open), LAB_SECRET.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .datasets import write_catalog
from .insights import build_journey
from .normalize import to_canonical
from .paths import datasets_dir, ensure_dirs, lab_root, results_dir
from .runs import load_index

_PASSWORD = os.environ.get("LAB_PASSWORD", "")
_SECRET = (os.environ.get("LAB_SECRET", "") or "mex-lab-dev-secret").encode()
_PORT = int(os.environ.get("LAB_PORT", "8090"))
_STARTED = time.monotonic()


# --------------------------------------------------------------------------- #
# Auth (optional signed cookie; disabled when LAB_PASSWORD is unset)
# --------------------------------------------------------------------------- #
def _sign(v: str) -> str:
    return hmac.new(_SECRET, v.encode(), hashlib.sha256).hexdigest()


def _make_cookie() -> str:
    exp = str(int(time.time()) + 7 * 86400)
    return f"{exp}.{_sign(exp)}"


def _cookie_ok(c: str) -> bool:
    try:
        exp, sig = c.split(".", 1)
        return hmac.compare_digest(sig, _sign(exp)) and int(exp) > time.time()
    except Exception:
        return False


def _authed(handler: "Handler") -> bool:
    if not _PASSWORD:
        return True
    raw = handler.headers.get("Cookie", "")
    for part in raw.split(";"):
        if part.strip().startswith("labauth="):
            return _cookie_ok(part.strip()[len("labauth="):])
    return False


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def _runs() -> list[dict]:
    idx = load_index()
    idx.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return idx


def _run_detail(run_id: str) -> dict | None:
    d = results_dir() / run_id
    rj = d / "run.json"
    if not rj.exists():
        return None
    try:
        return json.loads(rj.read_text())
    except Exception:
        return None


def _specs_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "specs"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _datasets() -> list[dict]:
    """Datasets in the data room that are ready to run (have a canonical/data CSV)."""
    out = []
    d = datasets_dir()
    if not d.exists():
        return out
    for sub in sorted(p for p in d.iterdir() if p.is_dir()):
        canon, raw = sub / "canonical.csv", sub / "data.csv"
        f = canon if canon.exists() else (raw if raw.exists() else None)
        if not f:
            continue
        sym, rows = "", None
        man = sub / "manifest.json"
        if man.exists():
            try:
                m = json.loads(man.read_text())
                sym, rows = m.get("symbol", ""), m.get("rows")
            except Exception:
                pass
        out.append({"name": sub.name, "file": str(f), "symbol": sym, "rows": rows})
    return out


def _specs() -> list[dict]:
    from ..spec import validate_file, spec_to_config, describe_config
    out = []
    for p in sorted(_specs_dir().glob("*.yaml")):
        row = {"kind": "spec", "id": f"spec:{p.name}", "name": p.name}
        try:
            rs = validate_file(p)
            cfg, unmapped = spec_to_config(rs)
            row["title"] = rs.name
            row["preset"] = rs.base_preset
            row["groups"] = list(rs.groups.keys())
            row["desc"] = describe_config(cfg)
            row["unmapped"] = unmapped
        except Exception as e:               # never let one bad spec break the list
            row["error"] = str(e)
        out.append(row)
    try:
        from ..config import PRESETS
        for n, c in PRESETS.items():
            if n.startswith("MECH_"):
                continue                      # neutral discovery mechanics, not strategies
            row = {"kind": "preset", "id": f"preset:{n}", "name": f"{n} (preset)", "title": n}
            try:
                row["desc"] = describe_config(c)
            except Exception:
                pass
            out.append(row)
    except Exception:
        pass
    return out


# --- 4th-variant builder (framework §4) ------------------------------------ #
def _builder_options() -> dict:
    """Building blocks the front-end offers: setup-classes -> valid entries,
    the coherent filters, the regime vocabulary for the gate, and base presets."""
    from ..generator import SETUP_ENTRIES
    from ..indicators import REGIME_LABELS
    from ..config import PRESETS
    return {
        "setups": {sc: [g for g, _ in opts] for sc, opts in SETUP_ENTRIES.items()},
        "confluence_entry": ["silver_bullet"],
        "filters": ["vwap", "cvd_delta"],
        "regimes": [r for r in REGIME_LABELS if r != "Indecision"],
        "base_presets": sorted(PRESETS),
    }


def _builder_build(body: dict) -> dict:
    from ..generator import spec_from_selection
    from ..spec import load_registry
    return spec_from_selection(
        load_registry(),
        setup_class=body.get("setup_class") or "trend_pullback",
        entry=body.get("entry") or None,
        filters=[f for f in (body.get("filters") or []) if f],
        regime_filter=[r for r in (body.get("regime_filter") or []) if r],
        base_asset=body.get("base_asset") or "NQ",
        base_preset=body.get("base_preset") or None,
        name=body.get("name") or "custom",
        timeframe=body.get("timeframe") or None,
    )


def _builder_preview(body: dict) -> tuple[dict, int]:
    from ..spec import load_registry, validate_spec, spec_to_config, describe_config
    from ..scoring import score_strategy
    try:
        spec = _builder_build(body)
        cfg, unmapped = spec_to_config(validate_spec(spec, load_registry()))
        desc = describe_config(cfg)
        rf = [r for r in (body.get("regime_filter") or []) if r]
        regime = rf[0] if len(rf) == 1 else None      # sharpen L1 only if a single regime
        desc["score"] = score_strategy(desc, regime=regime, setup_class=spec.get("setup_class"))
        return {"ok": True, "spec": spec, "desc": desc, "unmapped": unmapped}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 200


def _builder_save(body: dict) -> tuple[dict, int]:
    import yaml
    from ..spec import load_registry, validate_spec
    try:
        raw = body.get("name") or "custom"
        safe = "".join(c for c in raw if c.isalnum() or c in "-_") or "custom"
        if not safe.startswith("custom"):
            safe = "custom_" + safe                    # namespace user-built specs
        spec = _builder_build({**body, "name": safe})
        validate_spec(spec, load_registry())           # never write an invalid spec
        path = _specs_dir() / f"{safe}.yaml"
        path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
        return {"ok": True, "id": f"spec:{safe}.yaml", "name": f"{safe}.yaml"}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 200


# --- backtest jobs (subprocess into the bt-venv engine) -------------------- #
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _run_job(job_id: str, cmd: list[str]) -> None:
    def upd(**k):
        with _JOBS_LOCK:
            _JOBS[job_id].update(**k)
    upd(status="running")
    try:
        # Cap BLAS/OpenMP thread pools in every job: the backtest tools parallelize
        # with worker PROCESSES, so BLAS threads only oversubscribe the 2 cores —
        # and BLAS thread pools are fork-unsafe: a pool created AFTER heavy numpy
        # work can inherit a locked mutex and deadlock its children (seen as
        # auto-tune parking at a lever boundary on the VPS but not elsewhere).
        job_env = dict(os.environ)
        for v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                  "NUMEXPR_NUM_THREADS"):
            job_env.setdefault(v, "1")
        p = subprocess.Popen(cmd, cwd=str(_repo_root()), env=job_env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1)
        log, run_ids, progress = [], [], None
        for line in p.stdout:
            line = line.rstrip()
            if line.startswith("PROGRESS "):
                # machine-readable: "PROGRESS <done> <total> <note...>" — parsed
                # into a % bar, kept OUT of the human log.
                try:
                    _, done_s, total_s, *rest = line.split(" ", 3)
                    done_n, total_n = int(done_s), int(total_s)
                    pct = round(100 * done_n / total_n) if total_n else 0
                    progress = {"done": done_n, "total": total_n, "pct": pct,
                                "note": (rest[0] if rest else "")}
                    with _JOBS_LOCK:
                        _JOBS[job_id]["progress"] = progress
                except Exception:
                    pass
                continue
            if line.startswith("SWEEP_JSON "):
                try:
                    with _JOBS_LOCK:
                        _JOBS[job_id]["sweep"] = json.loads(line[len("SWEEP_JSON "):])
                except Exception:
                    pass
                continue
            if line.startswith("AUTOTUNE_JSON "):
                try:
                    with _JOBS_LOCK:
                        _JOBS[job_id]["autotune"] = json.loads(line[len("AUTOTUNE_JSON "):])
                except Exception:
                    pass
                continue
            log.append(line)
            if "recorded run " in line:
                try:
                    run_ids.append(line.split("recorded run ", 1)[1].split(" ")[0])
                except Exception:
                    pass
            with _JOBS_LOCK:
                _JOBS[job_id]["log"] = log[-80:]
                _JOBS[job_id]["run_ids"] = run_ids
        p.wait()
        rc = p.returncode
        if rc == 0:
            upd(status="done", rc=rc, error=None)
        else:
            # A non-zero exit means the run failed — surface WHY in the UI, not a
            # silent "done". SIGKILL (137 / -9) is almost always the OOM killer on
            # a big 1m dataset; sub-runs that died echo "SUBRUN-FAIL <sym> rc=...".
            tail = "\n".join(log[-12:])
            killed = rc in (-9, 137) or "rc=137" in tail or "rc=-9" in tail
            subfails = [l for l in log if l.startswith("SUBRUN-FAIL")]
            if killed:
                err = ("Out of memory — a run was killed by the system. This dataset is "
                       "large on 1m; run one contract at a time, set a 'Coarse since' "
                       "date, or use a higher timeframe.")
            elif subfails:
                err = "A run failed: " + "; ".join(subfails)
            else:
                err = f"The run exited with code {rc}. See the log for details."
            upd(status="error", rc=rc, error=err)
    except Exception as e:
        upd(status="error", error=f"Could not start the run: {e}")


def _start_job(dataset: str, spec: str, tf: str, lens: str, micro: bool = False) -> tuple[dict, int]:
    from ..config import PRESETS, TIMEFRAMES, micro_twin
    ds = {d["name"]: d for d in _datasets()}
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    tfs = [t.strip().lower() for t in tf.split(",") if t.strip()]
    bad = [t for t in tfs if t not in TIMEFRAMES]
    if not tfs or bad:
        return {"error": f"bad timeframe(s): {bad or tf!r}"}, 400
    if lens not in ("research", "funnel", "funded"):
        return {"error": "lens must be research, funnel or funded"}, 400

    cmd = [sys.executable, "-m", "backtest.run", "--data", ds[dataset]["file"],
           "--tf", ",".join(tfs), "--lab"]
    if spec.startswith("preset:"):
        name = spec.split(":", 1)[1]
        if name not in PRESETS:
            return {"error": f"unknown preset {name!r}"}, 400
        cmd += ["--preset", name]
    else:
        name = spec.split(":", 1)[1] if spec.startswith("spec:") else spec
        f = (_specs_dir() / name).resolve()
        if f.suffix != ".yaml" or f.parent != _specs_dir().resolve() or not f.exists():
            return {"error": f"unknown spec {name!r}"}, 400
        cmd += ["--spec", f"backtest/specs/{f.name}"]
    cmd += {"research": ["--research"], "funnel": ["--funnel"], "funded": ["--funded"]}[lens]

    # The DATASET decides the contract: always pass its symbol, so a preset ported
    # from another instrument (EL_TESORO carries a GC contract) can never silently
    # simulate the wrong contract on this data — that mislabels the run AND makes
    # the results meaningless (GC ticks on 6B prices = zero trades).
    sym = ds[dataset].get("symbol") or ""
    if sym:
        cmd += ["--symbol", sym]

    # Optional micro-twin comparison: run the full contract AND its micro (GC+MGC,
    # ES+MES, …) side by side — same price data, different contract size — so both
    # land in Runs next to each other. Two SEPARATE processes (memory freed between
    # them, so the big 1m frame doesn't OOM), but each sub-run's exit code is
    # captured: a killed/failed first contract echoes SUBRUN-FAIL and the whole job
    # exits non-zero, so the UI shows an error instead of a silent "done".
    twin = micro_twin(sym) if (micro and sym) else None
    if twin:
        import shlex
        a = " ".join(shlex.quote(x) for x in cmd)
        b = " ".join(shlex.quote(x) for x in cmd[:-1] + [twin])   # same cmd, twin symbol
        script = (f'{a}; e1=$?; [ $e1 -ne 0 ] && echo "SUBRUN-FAIL {sym} rc=$e1"; '
                  f'{b}; e2=$?; [ $e2 -ne 0 ] && echo "SUBRUN-FAIL {twin} rc=$e2"; '
                  f'[ $e1 -ne 0 -o $e2 -ne 0 ] && exit 1 || exit 0')
        run_cmd = ["sh", "-c", script]
        label = " ".join(cmd[2:]) + f"  [{sym}+{twin}]"
    else:
        run_cmd, label = cmd, " ".join(cmd[2:])

    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "queued", "log": [], "run_ids": [], "cmd": label}
    threading.Thread(target=_run_job, args=(job_id, run_cmd), daemon=True).start()
    return {"job": job_id}, 200


def _spawn(cmd: list[str], label: str) -> dict:
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "queued", "log": [], "run_ids": [], "cmd": label}
    threading.Thread(target=_run_job, args=(job_id, cmd), daemon=True).start()
    return {"job": job_id}


def _start_generate(q) -> tuple[dict, int]:
    from ..config import TIMEFRAMES
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    tf = (q.get("tf") or ["5m"])[0].strip().lower()
    if tf not in TIMEFRAMES:
        return {"error": f"unknown timeframe {tf!r}"}, 400

    def _int(name, dflt):
        try:
            return str(int((q.get(name) or [dflt])[0]))
        except Exception:
            return str(dflt)

    def _flt(name, dflt):
        try:
            return str(float((q.get(name) or [dflt])[0]))
        except Exception:
            return str(dflt)

    symbol = ds[dataset].get("symbol") or "NQ"
    # No --base-preset: the mill SAMPLES neutral mechanics per candidate, so the
    # stop/target is a discovered outcome, never assumed from the asset.
    cmd = [sys.executable, "-m", "backtest.generate", "--data", ds[dataset]["file"],
           "--n", _int("n", 100), "--tf", tf, "--holdout-days", _int("holdout", 365),
           "--min-trades", _int("min_trades", 100), "--min-pf", _flt("min_pf", 1.1),
           "--max-groups", _int("max_groups", 5),
           "--base-asset", symbol, "--seed", _int("seed", 0), "--top", _int("top", 50), "--lab"]
    since = (q.get("since") or [""])[0].strip()
    if since:
        cmd += ["--coarse-since", since]
    if (q.get("pao") or ["0"])[0] in ("1", "true", "on"):
        cmd += ["--price-action-only"]
    setup = (q.get("setup_class") or [""])[0].strip()
    if setup and setup != "any":
        cmd += ["--setup-class", setup]
    regimes = (q.get("regimes") or [""])[0].strip()
    if regimes:
        cmd += ["--regimes", regimes]
    return _spawn(cmd, "discover " + " ".join(cmd[cmd.index("--n"):])), 200


def _start_verify(q) -> tuple[dict, int]:
    from ..config import TIMEFRAMES
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    tf = (q.get("tf") or ["5m"])[0].strip().lower()
    if tf not in TIMEFRAMES:
        return {"error": f"unknown timeframe {tf!r}"}, 400
    seed = "0"
    try:
        seed = str(int((q.get("seed") or ["0"])[0]))
    except Exception:
        pass
    cfile = lab_root() / f"candidates_seed{seed}.json"
    if not cfile.exists():
        return {"error": f"no {cfile.name} yet — run Generate first"}, 400
    hold = "365"
    try:
        hold = str(int((q.get("holdout") or ["365"])[0]))
    except Exception:
        pass
    cmd = [sys.executable, "-m", "backtest.verify", "--data", ds[dataset]["file"],
           "--candidates", str(cfile), "--tf", tf, "--holdout-days", hold,
           "--base-asset", ds[dataset].get("symbol") or "NQ", "--lab"]
    return _spawn(cmd, f"verify seed{seed}"), 200


def _start_sweep(q) -> tuple[dict, int]:
    """Phase 3: fine-grained sweep of one parameter over a set of values."""
    from ..config import PRESETS, TIMEFRAMES
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    tf = (q.get("tf") or ["1m"])[0].strip().lower()
    if tf not in TIMEFRAMES:
        return {"error": f"unknown timeframe {tf!r}"}, 400
    auto = (q.get("auto") or ["0"])[0] in ("1", "true", "on")
    cmd = [sys.executable, "-m", "backtest.sweep", "--data", ds[dataset]["file"], "--tf", tf]
    if auto:
        cmd += ["--auto"]
    else:
        param = (q.get("param") or [""])[0].strip()
        if not param:
            return {"error": "pick a parameter to sweep"}, 400
        values = (q.get("values") or [""])[0].strip()
        if not values:
            return {"error": "give comma-separated values (e.g. 40,60,80,100)"}, 400
        cmd += ["--param", param, "--values", values]
    spec = (q.get("spec") or [""])[0]
    if spec.startswith("preset:"):
        name = spec.split(":", 1)[1]
        if name not in PRESETS:
            return {"error": f"unknown preset {name!r}"}, 400
        cmd += ["--preset", name]
    else:
        name = spec.split(":", 1)[1] if spec.startswith("spec:") else spec
        f = (_specs_dir() / name).resolve()
        if f.suffix != ".yaml" or f.parent != _specs_dir().resolve() or not f.exists():
            return {"error": f"unknown strategy {name!r}"}, 400
        cmd += ["--spec", f"backtest/specs/{f.name}"]
    if ds[dataset].get("symbol"):
        cmd += ["--symbol", ds[dataset]["symbol"]]
    # no funded flag: the sweep always measures raw edge AND funded survival —
    # suitability is an outcome of the test, never a goal chosen up front.
    since = (q.get("since") or [""])[0].strip()
    if since:
        cmd += ["--coarse-since", since]
    try:
        hold = int((q.get("holdout") or ["0"])[0])
        if hold > 0:
            cmd += ["--holdout-days", str(hold)]
    except Exception:
        pass
    return _spawn(cmd, "auto-tune" if auto else f"sweep {(q.get('param') or [''])[0]}"), 200


def _candidates() -> dict:
    root = lab_root()
    files = sorted(root.glob("verified_seed*.json")) or sorted(root.glob("candidates_seed*.json"))
    if not files:
        return {"rows": [], "source": None}
    f = files[-1]
    try:
        data = json.loads(f.read_text())
    except Exception:
        return {"rows": [], "source": f.name}
    rows = []
    for c in data:
        spec = c.get("spec") or {}
        v = c.get("verdict") or {}
        kis = c.get("kpis_is") or c.get("kpis") or {}
        rows.append({"name": spec.get("name") or c.get("name", ""),
                     "groups": list((spec.get("groups") or c.get("groups") or {}).keys()),
                     "is_pf": v.get("is_pf") if v else kis.get("profit_factor"),
                     "is_trades": kis.get("trades"),
                     "oos_pf": v.get("oos_pf"), "retain": v.get("retain"),
                     "oos_trades": v.get("oos_trades"), "pass": v.get("pass")})
    rows.sort(key=lambda r: (r.get("oos_pf") if r.get("oos_pf") is not None else -1,
                             r.get("is_pf") or -1), reverse=True)
    return {"rows": rows, "source": f.name, "verified": f.name.startswith("verified")}


def _fleet_stats(runs: list[dict]) -> dict:
    assets = sorted({r.get("asset", "") for r in runs if r.get("asset")})
    strats = sorted({r.get("strategy", "") for r in runs if r.get("strategy")})
    best = None
    for r in runs:
        pf = (r.get("kpis") or {}).get("profit_factor")
        if pf is not None and (best is None or pf > best.get("kpis", {}).get("profit_factor", -1)):
            best = r
    return {"runs": len(runs), "assets": assets, "strategies": strats,
            "best": best, "latest": runs[0] if runs else None}


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "MEXLab/1.0"

    def log_message(self, *a):  # quiet
        pass

    # -- helpers --
    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str), "application/json")

    # -- GET --
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/healthz":
            return self._send(200, "ok", "text/plain")
        if u.path == "/favicon.svg":
            return self._send(200, _FAVICON, "image/svg+xml",
                              {"Cache-Control": "public, max-age=86400"})
        if u.path == "/login":
            return self._send(200, LOGIN_HTML)
        if not _authed(self):
            return self._send(200, LOGIN_HTML)
        if u.path == "/":
            return self._send(200, PAGE_HTML)
        if u.path == "/api/runs":
            runs = _runs()
            return self._json({"runs": runs, "stats": _fleet_stats(runs),
                               "status": {"uptime_s": int(time.monotonic() - _STARTED),
                                          "lab_dir": str(datasets_dir().parent),
                                          "auth": bool(_PASSWORD)}})
        if u.path == "/api/run":
            rid = (q.get("id") or [""])[0]
            det = _run_detail(rid)
            return self._json(det or {"error": "not found"}, 200 if det else 404)
        if u.path == "/api/journey":
            strat = (q.get("strategy") or [""])[0]
            return self._json(build_journey(_runs(), strat or None))
        if u.path == "/api/datasets":
            return self._json({"datasets": _datasets()})
        if u.path == "/api/specs":
            return self._json({"specs": _specs()})
        if u.path == "/api/run/status":
            j = (q.get("job") or [""])[0]
            with _JOBS_LOCK:
                st = dict(_JOBS.get(j) or {})
            return self._json(st or {"error": "unknown job"}, 200 if st else 404)
        if u.path == "/api/candidates":
            return self._json(_candidates())
        if u.path == "/api/builder/options":
            return self._json(_builder_options())
        if u.path == "/api/fleet":
            from .fleet import load_fleet
            return self._json({"fleet": load_fleet()})
        return self._send(404, "not found", "text/plain")

    # -- POST --
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/login":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8", "replace")
            pw = urllib.parse.parse_qs(body).get("password", [""])[0]
            if _PASSWORD and hmac.compare_digest(pw, _PASSWORD):
                return self._send(303, "", headers={
                    "Location": "/", "Set-Cookie": f"labauth={_make_cookie()}; Path=/; HttpOnly; SameSite=Lax"})
            return self._send(200, LOGIN_HTML.replace("<!--ERR-->", "Wrong password."))
        if not _authed(self):
            return self._json({"error": "unauthorized"}, 401)
        if u.path == "/api/upload":
            return self._upload(q)
        if u.path == "/api/run":
            body, code = _start_job((q.get("dataset") or [""])[0], (q.get("spec") or [""])[0],
                                    (q.get("tf") or ["5m"])[0], (q.get("lens") or ["research"])[0],
                                    micro=(q.get("micro") or ["0"])[0] in ("1", "true", "on"))
            return self._json(body, code)
        if u.path == "/api/generate":
            body, code = _start_generate(q)
            return self._json(body, code)
        if u.path == "/api/verify":
            body, code = _start_verify(q)
            return self._json(body, code)
        if u.path == "/api/sweep":
            body, code = _start_sweep(q)
            return self._json(body, code)
        if u.path in ("/api/builder/preview", "/api/builder/save"):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8", "replace") if length > 0 else "{}"
            try:
                jb = json.loads(raw)
            except Exception:
                jb = {}
            fn = _builder_preview if u.path.endswith("preview") else _builder_save
            b, code = fn(jb)
            return self._json(b, code)
        if u.path in ("/api/fleet/promote", "/api/fleet/demote"):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8", "replace") if length > 0 else "{}"
            try:
                jb = json.loads(raw)
            except Exception:
                jb = {}
            from .fleet import promote, demote
            try:
                fleet = demote(jb.get("id")) if u.path.endswith("demote") else promote(jb)
                return self._json({"ok": True, "fleet": fleet})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)})
        return self._send(404, "not found", "text/plain")

    def _upload(self, q):
        name = (q.get("name") or ["dataset"])[0]
        symbol = (q.get("symbol") or [""])[0]
        # sanitize name -> a datasets/<name>/ folder
        safe = "".join(c for c in name if c.isalnum() or c in "-_") or "dataset"
        ddir = datasets_dir() / safe
        ddir.mkdir(parents=True, exist_ok=True)
        raw = ddir / "raw.csv"
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return self._json({"error": "empty body"}, 400)
        # stream body -> disk (chunked; big-file friendly)
        remaining, wrote = length, 0
        with open(raw, "wb") as f:
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
                wrote += len(chunk)
        try:
            canon = ddir / "canonical.csv"
            _, rows = to_canonical(raw, canon)
            mpath = write_catalog(canon, symbol=symbol)
            manifest = json.loads(Path(mpath).read_text())
        except Exception as e:
            return self._json({"error": f"normalize/catalog failed: {e}",
                               "bytes": wrote}, 422)
        return self._json({"ok": True, "dataset": safe, "rows": rows,
                           "bytes": wrote, "canonical": str(canon), "manifest": manifest})


def main():
    ensure_dirs()
    srv = ThreadingHTTPServer(("0.0.0.0", _PORT), Handler)
    print(f"MEX Lab cockpit on :{_PORT}  (LAB_DIR={datasets_dir().parent}, "
          f"auth={'on' if _PASSWORD else 'OFF'})")
    srv.serve_forever()


# --------------------------------------------------------------------------- #
# Templates (MEX house style)
# --------------------------------------------------------------------------- #
_CSS = """
:root{
 --abyss:#030F28;--deep:#081D46;--surface:#0E2A5E;--line:rgba(242,235,218,.17);
 --sand:#F2EBDA;--sub:rgba(242,235,218,.60);--dim:rgba(242,235,218,.42);
 --gold:#E8B54F;--gold2:#B98526;--azure:#5AA2FF;--rose:#E0796E;
 --panel:rgba(14,42,94,.42);
 --display:'Bricolage Grotesque',system-ui,sans-serif;
 --body:'Instrument Sans',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace}
*{box-sizing:border-box}
body{margin:0;color:var(--sand);font-family:var(--body);font-size:14px;line-height:1.55;background:var(--abyss)}
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background:
 radial-gradient(1000px 560px at 84% -10%,rgba(232,181,79,.16),transparent 60%),
 radial-gradient(820px 620px at -2% 40%,rgba(90,162,255,.13),transparent 62%),
 linear-gradient(180deg,#030F28,#061735 45%,#030F28)}
a{color:var(--azure)}.wrap{max-width:1180px;margin:0 auto;padding:22px}
.brand{display:flex;align-items:center;gap:9px}
.brand .wm{font-family:var(--display);font-weight:800;letter-spacing:-.03em;font-size:18px;color:var(--sand)}
.brand .wm em{font-style:normal;font-weight:400;letter-spacing:.10em;margin-left:.35em;color:var(--sub)}
.tag-lab{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);border:1px solid var(--line);padding:3px 8px;border-radius:2px;margin-left:12px}
.muted{color:var(--sub);font-family:var(--mono);font-size:11px;letter-spacing:.04em}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:14px 18px;min-width:130px}
.kpi .v{font-family:var(--display);font-size:26px;font-weight:600;letter-spacing:-.02em;color:var(--gold)}
.kpi .l{font-family:var(--mono);font-size:10px;color:var(--sub);text-transform:uppercase;letter-spacing:.14em;margin-top:6px}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0}
select,input,button{background:var(--deep);color:var(--sand);border:1px solid var(--line);border-radius:2px;padding:8px 11px;font-size:13px;font-family:var(--body)}
button{cursor:pointer;font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase}
button.go{background:linear-gradient(120deg,var(--gold),#F3CE7C);color:#0B1428;border:none;font-weight:700}
button.go:hover{filter:brightness(1.06)}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{padding:9px 10px;text-align:right;border-bottom:1px solid rgba(242,235,218,.08);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--sub);font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;cursor:pointer}
tr:hover td{background:rgba(14,42,94,.5)}
.pill{padding:2px 8px;border-radius:2px;font-family:var(--mono);font-size:10px}
.pos{color:var(--azure)}.neg{color:var(--rose)}
.tag{background:var(--deep);color:var(--sub);padding:2px 8px;border-radius:2px;font-family:var(--mono);font-size:10px;letter-spacing:.06em}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:18px;margin-top:16px}
.up{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.foot{color:var(--dim);font-family:var(--mono);font-size:11px;margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
#drop{border:1px dashed var(--line);border-radius:3px;padding:14px;text-align:center;color:var(--sub);flex:1;min-width:220px;cursor:pointer}
.hidden{display:none}#msg{font-size:12px}
.jbar{display:none;margin:12px 0 0}
.jbar-track{height:8px;background:var(--deep);border:1px solid var(--line);border-radius:99px;overflow:hidden}
.jbar-fill{height:100%;width:0;background:linear-gradient(90deg,var(--gold2),var(--gold));border-radius:99px;transition:width .5s ease}
.jbar-cap{font-family:var(--mono);font-size:11px;color:var(--sub);margin-top:6px;letter-spacing:.03em}
.jbar-cap .jbar-pct{color:var(--gold);font-weight:700}
.jerr{display:none;margin:10px 0 0;padding:11px 13px;background:rgba(224,121,110,.12);
 border:1px solid var(--rose);border-radius:3px;color:var(--sand);font-size:12.5px;line-height:1.5}
.jerr b{color:var(--rose)}
.lens{border:1px solid var(--line);border-radius:4px;padding:14px 16px;margin-top:10px;background:rgba(8,29,70,.32)}
.lens h3{margin:0 0 2px;font-family:var(--display);font-weight:600;font-size:15px;color:var(--gold);letter-spacing:-.01em}
.lens .q{color:var(--sub);font-size:12px;margin-bottom:8px}
.ins{display:flex;gap:9px;align-items:flex-start;padding:5px 0;font-size:13px;border-top:1px solid rgba(242,235,218,.07)}
.ins:first-of-type{border-top:none}.dot{width:7px;height:7px;border-radius:50%;margin-top:6px;flex:none}
.t-good{background:var(--azure)}.t-warn{background:var(--gold)}.t-bad{background:var(--rose)}.t-info{background:var(--sub)}
.verdict{border-radius:3px;padding:12px 14px;font-weight:600;border:1px solid}
.v-good{background:rgba(90,162,255,.10);border-color:rgba(90,162,255,.40);color:var(--azure)}
.v-warn{background:rgba(232,181,79,.10);border-color:rgba(232,181,79,.40);color:var(--gold)}
.v-bad{background:rgba(224,121,110,.10);border-color:rgba(224,121,110,.40);color:var(--rose)}
.v-info{background:rgba(14,42,94,.50);border-color:var(--line);color:var(--sub)}
.lensrow{font-family:var(--mono);font-size:10px;color:var(--sub);margin-top:6px;letter-spacing:.06em}
.lib{display:grid;grid-template-columns:repeat(auto-fill,minmax(288px,1fr));gap:10px;margin-top:12px}
.card{background:rgba(8,29,70,.34);border:1px solid var(--line);border-radius:4px;padding:12px 13px;cursor:pointer;transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--gold);transform:translateY(-1px)}
.card .ct{font-family:var(--display);font-weight:600;font-size:14px;color:var(--sand);letter-spacing:-.01em}
.card .row{font-family:var(--mono);font-size:10px;color:var(--sub);margin-top:6px;letter-spacing:.02em}
.card .row b{color:var(--gold);font-weight:500}
.fam{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.12em;padding:2px 7px;border-radius:2px;border:1px solid;white-space:nowrap}
.fam-confluence{color:var(--gold);border-color:rgba(232,181,79,.5);background:rgba(232,181,79,.08)}
.fam-reversal{color:var(--rose);border-color:rgba(224,121,110,.5);background:rgba(224,121,110,.08)}
.fam-trend{color:var(--azure);border-color:rgba(90,162,255,.5);background:rgba(90,162,255,.08)}
.fam-momentum{color:#9FD3A8;border-color:rgba(159,211,168,.5);background:rgba(159,211,168,.08)}
.fam-mixed{color:var(--sub);border-color:var(--line);background:rgba(242,235,218,.05)}
/* tabs */
.tabs{display:flex;gap:2px;margin:20px 0 4px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.tabs button{background:none;border:none;border-bottom:2px solid transparent;border-radius:0;color:var(--sub);padding:11px 18px;font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase}
.tabs button:hover{color:var(--sand)}
.tabs button.on{color:var(--gold);border-bottom-color:var(--gold)}
.tab{display:none}.tab.on{display:block}
.sub{font-family:var(--display);font-weight:600;font-size:16px;color:var(--sand);letter-spacing:-.01em}
.fld{font-family:var(--mono);font-size:10px;color:var(--sub);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips label{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;color:var(--sub);background:var(--deep);border:1px solid var(--line);border-radius:2px;padding:5px 9px;cursor:pointer;white-space:nowrap}
.chips label:hover{border-color:var(--gold);color:var(--sand)}
.linkbtn{background:none;border:none;color:var(--azure);padding:6px 4px;font-family:var(--mono);font-size:10px;text-transform:none;letter-spacing:0;cursor:pointer}
.field{display:flex;flex-direction:column;gap:5px}
.field>.fld{margin:0}
.up{align-items:flex-end}
.steps{font-family:var(--mono);font-size:11px;color:var(--sub);margin:2px 0 0;letter-spacing:.02em}
.steps b{color:var(--gold);font-weight:500}
.hint{color:var(--sub);font-family:var(--body);font-size:12px;margin-top:3px}
"""

# Brand mark (the gold "M") for the header, and the favicon (served at /favicon.svg).
_MARK = ('<svg viewBox="0 0 100 100" width="22" height="22" aria-hidden="true">'
         '<defs><linearGradient id="navgold" x1="0" y1="0" x2="1" y2="1">'
         '<stop offset="0" stop-color="#E8B54F"/><stop offset="1" stop-color="#B98526"/></linearGradient></defs>'
         '<path d="M-10.55,69.29 L100.15,69.29 L100.15,72.93 L-10.55,72.93 Z" fill="#F2EBDA" opacity=".42"/>'
         '<path d="M16.85,78 L21.65,41.87 L40.46,69.29 L51.20,69.29 L78,42.03 L83.10,78 L94.92,78 '
         'L86.27,16.94 L46.29,57.59 L46.63,57.59 L14.07,10.13 L5.05,78 Z" fill="url(#navgold)"/></svg>')
_BRAND = f'<a class=brand href="/">{_MARK}<span class=wm>MEX<em>TRADERS</em></span></a>'
_FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#E8B54F"/><stop offset="1" stop-color="#B98526"/></linearGradient></defs>'
            '<rect width="100" height="100" fill="#030F28"/>'
            '<path d="M2,69.95 L98,69.95 L98,75.08 L2,75.08 Z" fill="#F2EBDA" opacity=".52"/>'
            '<path d="M15.57,79 L20.56,41.48 L40.10,69.95 L51.24,69.95 L79.08,41.65 L84.37,79 L96.64,79 '
            'L87.66,15.59 L46.15,57.80 L46.50,57.80 L12.69,8.52 L3.32,79 Z" fill="url(#g)"/></svg>')
_HEAD = ('<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
         '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
         '<link rel=preconnect href="https://fonts.googleapis.com">'
         '<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>'
         '<link rel=stylesheet href="https://fonts.googleapis.com/css2?'
         'family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&'
         'family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap">')

_JS = r"""
const $=s=>document.querySelector(s), money=n=>(n>=0?'+$':'-$')+Math.abs(Math.round(n)).toLocaleString('en-US');
let RUNS=[], STATS={};
function kpi(v,l){return `<div class=kpi><div class=v>${v}</div><div class=l>${l}</div></div>`}
function opt(sel,vals){const cur=sel.value;[...sel.querySelectorAll('option:not(:first-child)')].forEach(o=>o.remove());
  vals.forEach(v=>{const o=document.createElement('option');o.value=o.textContent=v;sel.appendChild(o)});sel.value=cur}
function k(r,path,d){const o=r.kpis||{};return o[path]!==undefined?o[path]:d}
function pfcls(p){return p>=1?'pos':'neg'}
function render(){
  const fa=$('#fAsset').value,fs=$('#fStrat').value,ft=$('#fTf').value,fl=$('#fLens').value;
  const rows=RUNS.filter(r=>(!fa||r.asset==fa)&&(!fs||r.strategy==fs)&&(!ft||r.timeframe==ft)&&(!fl||r.lens==fl));
  $('#count').textContent=rows.length+' / '+RUNS.length+' runs';
  $('#rows').innerHTML=rows.map(r=>{
    const pf=k(r,'profit_factor',null),net=k(r,'net_profit',0),exp=k(r,'expectancy',0),
      win=k(r,'win_rate_pct',null),tr=k(r,'trades',0),dd=k(r,'max_drawdown',0);
    return `<tr data-id="${r.run_id}" style="cursor:pointer">
      <td title="click for detail">${(r.run_id||'').slice(0,42)}</td><td>${r.asset||''}</td>
      <td>${r.strategy||''}</td><td><span class=tag>${r.timeframe||''}</span></td>
      <td><span class=tag>${r.lens||''}</span></td><td>${tr}</td>
      <td>${win==null?'':win.toFixed(0)}</td>
      <td class=${pf==null?'':pfcls(pf)}>${pf==null?'':pf.toFixed(2)}</td>
      <td class=${exp>=0?'pos':'neg'}>${exp?money(exp):''}</td>
      <td class=${net>=0?'pos':'neg'}>${net?money(net):''}</td>
      <td>${dd?'$'+Math.round(dd).toLocaleString():''}</td>
      <td class=muted>${(r.created_at||'').slice(0,16).replace('T',' ')}</td></tr>`}).join('');
  $('#rows').querySelectorAll('tr').forEach(tr=>tr.addEventListener('click',()=>showDetail(tr.dataset.id)));
}
function kvs(obj,pre){return Object.entries(obj||{}).map(([k,v])=>{
  if(v&&typeof v==='object')return kvs(v,(pre?pre+'.':'')+k);
  return `<span class=tag style="margin:2px">${(pre?pre+'.':'')+k}: <b style="color:var(--sand)">${v}</b></span>`}).join('');}
function scoreHtml(desc){
  const sc=desc&&desc.score; if(!sc)return '';
  const comps=Object.entries(sc.components||{}).map(([k,v])=>{
    const L=k.split('_')[0];
    return `<span class=tag style="margin:2px">${L}: <b style="color:var(--sand)">${v}</b></span>`}).join('');
  return `<div style="margin-top:10px"><b>Setup score</b> `
    +`<span class=tag style="color:var(--azure)">${sc.grade} · ${sc.score}/100</span> `
    +`<span class=muted>${sc.note||''}</span>`
    +`<div style="margin-top:5px">${comps}</div></div>`;
}
function edgeHtml(edge){
  if(!edge||!Object.keys(edge).length)return '';
  const fmtpf=v=>(v===null||v===undefined)?'—':(v>1e6?'∞':Number(v).toFixed(2));
  const rows=Object.entries(edge).map(([reg,m])=>{
    const pos=(m.net||0)>=0;
    return `<div class=lensrow style="margin-top:2px;display:flex;gap:10px;align-items:center">`
      +`<span class=tag style="min-width:160px;display:inline-block">${reg}</span>`
      +`<span>PF <b style="color:${(m.profit_factor>=1)?'var(--gold)':'var(--rose)'}">${fmtpf(m.profit_factor)}</b></span>`
      +`<span class=muted>exp <b style="color:${pos?'var(--gold)':'var(--rose)'}">${m.expectancy}</b></span>`
      +`<span class=muted>win ${m.win_rate_pct}%</span>`
      +`<span class=muted>n ${m.trades}</span>`
      +`<span class=muted>net ${m.net}</span></div>`;
  }).join('');
  return `<div style="margin-top:10px"><b>Realized edge by regime</b> `
    +`<span class=muted>where the edge actually lived — regime tagged at each trade's entry (no look-ahead). `
    +`This is the measured truth; the setup score's regime-fit is only a prior.</span>`
    +`<div style="margin-top:5px">${rows}</div></div>`;
}
function diagnosisHtml(diag){
  if(!diag||diag.error)return '';
  const all=[].concat((diag.trades&&diag.trades.findings)||[],(diag.signals&&diag.signals.findings)||[]);
  if(!all.length)return '';
  const col={high:'var(--rose)',medium:'var(--gold)',low:'var(--sub)'};
  const rank={high:0,medium:1,low:2};
  all.sort((a,b)=>(rank[a.severity]??3)-(rank[b.severity]??3));
  const rows=all.map(f=>`<div class=lensrow style="margin-top:6px;display:flex;gap:9px;align-items:flex-start">`
    +`<span class=tag style="color:${col[f.severity]||'var(--sub)'};border-color:${col[f.severity]||'var(--line)'};min-width:64px;text-align:center">${f.severity}</span>`
    +`<span style="flex:1">${(f.message||'').replace(/</g,'&lt;')}</span></div>`).join('');
  return `<div style="margin-top:12px;padding:12px;background:rgba(90,162,255,.06);border:1px solid var(--line);border-radius:4px">`
    +`<b>Why this run behaved this way</b> <span class=muted>— derived from the trades and the signal flow, no pre-assumption the parameters are right. `
    +`Sweep the flagged parameter (Test → Sweep) to see the response.</span>`
    +`<div style="margin-top:6px">${rows}</div></div>`;
}
function regimeHtml(reg){
  if(!reg||reg.error||!reg.distribution)return '';
  const d=reg.distribution,keys=Object.keys(d);
  if(!keys.length)return '';
  const bars=keys.map(k=>`<div class=lensrow style="margin-top:2px">`
    +`<span class=tag style="min-width:160px;display:inline-block">${k}</span> `
    +`<b style="color:var(--gold)">${Math.round(d[k]*100)}%</b></div>`).join('');
  const idf=reg.indecision_frac?`<span class=muted> · warm-up/indecision ${Math.round(reg.indecision_frac*100)}%</span>`:'';
  return `<div style="margin-top:10px"><b>Regime (L1, objective)</b> `
    +`<span class=muted>dominant</span> <b style="color:var(--azure)">${reg.dominant}</b>${idf}`
    +`<div style="margin-top:5px">${bars}</div></div>`;
}
function stackHtml(desc,regime){
  if(!desc||!(desc.stack||[]).length)return '';
  const rdom=regime&&regime.dominant?regime.dominant:null;
  const rows=desc.stack.map(r=>{
    const on=r.active;
    let gr=on?`<b style="color:var(--gold)">${r.groups.join(', ')}</b>`
      :(r.status==='future'?'<span class=muted>— cross-market feed (not wired)</span>':'<span class=muted>—</span>');
    // annotate L1 with the run's objective regime tag when present
    if(r.layer==='L1'&&rdom){const rf=regime.indecision_frac?` · ${Math.round((1-regime.indecision_frac)*100)}% tradeable`:'';
      gr=`<b style="color:var(--azure)">${rdom}</b><span class=muted>${rf}</span>`;}
    const dim=(!on&&!(r.layer==='L1'&&rdom));
    return `<div class=lensrow style="margin-top:3px;${dim?'opacity:.45':''}">`
      +`<span class=tag style="min-width:118px;display:inline-block">${r.layer} · ${r.role}</span> ${gr}</div>`;
  }).join('');
  const meta=[];
  if(desc.family)meta.push('family: <b style="color:var(--sand)">'+desc.family+'</b>');
  if((desc.entries||[]).length)meta.push('entries: '+desc.entries.join(', '));
  if((desc.filters||[]).length)meta.push('filters: '+desc.filters.join(', '));
  if(desc.exit)meta.push('exit: '+[desc.exit.stop,desc.exit.target,(desc.exit.manage||[]).join('/')].filter(Boolean).join(' · '));
  return `<div style="margin-top:10px"><b>Decision stack (framework)</b>`
    +`<div class=muted style="margin:4px 0">${meta.join(' · ')}</div>${rows}</div>`;
}
async function showDetail(id){
  const d=$('#detail');d.style.display='block';d.innerHTML='<div class=muted>Loading…</div>';
  const r=await (await fetch('/api/run?id='+encodeURIComponent(id))).json();
  if(r.error){d.innerHTML='<div class=neg>'+r.error+'</div>';return;}
  const w=r.window||{},kind=r.kind||(r.source||'').split(':')[0];
  const badge=kind==='preset'?'<span class=tag style="color:var(--rose)">legacy preset — not registry-governed</span>'
    :'<span class=tag style="color:var(--azure)">registry spec</span>';
  const grp=r.groups?`<div style="margin-top:10px"><b>Indicators (registry blocks)</b><div style="margin-top:6px">${
    Object.entries(r.groups).map(([g,ps])=>`<div class=lensrow style="margin-top:4px"><b style="color:var(--gold)">${g}</b> — ${kvs(ps)}</div>`).join('')}</div></div>`:'';
  d.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center">
      <b>${r.strategy||''} · ${r.timeframe||''} · ${r.lens||''}</b>${badge}</div>
    <div class=lensrow style="margin-top:8px">run_id: ${r.run_id||''}</div>
    <div class=lensrow>data window: ${w.first||'?'} → ${w.last||'?'} · ${(w.bars_1m||0).toLocaleString()} 1m bars${r.segment&&r.segment!=='all'?' · <b style="color:var(--gold)">'+r.segment.toUpperCase()+'</b> (holdout '+(r.holdout_days||0)+'d)':''} · source ${r.source||''}</div>
    ${grp}
    ${stackHtml(r.desc,r.regime)}
    ${scoreHtml(r.desc)}
    ${regimeHtml(r.regime)}
    ${diagnosisHtml(r.diagnosis)}
    ${edgeHtml(r.edge_by_regime)}
    <div style="margin-top:10px"><b>Settings used</b><div style="margin-top:6px">${kvs(r.settings)}</div></div>
    <div style="margin-top:10px"><b>KPIs</b><div style="margin-top:6px">${kvs(r.kpis)}</div></div>
    <div class=up style="margin-top:14px">
      <label class=field><span class=fld>Promote as</span><select id=promStatus>
        <option value=eval>eval</option><option value=funded>funded</option><option value=validated>validated</option>
      </select></label>
      <button class=go id=promBtn>Promote to fleet</button>
      <span id=promMsg class=muted></span>
    </div>`;
  const lens=(r.lens||'').toLowerCase();
  const ps=$('#promStatus'); if(ps)ps.value=lens==='funded'?'funded':lens==='funnel'?'eval':'validated';
  const pb=$('#promBtn');
  if(pb)pb.addEventListener('click',()=>promoteRun(r));
  d.scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function promoteRun(r){
  const body={id:r.source||('run:'+r.run_id), name:r.strategy||r.run_id, asset:r.asset||'',
    status:$('#promStatus').value, kpis:r.kpis||null, run_id:r.run_id||null, timeframe:r.timeframe||''};
  try{
    const j=await (await fetch('/api/fleet/promote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    const m=$('#promMsg');
    if(j.ok){m.innerHTML='✓ promoted to fleet';renderFleet(j.fleet);}
    else m.innerHTML='<span class=neg>'+(j.error||'failed')+'</span>';
  }catch(e){$('#promMsg').innerHTML='<span class=neg>'+e+'</span>';}
}
function renderFleet(fleet){
  const el=$('#fleetRows'); if(!el)return;
  if(!fleet||!fleet.length){el.innerHTML='<div class=muted>no strategies yet — promote one from a run</div>';$('#fleetCount').textContent='0';return;}
  const badge=s=>`<span class="fam fam-${s==='funded'?'confluence':s==='eval'?'trend':'mixed'}">${s}</span>`;
  el.innerHTML=fleet.map(f=>{
    const pf=(f.kpis||{}).profit_factor;
    return `<div class=lensrow style="display:flex;align-items:center;gap:12px;margin-top:4px">
      <span class=tag style="min-width:120px;display:inline-block;color:var(--sand)">${f.name}</span>
      ${badge(f.status||'validated')}
      <span class=muted>${f.asset||''}</span>
      ${pf?`<span class=muted>PF <b style="color:var(--gold)">${pf}</b></span>`:''}
      ${f.seed?'<span class=muted>seed</span>':''}
      <button class=linkbtn data-fid="${f.id}" style="margin-left:auto;color:var(--rose)">remove</button>
    </div>`;}).join('');
  $('#fleetCount').textContent=fleet.length+' strateg'+(fleet.length===1?'y':'ies');
  el.querySelectorAll('button[data-fid]').forEach(b=>b.addEventListener('click',async()=>{
    const j=await (await fetch('/api/fleet/demote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:b.dataset.fid})})).json();
    if(j.ok)renderFleet(j.fleet);
  }));
}
async function loadFleet(){try{const j=await (await fetch('/api/fleet')).json();renderFleet(j.fleet||[]);}catch(e){}}
function fillKpis(){
  const b=STATS.best,bl=b?((b.kpis||{}).profit_factor||0).toFixed(2):'—';
  $('#kpis').innerHTML=kpi(STATS.runs||0,'runs')+kpi((STATS.assets||[]).length,'assets')
    +kpi((STATS.strategies||[]).length,'strategies')+kpi(bl,'best PF')
    +kpi((STATS.latest&&STATS.latest.timeframe)||'—','latest TF');
}
function renderJourney(j){
  const v=j.verdict||{};$('#verdict').innerHTML=`<div class="verdict v-${v.tone||'info'}">${v.text||''}</div>`;
  $('#lenses').innerHTML=(j.lenses||[]).map(L=>{
    const ins=(L.insights||[]).map(i=>`<div class=ins><span class="dot t-${i.tone}"></span><span>${i.text}</span></div>`).join('');
    const tfs=(L.runs||[]).map(r=>r.timeframe).join(', ');
    return `<div class=lens><h3>${L.lens.toUpperCase()}</h3><div class=q>${L.question}</div>${ins}
      ${tfs?`<div class=lensrow>runs: ${tfs}</div>`:''}</div>`}).join('');
}
async function loadJourney(strat){
  if(!strat){$('#verdict').innerHTML='';$('#lenses').innerHTML='<div class=muted>No strategy yet.</div>';return}
  const j=await (await fetch('/api/journey?strategy='+encodeURIComponent(strat))).json();renderJourney(j);
}
$('#jStrat').addEventListener('change',e=>loadJourney(e.target.value));
async function load(){
  const j=await (await fetch('/api/runs')).json();RUNS=j.runs||[];STATS=j.stats||{};
  opt($('#fAsset'),STATS.assets||[]);opt($('#fStrat'),STATS.strategies||[]);
  opt($('#fTf'),[...new Set(RUNS.map(r=>r.timeframe).filter(Boolean))]);
  opt($('#fLens'),[...new Set(RUNS.map(r=>r.lens).filter(Boolean))]);
  fillKpis();render();
  // Journey strategy picker
  const strats=STATS.strategies||[];const js=$('#jStrat');const cur=js.value;
  js.innerHTML=strats.map(s=>`<option>${s}</option>`).join('');
  const pick=cur&&strats.includes(cur)?cur:strats[0];if(pick){js.value=pick;loadJourney(pick);} else loadJourney(null);
  $('#sub').textContent='LAB_DIR '+(j.status.lab_dir||'')+(j.status.auth?' · secured':' · open');
  $('#foot').textContent='uptime '+Math.round((j.status.uptime_s||0)/60)+'m · reads index.json';
}
['#fAsset','#fStrat','#fTf','#fLens'].forEach(s=>$(s).addEventListener('change',render));
document.querySelectorAll('#tbl th').forEach(th=>th.addEventListener('click',()=>{
  const key=th.dataset.k,map={trades:'trades',win:'win_rate_pct',pf:'profit_factor',exp:'expectancy',net:'net_profit',dd:'max_drawdown'};
  if(map[key])RUNS.sort((a,b)=>((b.kpis||{})[map[key]]||-1e9)-((a.kpis||{})[map[key]]||-1e9));
  else RUNS.sort((a,b)=>String(b[key]||'').localeCompare(String(a[key]||'')));render();}));
// upload
$('#drop').addEventListener('click',()=>$('#file').click());
$('#file').addEventListener('change',e=>{const f=e.target.files[0];if(f){$('#drop').textContent=f.name+' ('+(f.size/1e6).toFixed(1)+' MB)';
  if(!$('#dsname').value)$('#dsname').value=f.name.replace(/\.[^.]+$/,'')}});
$('#upbtn').addEventListener('click',async()=>{
  const f=$('#file').files[0];if(!f){$('#msg').textContent='Choose a file first.';return}
  const name=encodeURIComponent($('#dsname').value||'dataset'),sym=encodeURIComponent($('#dssym').value||'');
  $('#msg').textContent='Uploading '+(f.size/1e6).toFixed(1)+' MB…';
  try{const r=await fetch('/api/upload?name='+name+'&symbol='+sym,{method:'POST',body:f});
    const j=await r.json();
    if(j.ok){$('#msg').innerHTML='<span class=pos>✓ '+j.dataset+': '+j.rows.toLocaleString()+' rows, cataloged.</span>';load();}
    else{$('#msg').innerHTML='<span class=neg>'+(j.error||'failed')+'</span>';}
  }catch(e){$('#msg').innerHTML='<span class=neg>'+e+'</span>';}
});
// wizard
let SPECS=[];
async function loadWizard(){
  try{
    SPECS=(await (await fetch('/api/specs')).json()).specs||[];
    const specOpts=SPECS.map(s=>{const f=(s.desc||{}).family;
      return `<option value="${s.id}">${s.title||s.name}${f?' · '+f:''}</option>`}).join('');
    $('#wSpec').innerHTML=specOpts;
    const swS=$('#swSpec');if(swS)swS.innerHTML=specOpts;
    const ds=(await (await fetch('/api/datasets')).json()).datasets||[];
    const dsOpts=ds.map(d=>`<option value="${d.name}">${d.name}${d.symbol?' · '+d.symbol:''}</option>`).join('')
      ||'<option value="">no datasets — upload one</option>';
    $('#wDs').innerHTML=dsOpts;
    const swD=$('#swDs');if(swD)swD.innerHTML=dsOpts;
    loadLibrary();
  }catch(e){}
}
function famPill(f){return `<span class="fam fam-${f||'trend'}">${f||'trend'}</span>`}
function libCard(s){
  const d=s.desc||{};
  if(s.error)return `<div class=card><div class=ct>${s.name}</div><div class=row style="color:var(--rose)">${s.error}</div></div>`;
  const c=d.confluence;
  const conf=c?`<div class=row>confluence · primary <b>${c.primary}</b> · gates <b>${(c.require||[]).join(', ')||'—'}</b></div>`
    +`<div class=row>killzones <b>${(c.killzones||[]).join(' · ')}</b> · lookback ${c.lookback}</div>`:'';
  const filt=(d.filters||[]).length?`<div class=row>filters ${d.filters.join(' · ')}</div>`:'';
  const ex=d.exit||{};
  const sc=d.score;
  const gradePill=sc?`<span class=tag title="setup-quality prior (framework §8) — not a verdict; the OOS funnel judges" style="color:var(--azure)">${sc.grade} · ${sc.score}</span>`:'';
  return `<div class=card data-id="${s.id}">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
      <span class=ct>${s.title||s.name}</span><span style="display:flex;gap:6px;align-items:center">${gradePill}${famPill(d.family)}</span></div>
    <div class=row>entry <b>${(d.entries||[]).join(', ')||'—'}</b></div>
    ${conf}${filt}
    <div class=row>exit · stop <b>${ex.stop||'?'}</b> · target <b>${ex.target||'?'}</b> · ${(ex.manage||[]).join('+')}</div>
    ${d.stack_summary?`<div class=row style="margin-top:5px;color:var(--azure)">stack · ${d.stack_summary}</div>`:''}
    <div class=row style="margin-top:7px;color:var(--dim)">${s.preset?('base '+s.preset+' · '):''}${(s.groups||[]).join(', ')}</div>
  </div>`;
}
function loadLibrary(){
  const specs=SPECS.filter(s=>s.kind==='spec');
  const order={confluence:0,trend:1,momentum:2,reversal:3,mixed:4};
  specs.sort((a,b)=>((order[(a.desc||{}).family]??9)-(order[(b.desc||{}).family]??9))||String(a.name).localeCompare(b.name));
  $('#libRows').innerHTML=specs.map(libCard).join('')||'<div class=muted>no specs</div>';
  $('#libCount').textContent=specs.length+' strategies';
  $('#libRows').querySelectorAll('.card').forEach(el=>el.addEventListener('click',()=>{
    const sel=$('#wSpec');if(sel)sel.value=el.dataset.id;
    showTab('test');                       // create → test: card loads into the runner
    window.scrollTo({top:0,behavior:'smooth'});
    sel&&sel.focus();
  }));
}
function _barFor(log){
  // a progress bar + caption injected right above the job's log <pre>
  let bar=log.previousElementSibling;
  if(!bar||!bar.classList||!bar.classList.contains('jbar')){
    bar=document.createElement('div');bar.className='jbar';
    bar.innerHTML='<div class=jbar-track><div class=jbar-fill></div></div>'+
      '<div class=jbar-cap><span class=jbar-pct></span> <span class=jbar-note></span></div>';
    log.parentNode.insertBefore(bar,log);
  }
  return bar;
}
function _errFor(log){
  let e=log.nextElementSibling;
  if(!e||!e.classList||!e.classList.contains('jerr')){
    e=document.createElement('div');e.className='jerr';
    log.parentNode.insertBefore(e,log.nextSibling);
  }
  return e;
}
function watchJob(id,logSel,btnSel,onDone){
  const log=$(logSel);log.style.display='block';
  const bar=_barFor(log);bar.style.display='block';
  const errBox=_errFor(log);errBox.style.display='none';
  const fill=bar.querySelector('.jbar-fill'),pct=bar.querySelector('.jbar-pct'),note=bar.querySelector('.jbar-note');
  const iv=setInterval(async()=>{
    const j=await (await fetch('/api/run/status?job='+id)).json();
    const p=j.progress;
    if(p&&j.status==='running'){fill.style.width=p.pct+'%';pct.textContent=p.pct+'%';note.textContent=p.note||'';}
    else if(j.status==='running'&&!p){pct.textContent='';note.textContent='starting…';}
    log.textContent=(j.log||[]).join('\n')||j.status||'…';log.scrollTop=log.scrollHeight;
    if(j.status==='done'||j.status==='error'){clearInterval(iv);if(btnSel)$(btnSel).disabled=false;
      fill.style.width='100%';pct.textContent=j.status==='done'?'100%':'';note.textContent=j.status;
      setTimeout(()=>{bar.style.display='none'},1200);
      if(j.status==='error'){
        errBox.style.display='block';
        errBox.innerHTML='<b>Run failed'+(j.rc!==undefined?' (exit '+j.rc+')':'')+'.</b> '+
          ((j.error||'See the log below.').replace(/</g,'&lt;'));
      } else {
        errBox.style.display='none';
        log.textContent+='\n\n[done'+(j.rc!==undefined?' rc='+j.rc:'')+
          (j.run_ids&&j.run_ids.length?' · '+j.run_ids.length+' run(s)':'')+']';
      }
      if(onDone)onDone(j);}
  },1500);
}
async function postJob(url,qs,logSel,btnSel,onDone){
  const b=btnSel&&$(btnSel);if(b)b.disabled=true;const log=$(logSel);log.style.display='block';log.textContent='Starting…';
  try{const r=await (await fetch(url+'?'+qs,{method:'POST'})).json();
    if(r.error){log.textContent=r.error;if(b)b.disabled=false;return}
    watchJob(r.job,logSel,btnSel,onDone);
  }catch(e){log.textContent=''+e;if(b)b.disabled=false;}
}
$('#wRun').addEventListener('click',()=>{
  const ds=$('#wDs').value;if(!ds){$('#wLog').style.display='block';$('#wLog').textContent='Upload a dataset first.';return}
  const qs='dataset='+encodeURIComponent(ds)+'&spec='+encodeURIComponent($('#wSpec').value)+
    '&tf='+encodeURIComponent($('#wTf').value)+'&lens='+encodeURIComponent($('#wLens').value)+
    '&micro='+($('#wMicro').checked?'1':'0');
  postJob('/api/run',qs,'#wLog','#wRun',()=>load());
});
// parameter sweep + auto-tune (phase 3)
function curveBars(curve,current,best,bestFunded){
  const rows=(curve||[]).filter(c=>!c.error);
  const mx=Math.max(0.01,...rows.map(c=>Math.abs(c.pf||0)));
  return rows.map(c=>{
    const cur=(c.value===current), bst=(best!==null&&best!==undefined&&c.value===best);
    const bfu=(bestFunded!==null&&bestFunded!==undefined&&c.value===bestFunded);
    const w=Math.max(2,Math.round(100*Math.abs(c.pf||0)/mx));
    const col=(c.pf>=1)?'linear-gradient(90deg,var(--gold2),var(--gold))':'var(--rose)';
    const fu=c.funded?('<span class=muted style="margin-left:8px">'+(c.funded.breached?'<span style="color:var(--rose)">breach</span>':'<span style="color:var(--gold)">survives</span>')+(c.funded.payouts?(' · '+c.funded.payouts+' payout'):'')+'</span>'):'';
    return `<div style="display:flex;align-items:center;gap:9px;margin-top:5px">
      <span style="min-width:84px;text-align:right;font-family:var(--mono);font-size:12px;color:${cur?'var(--gold)':'var(--sand)'}">${c.value}${cur?' ◀':''}${bst?' ★':''}${bfu?' ◆':''}</span>
      <span style="flex:1;background:var(--deep);border-radius:99px;height:16px;position:relative;overflow:hidden"><span style="display:block;height:100%;width:${w}%;background:${col};border-radius:99px"></span></span>
      <span style="min-width:210px;font-family:var(--mono);font-size:11px;color:var(--sub)">PF ${(c.pf||0).toFixed(2)} · net $${Math.round(c.net||0).toLocaleString()} · ${c.trades||0}t${fu}</span></div>`;
  }).join('');
}
function verdictHtml(t){
  const b=t.best,bf=t.best_funded;
  let out='';
  if(b)out+=`<div style="margin-top:6px;font-family:var(--mono);font-size:12px">→ strongest raw edge: <b style="color:var(--gold)">${t.param} = ${b.value}</b> <span class=muted>(PF ${(b.pf||0).toFixed(2)}, net $${Math.round(b.net||0).toLocaleString()}) — current ${t.current}</span></div>`;
  if(bf){const same=b&&bf.value===b.value;
    out+=`<div style="font-family:var(--mono);font-size:12px">→ strongest that <b>survives funded</b>: <b style="color:var(--gold)">${t.param} = ${bf.value}</b> <span class=muted>(PF ${(bf.pf||0).toFixed(2)}, ${(bf.funded||{}).payouts||0} payout(s))${same?' — same value: <b>funded-suitable</b>':''}</span></div>`;
  }else if(b){
    out+=`<div style="font-family:var(--mono);font-size:12px;color:var(--rose)">→ no value survives a funded account — the edge (if any) is eval-only here.</div>`;
  }
  return out;
}
function renderSweep(sw){
  const box=$('#swCurve');if(!sw||!sw.curve){box.style.display='none';return}
  box.style.display='block';
  box.innerHTML=`<div class=muted style="margin-bottom:4px">${sw.param} response — ◀ current, ★ best raw edge, ◆ best that survives funded. `
    +`${sw.engine_only?'engine-only (fast)':'recomputed indicators per value'}.</div>`
    +curveBars(sw.curve,sw.current,sw.best?sw.best.value:null,sw.best_funded?sw.best_funded.value:null)
    +verdictHtml(sw);
}
function renderAutotune(at){
  const box=$('#swTune');if(!at||!at.tuned){box.style.display='none';return}
  box.style.display='block';
  if(!at.tuned.length){box.innerHTML='<div class=muted>The data flagged nothing to tune — no parameter is clearly off on this run.</div>';return}
  const blocks=at.tuned.map(t=>{
    if(t.error)return `<div style="margin-top:12px"><b style="color:var(--rose)">${t.param}</b> — ${t.error}</div>`;
    return `<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line)">
      <div style="font-size:12.5px"><b style="color:var(--gold)">${t.param}</b> <span class=muted>— ${(t.message||'').replace(/</g,'&lt;')}</span></div>
      <div style="margin-top:6px">${curveBars(t.curve,t.current,t.best?t.best.value:null,t.best_funded?t.best_funded.value:null)}</div>${verdictHtml(t)}</div>`;
  }).join('');
  box.innerHTML=`<div class=muted>The data flagged ${at.tuned.length} parameter(s) and swept each over a range it derived from the measured distribution. ◀ current · ★ best raw edge · ◆ best that survives funded. The outcome labels suitability — funded, eval-only, or nothing.</div>${blocks}`;
}
$('#swAuto').addEventListener('click',()=>{
  const ds=$('#swDs').value;if(!ds){$('#swLog').style.display='block';$('#swLog').textContent='Upload a dataset first.';return}
  $('#swTune').style.display='none';
  const qs='auto=1&dataset='+encodeURIComponent(ds)+'&spec='+encodeURIComponent($('#swSpec').value)+
    '&tf='+encodeURIComponent($('#swTf').value);
  postJob('/api/sweep',qs,'#swLog','#swAuto',(j)=>{if(j&&j.autotune)renderAutotune(j.autotune);});
});
$('#swRun').addEventListener('click',()=>{
  const ds=$('#swDs').value;if(!ds){$('#swLog').style.display='block';$('#swLog').textContent='Upload a dataset first.';return}
  $('#swCurve').style.display='none';
  const qs='dataset='+encodeURIComponent(ds)+'&spec='+encodeURIComponent($('#swSpec').value)+
    '&tf='+encodeURIComponent($('#swTf').value)+'&param='+encodeURIComponent($('#swParam').value)+
    '&values='+encodeURIComponent($('#swVals').value);
  postJob('/api/sweep',qs,'#swLog','#swRun',(j)=>{if(j&&j.sweep)renderSweep(j.sweep);});
});
// generator
function gqs(){return 'dataset='+encodeURIComponent($('#gDs').value)+'&n='+encodeURIComponent($('#gN').value)+
  '&tf='+encodeURIComponent($('#gTf').value)+'&since='+encodeURIComponent($('#gSince').value)+
  '&holdout='+encodeURIComponent($('#gHold').value)+
  '&pao='+($('#gPao').checked?'1':'0')+'&seed='+encodeURIComponent($('#gSeed').value||'0')+
  '&setup_class='+encodeURIComponent($('#gThesis').value||'any')+'&regimes='+encodeURIComponent($('#gRegime').value||'');}
$('#gRun').addEventListener('click',()=>{if(!$('#gDs').value){$('#gLog').style.display='block';$('#gLog').textContent='Upload a dataset first.';return}
  postJob('/api/generate',gqs(),'#gLog','#gRun',()=>{load();loadCandidates();});});
$('#gVerify').addEventListener('click',()=>postJob('/api/verify',gqs(),'#gLog','#gVerify',()=>{load();loadCandidates();}));
async function loadCandidates(){
  const j=await (await fetch('/api/candidates')).json();
  $('#lbSrc').textContent=j.source?(j.source+(j.verified?' · OOS-verified':' · in-sample only (run Verify OOS)')):'no candidates yet';
  const rows=(j.rows||[]).slice(0,100);
  $('#lbrows').innerHTML=rows.map(r=>{const oos=r.oos_pf,isp=r.is_pf;
    return `<tr><td>${r.name||''}</td>
      <td class=muted style="text-align:left;white-space:normal;max-width:300px">${(r.groups||[]).join(', ')}</td>
      <td class=${isp>=1?'pos':'neg'}>${isp==null?'':isp.toFixed(2)}</td>
      <td class=${oos>=1?'pos':'neg'}>${oos==null?'—':oos.toFixed(2)}</td>
      <td>${r.retain==null?'—':r.retain.toFixed(2)}</td>
      <td>${r.oos_trades==null?'—':r.oos_trades}</td>
      <td>${r.pass===true?'<b class=pos>PASS</b>':r.pass===false?'<span class=neg>fail</span>':'—'}</td></tr>`}).join('')
    ||'<tr><td colspan=7 class=muted style="text-align:left">Run Generate → Verify OOS to populate.</td></tr>';
}
async function loadGenDatasets(){try{const ds=(await (await fetch('/api/datasets')).json()).datasets||[];
  $('#gDs').innerHTML=ds.map(d=>`<option value="${d.name}">${d.name}${d.symbol?' · '+d.symbol:''}</option>`).join('')||'<option value="">upload a dataset</option>';}catch(e){}}

// ---- 4th-variant builder ----
let BOPTS={setups:{}};
function builderBody(){
  const setup=$('#bSetup').value;
  return {setup_class:setup, entry:setup==='confluence'?null:$('#bEntry').value,
    filters:[...document.querySelectorAll('.bFilt:checked')].map(x=>x.value),
    regime_filter:[...document.querySelectorAll('.bReg:checked')].map(x=>x.value),
    base_preset:$('#bPreset').value, name:$('#bName').value||'custom'};
}
async function previewBuilder(){
  const el=$('#bPreview');
  try{
    const r=await (await fetch('/api/builder/preview',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(builderBody())})).json();
    if(!r.ok){el.innerHTML='<span class=neg>'+r.error+'</span>';return;}
    const d=r.desc,rf=(r.spec.regime_filter||[]);
    el.innerHTML=`<div class=lensrow>family <b style="color:var(--gold)">${d.family}</b> · entry <b>${(d.entries||[]).join(', ')||'—'}</b>`
      +((d.filters||[]).length?` · filters ${d.filters.join(' · ')}`:'')
      +(rf.length?` · <span style="color:var(--azure)">gate: ${rf.join(', ')}</span>`:' · <span class=muted>gate: all regimes</span>')
      +`</div>`+scoreHtml(d)+stackHtml(d,null);
  }catch(e){el.innerHTML='<span class=neg>'+e+'</span>';}
}
function fillBuilderEntry(){
  const setup=$('#bSetup').value,es=$('#bEntry');
  if(setup==='confluence'){es.innerHTML='<option value=silver_bullet>silver_bullet</option>';es.disabled=true;}
  else{es.disabled=false;es.innerHTML=(BOPTS.setups[setup]||[]).map(g=>`<option>${g}</option>`).join('');}
  previewBuilder();
}
async function saveBuilder(){
  const m=$('#bMsg');
  try{
    const r=await (await fetch('/api/builder/save',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(builderBody())})).json();
    if(!r.ok){m.innerHTML='<span class=neg>'+r.error+'</span>';return;}
    m.innerHTML='saved <b style="color:var(--gold)">'+r.name+'</b> — opened in Test';
    await loadWizard(); const sel=$('#wSpec'); if(sel)sel.value=r.id;
    showTab('test'); window.scrollTo({top:0,behavior:'smooth'});
  }catch(e){m.innerHTML='<span class=neg>'+e+'</span>';}
}
async function loadBuilder(){
  try{
    BOPTS=await (await fetch('/api/builder/options')).json();
    $('#bSetup').innerHTML=Object.keys(BOPTS.setups).map(s=>`<option>${s}</option>`).join('')+`<option value=confluence>confluence</option>`;
    $('#bPreset').innerHTML=(BOPTS.base_presets||[]).map(p=>`<option>${p}</option>`).join('');
    $('#bFilters').innerHTML=(BOPTS.filters||[]).map(f=>`<label><input type=checkbox class=bFilt value="${f}"> ${f}</label>`).join('');
    $('#bRegimes').innerHTML=(BOPTS.regimes||[]).map(r=>`<label><input type=checkbox class=bReg value="${r}"> ${r}</label>`).join('');
    $('#bSetup').addEventListener('change',fillBuilderEntry);
    $('#bEntry').addEventListener('change',previewBuilder);
    $('#bPreset').addEventListener('change',previewBuilder);
    document.querySelectorAll('.bFilt,.bReg').forEach(x=>x.addEventListener('change',previewBuilder));
    $('#bSave').addEventListener('click',saveBuilder);
    fillBuilderEntry();
  }catch(e){}
}
// ---- tabs ----
function showTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on', t.id==='tab-'+name));
  document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name));
}
document.querySelectorAll('#tabs button').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));
const gAdvT=$('#gAdvToggle');
if(gAdvT)gAdvT.addEventListener('click',()=>{const a=$('#gAdv');const open=a.style.display!=='none';a.style.display=open?'none':'flex';gAdvT.textContent=open?'+ advanced':'− advanced';});
showTab('create');

loadWizard();loadGenDatasets();
load();
loadCandidates();
loadFleet();
"""

LOGIN_HTML = f"""<!doctype html><html><head>{_HEAD}
<title>MEX Traders · Lab</title><style>{_CSS}</style></head><body><div class=wrap>
<div style="display:flex;align-items:center">{_BRAND}<span class=tag-lab>Backtest Lab</span></div>
<div class=panel style="max-width:340px">
<form method=post action=/login><div class=muted style="margin-bottom:8px">Owner login</div>
<div style="color:var(--rose);font-size:12px;margin-bottom:6px"><!--ERR--></div>
<input type=password name=password placeholder=Password autofocus style="width:100%">
<button class=go style="width:100%;margin-top:8px">Enter</button></form></div>
<div class=foot>Set LAB_PASSWORD to enable the gate.</div></div></body></html>"""

PAGE_HTML = f"""<!doctype html><html><head>{_HEAD}
<title>MEX Traders · Lab</title><style>{_CSS}</style></head><body><div class=wrap>
<div style="display:flex;justify-content:space-between;align-items:center">
  <div style="display:flex;align-items:center">{_BRAND}<span class=tag-lab>Backtest Lab</span></div>
  <span class=muted id=sub></span></div>
<div class=kpis id=kpis></div>

<div class=steps>Pipeline: <b>1 Data</b> → <b>2 Create</b> a strategy → <b>3 Test</b> it (classic · eval · funded) → <b>4 Runs</b> to review &amp; promote</div>
<div class=tabs id=tabs>
  <button data-tab=data>1 · Data</button>
  <button data-tab=create class=on>2 · Create</button>
  <button data-tab=test>3 · Test</button>
  <button data-tab=runs>4 · Runs</button>
</div>

<!-- ===================== 1 · DATA ===================== -->
<div class=tab id=tab-data>
  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Upload dataset</b><span class=muted>raw export → normalized → cataloged</span></div>
    <div class=hint>Start here: drop a 1-minute CSV export (Quantower/ATAS). It is normalized and cataloged, then available as a Dataset everywhere below.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Dataset name</span><input id=dsname placeholder="e.g. NQ_1m" style="width:170px"></label>
      <label class=field><span class=fld>Symbol</span><input id=dssym placeholder="NQ" style="width:100px"></label>
      <label class=field><span class=fld>CSV file</span><label id=drop>Click to choose a .csv export<input id=file type=file accept=.csv class=hidden></label></label>
      <button class=go id=upbtn>Upload</button>
    </div><div id=msg class=muted style="margin-top:8px"></div>
  </div>
</div>

<!-- ===================== 2 · CREATE ===================== -->
<div class=tab id=tab-create>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Discover strategies</b><span class=muted>seed a thesis — the machine finds the rest</span></div>
    <div class=hint>You set the <b>thesis</b> (and optionally a regime to focus on); the search <b>discovers</b> the entry, filters, params <b>and the stop/target mechanics</b> — nothing is assumed up front, not even per asset. It screens candidates in-sample, then Verify OOS. Filters and mechanics are an <b>outcome</b> of the test. Leave the thesis on "Any" for unbiased broad discovery. Results appear in Test → Candidates. Tip: use 5m or 15m (not 1m) and set a "Coarse since" date under + advanced to keep the 20-year screen fast.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Dataset</span><select id=gDs style="min-width:150px"></select></label>
      <label class=field><span class=fld>Thesis</span><select id=gThesis title="constrain the search to one setup-class, or Any for broad discovery">
        <option value=any>Any thesis (broad)</option>
        <option value=trend_pullback>trend pullback</option>
        <option value=breakout>breakout</option>
        <option value=mean_reversion>mean reversion</option>
        <option value=reversal>reversal</option>
        <option value=confluence>confluence</option>
      </select></label>
      <label class=field><span class=fld>Regime focus</span><select id=gRegime title="bias the search toward a regime's favoured setups (optional)">
        <option value="">All regimes</option>
        <option>Strong Bull Trend</option><option>Controlled Bull Trend</option>
        <option>Strong Bear Trend</option><option>Controlled Bear Trend</option>
        <option>Compression</option><option>Low-Volatility Range</option><option>High-Volatility Range</option>
      </select></label>
      <label class=field><span class=fld>Candidates</span><input id=gN value=100 style="width:70px"></label>
      <button class=go id=gRun>Discover</button>
      <button id=gVerify>Verify OOS</button>
      <button class=linkbtn id=gAdvToggle>+ advanced</button>
    </div>
    <div class=up id=gAdv style="margin-top:10px;display:none">
      <label class=field><span class=fld>Timeframe</span><input id=gTf value=5m style="width:64px"></label>
      <label class=field><span class=fld>Coarse since</span><input id=gSince placeholder="2022-01-01" style="width:150px"></label>
      <label class=field><span class=fld>OOS holdout (d)</span><input id=gHold value=365 style="width:80px"></label>
      <label class=field><span class=fld>Seed</span><input id=gSeed value=0 style="width:60px"></label>
      <label class=field><span class=fld>Price-action</span><span style="padding:8px 0"><input type=checkbox id=gPao> PA-only</span></label>
    </div>
    <pre id=gLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:240px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Strategy library</b><span class=muted id=libCount>—</span></div>
    <div class=hint>Governed + promoted strategies — grade, entries, gates, exit and framework stack. Click a card to load it into Test.</div>
    <div class=lib id=libRows></div>
  </div>

</div>

<!-- ===================== 3 · TEST ===================== -->
<div class=tab id=tab-test>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Run a backtest</b><span class=muted>test a strategy toward a goal</span></div>
    <div class=hint>Pick a strategy and dataset, choose the goal (lens), and run. Classic = raw edge · Eval = prop-firm pass-rate · Funded = payout simulation.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Strategy</span><select id=wSpec style="min-width:200px"></select></label>
      <label class=field><span class=fld>Dataset</span><select id=wDs style="min-width:150px"></select></label>
      <label class=field><span class=fld>Timeframes</span><input id=wTf value="5m,15m" style="width:150px"></label>
      <label class=field><span class=fld>Goal (lens)</span><select id=wLens>
        <option value=research>Classic — edge</option>
        <option value=funnel>Eval — funnel</option>
        <option value=funded>Funded — payouts</option>
      </select></label>
      <label class=field><span class=fld>Micro twin</span><span style="padding:8px 0"><input type=checkbox id=wMicro> + MGC/MES…</span></label>
      <button class=go id=wRun>Run</button>
    </div>
    <pre id=wLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:220px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Auto-tune from the data</b><span class=muted>the data decides — no parameter, no ranges</span></div>
    <div class=hint>Runs the strategy, lets the <b>diagnosis</b> name which parameters are off (stop too wide, FVG band too big, position too large) and derive each range from the measured distribution, then sweeps them. Every value is measured on <b>both</b> raw edge and funded survival — the outcome tells you what the strategy is suited for (funded · eval-only · nothing); you choose no goal up front. Tunes on the <b>last 3 years</b> (coarse gate, same design as the mill) — validate the winner on the full history with Run/Verify. On a 2-core box run this OR a backtest, not both at once.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Strategy</span><select id=swSpec style="min-width:190px"></select></label>
      <label class=field><span class=fld>Dataset</span><select id=swDs style="min-width:150px"></select></label>
      <label class=field><span class=fld>Timeframe</span><input id=swTf value="1m" style="width:70px"></label>
      <button class=go id=swAuto>Auto-tune</button>
    </div>
    <div id=swTune style="display:none;margin-top:14px"></div>
    <details style="margin-top:12px"><summary class=muted style="cursor:pointer">Advanced — sweep one parameter manually</summary>
      <div class=up style="margin-top:10px">
        <label class=field><span class=fld>Parameter</span><select id=swParam style="min-width:170px">
          <option value=fixed_stop_ticks>fixed_stop_ticks (stop)</option>
          <option value=tp_fixed_ticks>tp_fixed_ticks (target)</option>
          <option value=contract_size>contract_size (size)</option>
          <option value=gap_min_ticks>gap_min_ticks (FVG min)</option>
          <option value=gap_max_ticks>gap_max_ticks (FVG max)</option>
          <option value=cvd_trend_count>cvd_trend_count (CVD streak)</option>
          <option value=trail_start_ticks>trail_start_ticks (trail)</option>
          <option value=be_trigger_ticks>be_trigger_ticks (breakeven)</option>
        </select></label>
        <label class=field><span class=fld>Values (comma)</span><input id=swVals value="40,60,80,100,120" style="width:170px"></label>
        <button class=go id=swRun>Sweep</button>
      </div>
      <div id=swCurve style="display:none;margin-top:14px"></div>
    </details>
    <pre id=swLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:200px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Candidates</b><span class=muted id=lbSrc>no candidates yet</span></div>
    <div class=hint>OOS-verified survivors from the factory — the overfit gate. IS PF vs OOS PF, retain and verdict.</div>
    <div style="overflow-x:auto"><table style="margin-top:8px"><thead><tr>
      <th style="text-align:left">Strategy</th><th style="text-align:left">Indicators</th>
      <th>IS PF</th><th>OOS PF</th><th>Retain</th><th>OOS n</th><th>Verdict</th>
    </tr></thead><tbody id=lbrows></tbody></table></div>
  </div>

</div>

<!-- ===================== 4 · RUNS ===================== -->
<div class=tab id=tab-runs>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Fleet</b><span class=muted id=fleetCount>—</span></div>
    <div class=hint>Your validated / production strategies — the list you build on. Promote a strategy from any run below; the eight ported fleet strategies are seeded here.</div>
    <div id=fleetRows style="margin-top:10px"></div>
  </div>

  <div class=bar>
    <select id=fAsset><option value="">All assets</option></select>
    <select id=fStrat><option value="">All strategies</option></select>
    <select id=fTf><option value="">All timeframes</option></select>
    <select id=fLens><option value="">All lenses</option></select>
    <span class=muted id=count></span>
  </div>
  <div style="overflow-x:auto"><table id=tbl><thead><tr>
    <th data-k=run_id>Run</th><th data-k=asset>Asset</th><th data-k=strategy>Strategy</th>
    <th data-k=timeframe>TF</th><th data-k=lens>Lens</th><th data-k=trades>Trades</th>
    <th data-k=win>Win%</th><th data-k=pf>PF</th><th data-k=exp>Exp</th>
    <th data-k=net>Net</th><th data-k=dd>MaxDD</th><th data-k=created>When</th>
  </tr></thead><tbody id=rows></tbody></table></div>

  <div class=panel id=detail style="display:none"></div>

  <div class=panel id=journey style="margin-top:16px">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Journey</b>
      <select id=jStrat style="min-width:200px"></select>
    </div>
    <div id=verdict style="margin:10px 0"></div>
    <div id=lenses></div>
  </div>

</div>

<div class=foot id=foot></div></div>
<script>{_JS}</script></body></html>"""

if __name__ == "__main__":
    main()
