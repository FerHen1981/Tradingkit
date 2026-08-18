"""Fine-grained parameter sweep — phase 3 of diagnose/instrument/sweep.

Vary ONE parameter across a range, run the whole strategy at each value, and
return the response curve. Every value is measured on BOTH raw edge (PF / net /
trades / win% / maxDD) and funded-account survival — there is deliberately no
goal flag: suitability (funded · eval-only · nothing) is an OUTCOME of the test.
This is how "is the stop too wide / the FVG band too big" stops being a guess:
you see where the current value sits on the curve and where the response peaks.
The diagnostic (backtest.diagnose) tells you WHICH parameter to sweep; --auto
lets it also derive the ranges from the measured distributions.

    python -m backtest.sweep --data <csv> --preset EL_TESORO --symbol GC --tf 1m --auto
    python -m backtest.sweep --data <csv> --preset EL_TESORO --symbol GC --tf 1m \
        --param fixed_stop_ticks --values 20,30,40,50,60,80,100

Engine-only parameters (stop/TP/sizing) reuse one indicator computation across
all values; parameters that change the signal itself (FVG band, CVD streak,
regime knobs) recompute indicators per value. Values run across worker processes.
"""
from __future__ import annotations

import os

# Cap BLAS/OpenMP thread pools BEFORE numpy/pandas load (also set by the Lab
# job-runner). We parallelize with worker processes, so BLAS threads only
# oversubscribe the cores — and BLAS pools are fork-unsafe: forking a worker
# pool after heavy numpy work can inherit a locked mutex and deadlock the
# children (auto-tune parking at a lever boundary).
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from . import data as data_mod
from . import indicators as ind_mod
from .config import PRESETS, contract
from .engine import Engine
from .metrics import kpis

# Parameters that only change the engine's exit/sizing mechanics, not the entry
# signal arrays — so one indicator computation is shared across all values.
ENGINE_ONLY = {
    "fixed_stop_ticks", "max_stop_ticks", "tp_fixed_ticks", "r_multiple",
    "contract_size", "be_trigger_ticks", "be_offset_ticks", "trail_start_ticks",
    "trail_buffer_ticks", "day_trail_usd", "swing_buf_ticks", "expiry_bars",
    "use_breakeven", "use_trail", "use_recov_trail", "stop_swing",
}

_DF = None
_IND = None      # shared indicators (engine-only sweeps); None => recompute per value
_ARR = None      # pre-extracted engine arrays, shared read-only via fork COW —
                 # measured: without this, each worker rebuilt ~1-2GB of arrays
                 # over a 20y 1m frame (8.7GB total RSS with 2 workers = swap/OOM
                 # on the VPS). One parent copy, inherited copy-on-write, fixes it.


def _pool_init(df, ind, arrays=None):
    global _DF, _IND, _ARR
    _DF, _IND, _ARR = df, ind, arrays


def _run_value(cfg):
    """Worker: run the strategy at one parameter value. ALWAYS measures both the
    raw edge (classic KPIs) and the funded-account overlay — suitability is an
    OUTCOME of the test, never a goal chosen up front. The overlay is a post-hoc
    simulation over the daily P&L, so measuring it costs nothing."""
    if _ARR is not None:                       # engine-only sweep: shared arrays
        res = Engine(cfg, arrays=_ARR, research_mode=True).run()
    else:
        ind = _IND if _IND is not None else ind_mod.compute(_DF, cfg)
        res = Engine(cfg, _DF, ind, research_mode=True).run()
    k = kpis(res)
    row = {"trades": k.get("trades", 0), "net": k.get("net_profit", 0.0),
           "pf": k.get("profit_factor", 0.0), "win_pct": k.get("win_rate_pct", 0.0),
           "max_dd": k.get("max_drawdown", 0.0)}
    from .funded import daily_from_trades, simulate_funded, summarize
    s = summarize(simulate_funded(daily_from_trades(res.trades),
                                  account_size=cfg.initial_capital or 50_000))
    row["funded"] = {"breached": s["breached"], "payouts": s["payouts"],
                     "withdrawn": s["withdrawable"], "trading_days": s["trading_days"]}
    return row


