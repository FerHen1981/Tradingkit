"""Time-of-day x day-of-week performance heatmap.

Attributes every trade to its ENTRY (ET hour, ET weekday) bucket and aggregates
all the axes that matter for choosing when to trade: count, win%, profit factor,
expectancy, net $, average hold time (throughput), and worst loss.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Result
from .metrics import trades_frame

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _bucket_stats(g: pd.DataFrame) -> dict:
    net = g["net"].to_numpy()
    wins = net[net > 0]
    losses = net[net <= 0]
    gl = -losses.sum()
    hold_min = (g["exit_time"] - g["entry_time"]).dt.total_seconds().to_numpy() / 60.0
    return {
        "trades": len(g),
        "win_pct": round(100 * len(wins) / len(g), 1) if len(g) else 0.0,
        "pf": round(wins.sum() / gl, 2) if gl > 0 else (np.inf if len(wins) else 0.0),
        "expectancy": round(float(net.mean()), 1) if len(g) else 0.0,
        "net": round(float(net.sum()), 0),
        "avg_hold_min": round(float(np.nanmean(hold_min)), 1) if len(g) else 0.0,
        "worst": round(float(net.min()), 0) if len(g) else 0.0,
    }


def build(res: Result) -> pd.DataFrame:
    df = trades_frame(res)
    if df.empty:
        return df
    et = pd.to_datetime(df["entry_time"])
    df = df.assign(hour=et.dt.hour, weekday=et.dt.weekday)
    rows = []
    for (wd, hr), g in df.groupby(["weekday", "hour"]):
        s = _bucket_stats(g)
        s["weekday"] = WEEKDAYS[wd]
        s["wd"] = wd
        s["hour"] = hr
        rows.append(s)
    return pd.DataFrame(rows).sort_values(["wd", "hour"]).reset_index(drop=True)


def marginal(res: Result, by: str) -> pd.DataFrame:
    """Aggregate over a single axis: by='hour' or by='weekday'."""
    df = trades_frame(res)
    et = pd.to_datetime(df["entry_time"])
    df = df.assign(hour=et.dt.hour, weekday=et.dt.weekday)
    key = "hour" if by == "hour" else "weekday"
    rows = []
    for k, g in df.groupby(key):
        s = _bucket_stats(g)
        s[key] = WEEKDAYS[k] if by == "weekday" else k
        rows.append(s)
    out = pd.DataFrame(rows)
    return out.sort_values(key if by == "hour" else "net", ascending=(by == "hour")).reset_index(drop=True)


def grid(res: Result, metric: str = "expectancy") -> pd.DataFrame:
    """Weekday (rows) x hour (cols) pivot of one metric, for a visual heatmap."""
    hm = build(res)
    if hm.empty:
        return hm
    piv = hm.pivot(index="weekday", columns="hour", values=metric)
    piv = piv.reindex([d for d in WEEKDAYS if d in piv.index])
    return piv
