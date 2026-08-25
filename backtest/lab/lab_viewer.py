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

from .insights import build_journey
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
        sym, rows, first, last = "", None, None, None
        man = sub / "manifest.json"
        if man.exists():
            try:
                m = json.loads(man.read_text())
                sym, rows = m.get("symbol", ""), m.get("rows")
                first, last = m.get("first_dt"), m.get("last_dt")
            except Exception:
                pass
        out.append({"name": sub.name, "file": str(f), "symbol": sym, "rows": rows,
                    "first": first, "last": last})
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


# One heavy job at a time: every backtest/discover/verify/sweep/ingest saturates
# both cores and real memory, so two at once just fight each other into what
# looks like a stall. A second click now WAITS with a visible 'queued' status
# instead of silently degrading everything.
_HEAVY = threading.Semaphore(1)


def _run_job(job_id: str, cmd: list[str]) -> None:
    def upd(**k):
        with _JOBS_LOCK:
            _JOBS[job_id].update(**k)
    upd(status="queued")
    _HEAVY.acquire()
    try:
        _run_job_inner(job_id, cmd, upd)
    finally:
        _HEAVY.release()


def _run_job_inner(job_id: str, cmd: list[str], upd) -> None:
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
            if line.startswith("EVALSWEEP_JSON "):
                try:
                    with _JOBS_LOCK:
                        _JOBS[job_id]["evalsweep"] = json.loads(line[len("EVALSWEEP_JSON "):])
                except Exception:
                    pass
                continue
            if line.startswith("PORTFOLIO_JSON "):
                try:
                    with _JOBS_LOCK:
                        _JOBS[job_id]["portfolio"] = json.loads(line[len("PORTFOLIO_JSON "):])
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


def _start_job(dataset: str, spec: str, tf: str, lens: str, micro: bool = False,
               window: str = "recent3y") -> tuple[dict, int]:
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
           "--tf", ",".join(tfs), "--lab",
           "--window", ("full" if window == "full" else "recent3y")]
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


def _start_evalsweep(q) -> tuple[dict, int]:
    """Sweep the eval funnel across the registry's prop-firm programs."""
    from ..config import PRESETS, TIMEFRAMES
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    tf = (q.get("tf") or ["1m"])[0].strip().lower()
    if tf not in TIMEFRAMES:
        return {"error": f"unknown timeframe {tf!r}"}, 400
    cmd = [sys.executable, "-m", "backtest.evalsweep", "--data", ds[dataset]["file"], "--tf", tf]
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
    firm = (q.get("firm") or [""])[0].strip()
    if firm:
        cmd += ["--firm", firm]
    for name, flag in (("step", "--step"), ("horizon", "--horizon")):
        v = (q.get(name) or [""])[0].strip()
        if v:
            try:
                cmd += [flag, str(int(v))]
            except ValueError:
                pass
    if (q.get("noscale") or ["0"])[0] in ("1", "true", "on"):
        cmd += ["--no-scale-size"]
    return _spawn(cmd, "eval spectrum"), 200


def _start_portfolio(q) -> tuple[dict, int]:
    """Decorrelated selection over the OOS survivors (backtest.portfolio)."""
    seed = "0"
    try:
        seed = str(int((q.get("seed") or ["0"])[0]))
    except Exception:
        pass
    vfile = lab_root() / f"verified_seed{seed}.json"
    if not vfile.exists():
        return {"error": f"no {vfile.name} yet — run Verify OOS first"}, 400
    cmd = [sys.executable, "-m", "backtest.portfolio", "--verified", str(vfile)]
    if (q.get("all") or ["0"])[0] in ("1", "true", "on"):
        cmd += ["--all"]
    for name, flag in (("max_corr", "--max-corr"), ("max_badday", "--max-badday"),
                       ("max_regime", "--max-regime"), ("drawdown", "--drawdown")):
        v = (q.get(name) or [""])[0].strip()
        if v:
            try:
                cmd += [flag, str(float(v))]
            except ValueError:
                pass
    return _spawn(cmd, f"portfolio seed{seed}"), 200


def _pipeline_view() -> dict:
    """The twelve-stage plan plus each engine's status — the cockpit's spine."""
    from ..pipeline import fleet, state
    from ..pipeline.stages import GROUND_RULES, STAGES
    engines = fleet.names()
    return {
        "stages": [{"n": s.n, "key": s.key, "title": s.title, "gate": s.gate,
                    "hard": s.hard, "note": s.note} for s in STAGES],
        "ground_rules": list(GROUND_RULES),
        "fleet": fleet.summary(),
        "overview": state.overview(engines),
        "detail": {e: state.engine_view(e) for e in engines},
        "coverage": _stage1_coverage(),
    }


_STAGE_ARTIFACT_TAG = {
    "0": "trap0_data-audit", "1": "trap1_pariteit", "2": "trap2_structurele-edge",
    "3": "trap3_regimes", "4": "trap4_plateau", "5": "trap5_sizing",
    "6": "trap6_daily_mgmt", "7": "trap7_pa_lifecycle", "8": "trap8_time_for_money",
    "9": "trap9_prod_vs_harvest",
}


def _artifact_detail(engine: str, stage: str) -> dict:
    """The latest artifact for one engine+stage, trimmed to the numbers a human
    wants to see for that stage. Reads the files ground rule 11 already writes."""
    import glob
    tag = _STAGE_ARTIFACT_TAG.get(str(stage))
    if not engine or not tag:
        return {"found": False}
    d = lab_root() / "artifacts"
    hits = sorted(glob.glob(str(d / f"{engine}_{tag}_*.json")))
    if not hits:
        return {"found": False}
    try:
        raw = json.loads(open(hits[-1]).read())
    except Exception as e:
        return {"found": False, "error": str(e)[:120]}
    return {"found": True, "stage": stage, "file": os.path.basename(hits[-1]),
            "data": _trim_artifact(stage, raw)}


def _trim_artifact(stage: str, a: dict) -> dict:
    """Pick the human-relevant fields per stage (artifacts are large)."""
    s = str(stage)
    if s == "0":
        r = a.get("report", a)
        return {k: r.get(k) for k in ("bars", "years", "sessions", "median_bar_range_ticks",
                "roll_like_jumps", "ohlc_violations", "gaps_over_6h", "Delta_nonzero_pct",
                "findings", "verdict")}
    if s == "1":
        c = a.get("comparison", {})
        return {"status": a.get("status"), "checks": c.get("checks"), "sim": c.get("sim"),
                "pine": c.get("pine"), "paired_pct": a.get("paired_pct"),
                "pine_only_split": a.get("pine_only_split")}
    if s == "2":
        return {"kpis": a.get("kpis"), "by_year": a.get("by_year"), "verdict": a.get("verdict")}
    if s == "3":
        return {"total": a.get("total"), "by_regime": a.get("by_regime"),
                "best_regime": a.get("best_regime"), "best_share_pct": a.get("best_share_pct")}
    if s == "4":
        return {"years": a.get("years"), "quarters": a.get("quarters"), "long": a.get("long"),
                "short": a.get("short"), "neighbourhood": a.get("neighbourhood")}
    if s == "5":
        return {k: a.get(k) for k in ("stop_usd_total", "worst_case_usd", "dll",
                "fits_under_dll", "pf_1", "pf_n", "pf_invariant", "qty")}
    if s == "6":
        return {k: a.get(k) for k in ("with_day_mgmt", "without_day_mgmt") if k in a}
    if s == "7":
        return {k: a.get(k) for k in ("full_size", "one_contract", "intended_model",
                "frozen_qty") if k in a}
    if s == "8":
        return {k: a.get(k) for k in ("banked_per_account_day", "measured_at_full_size",
                "frozen_qty", "payouts", "days_to_first_payout", "dll_hits", "trading_days",
                "breached", "withdrawable", "per_month")}
    if s == "9":
        return {"with_filter": a.get("with_filter"), "without_filter": a.get("without_filter"),
                "mask_contribution_pct": a.get("mask_contribution_pct")}
    if s == "10":
        return {"status": a.get("status"), "dimensions": a.get("dimensions"),
                "exit_reasons": (a.get("exit_reasons") or {}).get("rows"),
                "excursion": {k: (a.get("excursion") or {}).get(k) for k in
                              ("paired", "median_mfe_diff_ticks", "median_mae_diff_ticks",
                               "within_tol_pct")},
                "matched_pct": a.get("matched_pct"), "same_bar_pct": a.get("same_bar_pct")}
    return a


