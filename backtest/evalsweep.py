"""Eval spectrum — which prop-firm account does this strategy pass, how fast?

The eval lens used to run against whatever account numbers happened to sit in
the preset (`acct_goal` / `acct_trail_dd`). That answers "does it pass THE eval",
which is not the question: every firm sells a different bargain, and the same
strategy meets a very different task per program. From the registry:

    target / drawdown   FundedNext 15k · The5ers 5k · FundingPips 10k   0.8
                        Apex 25k                                        1.0
                        Apex 50k                                        1.2
                        Topstep · MyFundedFutures · TPT 50k             1.5
                        Apex 250k                                       2.31
                        DayTraders 25k                                  3.33

At DayTraders a strategy must earn four times as much per unit of drawdown room
as at FundedNext. So "which account can I pass, and how quickly" is a real
question with a non-obvious answer — and the inputs are already in
`data/propfirms.json`.

This sweeps the walk-forward funnel across every eval program in the registry
and reports, per program: pass rate, median TRADING DAYS to pass, breach rate.
Position size scales per account via `sizing_mode="target_dd"` (risking a
fraction of the remaining drawdown room), because testing two fixed contracts on
a 250k account measures nothing.

    python -m backtest.evalsweep --data <csv> --preset EL_TORO --symbol NQ --tf 1m
"""
from __future__ import annotations

import os

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
from .firms import REGISTRY, to_overlay

_DF = None
_ARR = None


def _pool_init(df, arrays):
    global _DF, _ARR
    _DF, _ARR = df, arrays


def difficulty(p) -> float | None:
    """Profit target per unit of drawdown room — the honest 'how hard is this
    program' number, straight from the registry."""
    if not p.profit_target or not p.drawdown:
        return None
    return round(p.profit_target / p.drawdown, 2)


def _run_program(payload):
    """Worker: overlay one program on the base config and run the funnel."""
    key, cfg, step, horizon = payload
    from .funnel import summarize as _sm
    return key, _sm(_rf_with_arrays(cfg, step, horizon))


def _rf_with_arrays(cfg, step, horizon):
    """run_funnel needs (df, ind); we pass the pre-extracted arrays via a shim so
    every program reuses one indicator computation."""
    from .funnel import FunnelOutcome, _session_starts
    from .engine import Engine
    import numpy as np
    import pandas as pd
    starts = _session_starts(_DF)
    times = _DF["et"]
    outcomes = []
    for si in range(0, len(starts) - horizon, step):
        sb = int(starts[si])
        eb = int(starts[si + horizon]) if si + horizon < len(starts) else len(_DF)
        eng = Engine(cfg, research_mode=False, start_bar=sb, arrays=_ARR)
        res = eng.run(end_bar=eb)
        reason = eng.acct_halt_reason
        r = ("PASS" if "PASSED" in reason else
             "BREACH" if ("TRAILING" in reason or "FAILED" in reason) else "TIMEOUT")
        days = -1
        if res.resolve_bar >= 0:
            days = int(np.searchsorted(starts, res.resolve_bar, side="right")
                       - np.searchsorted(starts, sb, side="left"))
        outcomes.append(FunnelOutcome(start_bar=sb, start_time=pd.Timestamp(times.iloc[sb]),
                                      result=r, trades=len(res.trades),
                                      net_profit=eng.net_profit, bars=eb - sb, days=days))
    return outcomes


def sweep_programs(df, base_cfg, programs, step: int = 5, horizon: int = 20,
                   jobs: int = 0, scale_size: bool = True) -> list[dict]:
    """Run the funnel once per program. Returns one row per program, sorted by
    pass rate then speed."""
    from .engine import extract
    ind = ind_mod.compute(df, base_cfg)
    arrays = extract(df, ind)

    payloads, meta = [], {}
    for p in programs:
        cfg = base_cfg.with_(**to_overlay(p))
        if scale_size and p.drawdown_type in ("intraday_trailing", "eod_trailing"):
            # size to the account: risk a slice of the remaining DD room, so a
            # 250k program actually trades like a 250k program.
            cfg = cfg.with_(sizing_mode="target_dd")
        payloads.append((p.key, cfg, step, horizon))
        meta[p.key] = p

    jobs = jobs if jobs and jobs > 0 else (os.cpu_count() or 1)
    rows = []
    total = len(payloads)
    if jobs <= 1:
        _pool_init(df, arrays)
        for i, pl in enumerate(payloads, 1):
            key, s = _run_program(pl)
            rows.append(_row(meta[key], s))
            print(f"PROGRESS {i} {total} eval spectrum · {key}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=jobs, initializer=_pool_init,
                                 initargs=(df, arrays)) as ex:
            futs = {ex.submit(_run_program, pl): pl[0] for pl in payloads}
            done = 0
            for fut in as_completed(futs):
                key = futs[fut]
                try:
                    _k, s = fut.result()
                    rows.append(_row(meta[key], s))
                except Exception as e:
                    rows.append({"key": key, "firm": meta[key].firm,
                                 "size": int(meta[key].account_size), "error": repr(e)})
                done += 1
                print(f"PROGRESS {done} {total} eval spectrum · {key}", flush=True)

    rows.sort(key=lambda r: (-(r.get("pass_rate_pct") or 0),
                             r.get("median_days_to_pass") or 9_999))
    return rows


