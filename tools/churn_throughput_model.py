"""Churn / throughput model — turns caveat #2 into a number.

The net-income model assumed a funded account trades continuously. Reality: a
funded breach KILLS the PA; you must re-pass an eval before banking resumes, so
the account is idle during re-qualification. Realized banked = sim banked x UPTIME.

We measure the real durations:
  * eval attempt length (sessions to PASS/BREACH/TIMEOUT) from a resolution-aware
    funnel on ES (El León) @ the design size,
  * funded run length (sessions between breaches) from the GC flywheel cadence,
then:
  requal_sessions = ((1-p)/p) * mean_fail_sessions + mean_pass_sessions
  uptime          = funded_run / (funded_run + requal_sessions)
  realized/yr     = sim_banked/yr * uptime      (+ a one-time first-funding lead)
"""
from __future__ import annotations

import numpy as np

from backtest import data as dm, indicators as im
from backtest.config import contract
from backtest.engine import Engine, extract
from tools.legacy_accounts_analysis import ES_SIG

SESS_PER_YR = 252.0
# funded (GC El Tesoro, capped) — RECOVERED edge gap (9,18), PF 1.06.
# From tools/funded_flywheel_sim.py; per size a few nominal qty (banked_3y, breaches_3y).
FUNDED = {
    "250k": {1: (34_000, 10), 2: (63_500, 21), 3: (57_000, 28)},
    "300k": {1: (30_500, 7),  2: (51_000, 17), 3: (79_000, 21)},
}
YEARS = 3.0


def eval_durations(sym, sig, qty, dd, step=5, horizon=20):
    """Resolution-aware funnel: per attempt record outcome + sessions-to-resolve."""
    df = dm.load(f"data/{sym}_norm.csv")
    cfg = sig.with_(contract=contract(sym), contract_size=float(qty),
                    phase="Apex Eval", dd_model="Intraday",
                    acct_trail_dd=float(dd), acct_goal=(15_000.0 if dd == 6500 else 20_000.0),
                    consistency_pct=50.0)
    ind = im.compute(df, cfg)
    arrays = extract(df, ind)
    sess_idx = np.cumsum(df["new_session"].to_numpy(bool))     # session number per bar
    starts = np.flatnonzero(df["new_session"].to_numpy(bool))
    by = {"PASS": [], "BREACH": [], "TIMEOUT": []}
    for si in range(0, len(starts) - horizon, step):
        sb = int(starts[si])
        eb = int(starts[si + horizon]) if si + horizon < len(starts) else len(df)
        eng = Engine(cfg, research_mode=False, start_bar=sb, arrays=arrays)
        res = eng.run(end_bar=eb)
        reason = eng.acct_halt_reason
        r = "PASS" if "PASSED" in reason else ("BREACH" if ("TRAILING" in reason or "FAILED" in reason) else "TIMEOUT")
        resolve_bar = res.trades[-1].exit_bar if (r != "TIMEOUT" and res.trades and res.trades[-1].exit_bar > 0) else eb
        dur = max(1, int(sess_idx[min(resolve_bar, len(sess_idx)-1)] - sess_idx[sb]))
        by[r].append(dur)
    return by


def model(eval_qty, dd, size_label):
    # eval re-qualification time on ES (El León) at the design size
    by = eval_durations("ES", ES_SIG, eval_qty, dd)
    n = sum(len(v) for v in by.values())
    p = len(by["PASS"]) / n if n else 0.0
    mean_fail = np.mean(by["BREACH"] + by["TIMEOUT"]) if (by["BREACH"] + by["TIMEOUT"]) else 20.0
    mean_pass = np.mean(by["PASS"]) if by["PASS"] else 20.0
    requal = ((1 - p) / p) * mean_fail + mean_pass if p else float("inf")

    print(f"\n{size_label}  (ES eval @{eval_qty}ct  ->  GC funded)   "
          f"eval pass={p*100:.1f}%  requal~{requal:.0f}s (~{requal/5:.0f}wk)")
    print(f"  {'GCqty':>5} {'sim/yr':>9} {'breach/yr':>10} {'funded_run':>11} {'uptime':>7} {'REALIZED/yr':>12}")
    best = (None, -1)
    for gcq, (banked_3y, breaches_3y) in FUNDED[size_label].items():
        funded_run = (YEARS * SESS_PER_YR) / breaches_3y
        uptime = funded_run / (funded_run + requal)
        realized = (banked_3y / YEARS) * uptime
        mark = ""
        if realized > best[1]:
            best = (gcq, realized);
        print(f"  {gcq:>5} ${banked_3y/YEARS:>7,.0f} {breaches_3y/YEARS:>10.1f} "
              f"{funded_run:>9.0f}s {uptime*100:>6.0f}% ${realized:>10,.0f}")
    print(f"  -> best GC size = {best[0]}ct  ->  REALIZED ${best[1]:,.0f}/yr")
    return best[1]


def main():
    fleet = 0.0
    fleet += 3 * model(3, 6500, "250k")
    fleet += 1 * model(3, 7500, "300k")
    print(f"\nFLEET realized (3x250k + 1x300k), best funded size each ~ ${fleet:,.0f}/yr")


if __name__ == "__main__":
    main()