def _stage1_coverage() -> list[dict]:
    """Per TradingView export: which market and window it actually tested, and
    whether we hold a dataset that can run it. Trap 1 is a hard gate, so this is
    the shortest honest answer to 'what is blocking the whole pipeline'."""
    from ..pipeline.parity import export_window, read_export
    dsets = [{"name": d["name"], "symbol": (d.get("symbol") or "").upper(),
              "first": d.get("first"), "last": d.get("last")}
             for d in _datasets()]
    out = []
    for nm in _exports():
        f = _export_path(nm)
        if f is None:
            continue
        try:
            from ..pipeline import fleet
            from ..pipeline.cli import _dt
            exp = read_export(str(f))
            a, b = export_window(exp)
            root = "".join(c for c in str(exp.properties.get("Symbol") or "").split(":")[-1]
                           if c.isalpha())
            from ..pipeline.cli import window_overlap
            twin = fleet.TWIN.get(root)
            usable, short, missing_days = [], [], 0
            for d in dsets:
                if d["symbol"] not in (root, twin) or not d["symbol"]:
                    continue
                lo, hi = _dt(d.get("first")), _dt(d.get("last"))
                ov = window_overlap(lo, hi, a, b)
                label = d["name"] + ("" if d["symbol"] == root else f" (twin {d['symbol']})")
                if ov["verdict"] in ("volledig", "onbekend"):
                    usable.append(label)
                elif ov["verdict"] == "bijna volledig":
                    usable.append(f"{label} — mist {ov['missing_days']}d")
                    missing_days = max(missing_days, ov["missing_days"])
                else:
                    pct = 100 - (ov["missing_frac"] or 0) * 100
                    short.append(f"{label} dekt {pct:.0f}%"
                                 + (f", loopt tot {hi:%Y-%m-%d}" if hi else ""))
            out.append({"export": nm, "market": root, "twin": twin, "trades": exp.n_trades,
                        "window": f"{a:%Y-%m-%d} → {b:%Y-%m-%d}" if a and b else "?",
                        "datasets": usable, "too_short": short, "runnable": bool(usable),
                        "missing_days": missing_days})
        except Exception as e:                       # a corrupt upload must not blank the tab
            out.append({"export": nm, "market": "?", "twin": None, "trades": 0,
                        "window": "?", "datasets": [], "too_short": [],
                        "runnable": False, "missing_days": 0, "error": str(e)[:120]})
    return out


def _start_stage(q) -> tuple[dict, int]:
    from ..pipeline import fleet
    stage = (q.get("stage") or [""])[0]
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    engine = (q.get("engine") or [""])[0]
    if stage == "0":
        cmd = [sys.executable, "-m", "backtest.pipeline.cli", "stage0", "--dataset", dataset]
        if engine:
            if engine not in fleet.names():
                return {"error": f"unknown engine {engine!r}"}, 400
            cmd += ["--engine", engine]
        return _spawn(cmd, f"trap 0 · {dataset}"), 200
    if stage == "1":
        if engine not in fleet.names():
            return {"error": "pick an engine for the parity run"}, 400
        exp = (q.get("export") or [""])[0].strip()
        if not exp:
            return {"error": "stage 1 needs a TradingView export (.xlsx) to compare against"}, 400
        f = _export_path(exp)
        if f is None:
            return {"error": f"export not found: {os.path.basename(exp)} — upload it "
                             f"under 1 · Data of zet hem in validation/exports/"}, 400
        cmd = [sys.executable, "-m", "backtest.pipeline.cli", "stage1", "--dataset", dataset,
               "--engine", engine, "--export", str(f)]
        for name, flag in (("since", "--since"), ("until", "--until")):
            v = (q.get(name) or [""])[0].strip()
            if v:
                cmd += [flag, v]
        return _spawn(cmd, f"trap 1 · {engine}"), 200
    if stage == "2":
        if engine not in fleet.names():
            return {"error": "pick an engine for the structural-edge run"}, 400
        cmd = [sys.executable, "-m", "backtest.pipeline.cli", "stage2", "--dataset", dataset,
               "--engine", engine]
        for name, flag in (("since", "--since"), ("until", "--until")):
            v = (q.get(name) or [""])[0].strip()
            if v:
                cmd += [flag, v]
        return _spawn(cmd, f"trap 2 · {engine}"), 200
    if stage in ("3", "4", "5", "6", "7", "8", "9"):
        if engine not in fleet.names():
            return {"error": f"pick an engine for the stage-{stage} run"}, 400
        cmd = [sys.executable, "-m", "backtest.pipeline.cli", f"stage{stage}",
               "--dataset", dataset, "--engine", engine]
        for name, flag in (("since", "--since"), ("until", "--until")):
            v = (q.get(name) or [""])[0].strip()
            if v:
                cmd += [flag, v]
        return _spawn(cmd, f"trap {stage} · {engine}"), 200
    if stage == "10":
        # Like stage 1, the deployment gate needs the TradingView export to
        # validate against, plus --as-tested so a cosmetic input difference does
        # not block the run (ground rule 10 stays reported either way).
        if engine not in fleet.names():
            return {"error": "pick an engine for the TradingView-validation run"}, 400
        exp = (q.get("export") or [""])[0].strip()
        if not exp:
            return {"error": "stage 10 needs a TradingView export (.xlsx) to validate against"}, 400
        f = _export_path(exp)
        if f is None:
            return {"error": f"export not found: {os.path.basename(exp)} — upload it "
                             f"under 1 · Data of zet hem in validation/exports/"}, 400
        cmd = [sys.executable, "-m", "backtest.pipeline.cli", "stage10", "--dataset", dataset,
               "--engine", engine, "--export", str(f), "--as-tested"]
        for name, flag in (("since", "--since"), ("until", "--until")):
            v = (q.get(name) or [""])[0].strip()
            if v:
                cmd += [flag, v]
        return _spawn(cmd, f"trap 10 · {engine}"), 200
    return {"error": f"stage {stage!r} is not implemented yet"}, 400


def _start_scorecard(q) -> tuple[dict, int]:
    """Analysis scorecard — run one engine on one dataset and emit SCORECARD_JSON."""
    from ..pipeline import fleet
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    engine = (q.get("engine") or [""])[0]
    if engine not in fleet.names():
        return {"error": "pick an engine for the scorecard"}, 400
    cmd = [sys.executable, "-m", "backtest.pipeline.cli", "scorecard",
           "--dataset", dataset, "--engine", engine]
    if (q.get("posture") or [""])[0] == "raw":
        cmd.append("--raw")
    hold = (q.get("holdout_days") or ["0"])[0].strip()
    if hold.isdigit() and int(hold) > 0:
        cmd += ["--holdout-days", hold]
    for name, flag in (("since", "--since"), ("until", "--until")):
        v = (q.get(name) or [""])[0].strip()
        if v:
            cmd += [flag, v]
    return _spawn(cmd, f"scorecard · {engine}"), 200


def _start_audit(q) -> tuple[dict, int]:
    """Data-quality audit for one dataset — emits AUDIT_JSON."""
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    cmd = [sys.executable, "-m", "backtest.lab.dataprep", "audit", "--dataset", dataset]
    return _spawn(cmd, f"audit · {dataset}"), 200


def _start_aggregate(q) -> tuple[dict, int]:
    """Resample a 1-minute dataset to a coarser timeframe and store it — AGGREGATE_JSON."""
    from ..config import TIMEFRAMES
    ds = {d["name"]: d for d in _datasets()}
    dataset = (q.get("dataset") or [""])[0]
    if dataset not in ds:
        return {"error": f"unknown dataset {dataset!r}"}, 400
    tf = (q.get("tf") or [""])[0].strip().lower()
    if tf not in TIMEFRAMES or TIMEFRAMES[tf] <= 1:
        return {"error": f"kies een timeframe grofmaziger dan 1m ({', '.join(t for t in TIMEFRAMES if TIMEFRAMES[t] > 1)})"}, 400
    cmd = [sys.executable, "-m", "backtest.lab.dataprep", "aggregate",
           "--dataset", dataset, "--tf", tf]
    name = (q.get("name") or [""])[0].strip()
    if name:
        cmd += ["--name", name]
    return _spawn(cmd, f"aggregate · {dataset} -> {tf}"), 200


def _export_dirs() -> list[Path]:
    """Where TradingView exports may live: uploaded ones under $LAB_DIR/exports,
    and the ones committed as evidence in validation/exports (so a clean checkout
    can run stage 1 without anyone re-uploading them)."""
    repo = Path(__file__).resolve().parents[2] / "validation" / "exports"
    return [d for d in (lab_root() / "exports", repo) if d.is_dir()]


def _export_path(name: str):
    """Resolve an export name to a file, without letting the name escape the
    directories we allow."""
    base = os.path.basename(name)
    for d in _export_dirs():
        f = (d / base).resolve()
        if f.is_file() and f.parent == d.resolve():
            return f
    return None


