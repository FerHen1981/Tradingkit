"""Concrete analysis for the 4 Apex legacy accounts (3x250k + 1x300k, intraday DD).

Datasets (uploaded, normalized by tools/normalize_upload.py; delta empty -> CVD OFF):
  NQ  El Toro (tuned RTH)     -- edgeless/regime baseline
  GC  El Minero (FVG6-12,R1.5) -- validated strongest edge
  YM  El Toro port            -- UNVALIDATED (no YM-specific tuning), flagged

For each asset:
  1) research single run  -> PF, expectancy, win%, avgWin/avgLoss  (validation)
  2) eval funnel pass/breach/timeout across a contract-size sweep, under the
     apex_250k_intraday and apex_300k_intraday account overlays.
"""
from __future__ import annotations

import sys
import time

from backtest import data as data_mod
from backtest import indicators as ind_mod
from backtest.config import PRESETS, EL_TORO, contract
from backtest.engine import Engine
from backtest.funnel import run_funnel, summarize
from backtest.metrics import kpis

CVD_OFF = dict(use_cvd_filter=False, use_cvd_streak=False)

# --- signal presets per asset (CVD off; delta feed is empty in these exports) ---
NQ_SIG = PRESETS["EL_TORO_TUNED"].with_(name="NQ_ElToro", **CVD_OFF)

# GC recovered edge (tools/gc_edge_sweep.py): FVG 9-18 (wider than the documented
# 6-12), stop100, R1.5 -> PF 1.06 split-half robust (H1 1.22/H2 1.03) vs 0.99 floor.
GC_SIG = EL_TORO.with_(
    name="GC_ElMinero", gap_min_ticks=9.0, gap_max_ticks=18.0,
    stop_swing=False, fixed_stop_ticks=100.0, max_stop_ticks=100.0,
    tp_mode="R-multiple", r_multiple=1.5, confirm_bars=0,
    use_recov_trail=False, contract_size=2.0, **CVD_OFF,
)

# YM port of El Toro tuned — tick-unit inputs do NOT port cleanly (instruments.md).
YM_SIG = PRESETS["EL_TORO_TUNED"].with_(name="YM_ElToro_port", **CVD_OFF)

# El León (ES eval): FVG 9-15, fixed 100t stop, R1.5, 1 contract, delta OFF.
# Tuned edge (tools/edge_sweep.py): VWAP veto OFF + confirm 2 lifts PF 1.06 -> 1.09,
# most balanced split-half (H1 1.15 / H2 1.07). ES's optimum is the 9-15 band —
# widening it (unlike GC) does NOT help.
ES_SIG = EL_TORO.with_(
    name="ES_ElLeon", gap_min_ticks=9.0, gap_max_ticks=15.0,
    stop_swing=False, fixed_stop_ticks=100.0, max_stop_ticks=100.0,
    tp_mode="R-multiple", r_multiple=1.5, confirm_bars=2, use_vwap_veto=False,
    use_recov_trail=False, contract_size=1.0, **CVD_OFF,
)

ASSETS = {
    "NQ": ("data/NQ_norm.csv", "NQ", NQ_SIG, [5, 10, 13, 18, 25]),
    "GC": ("data/GC_norm.csv", "GC", GC_SIG, [1, 2, 3, 4, 6]),
    "YM": ("data/YM_norm.csv", "YM", YM_SIG, [3, 5, 8, 12]),
    "ES": ("data/ES_norm.csv", "ES", ES_SIG, [1, 2, 3, 4]),
}
# Apex legacy (pre-4.0) intraday-trailing overlays, built explicitly from the
# _APEX_SIZES table in backtest/firms.py (250k: tgt 15k / DD 6.5k; 300k: 20k / 7.5k).
def _apex_intraday(size, tgt, dd):
    return dict(phase="Apex Eval", dd_model="Intraday", initial_capital=float(size),
                acct_trail_dd=float(dd), acct_goal=float(tgt), acct_dll=1000.0,
                consistency_pct=50.0)

OVERLAYS = {
    "apex_250k_intraday": _apex_intraday(250_000, 15_000, 6_500),
    "apex_300k_intraday": _apex_intraday(300_000, 20_000, 7_500),
}


def research(sym):
    path, spec, sig, _ = ASSETS[sym]
    df = data_mod.load(path)
    cfg = sig.with_(contract=contract(spec))
    ind = ind_mod.compute(df, cfg)
    res = Engine(cfg, df, ind, research_mode=True).run()
    k = kpis(res)
    print(f"[{sym}] research: trades={k['trades']:,} win%={k['win_rate_pct']} "
          f"PF={k['profit_factor']} exp=${k['expectancy']}/ct  "
          f"avgWin=${k['avg_win']} avgLoss=${k['avg_loss']}  window {res.first_time}..{res.last_time}")
    return df, cfg, ind


def sweep(sym, df, sig_cfg, ind):
    _, spec, _, sizes = ASSETS[sym]
    for ov_key, ov in OVERLAYS.items():
        print(f"\n  -- {sym} on {ov_key}  (DD=${ov['acct_trail_dd']:,.0f} target=${ov['acct_goal']:,.0f}) --")
        print(f"     {'qty':>4} {'pass%':>6} {'breach%':>8} {'timeout%':>9} {'medTrades':>10}")
        for qty in sizes:
            cfg = sig_cfg.with_(contract=contract(spec), contract_size=float(qty), **ov)
            outs = run_funnel(cfg, df, ind, step_sessions=5, horizon_sessions=20)
            s = summarize(outs)
            n = s["starts"] or 1
            print(f"     {qty:>4} {s['pass_rate_pct']:>6} "
                  f"{round(100*s['breach']/n,1):>8} {round(100*s['timeout']/n,1):>9} "
                  f"{s['median_trades_to_resolve']:>10}")


def main():
    which = sys.argv[1:] or ["GC", "NQ", "YM"]
    t0 = time.time()
    for sym in which:
        print("=" * 78)
        df, cfg, ind = research(sym)
        sweep(sym, df, cfg, ind)
    print(f"\nDONE in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
