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


def edge_by_regime(res: Result, regime_labels) -> dict:
    """Realized edge broken down by the OBJECTIVE regime at each trade's ENTRY
    bar. `regime_labels` is the causal per-bar tag from indicators.classify_regime
    (no look-ahead), aligned to the same frame the engine ran on, so the label at
    a trade's entry_bar is what was knowable AT entry.

    This is the unbiased discovery: the data reveals where a strategy's edge
    actually lives, instead of us assuming it via the §6 matrix. Returns
    {regime: {trades, net, profit_factor, expectancy, win_rate_pct}} sorted by
    trade count, plus the fraction of trades whose regime could be resolved."""
    labels = np.asarray(regime_labels, dtype=object)
    n_bars = len(labels)
    buckets: dict[str, list] = {}
    for t in res.trades:
        i = int(t.entry_bar)
        reg = labels[i] if 0 <= i < n_bars else "Unknown"
        buckets.setdefault(str(reg), []).append(float(t.net))
    out = {}
    for reg, nets in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        arr = np.asarray(nets, dtype=float)
        wins = arr[arr > 0]
        gw = float(wins.sum())
        gl = float(-arr[arr <= 0].sum())
        out[reg] = {
            "trades": int(len(arr)),
            "net": round(float(arr.sum()), 2),
            "profit_factor": (round(gw / gl, 2) if gl > 0 else (float("inf") if gw > 0 else 0.0)),
            "expectancy": round(float(arr.mean()), 2),
            "win_rate_pct": round(100 * len(wins) / len(arr), 1),
        }
    return out


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
