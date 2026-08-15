"""CLI: run the El Toro / El Dorado backtests on the NQ dataset.

Examples:
    python -m backtest.run --data path/to/NQ_1m.csv --preset EL_DORADO
    python -m backtest.run --data path/to/NQ_1m.csv --preset EL_TORO --research
    python -m backtest.run --data path/to/NQ_1m.csv --all
"""
from __future__ import annotations

import argparse
import json
import os
import time

from . import data as data_mod
from . import indicators as ind_mod
from .config import PRESETS, contract
from .engine import Engine
from .funnel import run_funnel, summarize
from .metrics import kpis, trades_frame


def run_one(df, cfg, research: bool):
    t0 = time.time()
    ind = ind_mod.compute(df, cfg)
    eng = Engine(cfg, df, ind, research_mode=research)
    res = eng.run()
    dt = time.time() - t0
    return res, dt


def _print_report(cfg_name, res, research, dt):
    k = kpis(res)
    mode = "RESEARCH (no account halts)" if research else "NATIVE PHASE"
    print(f"\n{'='*70}\n{cfg_name}  [{mode}]   ({dt:.1f}s, {res.bars:,} bars)")
    print(f"  window: {res.first_time}  ->  {res.last_time}")
    if k.get("trades", 0) == 0:
        print("  no trades")
        return
    print(f"  trades={k['trades']:,}  win%={k['win_rate_pct']}  PF={k['profit_factor']}  "
          f"expectancy=${k['expectancy']}/trade")
    print(f"  net P&L (contracts only) = ${k['net_profit']:,}   maxDD=${k['max_drawdown']:,}   "
          f"commission=${k['total_commission']:,}")
    print(f"  longs={k['longs']}  shorts={k['shorts']}  avgWin=${k['avg_win']}  avgLoss=${k['avg_loss']}")
    print(f"  exit reasons: {k['exit_reasons']}")
    if not research:
        if res.eval_passed:
            print("  ACCOUNT: EVAL PASSED \U0001F389")
        elif res.eval_breached:
            print("  ACCOUNT: eval breached (blew the trailing drawdown)")
        if res.cfg_name == "EL_DORADO" or res.pa_total_banked or res.pa_breach_count:
            print(f"  PA overlay: banked=${res.pa_total_banked:,.0f}  breaches={res.pa_breach_count}  "
                  f"full-cycles(milk)={res.pa_milk_count}  payouts-in-cycle={res.pa_payouts_this_cycle}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--preset", choices=list(PRESETS))
    ap.add_argument("--spec", help="path to a strategy spec YAML (validated against registry.yaml)")
    ap.add_argument("--all", action="store_true", help="run both presets")
    ap.add_argument("--firm", help="prop-firm program key (e.g. apex_100k_eod, topstep_50k_eval) — overlays that firm's account rules; see backtest/firms.py")
    ap.add_argument("--symbol", help="contract spec to use (NQ, ES, GC, CL, 6E, ...); default NQ")
    ap.add_argument("--unit-mode", choices=["Ticks", "Points", "%", "ATR"],
                    help="override distance unit (use ATR to port a config across instruments)")
    ap.add_argument("--tf", help="timeframe(s) to aggregate the 1m source to; comma-list sweeps "
                    "(e.g. 5m,15m,1h). Choices: 1m,5m,10m,15m,30m,1h,2h,3h,4h,1d")
    ap.add_argument("--research", action="store_true", help="disable account halts (pure signal stats)")
    ap.add_argument("--funnel", action="store_true", help="walk-forward eval funnel (pass rate) instead of one run")
    ap.add_argument("--funnel-step", type=int, default=5, help="sessions between fresh eval starts")
    ap.add_argument("--funnel-horizon", type=int, default=20, help="sessions per eval before TIMEOUT")
    ap.add_argument("--trades-out", help="write the trade list CSV to this path")
    ap.add_argument("--json-out", help="write KPIs JSON to this path")
    ap.add_argument("--lab", action="store_true",
                    help="register each run in the Lab data room ($LAB_DIR) with a run_id")
    args = ap.parse_args()

    print(f"loading {args.data} ...")
    df = data_mod.load(args.data)
    print(f"  {len(df):,} bars  {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")

    # Build the list of (name, cfg) jobs — either from a spec or from presets.
    if args.spec:
        from .spec import validate_file, spec_to_config
        rspec = validate_file(args.spec)
        spec_cfg, unmapped = spec_to_config(rspec)
        if unmapped:
            print(f"  NOTE: spec set params the engine does not yet wire (ignored): "
                  f"{', '.join(unmapped)}")
        jobs = [(spec_cfg.name, spec_cfg)]
    else:
        names = list(PRESETS) if args.all else [args.preset]
        if names == [None]:
            ap.error("provide one of --preset NAME, --all, or --spec PATH")
        jobs = [(n, PRESETS[n]) for n in names]

    # Timeframe(s) to run: --tf wins; else a spec's timeframe; else 1m. A
    # comma-list sweeps (e.g. --tf 5m,15m,1h) — one job per (strategy x timeframe).
    from .config import TIMEFRAMES
    if args.tf:
        tfs = [t.strip().lower() for t in args.tf.split(",") if t.strip()]
    elif args.spec and rspec.timeframe:
        tfs = [str(rspec.timeframe).lower()]
    else:
        tfs = ["1m"]
    for t in tfs:
        if t not in TIMEFRAMES:
            ap.error(f"unknown timeframe {t!r}; known: {list(TIMEFRAMES)}")

    # Resample the 1m source once per distinct timeframe (cached).
    _dfcache: dict[str, "object"] = {}
    def df_for(tf):
        if tf not in _dfcache:
            d = df if tf == "1m" else data_mod.resample_tf(df, tf)
            print(f"  [{tf}] {len(d):,} bars")
            _dfcache[tf] = d
        return _dfcache[tf]

    # Expand jobs across timeframes; label with @tf when sweeping >1.
    tag = (lambda name, tf: f"{name}@{tf}") if len(tfs) > 1 else (lambda name, tf: name)
    expanded = [(tag(bn, tf), bn, cfg, tf) for bn, cfg in jobs for tf in tfs]
    single = len(expanded) == 1

    def _record(base_name, cfg, tf, lens, kpi_obj, trades_csv):
        """Register one run in the Lab data room with a recognizable run_id."""
        if not args.lab:
            return
        from datetime import datetime, timezone
        from .lab.runs import fingerprint, make_run_id, record_run
        asset = cfg.contract.symbol
        if args.spec:
            fp_src, source = {"groups": rspec.groups, "base_preset": rspec.base_preset}, f"spec:{args.spec}"
        else:
            fp_src, source = {"preset": base_name}, f"preset:{base_name}"
        fp = fingerprint({**fp_src, "asset": asset, "tf": tf, "lens": lens,
                          "unit_mode": cfg.unit_mode, "data": os.path.basename(args.data)})
        rid = make_run_id(asset, base_name, tf, lens, fp)
        meta = {"run_id": rid, "asset": asset, "strategy": base_name, "timeframe": tf,
                "lens": lens, "source": source, "data_file": os.path.basename(args.data),
                "created_at": datetime.now(timezone.utc).isoformat(), "kpis": kpi_obj}
        if args.spec:
            meta["groups"] = rspec.groups
        artifacts = {"kpis.json": json.dumps(kpi_obj, indent=2, default=str)}
        if trades_csv:
            artifacts["trades.csv"] = trades_csv
        d = record_run(meta, artifacts)
        print(f"  recorded run {rid} -> {d}")

    out = {}
    for name, base_name, cfg, tf in expanded:
        dtf = df_for(tf)
        if args.firm:
            from .firms import program, to_overlay
            p = program(args.firm)
            cfg = cfg.with_(**to_overlay(p))
            if not args.symbol and p.default_contract:
                cfg = cfg.with_(contract=contract(p.default_contract))
            if not p.executable_now:
                print(f"  NOTE: {p.firm} uses {p.drawdown_type} drawdown — runs as Research "
                      f"(no overlay) until the static/FTMO overlay ships.")
        if args.symbol:
            cfg = cfg.with_(contract=contract(args.symbol))
        if args.unit_mode:
            cfg = cfg.with_(unit_mode=args.unit_mode)
        if args.funnel:
            ind = ind_mod.compute(dtf, cfg)
            t0 = time.time()
            outs = run_funnel(cfg, dtf, ind, step_sessions=args.funnel_step,
                              horizon_sessions=args.funnel_horizon)
            s = summarize(outs)
            print(f"\n{'='*70}\n{name}  [EVAL FUNNEL]  ({time.time()-t0:.1f}s)")
            print(f"  fresh eval every {args.funnel_step} sessions, {args.funnel_horizon}-session horizon")
            print(f"  starts={s['starts']}  PASS={s['pass']} ({s['pass_rate_pct']}%)  "
                  f"BREACH={s['breach']}  TIMEOUT={s['timeout']}  median trades={s['median_trades_to_resolve']}")
            out[name] = s
            _record(base_name, cfg, tf, "eval", s, None)
            continue
        res, dt = run_one(dtf, cfg, args.research)
        _print_report(name, res, args.research, dt)
        out[name] = kpis(res)
        lens = "classic" if args.research else "native"
        _record(base_name, cfg, tf, lens, out[name],
                trades_frame(res).to_csv(index=False) if args.lab else None)
        if args.trades_out and single:
            trades_frame(res).to_csv(args.trades_out, index=False)
            print(f"  trades written to {args.trades_out}")
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
