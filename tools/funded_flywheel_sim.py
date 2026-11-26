"""Funded (PA) flywheel simulation for the 4 Apex legacy accounts.

Runs the funded scripts over the full 3y under Apex-PA intraday overlays for the
250k and 300k legacy accounts, and measures the payout flywheel:
  banked $, breaches (blown PAs), banked-per-breach, milk-cycles (6-payout ladders).

Two payout models bracket the "massive payout" question:
  A  CAPPED  — repo default: ladder caps $1.5k..$3k, wait-for-cap (conservative).
  B  LEGACY-UNCAPPED — no per-account cap: withdraw everything above the safety
     net each eligible cycle (models the pre-4.0 no-cap privilege). Implemented
     by monkeypatching ladder_cap -> huge and use_wait_for_cap=False.

Delta feed is empty in these exports -> CVD OFF (see the eval analysis).
"""
from __future__ import annotations

import sys
import backtest.engine as engine_mod
from backtest import data as dm, indicators as im
from backtest.config import PRESETS, EL_DORADO_TUNED, contract, ladder_cap as _real_cap
from backtest.engine import Engine

CVD_OFF = dict(use_cvd_filter=False, use_cvd_streak=False)

# Funded signals (CVD off). GC = El Tesoro (FVG6-12, fixed 100t, R2.5) on the
# validated El Dorado PA money-management; NQ = El Dorado tuned as-is.
# gap (9,18): the recovered GC edge (tools/gc_edge_sweep.py) — PF 1.06, split-half
# robust (H1 1.22 / H2 1.03), vs the 0.99 floor at the documented 6-12 band.
GC_FUNDED = EL_DORADO_TUNED.with_(
    name="GC_ElTesoro", gap_min_ticks=9.0, gap_max_ticks=18.0,
    stop_swing=False, fixed_stop_ticks=100.0, max_stop_ticks=100.0,
    tp_mode="R-multiple", r_multiple=2.5, confirm_bars=0, use_recov_trail=False, **CVD_OFF)
NQ_FUNDED = EL_DORADO_TUNED.with_(name="NQ_ElDorado", **CVD_OFF)

# El Rey (ES funded): FVG 9-15, fixed 100t, R1.5, VWAP off + confirm 2 (tuned edge
# PF 1.09, tools/edge_sweep.py) on the El Dorado PA management.
ES_FUNDED = EL_DORADO_TUNED.with_(
    name="ES_ElRey", gap_min_ticks=9.0, gap_max_ticks=15.0,
    stop_swing=False, fixed_stop_ticks=100.0, max_stop_ticks=100.0,
    tp_mode="R-multiple", r_multiple=1.5, confirm_bars=2, use_vwap_veto=False,
    use_recov_trail=False, **CVD_OFF)

ASSETS = {
    "GC": ("data/GC_norm.csv", "GC", GC_FUNDED, [1, 2, 3]),
    "NQ": ("data/NQ_norm.csv", "NQ", NQ_FUNDED, [2, 3, 5]),
    "ES": ("data/ES_norm.csv", "ES", ES_FUNDED, [1, 2, 3, 4]),
}

def pa_overlay(dd, wait_for_cap):
    return dict(phase="Apex PA", dd_model="Intraday", acct_trail_dd=float(dd),
                consistency_pct=50.0, acct_dll=1e12,   # legacy: no daily-loss limit
                min_payout=500.0, payout_buffer=500.0, use_wait_for_cap=wait_for_cap)

ACCOUNTS = {"250k": 6_500.0, "300k": 7_500.0}
MODELS = {"A_capped": True, "B_legacy_uncapped": False}


def run(sym):
    path, spec, sig, sizes = ASSETS[sym]
    df = dm.load(path)
    base = sig.with_(contract=contract(spec))
    ind = im.compute(df, base)
    print(f"\n{'='*82}\n{sym}  funded flywheel   window {df['et'].iloc[0]} .. {df['et'].iloc[-1]}")
    print(f"  {'acct':>5} {'model':>18} {'qty':>4} {'banked':>12} {'breaches':>9} "
          f"{'banked/breach':>14} {'milk':>5}")
    for acct, dd in ACCOUNTS.items():
        for mname, wait in MODELS.items():
            # monkeypatch cap for the uncapped model
            engine_mod.ladder_cap = _real_cap if wait else (lambda n: 1e12)
            for qty in sizes:
                cfg = base.with_(contract_size=float(qty), **pa_overlay(dd, wait))
                res = Engine(cfg, df, ind, research_mode=False).run()
                bpb = res.pa_total_banked / res.pa_breach_count if res.pa_breach_count else float('inf')
                print(f"  {acct:>5} {mname:>18} {qty:>4} ${res.pa_total_banked:>10,.0f} "
                      f"{res.pa_breach_count:>9} ${bpb:>12,.0f} {res.pa_milk_count:>5}")
            engine_mod.ladder_cap = _real_cap


def main():
    for sym in (sys.argv[1:] or ["GC", "NQ"]):
        run(sym)


if __name__ == "__main__":
    main()
