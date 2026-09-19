"""Rich performance scorecard for a single engine run.

`metrics.kpis()` gives the headline KPIs; this adds the depth the Analysis screen
needs — the excursion, streak, per-side and equity-curve views — WITHOUT a second
engine run. Everything here is derived from the trade list a run already produced.

Deliberately NOT here (v1): Sharpe / Sortino. They need a defined return series
against a capital base, which the engine does not produce today; adding them is a
separate decision (D-23 / SM-11). Excluding them keeps every number on this card
grounded in a quantity the engine actually measures.

Pure Python over `metrics`/`funded` output — no engine coupling — so it unit-tests
on a hand-built trade list.
"""
from __future__ import annotations

import numpy as np

from ..metrics import kpis


def _edge(nets: np.ndarray) -> dict:
    """Net / PF / win-rate / expectancy / avg win-loss for one bucket of trades."""
    n = len(nets)
    if n == 0:
        return {"trades": 0, "net": 0.0, "pf": 0.0, "win_rate_pct": 0.0,
                "expectancy": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    gl = float(-losses.sum())
    return {
        "trades": int(n),
        "net": round(float(nets.sum()), 2),
        "pf": (round(float(wins.sum()) / gl, 2) if gl > 0
               else (float("inf") if wins.sum() > 0 else 0.0)),
        "win_rate_pct": round(100 * len(wins) / n, 1),
        "expectancy": round(float(nets.mean()), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
    }


def _streaks(nets: np.ndarray) -> dict:
    """Longest consecutive win / loss runs, and the run in progress at the end.
    A scratch (net == 0) counts as a loss here — it is not a banked winner."""
    longest_win = longest_loss = cur = 0
    cur_sign = 0
    for x in nets:
        s = 1 if x > 0 else -1
        cur = cur + 1 if s == cur_sign else 1
        cur_sign = s
        if s > 0:
            longest_win = max(longest_win, cur)
        else:
            longest_loss = max(longest_loss, cur)
    return {"longest_win": longest_win, "longest_loss": longest_loss,
            "current": cur * cur_sign}      # signed: +3 = on a 3-win run


def _equity_curve(nets: np.ndarray, times, cap: int = 500) -> dict:
    """Cumulative banked equity after each closed trade, plus its drawdown.
    Down-sampled to at most `cap` points so the JSON stays small on long runs —
    the extremes (peak, trough) are preserved, only intermediate points thin out."""
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    n = len(eq)
    idx = (np.linspace(0, n - 1, cap).round().astype(int) if n > cap
           else np.arange(n))
    pts = [{"i": int(i), "t": (str(times[i]) if times is not None and i < len(times)
                               and times[i] is not None else None),
            "equity": round(float(eq[i]), 2), "dd": round(float(dd[i]), 2)}
           for i in idx]
    return {"points": pts, "final": round(float(eq[-1]), 2),
            "peak": round(float(peak[-1]), 2),
            "max_drawdown": round(float(dd.max()), 2),
            "downsampled": n > cap, "n": int(n)}


def _exit_reason_edge(nets: np.ndarray, reasons) -> list:
    """Per exit-reason: count and net — so a card can show WHICH exits pay and
    which bleed, not just how often each fires."""
    out: dict[str, list] = {}
    for x, r in zip(nets, reasons):
        out.setdefault(str(r or "?"), []).append(float(x))
    rows = [{"reason": r, "trades": len(v), "net": round(float(sum(v)), 2)}
            for r, v in out.items()]
    return sorted(rows, key=lambda d: -d["trades"])


def scorecard(res, daily: dict | None = None) -> dict:
    """Full scorecard for one Result. `daily` is an optional {date: net} map
    (funded.daily_from_trades) for the day-level equity view; when absent it is
    derived from exit dates so the card still renders."""
    base = kpis(res)
    trades = [t for t in res.trades if getattr(t, "exit_time", None) is not None]
    if not trades:
        return {"kpis": base, "trades": 0, "empty": True}

    nets = np.array([float(t.net) for t in trades])
    dirs = np.array([int(t.dir) for t in trades])
    mfe = np.array([float(t.mfe_ticks) for t in trades])
    mae = np.array([float(t.mae_ticks) for t in trades])
    holds = np.array([int(t.exit_bar) - int(t.entry_bar) for t in trades], dtype=float)
    times = [t.exit_time for t in trades]
    reasons = [t.reason for t in trades]

    # best / worst by banked net, with enough context to find the trade
    bi, wi = int(nets.argmax()), int(nets.argmin())

    def _trade_ref(i):
        t = trades[i]
        return {"net": round(float(t.net), 2), "dir": int(t.dir),
                "entry_time": str(t.entry_time), "exit_time": str(t.exit_time),
                "reason": t.reason, "mfe_ticks": round(float(t.mfe_ticks), 1),
                "mae_ticks": round(float(t.mae_ticks), 1)}

    # day-level series (banked $/day) for a calendar equity view
    if daily is None:
        try:
            from ..funded import daily_from_trades
            daily = daily_from_trades(trades)
        except Exception:
            daily = {}
    day_items = sorted(daily.items()) if daily else []
    day_curve = []
    if day_items:
        cum = 0.0
        for d, v in day_items:
            cum += float(v)
            day_curve.append({"d": str(d), "net": round(float(v), 2),
                              "equity": round(cum, 2)})
    win_days = sum(1 for _, v in day_items if v > 0)

    return {
        "kpis": base,
        "trades": len(trades),
        "equity_curve": _equity_curve(nets, times),
        "day_curve": day_curve,
        "streaks": _streaks(nets),
        "best_trade": _trade_ref(bi),
        "worst_trade": _trade_ref(wi),
        "by_direction": {
            "long": _edge(nets[dirs == 1]),
            "short": _edge(nets[dirs == -1]),
        },
        "excursion": {
            "avg_mfe_ticks": round(float(mfe.mean()), 1),
            "median_mfe_ticks": round(float(np.median(mfe)), 1),
            "avg_mae_ticks": round(float(mae.mean()), 1),
            "median_mae_ticks": round(float(np.median(mae)), 1),
        },
        "hold_time_bars": {
            "avg": round(float(holds.mean()), 1),
            "median": round(float(np.median(holds)), 1),
            "max": int(holds.max()),
        },
        "exit_reason_edge": _exit_reason_edge(nets, reasons),
        "days": {
            "trading_days": len(day_items),
            "win_days": win_days,
            "win_day_pct": round(100 * win_days / len(day_items), 1) if day_items else 0.0,
            "best_day": round(max((v for _, v in day_items), default=0.0), 2),
            "worst_day": round(min((v for _, v in day_items), default=0.0), 2),
        },
    }
