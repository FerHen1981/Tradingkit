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
# funded (GC El Tesoro, capped) from tools/funded_flywheel_sim.py
FUNDED = {"250k": (25_500, 14), "300k": (59_000, 18)}   # (banked_3y, breaches_3y)
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


def model(sym, qty, dd, size_label):
    by = eval_durations(sym, ES_SIG, qty, dd)
    n = sum(len(v) for v in by.values())
    p = len(by["PASS"]) / n if n else 0.0
    mean_fail = np.mean(by["BREACH"] + by["TIMEOUT"]) if (by["BREACH"] + by["TIMEOUT"]) else horizon
    mean_pass = np.mean(by["PASS"]) if by["PASS"] else 20.0
    attempts = 1.0 / p if p else float("inf")
    requal = ((1 - p) / p) * mean_fail + mean_pass if p else float("inf")

    banked_3y, breaches_3y = FUNDED[size_label]
    funded_run = (YEARS * SESS_PER_YR) / breaches_3y
    uptime = funded_run / (funded_run + requal)
    sim_yr = banked_3y / YEARS
    realized_yr = sim_yr * uptime

    print(f"\n{size_label}  (ES eval @{qty}ct  ->  GC funded)")
    print(f"  eval: pass={p*100:.1f}%  attempts~{attempts:.1f}  "
          f"mean_fail={mean_fail:.0f}s  mean_pass={mean_pass:.0f}s  -> requal~{requal:.0f} sessions (~{requal/5:.0f} wk)")
    print(f"  funded run ~{funded_run:.0f} sessions (~{funded_run/5:.0f} wk between breaches)")
    print(f"  UPTIME = {uptime*100:.0f}%   sim ${sim_yr:,.0f}/yr  ->  REALIZED ${realized_yr:,.0f}/yr")
    return realized_yr


def main():
    fleet = 0.0
    fleet += 3 * model("ES", 3, 6500, "250k")
    fleet += 1 * model("ES", 3, 7500, "300k")
    print(f"\nFLEET realized (3x250k + 1x300k) ~ ${fleet:,.0f}/yr  (churn-adjusted)")


if __name__ == "__main__":
    main()
