"""Split-half-validated signal sweep for any asset — recover/tune the edge.

Usage:  python tools/edge_sweep.py GC     (or ES, NQ, YM)

Sweeps the high-impact signal levers (VWAP veto, confirm window, FVG band,
session hours) and reports research PF on FULL / first-half / second-half, so a
config is only trusted when it is positive in BOTH halves (per
docs/optimization.md — avoids in-sample artefacts). Stop/R held at the asset's
baseline; run an MM refine separately once the signal is locked.

Key lesson so far: widening the FVG band lifts the GC edge from the 0.99 floor
(6-12) to a robust PF 1.06 (9-18). This tool tests the same for other assets.
"""
from __future__ import annotations

import sys
import numpy as np

from backtest import data as dm, indicators as im
from backtest.config import EL_TORO, contract
from backtest.engine import Engine, extract
from backtest.metrics import kpis

CVD_OFF = dict(use_cvd_filter=False, use_cvd_streak=False)
RTH = frozenset(range(9, 16))
ALLH = EL_TORO.enabled_hours

# per-asset baseline (stop/R from the from-scratch presets) + FVG band grid to test
BASES = {
    "GC": dict(spec="GC", stop=100.0, R=1.5, gaps=[(6, 12), (6, 15), (9, 18), (12, 24), (15, 30)]),
    "ES": dict(spec="ES", stop=100.0, R=1.5, gaps=[(9, 15), (9, 18), (12, 24), (15, 30), (6, 15)]),
    "NQ": dict(spec="NQ", stop=49.0, R=2.5, gaps=[(9, 15), (9, 18), (12, 24), (15, 30)]),
    "YM": dict(spec="YM", stop=100.0, R=1.5, gaps=[(9, 15), (12, 24), (15, 30), (20, 40)]),
}


def build(spec, stop, R, **ov):
    d = dict(stop_swing=False, fixed_stop_ticks=stop, max_stop_ticks=stop,
             tp_mode="R-multiple", r_multiple=R, use_recov_trail=False,
             contract_size=2.0, contract=contract(spec), **CVD_OFF)
    d.update(ov)
    return EL_TORO.with_(**d)


def pf_of(cfg, arrays, sb, eb):
    k = kpis(Engine(cfg, research_mode=True, start_bar=sb, arrays=arrays).run(end_bar=eb))
    return k["profit_factor"], k["trades"]


def main():
    sym = (sys.argv[1] if len(sys.argv) > 1 else "ES").upper()
    b = BASES[sym]
    df = dm.load(f"data/{sym}_norm.csv")
    n = len(df); mid = n // 2
    print(f"{sym} signal sweep — split-half validated (full / H1 / H2). "
          f"stop{b['stop']:.0f}/R{b['R']} fixed.\n")
    print(f"  {'vwap':>5} {'conf':>4} {'gap':>8} {'hours':>5} "
          f"{'PF_full':>8} {'PF_H1':>7} {'PF_H2':>7} {'trades':>7} {'robust':>7}")
    rows = []
    for vwap in (True, False):
        for confirm in (0, 2):
            for gap in b["gaps"]:
                for hname, hours in (("all", ALLH), ("RTH", RTH)):
                    cfg = build(b["spec"], b["stop"], b["R"], use_vwap_veto=vwap,
                                confirm_bars=confirm, gap_min_ticks=float(gap[0]),
                                gap_max_ticks=float(gap[1]), enabled_hours=hours)
                    ind = im.compute(df, cfg)
                    arrays = extract(df, ind)
                    pf_f, tr = pf_of(cfg, arrays, 0, n)
                    pf1, _ = pf_of(cfg, arrays, 0, mid)
                    pf2, _ = pf_of(cfg, arrays, mid, n)
                    robust = pf_f > 1.0 and pf1 > 1.0 and pf2 > 1.0
                    rows.append((pf_f, pf1, pf2, tr, robust, vwap, confirm, gap, hname))
                    print(f"  {str(vwap):>5} {confirm:>4} {str(gap):>8} {hname:>5} "
                          f"{pf_f:>8.3f} {pf1:>7.3f} {pf2:>7.3f} {tr:>7} {'YES' if robust else '':>7}")

    rows.sort(key=lambda r: (r[4], min(r[1], r[2])), reverse=True)
    print("\nTOP robust configs (by worst-half PF):")
    for pf_f, pf1, pf2, tr, robust, vwap, confirm, gap, hname in rows[:6]:
        print(f"  vwap={vwap} confirm={confirm} gap={gap} hours={hname}: "
              f"PF {pf_f:.3f} (H1 {pf1:.3f}/H2 {pf2:.3f}) trades={tr}  "
              f"[{'ROBUST' if robust else 'in-sample only'}]")


if __name__ == "__main__":
    main()
