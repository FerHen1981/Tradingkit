"""Tests for the dataset gate (tools/validate_dataset.py), covering the three
D-153 defects and the CVD-filter-off nuance. All on synthetic data — the 3y MGC
acceptance (0 duplicates / 6 gaps / hour-17-only-empty) needs Ferry's file, which
is hosted as a Release asset (D-141) and is not in the repo.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("validate_dataset", REPO / "tools" / "validate_dataset.py")
vd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vd)


# --- defect 1: dayfirst ------------------------------------------------------
def test_to_datetime_is_dayfirst():
    # "05-03-2026" is 5 March, not 3 May. Without dayfirst the gate swapped
    # day/month on 36.7% of Ferry's file.
    ts = vd._to_datetime(pd.Series(["05-03-2026 10:00:00", "12-01-2026 09:30:00"]))
    assert ts.iloc[0].month == 3 and ts.iloc[0].day == 5
    assert ts.iloc[1].month == 1 and ts.iloc[1].day == 12


def test_to_datetime_dayfirst_across_offsets():
    ts = vd._to_datetime(pd.Series(["05-03-2026 10:00:00 -05:00",
                                    "05-08-2026 10:00:00 -04:00"]))
    assert ts.iloc[0].month == 3 and ts.iloc[1].month == 8


# --- defect 3: Volume(from bar) + all-zero volume ----------------------------
def test_bar_volume_used_when_plain_volume_is_zero():
    df = pd.DataFrame({"DateTime": ["01-02-2026 10:00:00"], "Open": [1], "High": [1],
                       "Low": [1], "Close": [1], "Volume": [0], "Volume(from bar)": [250]})
    rep = vd.Report()
    out = vd.normalise_columns(df, rep)
    assert out["Volume"].iloc[0] == 250
    assert any("Volume taken from" in n for n in rep.notes)


def test_all_zero_volume_is_rejected():
    et = pd.date_range("2026-02-02 10:00", periods=3, freq="min", tz="America/New_York")
    df = pd.DataFrame({"et": et, "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                       "Volume": [0, 0, 0]})
    rep = vd.Report()
    vd.check_structure(df, rep)
    assert any("Volume is zero on every bar" in e for e in rep.errors)


# --- defect 2: the maintenance-break hour must not move across months --------
def _hourly_year(break_hour_by_month: dict[int, int]) -> pd.DataFrame:
    """One bar per ET hour per day for a year, OMITTING the given break hour per
    month — so a constant break_hour is a correct clock and a varying one is not."""
    rows = []
    d = dt.date(2025, 1, 1)
    while d.year == 2025:
        bh = break_hour_by_month[d.month]
        for h in range(24):
            if h == bh:
                continue
            rows.append(pd.Timestamp(d.year, d.month, d.day, h, 0))
        d += dt.timedelta(days=1)
    et = pd.DatetimeIndex(rows).tz_localize("America/New_York",
                                            ambiguous="NaT", nonexistent="shift_forward")
    df = pd.DataFrame({"et": et}).dropna(subset=["et"]).sort_values("et").reset_index(drop=True)
    return df


def test_shifting_break_hour_is_rejected():
    # summer months empty at 17, winter months empty at 18 -> clock ignores DST.
    bymonth = {m: (18 if m in (1, 2, 11, 12) else 17) for m in range(1, 13)}
    df = _hourly_year(bymonth)
    rep = vd.Report()
    vd.check_clock(df, rep)
    assert any("maintenance-break hour shifts" in e for e in rep.errors)


def test_constant_break_hour_passes():
    df = _hourly_year({m: 17 for m in range(1, 13)})
    rep = vd.Report()
    vd.check_clock(df, rep)
    assert not rep.errors


def test_constant_offset_column_over_dst_is_rejected():
    et = pd.date_range("2025-01-01", "2025-09-01", freq="D", tz="America/New_York")
    df = pd.DataFrame({"et": et, "UTC": "-04:00"})
    rep = vd.Report()
    vd.check_clock(df, rep)
    assert any("CONSTANT UTC offset" in e for e in rep.errors)


# --- the source-clock normalisation ------------------------------------------
def test_source_clock_normalisation_fixes_the_winter_hour():
    # A feed stamping a fixed -04:00: a winter 18:00 stamp is really 17:00 ET.
    df = pd.DataFrame({"DateTime": ["05-01-2026 18:00:00"],  # 5 Jan, winter
                       "Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0],
                       "Volume": [10]})
    rep = vd.Report()
    out = vd.parse_time(df, rep, source_clock="Etc/GMT+4")
    assert out is not None
    assert out["et"].iloc[0].hour == 17        # 18:00 @ -04:00 -> 17:00 EST
    # without the normalisation it would be read as ET wall clock (18:00)
    rep2 = vd.Report()
    naive = vd.parse_time(df.copy(), rep2, source_clock=None)
    assert naive["et"].iloc[0].hour == 18


# --- end-to-end: the CVD-filter-off nuance -----------------------------------
def _write_csv(tmp_path, with_delta: bool) -> Path:
    # a tiny but internally consistent 1-minute file, no order flow
    rows = []
    t = dt.datetime(2026, 2, 2, 10, 0)
    for i in range(5):
        rows.append((t.strftime("%d-%m-%Y %H:%M:%S"), 100, 100.5, 99.5, 100, 250))
        t += dt.timedelta(minutes=1)
    cols = "DateTime,Open,High,Low,Close,Volume"
    body = "\n".join(",".join(str(x) for x in r) for r in rows)
    p = tmp_path / "mini.csv"
    p.write_text(cols + "\n" + body + "\n")
    return p


def _run(path: Path, *extra) -> int:
    return subprocess.run([sys.executable, str(REPO / "tools" / "validate_dataset.py"),
                           str(path), "--symbol", "MGC", *extra],
                          capture_output=True, text=True).returncode


def test_no_delta_rejects_by_default(tmp_path):
    assert _run(_write_csv(tmp_path, with_delta=False)) == 1


def test_no_delta_passes_when_filter_is_off(tmp_path):
    assert _run(_write_csv(tmp_path, with_delta=False), "--no-delta-filter") == 0
