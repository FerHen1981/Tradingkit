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

import os
import re

import pandas as pd


REQUIRED = ["DateTime", "Open", "High", "Low", "Close", "Volume", "Delta"]


def dataset_id(path) -> str:
    """Stable dataset identity for run fingerprints. Every Lab dataset stores its
    file as datasets/<name>/canonical.csv, so the FILE name alone collides across
    datasets (a GC run and a 6B run would fingerprint identically and overwrite
    each other) — use the parent directory name for those."""
    p = os.path.abspath(str(path))
    b = os.path.basename(p)
    if b.lower() in ("canonical.csv", "data.csv"):
        return os.path.basename(os.path.dirname(p)) or b
    return b


def _cache_path(src: str) -> str:
    return src + ".cache.pkl"


def _write_cache(df: pd.DataFrame, src: str) -> None:
    """Best-effort parse cache. Measured on a 4.3M-row 1m CSV: parsing costs ~50s
    (17s read_csv + 32s strict %z to_datetime) on EVERY job; the pickle loads in a
    few seconds. Only written when the disk keeps comfortable headroom (cache is
    roughly the CSV's size), atomically via rename; any failure just means no
    cache — never a failed load."""
    pkl = _cache_path(src)
    tmp = pkl + ".tmp"
    try:
        st = os.statvfs(os.path.dirname(os.path.abspath(src)) or ".")
        free = st.f_bavail * st.f_frsize
        if free < 2 * os.path.getsize(src):
            return
        df.to_pickle(tmp)
        os.replace(tmp, pkl)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def load_window(csv_path: str, years: int = 3, cache: bool = True) -> pd.DataFrame:
    """Load only the most recent `years` of a dataset, via a small per-window
    pickle built ONCE from the full parse. Interactive jobs (backtest iteration,
    tuning, sweeps) use this so they never hold the 20-year frame in memory —
    measured on this stack: ~1M 1m bars runs smoothly on a small 2-core box
    (engine ~15s, ~350MB/worker) where the full 4-5M-bar frame costs 60-90s per
    pass plus real memory pressure. Full-history stays for explicit validation."""
    src = str(csv_path)
    wpkl = f"{src}.recent{years}y.pkl"
    if cache:
        try:
            if os.path.exists(wpkl) and os.path.getmtime(wpkl) >= os.path.getmtime(src):
                return pd.read_pickle(wpkl)
        except Exception:
            pass
    df = load(src, cache=cache)
    since = df["et"].iloc[-1] - pd.Timedelta(days=int(years) * 365)
    out = df[df["et"] >= since].reset_index(drop=True).copy()
    del df
    if cache:
        tmp = wpkl + ".tmp"
        try:
            out.to_pickle(tmp)
            os.replace(tmp, wpkl)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    return out


def load(csv_path: str, cache: bool = True) -> pd.DataFrame:
    src = str(csv_path)
    if cache:
        pkl = _cache_path(src)
        try:
            if os.path.exists(pkl) and os.path.getmtime(pkl) >= os.path.getmtime(src):
                return pd.read_pickle(pkl)
        except Exception:
            pass                      # unreadable cache -> reparse the CSV below

    df = pd.read_csv(src)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    et = _parse_datetimes(df["DateTime"])
    if et.dt.tz is None:
        et = et.dt.tz_localize("America/New_York")
    et = et.dt.tz_convert("America/New_York")

    df = df.copy()
    df["et"] = et
    df = _derive(df)
    if cache:
        _write_cache(df, src)
    return df


_OFFSET_RE = re.compile(r"(?:[+-]\d{2}:?\d{2}|Z)\s*$")


def _has_offset(col: pd.Series) -> bool:
    """Does this column carry UTC offsets, or is it wall-clock only?

    Decides whether utc=True is safe. It is not safe on naive input: pandas would
    read the wall clock as UTC and convert it to ET five hours off, silently
    shifting every bar into the wrong session."""
    for v in col.head(200):
        if isinstance(v, str) and v.strip():
            return bool(_OFFSET_RE.search(v.strip()))
    return False


def _parse_datetimes(col: pd.Series) -> pd.Series:
    """Parse the DateTime column, tolerating a DST boundary inside the file.

    Any multi-year ET export crosses one: December bars carry -05:00 and August
    bars -04:00. pandas raises "Mixed timezones detected" for that DURING
    parsing, before `errors="coerce"` can do anything, so the old flexible
    fallback was unreachable — a 2011-2026 file simply blew up. Parsing such a
    column to UTC and converting back to ET is correct and lossless, because the
    offset in each row already pins the instant.

    dayfirst matters too: without it "16-08-2026" is read as month 16 and
    coerced to NaT, which is how a naive export used to fail for no visible
    reason."""
    if _has_offset(col):
        attempts = (
            {"format": "%d-%m-%Y %H:%M:%S %z"},        # the normalizer's own output
            {"format": "%d-%m-%Y %H:%M:%S %z", "utc": True},   # ... across a DST boundary
            {"dayfirst": True},                        # other platforms' exports
            {"dayfirst": True, "utc": True},
            {"format": "ISO8601", "utc": True},        # year-first exports
        )
    else:
        # No offsets: the values are ET wall-clock and load() localizes them.
        # utc=True is deliberately absent — it would shift every bar.
        attempts = (
            {"format": "%d-%m-%Y %H:%M:%S"},
            {"dayfirst": True},
            {"format": "ISO8601"},
        )

    last_err = None
    for kw in attempts:
        try:
            et = pd.to_datetime(col, errors="coerce", **kw)
        except (ValueError, TypeError) as e:
            last_err = e
            continue
        if not et.isna().any():
            return et
    if last_err is not None:
        raise ValueError(f"DateTime column could not be parsed: {last_err}")
    n = int(pd.to_datetime(col, errors="coerce", dayfirst=True).isna().sum())
    raise ValueError(f"{n} DateTime values failed to parse")


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


def _as_ts(value, tz):
    ts = pd.Timestamp(value)
    return ts.tz_localize(tz) if ts.tz is None else ts.tz_convert(tz)


def slice_dates(df: pd.DataFrame, since=None, until=None) -> pd.DataFrame:
    """Keep rows with `since` <= et < `until` (either bound optional)."""
    et = df["et"]
    tz = et.dt.tz
    mask = pd.Series(True, index=df.index)
    if since is not None:
        mask &= et >= _as_ts(since, tz)
    if until is not None:
        mask &= et < _as_ts(until, tz)
    return df[mask].reset_index(drop=True)


def holdout_split(df: pd.DataFrame, days: int):
    """Split into (in_sample, out_of_sample, cutoff): OOS = the last `days` days
    of the data span. The generator searches on in-sample and verifies once on OOS.
    """
    et = df["et"]
    cutoff = et.iloc[-1] - pd.Timedelta(days=int(days))
    is_df = df[et <= cutoff].reset_index(drop=True)
    oos_df = df[et > cutoff].reset_index(drop=True)
    return is_df, oos_df, cutoff


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
