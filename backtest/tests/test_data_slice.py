"""Date slicing + IS/OOS holdout split (runs on the bt-venv; needs pandas)."""
import pandas as pd

from backtest.data import slice_dates, holdout_split


def _mk(n_days):
    idx = pd.date_range("2024-01-01 18:00", periods=n_days, freq="1D", tz="America/New_York")
    return pd.DataFrame({"et": idx, "Close": range(n_days)})


def test_slice_since_until():
    df = _mk(100)
    s = slice_dates(df, since="2024-02-01", until="2024-03-01")
    assert s["et"].iloc[0] >= pd.Timestamp("2024-02-01", tz="America/New_York")
    assert s["et"].iloc[-1] < pd.Timestamp("2024-03-01", tz="America/New_York")
    assert len(s) == 29   # february 2024 (leap year), 1..29


def test_slice_open_bounds():
    df = _mk(50)
    assert len(slice_dates(df, since=None, until=None)) == 50
    assert len(slice_dates(df, since="2024-01-10")) == 41


def test_holdout_split_last_days():
    df = _mk(100)                     # 100 daily bars
    is_df, oos_df, cut = holdout_split(df, days=10)
    # OOS = last ~10 days; the two halves partition the data
    assert len(is_df) + len(oos_df) == 100
    assert oos_df["et"].iloc[0] > cut and is_df["et"].iloc[-1] <= cut
    assert 9 <= len(oos_df) <= 11