def _exports() -> list[str]:
    seen, out = set(), []
    for d in _export_dirs():
        for p in sorted(d.glob("*.xlsx")):
            if p.name not in seen:
                seen.add(p.name)
                out.append(p.name)
    return out


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
        if u.path == "/api/pipeline":
            return self._json(_pipeline_view())
        if u.path == "/api/exports":
            return self._json({"exports": _exports()})
        if u.path == "/api/artifact":
            q = urllib.parse.parse_qs(u.query)
            return self._json(_artifact_detail((q.get("engine") or [""])[0],
                                               (q.get("stage") or [""])[0]))
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
                                    micro=(q.get("micro") or ["0"])[0] in ("1", "true", "on"),
                                    window=(q.get("window") or ["recent3y"])[0])
            return self._json(body, code)
        if u.path == "/api/generate":
            body, code = _start_generate(q)
            return self._json(body, code)
        if u.path == "/api/verify":
            body, code = _start_verify(q)
            return self._json(body, code)
        if u.path == "/api/evalsweep":
            body, code = _start_evalsweep(q)
            return self._json(body, code)
        if u.path == "/api/stage":
            body, code = _start_stage(q)
            return self._json(body, code)
        if u.path == "/api/scorecard":
            body, code = _start_scorecard(q)
            return self._json(body, code)
        if u.path == "/api/dataset/audit":
            body, code = _start_audit(q)
            return self._json(body, code)
        if u.path == "/api/dataset/aggregate":
            body, code = _start_aggregate(q)
            return self._json(body, code)
        if u.path == "/api/portfolio":
            body, code = _start_portfolio(q)
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
        try:
            with open(raw, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
                    wrote += len(chunk)
        except OSError as e:
            return self._json({"error": f"could not store the upload (disk?): {e}",
                               "bytes": wrote}, 507)
        if wrote < length:
            return self._json({"error": f"upload truncated: got {wrote:,} of {length:,} "
                                        "bytes — connection dropped mid-transfer",
                               "bytes": wrote}, 400)
        # Normalize + catalog in a BACKGROUND job (with live progress), not inside
        # this request: a 1GB export takes minutes to normalize, and a synchronous
        # response here is exactly what reverse-proxy/browser timeouts kill —
        # which looked like "the upload failed" even though the bytes arrived.
        job = _spawn([sys.executable, "-m", "backtest.lab.ingest", "--raw", str(raw),
                      "--name", safe, "--symbol", symbol, "--delete-raw"],
                     f"ingest {safe}")
        return self._json({"ok": True, "dataset": safe, "bytes": wrote, "job": job["job"]})


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
    +`Sweep the flagged parameter (Strats → Sweep) to see the response.</span>`
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
$('#upbtn').addEventListener('click',()=>{
  const f=$('#file').files[0];if(!f){$('#msg').textContent='Choose a file first.';return}
  const name=encodeURIComponent($('#dsname').value||'dataset'),sym=encodeURIComponent($('#dssym').value||'');
  const log=$('#upLog');log.style.display='block';log.textContent='';
  const bar=_barFor(log);bar.style.display='block';
  const fill=bar.querySelector('.jbar-fill'),pct=bar.querySelector('.jbar-pct'),note=bar.querySelector('.jbar-note');
  const btn=$('#upbtn');btn.disabled=true;$('#msg').textContent='';
  // phase 1: the upload itself, with REAL transfer progress (XHR — fetch has none)
  const xhr=new XMLHttpRequest();
  xhr.open('POST','/api/upload?name='+name+'&symbol='+sym);
  xhr.upload.onprogress=e=>{if(e.lengthComputable){
    const p=Math.round(100*e.loaded/e.total);
    fill.style.width=p+'%';pct.textContent=p+'%';
    note.textContent='uploading '+(e.loaded/1e6).toFixed(0)+'/'+(e.total/1e6).toFixed(0)+' MB';}};
  xhr.onerror=()=>{btn.disabled=false;bar.style.display='none';
    $('#msg').innerHTML='<span class=neg>Upload failed at the network level — if this file is large, '
      +'the reverse proxy in front of the lab may cap the request body (nginx default is 1MB: raise '
      +'client_max_body_size). Fallback: scp the file to the VPS and run backtest.lab.ingest.</span>';};
  xhr.onload=()=>{
    let j={};try{j=JSON.parse(xhr.responseText)}catch(e){}
    if(xhr.status===413){btn.disabled=false;bar.style.display='none';
      $('#msg').innerHTML='<span class=neg>The proxy rejected the file as too large (HTTP 413). Raise '
        +'client_max_body_size in its config, or scp + backtest.lab.ingest.</span>';return}
    if(!j.ok){btn.disabled=false;bar.style.display='none';
      $('#msg').innerHTML='<span class=neg>'+((j.error||('upload failed (HTTP '+xhr.status+')')).replace(/</g,'&lt;'))+'</span>';return}
    // phase 2: normalize+catalog runs as a background job — same bar, live progress
    $('#msg').textContent='Upload complete ('+(j.bytes/1e6).toFixed(0)+' MB) — normalizing…';
    watchJob(j.job,'#upLog','#upbtn',(jj)=>{
      if(jj.status==='done'){$('#msg').innerHTML='<span class=pos>✓ '+j.dataset+' normalized & cataloged.</span>';load();loadWizard();}
      else{$('#msg').innerHTML='<span class=neg>normalize failed — see the log above.</span>';}
    });
  };
  xhr.send(f);
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
    const esS=$('#esSpec');if(esS)esS.innerHTML=specOpts;
    const ds=(await (await fetch('/api/datasets')).json()).datasets||[];
    const dsOpts=ds.map(d=>`<option value="${d.name}">${d.name}${d.symbol?' · '+d.symbol:''}</option>`).join('')
      ||'<option value="">no datasets — upload one</option>';
    $('#wDs').innerHTML=dsOpts;
    const swD=$('#swDs');if(swD)swD.innerHTML=dsOpts;
    const esD=$('#esDs');if(esD)esD.innerHTML=dsOpts;
    const stD=$('#stDs');if(stD)stD.innerHTML=dsOpts;
    const scD=$('#scDs');if(scD)scD.innerHTML=dsOpts;
    const daD=$('#daDs');if(daD)daD.innerHTML=dsOpts;
    const agD=$('#agDs');if(agD)agD.innerHTML=dsOpts;
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
    showTab('strats');                     // library card loads into the backtest runner (Strats)
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
    if(j.status==='queued'){pct.textContent='';note.textContent='queued — waiting for the running job to finish (one heavy job at a time)';}
    else if(p&&j.status==='running'){fill.style.width=p.pct+'%';pct.textContent=p.pct+'%';note.textContent=p.note||'';}
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
    '&micro='+($('#wMicro').checked?'1':'0')+'&window='+encodeURIComponent($('#wWin').value);
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
  if(!at.tuned.length){
    box.innerHTML='<div class=muted>No sweepable parameter flagged — below is what the data <b>did</b> find. '
      +'If the edge itself is absent, tuning cannot create one: that is the job of the discovery funnel (Verkenning).</div>'
      +(diagnosisHtml(at.diagnosis)||'<div class=muted style="margin-top:8px">No findings at all — the mechanics look consistent with this data; the (lack of) edge is the signal itself.</div>');
    return}
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
function renderEvalSweep(e){
  const box=$('#esOut');if(!e||!e.rows){box.style.display='none';return}
  box.style.display='block';
  const rows=e.rows.map(r=>{
    if(r.error)return `<tr><td>${r.key}</td><td colspan=6 class=neg>${(r.error||'').replace(/</g,'&lt;')}</td></tr>`;
    const pass=r.pass_rate_pct||0;
    const col=pass>0?'var(--gold)':'var(--sub)';
    const d=(r.median_days_to_pass===null||r.median_days_to_pass===undefined)?'—':r.median_days_to_pass;
    return `<tr><td style="text-align:left">${r.key}</td>
      <td>${(r.size||0).toLocaleString()}</td><td>${(r.difficulty??'—')}</td>
      <td style="color:${col}"><b>${pass.toFixed(1)}%</b></td><td>${d}</td>
      <td>${r.breach}</td><td>${r.timeout}</td></tr>`;}).join('');
  box.innerHTML=`<table style="margin-top:4px"><thead><tr>
      <th style="text-align:left">Program</th><th>Size</th><th title="profit target / drawdown">T/DD</th>
      <th>Pass</th><th title="median trading days to pass">Days</th><th>Breach</th><th>Timeout</th>
    </tr></thead><tbody>${rows}</tbody></table>
    <div class=muted style="margin-top:8px">Sorted by pass rate, then speed. T/DD is how much profit the
    program demands per unit of drawdown room — the higher, the harder the same strategy has it.</div>`;
}
$('#esRun').addEventListener('click',()=>{
  const ds=$('#esDs').value;if(!ds){$('#esLog').style.display='block';$('#esLog').textContent='Upload a dataset first.';return}
  $('#esOut').style.display='none';
  const qs='dataset='+encodeURIComponent(ds)+'&spec='+encodeURIComponent($('#esSpec').value)
    +'&tf='+encodeURIComponent($('#esTf').value)+'&firm='+encodeURIComponent($('#esFirm').value||'')
    +'&step='+encodeURIComponent($('#esStep').value||'5')+'&horizon='+encodeURIComponent($('#esHor').value||'20');
  postJob('/api/evalsweep',qs,'#esLog','#esRun',(j)=>{if(j&&j.evalsweep)renderEvalSweep(j.evalsweep);});
});
function renderPortfolio(p){
  const box=$('#pfOut');if(!p||!p.selected){box.style.display='none';return}
  box.style.display='block';
  const keep=p.selected.map(s=>`<div class=lensrow style="margin-top:4px;display:flex;gap:10px;align-items:center">
    <span class=tag style="color:var(--gold);border-color:var(--gold);min-width:52px;text-align:center">keep</span>
    <b style="min-width:150px">${s.name}</b>
    <span class=muted>net $${Math.round(s.edge||0).toLocaleString()}</span>
    <span class=muted>bad days ${s.bad_days}</span>
    <span class=muted>earns in: ${(s.top_regimes||[]).join(', ')||'—'}</span></div>`).join('');
  const drop=(p.rejected||[]).map(r=>`<div class=lensrow style="margin-top:4px;display:flex;gap:10px;align-items:flex-start">
    <span class=tag style="color:var(--rose);border-color:var(--rose);min-width:52px;text-align:center">drop</span>
    <b style="min-width:150px">${r.name}</b>
    <span class=muted style="flex:1">${(r.message||'').replace(/</g,'&lt;')}</span></div>`).join('');
  box.innerHTML=`<div class=muted><b style="color:var(--sand)">${p.selected.length} of ${p.n}</b> survivors are genuinely different.</div>`
    +keep+drop+`<div class=muted style="margin-top:10px">Dropped candidates add size to a position you already hold — not diversification.</div>`;
}
$('#pfRun').addEventListener('click',()=>{
  $('#pfOut').style.display='none';
  const qs='all='+($('#pfAll').checked?'1':'0')+'&max_corr='+encodeURIComponent($('#pfCorr').value)
    +'&max_badday='+encodeURIComponent($('#pfBad').value)+'&max_regime='+encodeURIComponent($('#pfReg').value);
  postJob('/api/portfolio',qs,'#pfLog','#pfRun',(j)=>{if(j&&j.portfolio)renderPortfolio(j.portfolio);});
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
  postJob('/api/generate',gqs(),'#gLog','#gRun',()=>{load();loadCandidates();syncVerifyWhat();});});
$('#gVerify').addEventListener('click',()=>postJob('/api/verify',gqs(),'#vfLog','#gVerify',()=>{load();loadCandidates();}));
// toon welke instellingen Verify gebruikt (ze staan in Verkenning)
function syncVerifyWhat(){
  const el=$('#vfWhat');if(!el)return;
  const ds=$('#gDs')&&$('#gDs').value||'—';
  el.textContent='uses '+ds+' · '+($('#gTf')?$('#gTf').value:'?')+' · holdout '
    +($('#gHold')?$('#gHold').value:'?')+'d · seed '+($('#gSeed')?$('#gSeed').value:'0')
    +'  (set in Verkenning)';
}
['#gDs','#gTf','#gHold','#gSeed'].forEach(sel=>{const e=$(sel);if(e)e.addEventListener('change',syncVerifyWhat)});
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
    m.innerHTML='saved <b style="color:var(--gold)">'+r.name+'</b> — geopend in Strats';
    await loadWizard(); const sel=$('#wSpec'); if(sel)sel.value=r.id;
    showTab('strats'); window.scrollTo({top:0,behavior:'smooth'});
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

// ---------- 2 · Pijplijn ----------
let PIPE=null;
const ST_MARK={passed:['+','var(--gold)'],data_parity:['=','var(--azure)'],
               failed:['x','var(--rose)'],running:['~','var(--azure)'],
               inconclusive:['?','var(--sub)'],todo:['·','var(--dim)']};
async function loadPipeline(){
  try{PIPE=await (await fetch('/api/pipeline')).json();}catch(e){return}
  const S=PIPE.stages;
  $('#plHead').textContent=S.length+' gated trappen · '+PIPE.fleet.length+' engines';
  // matrix: engine x trap
  const head='<tr><th style="text-align:left">Engine</th><th>Markt</th>'
    +S.map(s=>`<th title="${(s.title+' — '+s.gate).replace(/"/g,'&quot;')}">${s.n}${s.hard?'!':''}</th>`).join('')
    +'<th style="text-align:left">Gehaald t/m</th></tr>';
  const rows=PIPE.overview.map(o=>{
    const f=PIPE.fleet.find(x=>x.name===o.engine)||{};
    const cells=o.stages.map(v=>{const m=ST_MARK[v.status]||ST_MARK.todo;
      return `<td style="color:${m[1]};font-family:var(--mono)" title="${v.status}">${m[0]}</td>`}).join('');
    const reached=o.reached>=0?('trap '+o.reached):'—';
    return `<tr data-eng="${o.engine}" style="cursor:pointer"><td style="text-align:left">${o.engine.replace('EL_','')}</td>
      <td>${f.market||''}</td>${cells}<td style="text-align:left;color:${o.reached>=0?'var(--gold)':'var(--sub)'}">${reached}</td></tr>`;
  }).join('');
  $('#plMatrix').innerHTML=`<table><thead>${head}</thead><tbody>${rows}</tbody></table>
    <div class=muted style="margin-top:8px">+ gehaald · x gefaald · ~ loopt · ? inconclusief · · nog niet gedraaid.
    <b>!</b> = harde poort. Klik een rij voor de poorten per trap.</div>`;
  document.querySelectorAll('#plMatrix tbody tr').forEach(tr=>tr.addEventListener('click',()=>showEngine(tr.dataset.eng)));
  $('#plRules').innerHTML='<b>Niet-onderhandelbare grondregels</b><div style="margin-top:6px">'
    +PIPE.ground_rules.map((r,i)=>`<div class=lensrow style="margin-top:3px"><span class=tag style="min-width:26px;text-align:center">${i+1}</span> ${r}</div>`).join('')+'</div>';
  // trap 1 dekking
  const cov=PIPE.coverage||[]; const runnable=cov.filter(c=>c.runnable).length;
  $('#covCount').textContent=runnable+' van '+cov.length+' te draaien';
  $('#covTable').innerHTML = cov.length ? '<table><thead><tr><th style="text-align:left">Export</th>'
    +'<th>Markt</th><th>Trades</th><th style="text-align:left">Getest venster</th>'
    +'<th style="text-align:left">Dataset</th></tr></thead><tbody>'
    +cov.map(c=>`<tr><td style="text-align:left" class=mono>${c.export}</td><td>${c.market}</td>
      <td>${c.trades}</td><td style="text-align:left">${c.window}</td>
      <td style="text-align:left">${c.runnable
        ? '<span style="color:'+(c.missing_days?'var(--gold)':'var(--azure)')+'">'
          +c.datasets.join(', ')
          +(c.missing_days?' — staart ontbreekt, onder de 10%-tolerantie':'')+'</span>'
        : '<span style="color:var(--rose)">'
          +((c.too_short||[]).length
            ? 'te kort — '+c.too_short.join(', ')+'; export vraagt tot '+(c.window.split('→')[1]||'').trim()
            : 'ontbreekt — nodig: 1-minuut '+c.market+(c.twin?' of '+c.twin:'')+' over '+c.window)
          +'</span>'}
      </td></tr>`).join('')+'</tbody></table>'
    : '<div class=hint>Geen exports gevonden — zet ze in <span class=mono>validation/exports/</span> '
      +'of upload ze onder 1 · Data.</div>';

  // vloot
  $('#flCount').textContent=PIPE.fleet.length+' engines';
  $('#flTable').innerHTML='<table><thead><tr><th style="text-align:left">Engine</th><th>Markt</th><th>Qty</th>'
    +'<th>FVG</th><th>CVD</th><th>Stop</th><th>R</th><th>Expiry</th><th style="text-align:left">Dagexit</th>'
    +'<th style="text-align:left">Regime</th></tr></thead><tbody>'
    +PIPE.fleet.map(f=>`<tr><td style="text-align:left">${f.name.replace('EL_','')}${f.parity_pending?' <span class=tag style="color:var(--rose);border-color:var(--rose)">pariteit open</span>':''}</td>
      <td>${f.market}</td><td>${f.qty}</td><td>${f.fvg}</td><td>${f.cvd}</td><td>${f.stop}</td>
      <td>${f.r}</td><td>${f.expiry}</td><td style="text-align:left">${f.day_exit}</td>
      <td style="text-align:left">${f.regime}</td></tr>`
     +(f.pine_defect?`<tr><td colspan=10 style="text-align:left;color:var(--rose);font-size:12px;padding:2px 6px 8px">
       <b>! brondefect</b> — ${f.pine_defect.replace(/</g,'&lt;')}</td></tr>`:'')).join('')+'</tbody></table>';
  const engOpts=PIPE.fleet.map(f=>`<option value="${f.name}">${f.name.replace('EL_','')}</option>`).join('');
  const es=$('#stEngine'); if(es) es.innerHTML=engOpts;
  const sce=$('#scEngine'); if(sce) sce.innerHTML=engOpts;
}
function showEngine(name){
  const view=(PIPE.detail||{})[name]||[];
  const box=$('#stOut'); box.style.display='block';
  box.innerHTML=`<div style="font-size:13px"><b style="color:var(--gold)">${name.replace('EL_','')}</b> — poorten</div>`
    +view.map(v=>{const m=ST_MARK[v.status]||ST_MARK.todo;
      const blocked=(v.blocked_by||[]).length?`<div class=muted style="margin-left:36px;color:var(--rose)">geblokkeerd door open harde poort: ${v.blocked_by.join(', ')}</div>`:'';
      const done=['passed','data_parity','failed','inconclusive'].includes(v.status);
      return `<div style="margin-top:8px"><div style="display:flex;gap:9px;align-items:baseline;${done?'cursor:pointer':''}"
          ${done?`onclick="toggleArtifact('${name}','${v.n}',this)"`:''}>
        <span style="min-width:26px;text-align:right;font-family:var(--mono);color:${m[1]}">${v.n}${m[0]}</span>
        <b>${v.title}</b>${v.hard?' <span class=tag style="color:var(--rose);border-color:var(--rose)">harde poort</span>':''}
        <span class=muted>${v.status}${v.summary?' — '+v.summary:''}</span>${done?' <span class=muted style="color:var(--azure)">▸ cijfers</span>':''}</div>
        <div class=muted style="margin-left:36px">${v.gate}</div>${v.note?`<div class=muted style="margin-left:36px;color:var(--gold)">${v.note}</div>`:''}${blocked}
        <div class=artbox style="margin-left:36px;margin-top:6px;display:none"></div></div>`;
    }).join('');
  box.scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function toggleArtifact(engine,n,el){
  const box=el.parentElement.querySelector('.artbox');
  if(box.style.display!=='none'){box.style.display='none';return;}
  box.style.display='block'; box.innerHTML='<span class=muted>laden…</span>';
  try{
    const j=await (await fetch('/api/artifact?engine='+encodeURIComponent(engine)+'&stage='+n)).json();
    if(!j.found){box.innerHTML='<span class=muted>geen artefact — trap nog niet gedraaid</span>';return;}
    box.innerHTML=renderArtifact(n, j.data);
  }catch(e){box.innerHTML='<span style="color:var(--rose)">kon artefact niet laden</span>';}
}
function _tbl(rows){return '<table style="font-size:12px;margin-top:4px"><tbody>'+rows.map(r=>'<tr>'+r.map((c,i)=>`<td style="text-align:${i?'right':'left'};padding:1px 10px 1px 0">${c}</td>`).join('')+'</tr>').join('')+'</tbody></table>';}
function _e(e){return e?`${e.trades} tr · net $${(e.net||0).toLocaleString()} · PF ${e.pf} · WR ${e.wr}% · E $${e.expectancy}`:'—';}
function renderArtifact(n, d){
  n=String(n);
  if(n==='0'){const f=(d.findings||[]).map(x=>`<div style="color:var(--gold)">• ${x.message}</div>`).join('');
    return _tbl([['bars',(d.bars||0).toLocaleString()],['jaren',d.years],['sessies',d.sessions],
      ['bar-range (ticks)',d.median_bar_range_ticks],['roll-sprongen',d.roll_like_jumps],
      ['OHLC-fouten',d.ohlc_violations],['Delta ≠0 %',d.Delta_nonzero_pct]])+f;}
  if(n==='1'){const c=(d.checks||[]).map(x=>[x.name,(x.sim+' / '+x.pine),(x.ok?'ok':'✗ '+x.detail)]);
    const sp=d.pine_only_split||{};
    return _tbl(c)+`<div class=muted style="margin-top:4px">gepaard ${d.paired_pct}% · pine-only: `
      +`${sp.we_placed_but_never_filled||0} niet-gevuld · ${sp.we_were_in_a_position||0} in positie · ${sp.we_never_placed||0} geen order</div>`;}
  if(n==='2'){const y=Object.entries(d.by_year||{}).map(([k,v])=>[k,`${v.trades} tr`,`net $${(v.net||0).toLocaleString()}`,`PF ${v.pf}`,`E $${v.expectancy}`]);
    const k=d.kpis||{};
    return `<div class=muted>volledige periode: ${_e({trades:k.trades,net:k.net_profit,pf:k.profit_factor,wr:k.win_rate_pct,expectancy:k.expectancy})}</div>`+_tbl(y);}
  if(n==='3'){const r=Object.entries(d.by_regime||{}).map(([k,v])=>[k,`${v.share_pct}%`,`IN: ${_e(v.in)}`]);
    return `<div class=muted>totaal: ${_e(d.total)} · beste regime ${d.best_regime} (${d.best_share_pct}% netto)</div>`+_tbl(r);}
  if(n==='4'){const y=Object.entries(d.years||{}).map(([k,v])=>[k,`PF ${v.pf}`,`E $${v.expectancy}`]);
    const nb=(d.neighbourhood||[]).map(x=>[`${x.param} ${x.delta>0?'+':''}${x.delta}`,`PF ${x.pf}`,`${x.trades} tr`]);
    return `<div class=muted>LONG ${_e(d.long)}<br>SHORT ${_e(d.short)}</div>`
      +'<div class=muted style="margin-top:4px">per jaar</div>'+_tbl(y)
      +'<div class=muted style="margin-top:4px">parameterburen (plateau-check)</div>'+_tbl(nb);}
  if(n==='5')return _tbl([['volledige stop $',(d.stop_usd_total||0).toLocaleString()],
    ['worst-case incl. kosten $',(d.worst_case_usd||0).toLocaleString()],['DLL $',(d.dll||0).toLocaleString()],
    ['past onder DLL',d.fits_under_dll?'ja':'NEE'],['PF 1 contract',d.pf_1],['PF '+d.qty+' contracten',d.pf_n],
    ['PF grootte-invariant',d.pf_invariant?'ja':'NEE']]);
  if(n==='6'){const w=d.with_day_mgmt||{},o=d.without_day_mgmt||{};
    return _tbl([['','MÉT dagbeheer','ZONDER'],
      ['payouts',w.payouts,o.payouts],['gebankt $',(w.withdrawable||0).toLocaleString(),(o.withdrawable||0).toLocaleString()],
      ['$/account-dag',w.banked_per_account_day,o.banked_per_account_day],
      ['breach',w.breached?'ja':'nee',o.breached?'ja':'nee']]);}
  if(n==='7'){const m=(d.intended_model==='EOD')?'eod':'intraday';
    const f=(d.full_size||{})[m]||{},o=(d.one_contract||{})[m]||{};
    return `<div class=muted>model ${d.intended_model} · bevroren grootte ${d.frozen_qty} ct</div>`
      +_tbl([['',`volle (${d.frozen_qty} ct)`,'1 contract'],
      ['payouts',f.payouts,o.payouts],['gebankt $',(f.withdrawable||0).toLocaleString(),(o.withdrawable||0).toLocaleString()],
      ['breach',f.breached?'ja':'nee',o.breached?'ja':'nee']]);}
  if(n==='8')return _tbl([['$ per bezette account-dag',`<b style="color:var(--gold)">$${d.banked_per_account_day}</b>`],
    ['gemeten op',d.measured_at_full_size?(d.frozen_qty+' ct (volle grootte)'):'1 ct — volle grootte breacht'],
    ['payouts',d.payouts],['dagen tot payout #1',d.days_to_first_payout??'—'],['DLL-hits',d.dll_hits],
    ['handelsdagen',d.trading_days],['gebankt totaal $',(d.withdrawable||0).toLocaleString()],
    ['per maand $',(d.per_month||0).toLocaleString()],['breach',d.breached?'ja':'nee']]);
  if(n==='9')return `<div class=muted>mét uur/dag-masker: ${_e(d.with_filter)}<br>`
    +`zónder masker: ${_e(d.without_filter)}<br>masker draagt ${d.mask_contribution_pct}% van de netto bij</div>`;
  if(n==='10'){const dim=d.dimensions||{};
    const dr=Object.entries(dim).map(([k,v])=>[k,(v.ok?'ok':'✗'),(v.detail||'')]);
    const er=(d.exit_reasons||[]).map(x=>[x.category,`${x.sim_n} (${x.sim_pct}%)`,`${x.pine_n} (${x.pine_pct}%)`,`Δ${x.gap_pp}pp`]);
    const ex=d.excursion||{};
    return `<div class=muted>timing: ${d.matched_pct}% gepaard · ${d.same_bar_pct}% zelfde bar</div>`
      +'<div class=muted style="margin-top:4px">dimensies (harde deployment-poort)</div>'+_tbl(dr)
      +'<div class=muted style="margin-top:4px">exit-redenen · sim vs pine</div>'+_tbl(er)
      +`<div class=muted style="margin-top:4px">MFE/MAE op ${ex.paired||0} paren: mediaan `
      +`${ex.median_mfe_diff_ticks??'—'}t / ${ex.median_mae_diff_ticks??'—'}t · ${ex.within_tol_pct??'—'}% binnen tolerantie</div>`;}
  return '<pre style="font-size:11px;white-space:pre-wrap">'+JSON.stringify(d,null,1).slice(0,1200)+'</pre>';
}
async function loadExports(){
  try{const j=await (await fetch('/api/exports')).json();
    const el=$('#stExport'); if(!el)return;
    el.innerHTML=(j.exports||[]).map(x=>`<option value="${x}">${x}</option>`).join('')
      ||'<option value="">geen export — upload een .xlsx</option>';
  }catch(e){}
}
$('#stRun')&&$('#stRun').addEventListener('click',()=>{
  const qs='stage='+encodeURIComponent($('#stStage').value)+'&engine='+encodeURIComponent($('#stEngine').value)
    +'&dataset='+encodeURIComponent($('#stDs').value)+'&export='+encodeURIComponent($('#stExport').value||'');
  postJob('/api/stage',qs,'#stLog','#stRun',()=>{loadPipeline();});
});

// --- scorecard (Analysis) ---
function _svgEquity(ec){
  const pts=(ec&&ec.points)||[]; if(pts.length<2) return '<div class=muted>te weinig trades voor een curve</div>';
  const W=680,H=160,pad=6, ys=pts.map(p=>p.equity), mn=Math.min(0,...ys), mx=Math.max(0,...ys), rng=(mx-mn)||1;
  const x=i=>pad+(W-2*pad)*i/(pts.length-1), y=v=>pad+(H-2*pad)*(1-(v-mn)/rng);
  const path=pts.map((p,i)=>`${i?'L':'M'}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join(' ');
  const zeroY=y(0).toFixed(1), col=(ys[ys.length-1]>=0)?'var(--gold)':'var(--rose)';
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio=none style="width:100%;height:${H}px;background:var(--deep);border:1px solid var(--line);border-radius:3px">
    <line x1="${pad}" y1="${zeroY}" x2="${W-pad}" y2="${zeroY}" stroke="var(--line)" stroke-dasharray="3 3"/>
    <path d="${path}" fill=none stroke="${col}" stroke-width=1.6 vector-effect=non-scaling-stroke/></svg>`;
}
function renderScorecard(card){
  const box=$('#scOut'); box.style.display='block';
  if(!card||card.empty||!card.trades){box.innerHTML='<div class=muted>Geen trades in dit venster.</div>';return}
  const k=card.kpis,bd=card.by_direction,st=card.streaks,ex=card.excursion,ht=card.hold_time_bars,dy=card.days;
  const money=v=>'$'+Math.round(v).toLocaleString();
  const kpi=(lab,val,cls)=>`<div style="min-width:92px"><div class=muted style="font-size:11px">${lab}</div><div style="font-family:var(--display);font-size:20px;color:${cls||'var(--gold)'}">${val}</div></div>`;
  const dirRow=(nm,d)=>[nm,d.trades,money(d.net),'PF '+d.pf,d.win_rate_pct+'%','E $'+d.expectancy];
  $('#scMeta').textContent=card.engine.replace('EL_','')+' · '+card.dataset+' · '+card.posture;
  box.innerHTML=
    `<div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:12px">
      ${kpi('trades',k.trades)}${kpi('net',money(k.net_profit),k.net_profit>=0?'var(--azure)':'var(--rose)')}
      ${kpi('PF',k.profit_factor)}${kpi('win%',k.win_rate_pct)}${kpi('E/trade','$'+k.expectancy)}
      ${kpi('max DD',money(k.max_drawdown),'var(--rose)')}</div>`
    +`<div class=muted style="font-size:11px;margin-bottom:3px">equity-curve — gebankt per trade${card.equity_curve.downsampled?' (uitgedund)':''}</div>`
    +_svgEquity(card.equity_curve)
    +`<div style="display:flex;gap:26px;flex-wrap:wrap;margin-top:14px">
        <div><div class=muted style="font-size:11px">per richting</div>${_tbl([dirRow('long',bd.long),dirRow('short',bd.short)])}</div>
        <div><div class=muted style="font-size:11px">streaks &amp; excursie</div>${_tbl([
          ['langste win',st.longest_win],['langste verlies',st.longest_loss],
          ['MFE ø (t)',ex.avg_mfe_ticks],['MAE ø (t)',ex.avg_mae_ticks],['hold ø (bars)',ht.avg]])}</div>
        <div><div class=muted style="font-size:11px">best / worst &amp; dagen</div>${_tbl([
          ['best',money(card.best_trade.net)+' ('+(card.best_trade.reason||'?')+')'],
          ['worst',money(card.worst_trade.net)+' ('+(card.worst_trade.reason||'?')+')'],
          ['win-dagen',dy.win_days+'/'+dy.trading_days+' ('+dy.win_day_pct+'%)'],
          ['beste/slechtste dag',money(dy.best_day)+' / '+money(dy.worst_day)]])}</div>
      </div>`
    +`<div style="margin-top:14px"><div class=muted style="font-size:11px">exit-redenen (aantal · net)</div>${
        _tbl((card.exit_reason_edge||[]).map(r=>[r.reason,r.trades,money(r.net)]))}</div>`;
}
function _isoosKpi(c){
  const k=(c&&c.kpis)||{};
  if(!k.trades) return '<span class=muted>geen trades</span>';
  const m=v=>'$'+Math.round(v).toLocaleString();
  return `${k.trades} tr · net <b style="color:${k.net_profit>=0?'var(--azure)':'var(--rose)'}">${m(k.net_profit)}</b> · PF ${k.profit_factor} · WR ${k.win_rate_pct}% · E $${k.expectancy} · maxDD ${m(k.max_drawdown)}`;
}
function renderIsOos(p){
  const box=$('#scOut'); box.style.display='block';
  $('#scMeta').textContent=(p.engine||'').replace('EL_','')+' · '+p.dataset+' · '+p.posture+' · holdout '+p.holdout_days+'d';
  const vc=p.holds?'var(--azure)':'var(--rose)';
  box.innerHTML=
    `<div style="border-left:3px solid ${vc};padding:6px 12px;margin-bottom:12px">
       <b style="color:${vc}">${p.holds?'✓ edge houdt stand out-of-sample':'✗ overfit-risico'}</b>
       <span class=muted style="margin-left:8px">retain ${p.retain} (OOS PF ÷ IS PF, drempel 0.60)</span></div>`
    +`<table style="font-size:12.5px;width:100%"><tbody>
        <tr><td style="padding:4px 10px 4px 0;color:var(--gold)">in-sample</td><td style="text-align:left">${_isoosKpi(p.is)}</td></tr>
        <tr><td style="padding:4px 10px 4px 0;color:var(--gold)">out-of-sample</td><td style="text-align:left">${_isoosKpi(p.oos)}</td></tr>
      </tbody></table>`
    +`<div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:12px">
        <div style="flex:1;min-width:280px"><div class=muted style="font-size:11px;margin-bottom:3px">IS equity</div>${_svgEquity(p.is.equity_curve)}</div>
        <div style="flex:1;min-width:280px"><div class=muted style="font-size:11px;margin-bottom:3px">OOS equity</div>${_svgEquity(p.oos.equity_curve)}</div>
      </div>`
    +`<div class=muted style="font-size:11.5px;margin-top:8px">${p.verdict} · cutoff ${(''+p.cutoff).slice(0,10)}</div>`;
}
$('#scRun')&&$('#scRun').addEventListener('click',()=>{
  const eng=$('#scEngine').value, ds=$('#scDs').value;
  if(!eng||!ds){$('#scLog').style.display='block';$('#scLog').textContent='Kies een engine én dataset.';return}
  const hold=parseInt($('#scHold').value||'0',10)||0;
  const qs='engine='+encodeURIComponent(eng)+'&dataset='+encodeURIComponent(ds)
    +'&posture='+encodeURIComponent($('#scPosture').value)+'&holdout_days='+hold;
  postJob('/api/scorecard',qs,'#scLog','#scRun',(j)=>{
    const iso=(j.log||[]).find(l=>l.startsWith('ISOOS_JSON '));
    if(iso){try{renderIsOos(JSON.parse(iso.slice(11)));return;}catch(e){}}
    const line=(j.log||[]).find(l=>l.startsWith('SCORECARD_JSON '));
    if(line){try{renderScorecard(JSON.parse(line.slice(15)));}catch(e){$('#scOut').style.display='block';$('#scOut').innerHTML='<div class=muted>kon scorecard niet lezen</div>';}}
  });
});

// --- data prep (Data): validate + aggregate ---
function renderAudit(rep){
  const box=$('#daOut'); box.style.display='block';
  const sev={high:'var(--rose)',medium:'var(--gold)',low:'var(--sub)'};
  const f=(rep.findings||[]).map(x=>`<div style="color:${sev[x.severity]||'var(--sub)'};font-size:12.5px;margin-top:2px">[${x.severity}] ${x.message}</div>`).join('')
    ||'<div style="color:var(--azure);font-size:12.5px">geen bevindingen — schoon</div>';
  const rows=[['bars',(rep.bars||0).toLocaleString()],
    ['periode',(''+(rep.first||'')).slice(0,10)+' → '+(''+(rep.last||'')).slice(0,10)+' ('+rep.years+'j)'],
    ['sessies',rep.sessions],['bar-interval',rep.bar_interval],['tijdzone',rep.timezone],
    ['gaps >6h / intrasessie',(rep.gaps_over_6h??'—')+' / '+(rep.intrasession_gap_minutes??'—')+'m'],
    ['OHLC-fouten',rep.ohlc_violations],['bar-range (ticks)',rep.median_bar_range_ticks??'—'],
    ['roll-sprongen',rep.roll_like_jumps??'—'],['Delta ≠0 %',rep.Delta_nonzero_pct??'—']];
  const vc=rep.verdict==='clean'?'var(--azure)':rep.verdict==='attention'?'var(--rose)':'var(--gold)';
  box.innerHTML=`<div class=muted style="font-size:11px;margin-bottom:4px">${rep.dataset} · ${rep.symbol||'?'} · verdict <b style="color:${vc}">${rep.verdict}</b></div>`
    +_tbl(rows)+'<div style="margin-top:8px">'+f+'</div>';
}
$('#daRun')&&$('#daRun').addEventListener('click',()=>{
  const ds=$('#daDs').value; if(!ds){$('#daLog').style.display='block';$('#daLog').textContent='Kies een dataset.';return}
  postJob('/api/dataset/audit','dataset='+encodeURIComponent(ds),'#daLog','#daRun',(j)=>{
    const line=(j.log||[]).find(l=>l.startsWith('AUDIT_JSON '));
    if(line){try{renderAudit(JSON.parse(line.slice(11)));}catch(e){}}
  });
});
$('#agRun')&&$('#agRun').addEventListener('click',()=>{
  const ds=$('#agDs').value; if(!ds){$('#agLog').style.display='block';$('#agLog').textContent='Kies een bron-dataset.';return}
  const qs='dataset='+encodeURIComponent(ds)+'&tf='+encodeURIComponent($('#agTf').value)+'&name='+encodeURIComponent($('#agName').value||'');
  postJob('/api/dataset/aggregate',qs,'#agLog','#agRun',(j)=>{
    const line=(j.log||[]).find(l=>l.startsWith('AGGREGATE_JSON '));
    if(line){try{const r=JSON.parse(line.slice(15));const o=$('#agOut');o.style.display='block';
      o.innerHTML='<span style="color:var(--azure)">✓ nieuwe dataset <b>'+r.dataset+'</b></span> — '+(r.rows||0).toLocaleString()+' bars · '+r.timeframe;}catch(e){}}
    loadWizard(); loadGenDatasets();
  });
});

function showTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on', t.id==='tab-'+name));
  document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name));
  try{history.replaceState(null,'','#'+name);}catch(e){}
}
document.querySelectorAll('#tabs button').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));
const gAdvT=$('#gAdvToggle');
if(gAdvT)gAdvT.addEventListener('click',()=>{const a=$('#gAdv');const open=a.style.display!=='none';a.style.display=open?'none':'flex';gAdvT.textContent=open?'+ advanced':'− advanced';});
showTab((location.hash&&document.getElementById('tab-'+location.hash.slice(1)))?location.hash.slice(1):'pipeline');
loadPipeline();loadExports();

