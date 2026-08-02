"""Recover the GC edge from scratch — split-half-validated signal sweep.

My first GC reconstruction (FVG6-12/stop100/R1.5, VWAP veto ON, confirm 0) gave
research PF 0.99, below the documented winner (~1.13, H1 1.19 / H2 1.05). The
gap must be in the non-documented signal params. This sweeps the high-impact
signal levers (VWAP veto, confirm window, FVG band, session hours) and reports
PF on FULL / first-half / second-half, so we pick a config that is robust in
BOTH halves — not an in-sample artefact (per docs/optimization.md).

Stop (100t) and R (1.5) held at the documented winner; a short MM refine follows
separately once the signal is locked.
"""
from __future__ import annotations

import numpy as np

from backtest import data as dm, indicators as im
from backtest.config import EL_TORO, contract
from backtest.engine import Engine, extract
from backtest.metrics import kpis

CVD_OFF = dict(use_cvd_filter=False, use_cvd_streak=False)
RTH = frozenset(range(9, 16))
ALLH = EL_TORO.enabled_hours


def base_gc(**ov):
    d = dict(gap_min_ticks=6.0, gap_max_ticks=12.0, stop_swing=False,
             fixed_stop_ticks=100.0, max_stop_ticks=100.0, tp_mode="R-multiple",
             r_multiple=1.5, use_recov_trail=False, contract_size=2.0,
             contract=contract("GC"), **CVD_OFF)   # FIX: GC spec (mintick 0.10), not NQ default
    d.update(ov)
    return EL_TORO.with_(**d)


def pf_of(cfg, arrays, sb, eb):
    k = kpis(Engine(cfg, research_mode=True, start_bar=sb, arrays=arrays).run(end_bar=eb))
    return k["profit_factor"], k["trades"], k["expectancy"]


def main():
    df = dm.load("data/GC_norm.csv")
    n = len(df); mid = n // 2
    variants = []
    for vwap in (True, False):
        for confirm in (0, 2):
            for gap in ((6, 12), (6, 15), (9, 18), (12, 24), (15, 30)):
                for hours_name, hours in (("all", ALLH), ("RTH", RTH)):
                    variants.append((vwap, confirm, gap, hours_name, hours))

    print(f"GC signal sweep — {len(variants)} configs, split-half validated "
          f"(full / H1 / H2). stop100/R1.5 fixed.\n")
    print(f"  {'vwap':>5} {'conf':>4} {'gap':>7} {'hours':>5} "
          f"{'PF_full':>8} {'PF_H1':>7} {'PF_H2':>7} {'trades':>7} {'robust':>7}")
    rows = []
    for vwap, confirm, gap, hname, hours in variants:
        cfg = base_gc(use_vwap_veto=vwap, confirm_bars=confirm,
                      gap_min_ticks=float(gap[0]), gap_max_ticks=float(gap[1]),
                      enabled_hours=hours)
        ind = im.compute(df, cfg)
        arrays = extract(df, ind)
        pf_f, tr, _ = pf_of(cfg, arrays, 0, n)
        pf1, _, _ = pf_of(cfg, arrays, 0, mid)
        pf2, _, _ = pf_of(cfg, arrays, mid, n)
        robust = pf1 > 1.0 and pf2 > 1.0 and pf_f > 1.0
        rows.append((pf_f, pf1, pf2, tr, robust, vwap, confirm, gap, hname))
        print(f"  {str(vwap):>5} {confirm:>4} {str(gap):>7} {hname:>5} "
              f"{pf_f:>8.3f} {pf1:>7.3f} {pf2:>7.3f} {tr:>7} {'YES' if robust else '':>7}")

    rows.sort(key=lambda r: (r[4], min(r[1], r[2])), reverse=True)  # robust first, then worst-half PF
    print("\nTOP robust configs (by worst-half PF):")
    for pf_f, pf1, pf2, tr, robust, vwap, confirm, gap, hname in rows[:6]:
        tag = "ROBUST" if robust else "in-sample only"
        print(f"  vwap={vwap} confirm={confirm} gap={gap} hours={hname}: "
              f"PF {pf_f:.3f} (H1 {pf1:.3f}/H2 {pf2:.3f}) trades={tr}  [{tag}]")


if __name__ == "__main__":
    main()
