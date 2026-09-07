"""The Analysis scorecard — the derived views on top of metrics.kpis.

These pin the derivations that kpis() does NOT give: win/loss streaks, best/worst
trade, the per-direction split, MFE/MAE aggregation, and the equity curve. Numbers
are computed on a hand-built trade list so the expected values are exact.
"""
from __future__ import annotations

import pandas as pd

from backtest.pipeline import scorecard as sc


class _T:
    """Minimal stand-in for engine.Trade (all fields metrics/scorecard read)."""
    def __init__(self, i, dir_, net, reason="TP", mfe=100.0, mae=20.0, hold=10):
        self.dir, self.net, self.reason = dir_, float(net), reason
        self.qty = 1.0
        self.entry_bar = i * 100
        self.exit_bar = i * 100 + hold
        self.entry_time = pd.Timestamp("2025-01-02 09:30") + pd.Timedelta(days=i)
        self.exit_time = self.entry_time + pd.Timedelta(minutes=hold)
        self.entry_px, self.exit_px = 100.0, 101.0
        self.gross = self.net
        self.commission = 1.0
        self.mfe_ticks, self.mae_ticks = float(mfe), float(mae)


class _Res:
    def __init__(self, trades):
        self.trades = trades


def test_empty_run_is_handled():
    card = sc.scorecard(_Res([]))
    assert card["empty"] and card["trades"] == 0


def test_streaks_count_longest_runs():
    # W W W L L W  -> longest win 3, longest loss 2, ending on a 1-win run
    nets = [10, 10, 10, -5, -5, 10]
    card = sc.scorecard(_Res([_T(i, 1, n) for i, n in enumerate(nets)]))
    assert card["streaks"]["longest_win"] == 3
    assert card["streaks"]["longest_loss"] == 2
    assert card["streaks"]["current"] == 1


def test_best_and_worst_trade_are_identified():
    nets = [10, -40, 25, -5]
    card = sc.scorecard(_Res([_T(i, 1, n) for i, n in enumerate(nets)]))
    assert card["best_trade"]["net"] == 25.0
    assert card["worst_trade"]["net"] == -40.0


def test_per_direction_split():
    trades = [_T(0, 1, 30), _T(1, 1, -10), _T(2, -1, 20), _T(3, -1, 20)]
    card = sc.scorecard(_Res(trades))
    lo, sh = card["by_direction"]["long"], card["by_direction"]["short"]
    assert lo["trades"] == 2 and lo["net"] == 20.0
    assert sh["trades"] == 2 and sh["net"] == 40.0 and sh["win_rate_pct"] == 100.0


def test_excursion_and_hold_time_aggregate():
    trades = [_T(0, 1, 10, mfe=100, mae=20, hold=10),
              _T(1, 1, 10, mfe=200, mae=40, hold=30)]
    card = sc.scorecard(_Res(trades))
    assert card["excursion"]["avg_mfe_ticks"] == 150.0
    assert card["excursion"]["avg_mae_ticks"] == 30.0
    assert card["hold_time_bars"]["avg"] == 20.0
    assert card["hold_time_bars"]["max"] == 30


def test_equity_curve_is_cumulative_and_reports_drawdown():
    # +10, -30, +40 -> equity 10, -20, 20 ; peak-to-trough dd = 30
    nets = [10, -30, 40]
    card = sc.scorecard(_Res([_T(i, 1, n) for i, n in enumerate(nets)]))
    ec = card["equity_curve"]
    assert [p["equity"] for p in ec["points"]] == [10.0, -20.0, 20.0]
    assert ec["final"] == 20.0
    assert ec["max_drawdown"] == 30.0


def test_equity_curve_downsamples_long_runs():
    trades = [_T(i, 1, 1) for i in range(1200)]
    card = sc.scorecard(_Res(trades))
    ec = card["equity_curve"]
    assert ec["downsampled"] and ec["n"] == 1200
    assert len(ec["points"]) <= 500
    assert ec["final"] == 1200.0        # extremes preserved despite thinning


def test_exit_reason_edge_sums_net_per_reason():
    trades = [_T(0, 1, 50, reason="TP"), _T(1, 1, 60, reason="TP"),
              _T(2, 1, -40, reason="SL")]
    card = sc.scorecard(_Res(trades))
    by = {r["reason"]: r for r in card["exit_reason_edge"]}
    assert by["TP"]["trades"] == 2 and by["TP"]["net"] == 110.0
    assert by["SL"]["net"] == -40.0