loadWizard();loadGenDatasets();loadBuilder();
load();
loadCandidates();
setTimeout(syncVerifyWhat, 300);   // na loadWizard(), zodra de dropdowns gevuld zijn
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

<div class=steps>Levenscyclus: <b>Data</b> laden → <b>Vaults</b> strategie vormen → <b>Strats</b> fijnslijpen → <b>Analysis</b> doormeten → <b>Pijplijn</b> valideren tot live &nbsp;·&nbsp; <b>Verkenning</b> = nieuwe strategieën ontdekken (vóór bevriezing)</div>
<div class=tabs id=tabs>
  <button data-tab=data>Data</button>
  <button data-tab=vaults>Vaults</button>
  <button data-tab=strats>Strats</button>
  <button data-tab=analysis>Analysis</button>
  <button data-tab=pipeline class=on>Pijplijn</button>
  <button data-tab=verkenning>Verkenning</button>
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
    <pre id=upLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:200px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Valideer dataset — datakwaliteit</b><span class=muted>coverage · gaps · OHLC · roll · tick</span></div>
    <div class=hint>Draai de data-audit (dezelfde als trap 0): dekking, tijdzone, continuïteit/gaps, OHLC-sanity, tick-size, Delta-dekking en contract-roll-artefacten. Een <b>high</b>-bevinding betekent: eerst oplossen vóór je erop backtest.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Dataset</span><select id=daDs style="min-width:180px"></select></label>
      <button class=go id=daRun>Valideer</button>
    </div>
    <div id=daOut style="display:none;margin-top:14px"></div>
    <pre id=daLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:200px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Aggregeer timeframe — 1m → 5/15/30m…</b><span class=muted>sessie-aligned op 18:00 ET</span></div>
    <div class=hint>Maak van een 1-minuut dataset een grofmazigere, <b>opgeslagen</b> dataset (verschijnt als nieuwe kaart in de catalogus). Sessie-aligned en gap-safe. Let op: de pijplijn-poorten zijn op <b>1m</b> gevalideerd — een geaggregeerde set is voor analyse/verkenning, niet om trap 1 tegen een 1m-export te herdraaien.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Bron (1m)</span><select id=agDs style="min-width:180px"></select></label>
      <label class=field><span class=fld>Timeframe</span><select id=agTf>
        <option>5m</option><option>10m</option><option>15m</option><option>30m</option>
        <option>1h</option><option>2h</option><option>4h</option></select></label>
      <label class=field><span class=fld>Naam (optioneel)</span><input id=agName placeholder="&lt;bron&gt;_&lt;tf&gt;" style="width:160px"></label>
      <button class=go id=agRun>Aggregeer</button>
    </div>
    <div id=agOut style="display:none;margin-top:12px"></div>
    <pre id=agLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:200px;overflow:auto;white-space:pre-wrap"></pre>
  </div>
