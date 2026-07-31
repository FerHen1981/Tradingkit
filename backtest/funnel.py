"""Walk-forward eval funnel.

A single continuous run is the wrong lens for an Apex *Eval* strategy (El Toro):
once it passes or breaches, the account is done. To judge "how reliably does it
fund an account", start a *fresh* eval at many points in history and measure the
distribution of outcomes: PASS (hit +goal), BREACH (blew the trailing DD), or
TIMEOUT (neither within the horizon).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Config
from .engine import Engine, extract


@dataclass
class FunnelOutcome:
    start_bar: int
    start_time: pd.Timestamp
    result: str          # "PASS" | "BREACH" | "TIMEOUT"
    trades: int
    net_profit: float
    bars: int


def _session_starts(df: pd.DataFrame) -> np.ndarray:
    return np.flatnonzero(df["new_session"].to_numpy(bool))


def run_funnel(cfg: Config, df: pd.DataFrame, ind: pd.DataFrame,
               step_sessions: int = 5, horizon_sessions: int = 20) -> list[FunnelOutcome]:
    starts = _session_starts(df)
    arrays = extract(df, ind)   # extract once, reuse for every fresh eval
    times = df["et"]
    # map each session-start bar to a horizon end bar (start + horizon sessions)
    outcomes: list[FunnelOutcome] = []
    for si in range(0, len(starts) - horizon_sessions, step_sessions):
        sb = int(starts[si])
        eb = int(starts[si + horizon_sessions]) if si + horizon_sessions < len(starts) else len(df)
        eng = Engine(cfg, research_mode=False, start_bar=sb, arrays=arrays)
        res = eng.run(end_bar=eb)
        reason = eng.acct_halt_reason
        if "PASSED" in reason:                 # "EVAL PASSED" or "CHALLENGE PASSED"
            r = "PASS"
        elif "TRAILING" in reason or "FAILED" in reason:
            r = "BREACH"
        else:
            r = "TIMEOUT"
        outcomes.append(FunnelOutcome(
            start_bar=sb, start_time=pd.Timestamp(times.iloc[sb]), result=r,
            trades=len(res.trades), net_profit=eng.net_profit, bars=eb - sb))
    return outcomes


def summarize(outcomes: list[FunnelOutcome]) -> dict:
    n = len(outcomes)
    if n == 0:
        return {"starts": 0}
    res = np.array([o.result for o in outcomes])
    npass = int((res == "PASS").sum())
    nbreach = int((res == "BREACH").sum())
    ntimeout = int((res == "TIMEOUT").sum())
    resolved = npass + nbreach
    trades = np.array([o.trades for o in outcomes])
    return {
        "starts": n,
        "pass": npass,
        "breach": nbreach,
        "timeout": ntimeout,
        "pass_rate_pct": round(100 * npass / n, 1),
        "pass_rate_of_resolved_pct": round(100 * npass / resolved, 1) if resolved else 0.0,
        "median_trades_to_resolve": int(np.median(trades)) if n else 0,
    }
