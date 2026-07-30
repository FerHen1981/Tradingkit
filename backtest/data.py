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
        n = int(et.isna().sum())
        raise ValueError(f"{n} DateTime values failed to parse")
    et = et.dt.tz_convert("America/New_York")

    df = df.copy()
    df["et"] = et
    df["hour"] = et.dt.hour.to_numpy()
    df["minute"] = et.dt.minute.to_numpy()
    df["weekday"] = et.dt.weekday.to_numpy()          # 0=Mon .. 6=Sun
    df["mod"] = df["hour"] * 60 + df["minute"]

    # Trade date: session opens 18:00 ET -> shift +6h so 18:00 becomes 00:00 next day.
    session_date = (et + pd.Timedelta(hours=6)).dt.date
    df["session_date"] = session_date
    df["new_session"] = pd.Series(session_date, index=df.index).ne(
        pd.Series(session_date, index=df.index).shift(1)
    ).to_numpy()
    df.loc[df.index[0], "new_session"] = True

    df = df.reset_index(drop=True)
    return df
