"""CLI: run the El Toro / El Dorado backtests on the NQ dataset.

Examples:
    python -m backtest.run --data path/to/NQ_1m.csv --preset EL_DORADO
    python -m backtest.run --data path/to/NQ_1m.csv --preset EL_TORO --research
    python -m backtest.run --data path/to/NQ_1m.csv --all
"""
from __future__ import annotations

import argparse
import json
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
    ap.add_argument("--all", action="store_true", help="run both presets")
    ap.add_argument("--symbol", help="contract spec to use (NQ, ES, GC, CL, 6E, ...); default NQ")
    ap.add_argument("--unit-mode", choices=["Ticks", "Points", "%", "ATR"],
                    help="override distance unit (use ATR to port a config across instruments)")
    ap.add_argument("--research", action="store_true", help="disable account halts (pure signal stats)")
    ap.add_argument("--funnel", action="store_true", help="walk-forward eval funnel (pass rate) instead of one run")
    ap.add_argument("--funnel-step", type=int, default=5, help="sessions between fresh eval starts")
    ap.add_argument("--funnel-horizon", type=int, default=20, help="sessions per eval before TIMEOUT")
    ap.add_argument("--trades-out", help="write the trade list CSV to this path")
    ap.add_argument("--json-out", help="write KPIs JSON to this path")
    args = ap.parse_args()

    print(f"loading {args.data} ...")
    df = data_mod.load(args.data)
    print(f"  {len(df):,} bars  {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")

    presets = list(PRESETS) if args.all else [args.preset]
    out = {}
    for name in presets:
        cfg = PRESETS[name]
        if args.symbol:
            cfg = cfg.with_(contract=contract(args.symbol))
        if args.unit_mode:
            cfg = cfg.with_(unit_mode=args.unit_mode)
        if args.funnel:
            ind = ind_mod.compute(df, cfg)
            t0 = time.time()
            outs = run_funnel(cfg, df, ind, step_sessions=args.funnel_step,
                              horizon_sessions=args.funnel_horizon)
            s = summarize(outs)
            print(f"\n{'='*70}\n{name}  [EVAL FUNNEL]  ({time.time()-t0:.1f}s)")
            print(f"  fresh eval every {args.funnel_step} sessions, {args.funnel_horizon}-session horizon")
            print(f"  starts={s['starts']}  PASS={s['pass']} ({s['pass_rate_pct']}%)  "
                  f"BREACH={s['breach']}  TIMEOUT={s['timeout']}  median trades={s['median_trades_to_resolve']}")
            out[name] = s
            continue
        res, dt = run_one(df, cfg, args.research)
        _print_report(name, res, args.research, dt)
        out[name] = kpis(res)
        if args.trades_out and len(presets) == 1:
            trades_frame(res).to_csv(args.trades_out, index=False)
            print(f"  trades written to {args.trades_out}")
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