</div>

<!-- ===================== VAULTS ===================== -->
<div class=tab id=tab-vaults>
  <div class=hint style="margin-bottom:14px">Waar strategieën tot stand komen — de <b>grofmazige</b> basis. Vink indicatoren aan of begin bij een preset; opslaan zet de strategie klaar in <b>Strats</b> om te fijnslijpen. Een strategie wordt pas een pijplijn-engine nadat hij bevroren is.</div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Bouw een strategie — indicatoren aanvinken</b><span class=muted>redundantie-guard aan</span></div>
    <div class=hint>Kies een setup-klasse en entry, vink coherente filters en desgewenst een regime-gate aan, en zet een basis-preset (de handmatige parameter-ingang). De bouwer stelt de spec samen en toont meteen de score en de framework-stack. Opslaan → klaar in Strats.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Setup-klasse</span><select id=bSetup style="min-width:150px"></select></label>
      <label class=field><span class=fld>Entry</span><select id=bEntry style="min-width:160px"></select></label>
      <label class=field><span class=fld>Basis-preset</span><select id=bPreset style="min-width:150px"></select></label>
      <label class=field><span class=fld>Naam</span><input id=bName placeholder="custom" style="width:130px"></label>
    </div>
    <div style="display:flex;gap:28px;flex-wrap:wrap;margin-top:12px">
      <div><div class=muted style="font-size:11px;margin-bottom:5px">filters</div>
        <div id=bFilters style="display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px"></div></div>
      <div><div class=muted style="font-size:11px;margin-bottom:5px">regime-gate (leeg = alle regimes)</div>
        <div id=bRegimes style="display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px"></div></div>
    </div>
    <div id=bPreview style="margin-top:14px"></div>
    <div style="margin-top:12px"><button class=go id=bSave>Opslaan → Strats</button><span id=bMsg class=muted style="margin-left:10px"></span></div>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Strategy library</b><span class=muted id=libCount>—</span></div>
    <div class=hint>Governed + promoted strategies — grade, entries, gates, exit and framework stack. Click a card to load it into the Strats runner.</div>
    <div class=lib id=libRows></div>
  </div>
