"""Trade-list KPIs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Result


def trades_frame(res: Result) -> pd.DataFrame:
    rows = [{
        "dir": t.dir, "qty": t.qty,
        "entry_time": t.entry_time, "entry_px": t.entry_px,
        "exit_time": t.exit_time, "exit_px": t.exit_px,
        "reason": t.reason, "gross": t.gross, "commission": t.commission,
        "net": t.net, "mfe_ticks": t.mfe_ticks, "mae_ticks": t.mae_ticks,
    } for t in res.trades]
    return pd.DataFrame(rows)


def kpis(res: Result) -> dict:
    df = trades_frame(res)
    n = len(df)
    if n == 0:
        return {"trades": 0}
    net = df["net"].to_numpy()
    wins = net[net > 0]
    losses = net[net <= 0]
    equity = np.cumsum(net)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    reasons = df["reason"].value_counts().to_dict()
    return {
        "trades": n,
        "net_profit": round(float(net.sum()), 2),
        "win_rate_pct": round(100 * len(wins) / n, 1),
        "avg_trade": round(float(net.mean()), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "profit_factor": round(float(gross_win / gross_loss), 2) if gross_loss > 0 else float("inf"),
        "expectancy": round(float(net.mean()), 2),
        "max_drawdown": round(float(dd.max()), 2),
        "total_commission": round(float(df["commission"].sum()), 2),
        "longs": int((df["dir"] == 1).sum()),
        "shorts": int((df["dir"] == -1).sum()),
        "exit_reasons": reasons,
    }
