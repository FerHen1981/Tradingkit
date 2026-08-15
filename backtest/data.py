"""Load and prepare the NQ 1-minute dataset.

Expected columns (as delivered):
    DateTime (e.g. "18-6-2023 18:00:00 -04:00"), Open, High, Low, Close,
    CVD_close, Volume, BuyVolume, SellVolume, Delta

The DateTime carries an explicit ET offset. We keep an ET-localised timestamp
and derive:
  * ``et``            – tz-aware timestamp in America/New_York
  * ``hour``,``minute``,``weekday`` (ET, weekday 0=Mon)
  * ``mod``          – minute of ET day (hour*60+minute)
  * ``session_date`` – CME "trade date": the session rolls at 18:00 ET, so we
                       shift by +6h and take the date. New session == this value
                       changes (equivalent to Pine ``timeframe.change("1D")``).
  * ``new_session``  – bool, first bar of a new trade date
"""
from __future__ import annotations

import pandas as pd


REQUIRED = ["DateTime", "Open", "High", "Low", "Close", "Volume", "Delta"]


def load(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    et = pd.to_datetime(df["DateTime"], format="%d-%m-%Y %H:%M:%S %z", errors="coerce")
    if et.isna().any():
        # fall back to flexible parsing for other instrument exports
        et = pd.to_datetime(df["DateTime"], errors="coerce", utc=False)
    if et.isna().any():
        n = int(et.isna().sum())
        raise ValueError(f"{n} DateTime values failed to parse")
    if et.dt.tz is None:
        et = et.dt.tz_localize("America/New_York")
    et = et.dt.tz_convert("America/New_York")

    df = df.copy()
    df["et"] = et
    return _derive(df)


def _derive(df: pd.DataFrame) -> pd.DataFrame:
    """(Re)compute the time-derived columns from an existing ET timestamp column.
    Shared by load() and resample()."""
    et = df["et"]
    df = df.copy()
    df["hour"] = et.dt.hour.to_numpy()
    df["minute"] = et.dt.minute.to_numpy()
    df["weekday"] = et.dt.weekday.to_numpy()          # 0=Mon .. 6=Sun
    df["mod"] = df["hour"] * 60 + df["minute"]

    # Trade date: session opens 18:00 ET -> shift +6h so 18:00 becomes 00:00 next day.
    session_date = (et + pd.Timedelta(hours=6)).dt.date
    df["session_date"] = session_date
    new_session = pd.Series(session_date, index=df.index).ne(
        pd.Series(session_date, index=df.index).shift(1)
    ).to_numpy().copy()
    new_session[0] = True
    df["new_session"] = new_session
    return df.reset_index(drop=True)


def resample_tf(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate to a canonical timeframe label (1m,5m,10m,15m,30m,1h,2h,3h,4h,1d)."""
    from .config import tf_minutes
    return resample(df, tf_minutes(timeframe))


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate 1-minute bars to N-minute bars, aligned to each session's
    18:00 ET open (bars never span the session boundary or the maintenance
    break). Elapsed-minute bucketing is gap-safe.
    """
    if minutes <= 1:
        return df.reset_index(drop=True)
    g = df.copy()
    first = g.groupby("session_date")["et"].transform("first")
    elapsed = ((g["et"] - first).dt.total_seconds() // 60).astype("int64")
    g["_bucket"] = elapsed // minutes

    agg = {"et": ("et", "first"), "Open": ("Open", "first"), "High": ("High", "max"),
           "Low": ("Low", "min"), "Close": ("Close", "last")}
    for opt, how in (("Volume", "sum"), ("Delta", "sum"), ("BuyVolume", "sum"),
                     ("SellVolume", "sum"), ("CVD_close", "last")):
        if opt in g.columns:
            agg[opt] = (opt, how)

    out = (g.groupby(["session_date", "_bucket"], sort=True)
             .agg(**agg)
             .reset_index()
             .sort_values("et")
             .drop(columns=["session_date", "_bucket"]))
    return _derive(out)