</div>

<!-- ===================== PIJPLIJN ===================== -->
<div class=tab id=tab-pipeline>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Het stappenplan — MEX research pipeline v7</b>
      <span class=muted id=plHead>twaalf gated trappen</span></div>
    <div class=hint>Een engine gaat pas naar de volgende trap als de poort van de vorige aantoonbaar
      gehaald is. Een poort niet halen is een geldige uitkomst: leg hem vast en stop. Afdwingen staat
      bewust <b>uit</b> — je mag elke trap draaien, maar de status van alles ervóór blijft zichtbaar,
      zodat een resultaat dat vooruitloopt op zijn poort ook zichtbaar vooruitloopt.</div>
    <div id=plMatrix style="margin-top:14px;overflow-x:auto"></div>
    <div id=plRules style="margin-top:16px"></div>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Trap draaien</b><span class=muted>trap 0 en 1 zijn geïmplementeerd</span></div>
    <div class=hint>Trap 0 stelt vast wat de data <i>is</i>. Trap 1 is de <b>harde poort</b>: de simulator
      moet de Pine-baseline reproduceren. Zolang die niet gehaald is, is elk parameterzoekresultaat
      eronder ongeldig (grondregel 1) — dat is geen formaliteit maar de reden waarom eerdere rankings
      zijn vervallen.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Trap</span><select id=stStage style="min-width:230px">
        <option value=0>0 · Data-audit</option>
        <option value=1>1 · Pine-pariteit (harde poort)</option>
        <option value=10>10 · TradingView-validatie (harde poort)</option>
      </select></label>
      <label class=field><span class=fld>Engine</span><select id=stEngine style="min-width:210px"></select></label>
      <label class=field><span class=fld>Dataset</span><select id=stDs style="min-width:150px"></select></label>
      <label class=field><span class=fld>TV-export (trap 1 &amp; 10)</span><select id=stExport style="min-width:200px"></select></label>
      <button class=go id=stRun>Draai trap</button>
    </div>
    <div id=stOut style="display:none;margin-top:14px"></div>
    <pre id=stLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:260px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Trap 1 · dekking — kan de harde poort überhaupt draaien?</b>
      <span class=muted id=covCount>—</span></div>
    <div class=hint>Per TradingView-export: welke markt en welk venster er écht getest is
      (de <span class=mono>Backtesting range</span>, niet de <span class=mono>Start date</span>-input),
      en of we daar data voor hebben. Zolang dit rood staat is trap 1 dicht en zijn trap 2 t/m 9
      ongeldig — grondregel 1.</div>
    <div id=covTable style="margin-top:12px;overflow-x:auto"></div>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>De vloot — v1_0_0, pijplijn-invoer</b><span class=muted id=flCount>—</span></div>
    <div class=hint>Overgenomen uit <span class=mono>MEX_FLEET_PACKAGE_2026-08-23/01_Scripts</span>. Dit zijn
      geen getunede waarden maar de exacte inputs van de uitgebrachte Pine-scripts — precies waarmee de
      simulator op trap 1 pariteit moet aantonen.</div>
    <div id=flTable style="margin-top:12px;overflow-x:auto"></div>
  </div>

