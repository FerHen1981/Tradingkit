"""Fine-grained parameter sweep — phase 3 of diagnose/instrument/sweep.

Vary ONE parameter across a range, run the whole strategy at each value, and
return the response curve (PF / net / trades / win% / maxDD, and funded breach if
asked). This is how "is the stop too wide / the FVG band too big" stops being a
guess: you see where the current value sits on the curve and where the response
peaks. The diagnostic (backtest.diagnose) tells you WHICH parameter to sweep;
this measures the response, no pre-assumption that today's value is right.

    python -m backtest.sweep --data <csv> --preset EL_TESORO --symbol GC --tf 1m \
        --param fixed_stop_ticks --values 20,30,40,50,60,80,100 --funded

Engine-only parameters (stop/TP/sizing) reuse one indicator computation across
all values; parameters that change the signal itself (FVG band, CVD streak,
regime knobs) recompute indicators per value. Values run across worker processes.
"""
from __future__ import annotations

import argparse
import json
import os
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


def _pool_init(df, ind):
    global _DF, _IND
    _DF, _IND = df, ind


def _run_value(payload):
    """Worker: run the strategy at one parameter value. payload=(cfg, funded)."""
    cfg, funded = payload
    ind = _IND if _IND is not None else ind_mod.compute(_DF, cfg)
    res = Engine(cfg, _DF, ind, research_mode=True).run()
    k = kpis(res)
    row = {"trades": k.get("trades", 0), "net": k.get("net_profit", 0.0),
           "pf": k.get("profit_factor", 0.0), "win_pct": k.get("win_rate_pct", 0.0),
           "max_dd": k.get("max_drawdown", 0.0)}
    if funded:
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


def sweep_param(df, base_cfg, param: str, values: list, funded: bool = False,
                jobs: int = 0) -> dict:
    """Run base_cfg across `values` of `param`. Returns {param, current, curve,
    best, engine_only}. curve rows carry the value + its KPIs."""
    if not hasattr(base_cfg, param):
        raise ValueError(f"unknown parameter {param!r}")
    current = getattr(base_cfg, param)
    engine_only = param in ENGINE_ONLY
    shared_ind = ind_mod.compute(df, base_cfg) if engine_only else None

    cfgs = [(base_cfg.with_(**{param: v}), funded) for v in values]
    jobs = jobs if jobs and jobs > 0 else (os.cpu_count() or 1)
    rows = [None] * len(values)
    if jobs <= 1:
        _pool_init(df, shared_ind)
        for i, payload in enumerate(cfgs):
            rows[i] = _run_value(payload)
    else:
        with ProcessPoolExecutor(max_workers=jobs, initializer=_pool_init,
                                 initargs=(df, shared_ind)) as ex:
            futs = {ex.submit(_run_value, payload): i for i, payload in enumerate(cfgs)}
            done = 0
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    rows[i] = fut.result()
                except Exception as e:
                    rows[i] = {"error": repr(e)}
                done += 1
                print(f"PROGRESS {done} {len(values)} sweep {param}", flush=True)

    curve = [{"value": v, **(r or {})} for v, r in zip(values, rows)]
    valid = [c for c in curve if not c.get("error") and (c.get("trades") or 0) > 0]
    # "best" by PF among values that also survive funded (if funded requested)
    def _key(c):
        if funded and c.get("funded", {}).get("breached", True):
            return (-1, c.get("pf") or 0)          # breached: rank below survivors
        return (0, c.get("pf") or 0)
    best = max(valid, key=_key) if valid else None
    return {"param": param, "current": current, "engine_only": engine_only,
            "funded": funded, "curve": curve, "best": best}


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


def main():
    ap = argparse.ArgumentParser(description="Fine-grained single-parameter sweep.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--preset", help="preset name (see backtest.config.PRESETS)")
    ap.add_argument("--spec", help="or a spec YAML")
    ap.add_argument("--symbol", help="contract override (GC, MGC, ES, ...)")
    ap.add_argument("--tf", default="1m")
    ap.add_argument("--param", required=True, help="Config field to sweep (e.g. fixed_stop_ticks)")
    ap.add_argument("--values", required=True, help="comma-separated values (e.g. 20,40,60,80,100)")
    ap.add_argument("--funded", action="store_true", help="also report funded breach/payout per value")
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
    df = data_mod.load(args.data)
    if args.coarse_since:
        df = data_mod.slice_dates(df, since=args.coarse_since)
    if args.holdout_days:
        df, _oos, _cut = data_mod.holdout_split(df, args.holdout_days)
    df = df if args.tf == "1m" else data_mod.resample_tf(df, args.tf)
    print(f"  {len(df):,} {args.tf} bars  {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")

    values = [_coerce(getattr(base, args.param), v) for v in args.values.split(",") if v.strip()]
    print(f"  sweeping {args.param} over {values}  (current={getattr(base, args.param)}, "
          f"{'engine-only, shared indicators' if args.param in ENGINE_ONLY else 'recompute indicators per value'})")
    t0 = time.time()
    out = sweep_param(df, base, args.param, values, funded=args.funded, jobs=args.jobs)
    print(f"\n  {args.param} response ({time.time()-t0:.0f}s):")
    for c in out["curve"]:
        print(_fmt_row(c, out["current"]))
    if out["best"]:
        b = out["best"]
        print(f"\n  best PF at {args.param}={b['value']}: PF {b.get('pf', 0):.2f}, "
              f"net ${b.get('net', 0):,.0f}, {b.get('trades', 0)} trades"
              + ("  (survives funded)" if args.funded and not b.get("funded", {}).get("breached", True) else ""))
    # machine-readable result for the Lab UI to render as a response curve.
    print("SWEEP_JSON " + json.dumps(out, default=str), flush=True)


if __name__ == "__main__":
    main()