def _coerce(sample, raw: str):
    """Coerce a CLI string to the type of the current value."""
    if isinstance(sample, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(sample, int) and not isinstance(sample, bool):
        return int(float(raw))
    if isinstance(sample, float):
        return float(raw)
    return raw


def sweep_param(df, base_cfg, param: str, values: list,
                jobs: int = 0, shared_ind=None, shared_arrays=None, prog=None) -> dict:
    """Run base_cfg across `values` of `param`. Returns {param, current, curve,
    best, best_funded, engine_only}. `best` is purely the strongest raw edge (PF);
    `best_funded` is the strongest value that ALSO survives the funded overlay —
    reported side by side so the outcome says what the strategy is suited for
    (funded / eval-only / nothing) without a goal biasing the pick. `shared_ind` /
    `shared_arrays` let a caller (auto-tune) reuse one indicator computation and
    one array extraction across engine-only sweeps; `prog(done, total)` overrides
    the per-value progress line."""
    if not hasattr(base_cfg, param):
        raise ValueError(f"unknown parameter {param!r}")
    current = getattr(base_cfg, param)
    engine_only = param in ENGINE_ONLY
    if engine_only:
        if shared_ind is None and shared_arrays is None:
            # the shared indicator build (~35s on 20y 1m) is otherwise silent — a
            # note keeps the UI caption moving before the per-value bar starts.
            def _ind_prog(k, tot):
                print(f"PROGRESS 0 {max(len(values), 1)} computing shared indicators {k}/{tot}", flush=True)
            shared_ind = ind_mod.compute(df, base_cfg, progress=_ind_prog)
        if shared_arrays is None:
            # extract the engine arrays ONCE in the parent; workers inherit them
            # copy-on-write (fork), instead of each rebuilding ~1-2GB from the
            # frames — measured 8.7GB total RSS on 20y 1m without this.
            from .engine import extract
            shared_arrays = extract(df, shared_ind)
        init_args = (None, None, shared_arrays)
    else:
        shared_ind = None       # signal params must recompute indicators per value
        init_args = (df, None, None)
    if prog is None:
        def prog(done, total, _p=param):
            print(f"PROGRESS {done} {total} sweep {_p}", flush=True)

    cfgs = [base_cfg.with_(**{param: v}) for v in values]
    jobs = jobs if jobs and jobs > 0 else (os.cpu_count() or 1)
    rows = [None] * len(values)
    if jobs <= 1:
        _pool_init(*init_args)
        for i, payload in enumerate(cfgs):
            rows[i] = _run_value(payload)
            prog(i + 1, len(values))
        _pool_init(None, None, None)    # release module refs after a serial sweep
    else:
        with ProcessPoolExecutor(max_workers=jobs, initializer=_pool_init,
                                 initargs=init_args) as ex:
            futs = {ex.submit(_run_value, payload): i for i, payload in enumerate(cfgs)}
            done = 0
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    rows[i] = fut.result()
                except Exception as e:
                    rows[i] = {"error": repr(e)}
                done += 1
                prog(done, len(values))

    curve = [{"value": v, **(r or {})} for v, r in zip(values, rows)]
    valid = [c for c in curve if not c.get("error") and (c.get("trades") or 0) > 0]
    # two UNBIASED readings, side by side: strongest raw edge, and strongest value
    # that also survives the funded account. Neither influences the other — the
    # outcome (not a chosen goal) says what the strategy is suited for.
    best = max(valid, key=lambda c: c.get("pf") or 0) if valid else None
    survivors = [c for c in valid if not c.get("funded", {}).get("breached", True)]
    best_funded = max(survivors, key=lambda c: c.get("pf") or 0) if survivors else None
    return {"param": param, "current": current, "engine_only": engine_only,
            "curve": curve, "best": best, "best_funded": best_funded}


def autotune(df, base_cfg, jobs: int = 0, max_levers: int = 4) -> dict:
    """Data-driven tuning — NO manual parameter, range, or goal. Run the strategy
    once, let the diagnosis (from the data) name which parameters are off and
    derive the candidate range for each from the measured distributions, then
    sweep those. Every value is measured on BOTH raw edge and funded survival;
    the outcome — not a chosen lens — says what the strategy is suited for.
    Returns {diagnosis, tuned:[{code, message, param, current, curve, best,
    best_funded}]}."""
    from .diagnose import diagnose_trades, diagnose_signals
    from .metrics import trades_frame
    from .funded import APEX_DD

    def _ind_prog(k, tot):
        print(f"PROGRESS {k} {tot+40} auto-tune · computing indicators", flush=True)
    ind = ind_mod.compute(df, base_cfg, progress=_ind_prog)
    print("PROGRESS 8 46 auto-tune · running base strategy", flush=True)
    res = Engine(base_cfg, df, ind, research_mode=True, diag=True).run()
    dd = float(APEX_DD.get(int(base_cfg.initial_capital or 50_000), 2_500))
    dtrades = diagnose_trades(trades_frame(res), base_cfg, drawdown=dd)
    dsignals = diagnose_signals(ind, base_cfg, res.veto_counts)

    # collect the data-derived levers, one per parameter, highest severity first
    sev = {"high": 0, "medium": 1, "low": 2}
    flagged = sorted([f for f in (dtrades["findings"] + dsignals["findings"])
                      if f.get("lever") and f["lever"].get("values")],
                     key=lambda f: sev.get(f["severity"], 3))
    seen, levers = set(), []
    for f in flagged:
        p = f["lever"]["param"]
        if p in seen or not hasattr(base_cfg, p):
            continue
        seen.add(p)
        levers.append(f)
    levers = levers[:max_levers]
    print(f"PROGRESS 12 46 auto-tune · sweeping {len(levers)} data-flagged parameter(s)", flush=True)

    # the engine arrays are extracted ONCE here and shared (fork copy-on-write)
    # across every engine-only lever's workers — without this each worker rebuilt
    # ~1-2GB of arrays (measured 8.7GB total RSS on 20y 1m = swap/OOM on the VPS).
    shared_arrays, tuned, L = None, [], max(len(levers), 1)
    for j, f in enumerate(levers):
        lv = f["lever"]
        param, values = lv["param"], lv["values"]
        engine_only = param in ENGINE_ONLY
        # announce the lever BEFORE any pool/compute work, so the UI caption
        # changes immediately — a stall after this line points at the workers,
        # a caption that never changes points at the parent.
        print(f"PROGRESS {12 + int(34 * j / L)} 46 auto-tune · starting {param} "
              f"sweep ({len(values)} values)", flush=True)
        if engine_only and shared_arrays is None:
            from .engine import extract
            shared_arrays = extract(df, ind)

        def _prog(done, total, _j=j, _p=param):
            frac = (done / total) if total else 1.0
            print(f"PROGRESS {12 + int(34 * (_j + frac) / L)} 46 auto-tune · "
                  f"{_p} {done}/{total}", flush=True)
        try:
            out = sweep_param(df, base_cfg, param, values, jobs=jobs,
                              shared_ind=(ind if engine_only else None),
                              shared_arrays=(shared_arrays if engine_only else None),
                              prog=_prog)
        except Exception as e:
            tuned.append({"code": f["code"], "message": f["message"], "param": param, "error": repr(e)})
            continue
        tuned.append({"code": f["code"], "message": f["message"], "param": param,
                      "current": out["current"], "curve": out["curve"], "best": out["best"],
                      "best_funded": out["best_funded"], "engine_only": out["engine_only"]})
    return {"diagnosis": {"trades": dtrades, "signals": dsignals}, "tuned": tuned}


def _fmt_row(c, current) -> str:
    mark = " <= current" if c["value"] == current else ""
    fu = ""
    if "funded" in c:
        f = c["funded"]
        fu = f"  funded={'BREACH' if f['breached'] else 'survives'}(pay {f['payouts']}, ${f['withdrawn']:,.0f})"
    if c.get("error"):
        return f"    {str(c['value']):>10}  ERROR {c['error']}"
    return (f"    {str(c['value']):>10}  PF {c.get('pf', 0):>5.2f}  net ${c.get('net', 0):>10,.0f}  "
            f"trades {c.get('trades', 0):>6}  win {c.get('win_pct', 0):>4}%  "
            f"maxDD ${c.get('max_dd', 0):>8,.0f}{fu}{mark}")


def _print_verdict(t: dict) -> None:
    """The two unbiased readings, side by side — the outcome labels suitability."""
    b, bf = t.get("best"), t.get("best_funded")
    if b:
        print(f"    -> strongest raw edge at {t['param']}={b['value']} "
              f"(PF {b.get('pf', 0):.2f}, net ${b.get('net', 0):,.0f})")
    if bf:
        same = b and bf["value"] == b["value"]
        print(f"    -> strongest that SURVIVES a funded account: {t['param']}={bf['value']} "
              f"(PF {bf.get('pf', 0):.2f}, {bf.get('funded', {}).get('payouts', 0)} payout(s))"
              + ("  [= same value: funded-suitable]" if same else ""))
    elif b:
        print("    -> NO value survives the funded account: edge (if any) is eval-only here.")


def main():
    ap = argparse.ArgumentParser(description="Fine-grained single-parameter sweep.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--preset", help="preset name (see backtest.config.PRESETS)")
    ap.add_argument("--spec", help="or a spec YAML")
    ap.add_argument("--symbol", help="contract override (GC, MGC, ES, ...)")
    ap.add_argument("--tf", default="1m")
    ap.add_argument("--auto", action="store_true",
                    help="DATA-DRIVEN: let the diagnosis pick which parameters are off and derive "
                         "the range from the measured distributions — no --param/--values needed")
    ap.add_argument("--param", help="Config field to sweep (e.g. fixed_stop_ticks); omit with --auto")
    ap.add_argument("--values", help="comma-separated values (e.g. 20,40,60,80,100); omit with --auto")
    # NOTE: no --funded goal flag. Every value is always measured on BOTH raw edge
    # and funded survival; suitability is an outcome of the test, never an input.
    ap.add_argument("--holdout-days", type=int, default=0, help="hold out the last N days (run in-sample)")
    ap.add_argument("--coarse-since", help="limit to data on/after this date (speed)")
    ap.add_argument("--jobs", type=int, default=0, help="worker processes (0 = all cores)")
    args = ap.parse_args()

    if args.preset:
        base = PRESETS[args.preset]
    elif args.spec:
        from .spec import validate_file, spec_to_config
        base, _ = spec_to_config(validate_file(args.spec))
    else:
        ap.error("provide --preset or --spec")
    if args.symbol:
        base = base.with_(contract=contract(args.symbol))

    print(f"loading {args.data} ...")
    print("PROGRESS 0 100 loading dataset (first load parses the CSV, ~1 min on 20y 1m; "
          "cached after that)", flush=True)
    df = data_mod.load(args.data)
    if args.coarse_since:
        df = data_mod.slice_dates(df, since=args.coarse_since)
    elif args.auto:
        # Coarse gate, same design as the mill: tune the response curves on the
        # last 3 years, validate winners on the full history / Verify OOS. Also
        # what keeps auto-tune inside a small VPS's memory on 1m data — the full
        # 20y frame needs multi-GB per parallel worker. Override: --coarse-since.
        from datetime import timedelta
        since = (df["et"].iloc[-1] - timedelta(days=3 * 365)).date()
        n0 = len(df)
        df = data_mod.slice_dates(df, since=str(since))
        if len(df) < n0:
            print(f"  AUTO-TUNE coarse window: last 3 years ({since} ->), "
                  f"{len(df):,} of {n0:,} bars — response curves only; validate the "
                  f"winner on the full history (Run/Verify). --coarse-since overrides.")
    if args.holdout_days:
        df, _oos, _cut = data_mod.holdout_split(df, args.holdout_days)
    df = df if args.tf == "1m" else data_mod.resample_tf(df, args.tf)
    print(f"  {len(df):,} {args.tf} bars  {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")

    if args.auto:
        print("  AUTO-TUNE: the data picks the parameters and ranges (no manual input).")
        t0 = time.time()
        out = autotune(df, base, jobs=args.jobs)
        if not out["tuned"]:
            # no sweepable lever — still show WHY the run behaved as it did, so
            # 'nothing to tune' is never a bare shrug. If the edge itself is
            # absent, tuning can't create one: that's the discovery funnel's job.
            d = out.get("diagnosis") or {}
            fs = (d.get("trades", {}).get("findings", []) +
                  d.get("signals", {}).get("findings", []))
            print("\n  no sweepable parameter flagged. What the data DID find:")
            for f in fs or [{"severity": "-", "message": "no findings — mechanics look consistent with this data; the (lack of) edge is the signal itself."}]:
                print(f"    [{f['severity']}] {f['message']}")
        for t in out["tuned"]:
            if t.get("error"):
                print(f"\n  {t['param']}: ERROR {t['error']}");  continue
            print(f"\n  {t['param']} (flagged: {t['code']}) — current {t['current']}:")
            for c in t["curve"]:
                print(_fmt_row(c, t["current"]))
            _print_verdict(t)
        print(f"\n  auto-tune done ({time.time()-t0:.0f}s)")
        print("AUTOTUNE_JSON " + json.dumps(out, default=str), flush=True)
        return

    if not args.param or not args.values:
        ap.error("provide --param and --values, or use --auto")
    values = [_coerce(getattr(base, args.param), v) for v in args.values.split(",") if v.strip()]
    print(f"  sweeping {args.param} over {values}  (current={getattr(base, args.param)}, "
          f"{'engine-only, shared indicators' if args.param in ENGINE_ONLY else 'recompute indicators per value'})")
    t0 = time.time()
    out = sweep_param(df, base, args.param, values, jobs=args.jobs)
    print(f"\n  {args.param} response ({time.time()-t0:.0f}s):")
    for c in out["curve"]:
        print(_fmt_row(c, out["current"]))
    _print_verdict(out)
    # machine-readable result for the Lab UI to render as a response curve.
    print("SWEEP_JSON " + json.dumps(out, default=str), flush=True)


if __name__ == "__main__":
    main()
