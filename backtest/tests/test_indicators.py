"""Focused checks on the indicator layer (the part most prone to off-by-one
errors when porting Pine's bar-indexing)."""
import numpy as np
import pandas as pd

from backtest.config import EL_DORADO
from backtest.indicators import _pivot_confirmed, _run_length_positive, compute


def _mk(bars):
    """bars: list of (o,h,l,c,vol,delta) -> prepared df with minimal columns."""
    idx = pd.date_range("2024-01-02 18:00", periods=len(bars), freq="1min", tz="America/New_York")
    df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close", "Volume", "Delta"])
    df["et"] = idx
    df["new_session"] = [True] + [False] * (len(bars) - 1)
    return df


def test_fvg_bullish_detected_and_sized():
    # bar i has low >= high[i-2] -> bullish gap. Craft a clean 3-bar gap.
    bars = [
        (100, 101, 99, 100, 10, 5),
        (100, 102, 100, 101, 10, 5),
        (104, 106, 103.5, 105, 10, 5),  # low 103.5 >= high[i-2]=101 -> bull gap top=103.5 bottom=101
    ]
    df = _mk(bars)
    cfg = EL_DORADO.with_(use_gap_filter=False)
    ind = compute(df, cfg)
    assert ind["fvg_dir"].iloc[2] == 1
    assert abs(ind["fvg_top"].iloc[2] - 103.5) < 1e-9
    assert abs(ind["fvg_bot"].iloc[2] - 101.0) < 1e-9


def test_fvg_bearish_detected():
    bars = [
        (100, 101, 99, 100, 10, -5),
        (99, 100, 98, 99, 10, -5),
        (96, 96.5, 95, 95.5, 10, -5),  # low[i-2]=99 >= high[i]=96.5 -> bear gap
    ]
    df = _mk(bars)
    cfg = EL_DORADO.with_(use_gap_filter=False)
    ind = compute(df, cfg)
    assert ind["fvg_dir"].iloc[2] == -1


def test_pivot_low_confirms_after_k_bars():
    # a clear V bottom at index 3 with k=2 confirms at index 5
    lows = np.array([10, 9, 8, 5, 8, 9, 10, 11], dtype=float)
    piv = _pivot_confirmed(lows, 2, "low")
    assert np.isnan(piv[4])          # not yet confirmed
    assert piv[5] == 5               # confirmed 2 bars later
    assert piv[6] == 5               # held via fixnan


def test_delta_streak_run_length():
    d = np.array([1, 1, -1, 1, 1, 1, 0, 1], dtype=float)
    r = _run_length_positive(d)
    assert list(r) == [1, 2, 0, 1, 2, 3, 0, 1]


def test_resample_preserves_ohlc_and_volume():
    from backtest.data import resample
    # 6 one-minute bars in one session -> two 3-minute bars
    idx = pd.date_range("2024-01-02 18:00", periods=6, freq="1min", tz="America/New_York")
    df = pd.DataFrame({
        "Open": [10, 11, 12, 13, 14, 15], "High": [11, 12, 13, 14, 15, 16],
        "Low": [9, 10, 11, 12, 13, 14], "Close": [11, 12, 13, 14, 15, 16],
        "Volume": [1, 2, 3, 4, 5, 6], "Delta": [1, -1, 2, -2, 3, -3],
    })
    df["et"] = idx
    df["session_date"] = idx[0].date()
    df["new_session"] = [True] + [False] * 5
    r = resample(df, 3)
    assert len(r) == 2
    assert r["Open"].iloc[0] == 10 and r["Close"].iloc[0] == 13   # first/last of bars 0-2
    assert r["High"].iloc[0] == 13 and r["Low"].iloc[0] == 9      # max/min
    assert r["Volume"].iloc[0] == 6 and r["Delta"].iloc[0] == 2   # sums
    assert r["Volume"].sum() == df["Volume"].sum()                # conserved
    assert bool(r["new_session"].iloc[0]) is True


def test_vwap_resets_each_session():
    bars = [(100, 100, 100, 100, 1, 0), (200, 200, 200, 200, 1, 0)]
    df = _mk(bars)
    df.loc[1, "new_session"] = True   # force a reset on bar 2
    ind = compute(df, EL_DORADO)
    assert abs(ind["vwap"].iloc[0] - 100) < 1e-9
    assert abs(ind["vwap"].iloc[1] - 200) < 1e-9   # reset, not blended