</div>

<div class=tab id=tab-verkenning>
  <div class=hint style="margin-bottom:14px">De <b>mill</b> — strategie-ontdekking vóór bevriezing. Doorzoek een ruimte, vind kandidaten, toets ze out-of-sample, selecteer een niet-gecorreleerde set. Dit is de dev-kant: een gevonden strategie gaat pas naar de pijplijn nádat hij bevroren is (grondregel 1: pariteit vóór optimalisatie). Losstaand van de bevroren vloot.</div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Discover strategies</b><span class=muted>seed a thesis — the machine finds the rest</span></div>
    <div class=hint>You set the <b>thesis</b> (and optionally a regime to focus on); the search <b>discovers</b> the entry, filters, params <b>and the stop/target mechanics</b> — nothing is assumed up front, not even per asset. It screens candidates in-sample, then Verify OOS. Filters and mechanics are an <b>outcome</b> of the test. Leave the thesis on "Any" for unbiased broad discovery. Results appear in the Candidates panel below. Tip: use 5m or 15m (not 1m) and set a "Coarse since" date under + advanced to keep the 20-year screen fast.</div>
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
      <b class=sub>Candidates — wat de OOS-poort overleefde</b><span class=muted id=lbSrc>no candidates yet</span></div>
    <div class=hint>The overfit gate: every candidate from <b>Discover</b> above is re-run on the untouched
      hold-out window. IS PF next to OOS PF — what does not hold here won the in-sample lottery.
      Run this <b>before</b> 3.2, it also records the daily series the portfolio step needs.</div>
    <div class=up style="margin-top:12px">
      <button class=go id=gVerify>Verify OOS</button>
      <span class=muted id=vfWhat style="margin-left:4px"></span>
    </div>
    <pre id=vfLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:180px;overflow:auto;white-space:pre-wrap"></pre>
    <div style="overflow-x:auto"><table style="margin-top:8px"><thead><tr>
      <th style="text-align:left">Strategy</th><th style="text-align:left">Indicators</th>
      <th>IS PF</th><th>OOS PF</th><th>Retain</th><th>OOS n</th><th>Verdict</th>
    </tr></thead><tbody id=lbrows></tbody></table></div>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Portfolio — welke overlevers écht verschillen</b>
      <span class=muted>a set, not a ranking</span></div>
    <div class=hint>The OOS gate judges every candidate <i>on its own</i>, so survivors are often the
      same trade under different names — and running clones on separate prop accounts means they
      breach on the <b>same day</b>. This measures it: daily-return correlation (only positive
      counts against you — losing on opposite days is a feature), shared <b>bad days</b>
      (a day losing 20%+ of the drawdown buffer), and regime overlap. Every drop names the peer
      it duplicates.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Include failed</span><span style="padding:8px 0"><input type=checkbox id=pfAll> also non-passing</span></label>
      <label class=field><span class=fld>Max corr</span><input id=pfCorr value="0.35" style="width:70px"></label>
      <label class=field><span class=fld>Max bad-day overlap</span><input id=pfBad value="0.40" style="width:70px"></label>
      <label class=field><span class=fld>Max regime overlap</span><input id=pfReg value="0.90" style="width:70px"></label>
      <button class=go id=pfRun>Select portfolio</button>
    </div>
    <div id=pfOut style="display:none;margin-top:14px"></div>
    <pre id=pfLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:180px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

