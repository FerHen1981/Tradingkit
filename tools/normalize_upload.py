"""Normalize the uploaded raw 1m tickdata exports into the engine's format.

Input quirks handled:
  * European decimal comma ("11319,75") + quoted numeric fields
  * NQ: DST-aware CET offsets (+02:00/+01:00), inline on DateTime; has an
    order-flow Delta column but it is ALL ZERO in this export -> unusable.
  * GC/YM: a separate constant "UTC" offset column of -04:00 (exchange
    wall-clock, NOT DST-aware) and NO delta column at all.

Output: DateTime (ISO-8601, ET-aware), Open, High, Low, Close, Volume, Delta.
Delta is written as 0 for every asset (NQ order-flow is empty; GC/YM have none)
so every run must use CVD/delta filter OFF -- consistent with docs/forex_delta.md
(delta adds no edge on NQ; GC's edge was validated WITHOUT delta).
"""
from __future__ import annotations

import sys
import pandas as pd

SRC = {
    "NQ": "data/3 years of NQ 1m tickdata.csv",
    "GC": "data/3 years of GC 1m tickdata.csv",
    "YM": "data/3 years of YM 1m tickdata.csv",
    "ES": "data/3 years of ES 1m tickdata.csv",
}
OUT = {"NQ": "data/NQ_norm.csv", "GC": "data/GC_norm.csv", "YM": "data/YM_norm.csv",
       "ES": "data/ES_norm.csv"}
# ES uses the GC/YM export shape (UTC-offset column, decimal comma, no delta).
_ETWALL = {"GC", "YM", "ES"}


def _num(df, cols):
    for c in cols:
        if True:  # columns may be pandas 'str' dtype, not object — always convert
            df[c] = (df[c].astype(str).str.replace(" ", "", regex=False)
                     .str.replace(".", "", regex=False)   # no thousands sep expected, but be safe
                     .str.replace(",", ".", regex=False))
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def norm_nq(path):
    cols = ["DateTime", "Open", "High", "Low", "Close", "Volume(from bar)"]
    df = pd.read_csv(path, encoding="utf-8-sig", usecols=cols)
    df = _num(df, ["Open", "High", "Low", "Close", "Volume(from bar)"])
    et = pd.to_datetime(df["DateTime"], format="%d-%m-%Y %H:%M:%S %z",
                        errors="coerce", utc=True)
    et = et.dt.tz_convert("America/New_York")
    out = pd.DataFrame({
        "DateTime": et.dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S%z"),
        "Open": df["Open"], "High": df["High"], "Low": df["Low"], "Close": df["Close"],
        "Volume": df["Volume(from bar)"].fillna(0), "Delta": 0,
    })
    return out.dropna(subset=["Open", "High", "Low", "Close"])


def norm_etwall(path):
    cols = ["DateTime", "Open", "High", "Low", "Close", "Volume(from bar)"]
    df = pd.read_csv(path, encoding="utf-8-sig", usecols=cols)
    df = _num(df, ["Open", "High", "Low", "Close", "Volume(from bar)"])
    naive = pd.to_datetime(df["DateTime"], dayfirst=True, errors="coerce")
    # wall-clock is exchange (ET); localize DST-aware, dropping the vendor's
    # constant -04:00 label. Ambiguous/nonexistent DST-transition bars -> NaT-safe.
    et = naive.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    out = pd.DataFrame({
        "DateTime": et.dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S%z"),
        "Open": df["Open"], "High": df["High"], "Low": df["Low"], "Close": df["Close"],
        "Volume": df["Volume(from bar)"].fillna(0), "Delta": 0,
    })
    return out.dropna(subset=["Open", "High", "Low", "Close", "DateTime"])


def main():
    which = sys.argv[1:] or ["NQ", "GC", "YM"]
    for sym in which:
        fn = norm_nq if sym == "NQ" else norm_etwall
        out = fn(SRC[sym])
        out.to_csv(OUT[sym], index=False)
        print(f"{sym}: {len(out):,} rows -> {OUT[sym]}  ({out['DateTime'].iloc[0]} .. {out['DateTime'].iloc[-1]})")


if __name__ == "__main__":
    main()