def _row(p, s: dict) -> dict:
    return {"key": p.key, "firm": p.firm, "size": int(p.account_size),
            "dd_type": p.drawdown_type, "target": p.profit_target, "drawdown": p.drawdown,
            "difficulty": difficulty(p), "min_days": p.min_days,
            "consistency_pct": p.consistency_pct, "fee": p.activation_fee,
            "starts": s.get("starts", 0), "pass_rate_pct": s.get("pass_rate_pct", 0.0),
            "breach": s.get("breach", 0), "timeout": s.get("timeout", 0),
            "median_days_to_pass": s.get("median_days_to_pass"),
            "median_days_to_breach": s.get("median_days_to_breach"),
            "executable": p.executable_now}


def main():
    ap = argparse.ArgumentParser(description="Sweep the eval funnel across prop-firm programs.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--preset", help="preset name")
    ap.add_argument("--spec", help="or a spec YAML")
    ap.add_argument("--symbol", help="contract override")
    ap.add_argument("--tf", default="1m")
    ap.add_argument("--firm", default="", help="limit to one firm (default: every eval program)")
    ap.add_argument("--asset-class", default="futures",
                    help="registry asset class to sweep (futures|forex|cfd); "
                         "mixing classes in one sweep compares unlike things")
    ap.add_argument("--step", type=int, default=5, help="sessions between fresh eval starts")
    ap.add_argument("--horizon", type=int, default=20, help="sessions per eval before TIMEOUT")
    ap.add_argument("--no-scale-size", action="store_true",
                    help="keep the preset's fixed contract size instead of scaling to the account")
    ap.add_argument("--coarse-since", help="limit the window (default: prepared last 3 years)")
    ap.add_argument("--jobs", type=int, default=0)
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
    if args.coarse_since:
        print("PROGRESS 0 100 loading dataset", flush=True)
        df = data_mod.slice_dates(data_mod.load(args.data), since=args.coarse_since)
    else:
        print("PROGRESS 0 100 loading recent-3y slice (prepared; fast)", flush=True)
        df = data_mod.load_window(args.data, years=3)
    df = df if args.tf == "1m" else data_mod.resample_tf(df, args.tf)
    print(f"  {len(df):,} {args.tf} bars  {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")

    progs = [p for p in REGISTRY.values()
             if p.stage == "eval" and p.asset_class == args.asset_class
             and (not args.firm or p.firm.lower() == args.firm.lower())]
    skipped = [p.key for p in progs if not p.executable_now]
    progs = [p for p in progs if p.executable_now]
    if not progs:
        print(f"no executable eval programs for asset_class={args.asset_class!r}"
              + (f" firm={args.firm!r}" if args.firm else ""))
        return
    if skipped:
        print(f"  skipped {len(skipped)} program(s) the engine cannot model yet: {skipped}")
    print(f"  sweeping {len(progs)} eval program(s); fresh eval every {args.step} sessions, "
          f"{args.horizon}-session horizon"
          + ("" if args.no_scale_size else "; size scaled to each account (target_dd)"))

    t0 = time.time()
    rows = sweep_programs(df, base, progs, step=args.step, horizon=args.horizon,
                          jobs=args.jobs, scale_size=not args.no_scale_size)
    print(f"\n  eval spectrum ({time.time()-t0:.0f}s) — sorted by pass rate, then speed:\n")
    print(f"    {'program':<28}{'size':>8}{'T/DD':>6}{'pass%':>7}{'days':>6}{'breach':>7}{'timeout':>8}")
    for r in rows:
        if r.get("error"):
            print(f"    {r['key']:<28}{r['size']:>8}  ERROR {r['error'][:40]}")
            continue
        d = r["median_days_to_pass"]
        print(f"    {r['key']:<28}{r['size']:>8}{(r['difficulty'] or 0):>6.2f}"
              f"{r['pass_rate_pct']:>7.1f}{(d if d is not None else '—'):>6}"
              f"{r['breach']:>7}{r['timeout']:>8}")
    best = next((r for r in rows if not r.get("error") and (r.get("pass_rate_pct") or 0) > 0), None)
    if best:
        d = best["median_days_to_pass"]
        print(f"\n  best fit: {best['key']} — {best['pass_rate_pct']}% of fresh evals pass"
              + (f", median {d} trading days" if d is not None else "")
              + f" (difficulty {best['difficulty']})")
    else:
        print("\n  no program passed even once — this strategy funds nothing in this window.")
    print("EVALSWEEP_JSON " + json.dumps({"rows": rows}, default=str), flush=True)


if __name__ == "__main__":
    main()