</div>

<!-- ===================== STRATS ===================== -->
<div class=tab id=tab-strats>
  <div class=hint style="margin-bottom:14px">Fijnslijpen van bestaande strategieën — parameter-presets tunen, optimaliseren en multi-timeframe testen. Optimalisatie hoort <b>hier</b> thuis (dev), niet ná bevriezing (grondregel 1).</div>

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
      <b class=sub>Eval-spectrum — welk account, hoe snel</b>
      <span class=muted>every firm sells a different bargain</span></div>
    <div class=hint>Runs a <b>fresh eval</b> every N sessions against <b>each program in the registry</b>
      and reports pass rate and median <b>trading days</b> to pass. The task differs sharply per program —
      target ÷ drawdown runs from <b>0.8</b> (FundedNext 15k) to <b>3.33</b> (DayTraders 25k), so the same
      strategy must earn four times as much per unit of drawdown room at one firm as at another.
      Position size scales to each account (target_dd), otherwise a 250k test measures nothing.</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Strategy</span><select id=esSpec style="min-width:190px"></select></label>
      <label class=field><span class=fld>Dataset</span><select id=esDs style="min-width:150px"></select></label>
      <label class=field><span class=fld>Timeframe</span><input id=esTf value="1m" style="width:70px"></label>
      <label class=field><span class=fld>Firm</span><input id=esFirm placeholder="all" style="width:110px"></label>
      <label class=field><span class=fld>Step (sessions)</span><input id=esStep value="5" style="width:70px"></label>
      <label class=field><span class=fld>Horizon</span><input id=esHor value="20" style="width:70px"></label>
      <button class=go id=esRun>Run spectrum</button>
    </div>
    <div id=esOut style="display:none;margin-top:14px;overflow-x:auto"></div>
    <pre id=esLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:180px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Backtest draaien — een strategie doormeten</b><span class=muted>test a strategy toward a goal</span></div>
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
      <label class=field><span class=fld>Window</span><select id=wWin>
        <option value=recent3y>Recent 3y — fast</option>
        <option value=full>Full history — validation (minutes)</option>
      </select></label>
      <label class=field><span class=fld>Micro twin</span><span style="padding:8px 0"><input type=checkbox id=wMicro> + MGC/MES…</span></label>
      <button class=go id=wRun>Run</button>
    </div>
    <pre id=wLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:220px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

</div>

<!-- ===================== ANALYSIS ===================== -->
<div class=tab id=tab-analysis>
  <div class=hint style="margin-bottom:14px">Doormeten, geen poort — het volledige performancebeeld van één engine op één dataset: equity-curve, streaks, best/worst, per-richting, MFE/MAE, hold-time en exit-redenen. Onderaan de run-historie.</div>

  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <b class=sub>Scorecard — meet één engine door</b><span class=muted id=scMeta></span></div>
    <div class=hint><b>Deployment</b> = zoals de engine live draait (account-overlay aan); <b>Raw</b> = de kale mechaniek (1 contract, geen dagcaps). Geen Sharpe/Sortino in v1 (apart besluit, D-23).</div>
    <div class=up style="margin-top:12px">
      <label class=field><span class=fld>Engine</span><select id=scEngine style="min-width:210px"></select></label>
      <label class=field><span class=fld>Dataset</span><select id=scDs style="min-width:150px"></select></label>
      <label class=field><span class=fld>Houding</span><select id=scPosture>
        <option value=deploy>Deployment (overlay aan)</option>
        <option value=raw>Raw (kale mechaniek)</option></select></label>
      <label class=field><span class=fld>Holdout (d)</span><input id=scHold value=0 style="width:80px" title="0 = geen split; N = laatste N dagen als out-of-sample"></label>
      <button class=go id=scRun>Scorecard</button>
    </div>
    <div id=scOut style="display:none;margin-top:14px"></div>
    <pre id=scLog style="display:none;margin:12px 0 0;padding:12px;background:#081D46;border:1px solid var(--line);border-radius:3px;font-family:var(--mono);font-size:11px;color:var(--sub);max-height:200px;overflow:auto;white-space:pre-wrap"></pre>
  </div>

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
