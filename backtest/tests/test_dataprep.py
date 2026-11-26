"""Dataset prep — aggregate (resample-to-a-stored-dataset) and audit.

The load-bearing property is the round-trip: an aggregated dataset must be
readable straight back by data.load with its dates intact. A DateTime written in
ISO YYYY-MM-DD would be mis-parsed by the day-first loader and smear the series
across months while keeping the row count right — a silent corruption — so these
tests assert the SPAN and the aggregation math, not just the row count.
"""
from __future__ import annotations

import json
import types

import numpy as np
import pandas as pd
import pytest

from backtest import data as dm
from backtest.lab import dataprep
from backtest.lab.datasets import write_catalog
from backtest.lab.paths import datasets_dir


@pytest.fixture
def one_min(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    d = datasets_dir() / "SYN"
    d.mkdir(parents=True)
    rng = np.random.default_rng(4)
    n = 6000
    px = 6000 + np.cumsum(rng.normal(0, 3, n))
    idx = pd.date_range("2025-01-02 18:00", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"),
        "Open": px, "Close": px + rng.normal(0, 2, n),
        "High": px + np.abs(rng.normal(0, 4, n)), "Low": px - np.abs(rng.normal(0, 4, n)),
        "Volume": rng.integers(10, 500, n).astype(float),
        "Delta": rng.integers(-50, 50, n).astype(float)})
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    raw.to_csv(d / "canonical.csv", index=False)
    write_catalog(d / "canonical.csv", symbol="MES", timeframe="1m")
    return "SYN"


def _agg(dataset, tf, name=None, overwrite=False):
    dataprep.cmd_aggregate(types.SimpleNamespace(
        dataset=dataset, tf=tf, name=name, overwrite=overwrite))


def test_aggregate_round_trips_with_dates_intact(one_min):
    src = dm.load(str(datasets_dir() / one_min / "canonical.csv"))
    _agg(one_min, "5m")
    got = dm.load(str(datasets_dir() / f"{one_min}_5m" / "canonical.csv"))
    # 6000 1-min bars -> 1200 5-min bars
    assert len(got) == 1200
    # the span must be preserved (this is what an ISO/day-first mixup breaks)
    assert got["et"].iloc[0] == src["et"].iloc[0]
    assert got["et"].iloc[-1] == src["et"].iloc[-1] - pd.Timedelta(minutes=4)


def test_aggregate_ohlcv_math(one_min):
    src = dm.load(str(datasets_dir() / one_min / "canonical.csv"))
    _agg(one_min, "5m")
    got = dm.load(str(datasets_dir() / f"{one_min}_5m" / "canonical.csv"))
    assert got["Open"].iloc[0] == src["Open"].iloc[0]
    assert np.isclose(got["High"].iloc[0], src["High"].iloc[:5].max())
    assert np.isclose(got["Low"].iloc[0], src["Low"].iloc[:5].min())
    assert np.isclose(got["Volume"].iloc[0], src["Volume"].iloc[:5].sum())
    assert np.isclose(got["Delta"].iloc[0], src["Delta"].iloc[:5].sum())


def test_aggregate_writes_manifest_with_the_real_timeframe(one_min):
    _agg(one_min, "15m")
    man = json.loads((datasets_dir() / f"{one_min}_15m" / "manifest.json").read_text())
    assert man["timeframe"] == "15m" and man["symbol"] == "MES"
    assert man["rows"] == 400          # 6000 / 15


def test_aggregate_refuses_to_clobber_without_overwrite(one_min):
    _agg(one_min, "5m")
    with pytest.raises(SystemExit):
        _agg(one_min, "5m")
    _agg(one_min, "5m", overwrite=True)      # explicit overwrite is allowed


def test_aggregate_rejects_1m(one_min):
    with pytest.raises(SystemExit):
        _agg(one_min, "1m")


def test_audit_runs_on_an_aggregated_dataset(one_min, capsys):
    _agg(one_min, "5m")
    dataprep.cmd_audit(types.SimpleNamespace(dataset=f"{one_min}_5m"))
    line = [l for l in capsys.readouterr().out.splitlines()
            if l.startswith("AUDIT_JSON ")][-1]
    rep = json.loads(line[len("AUDIT_JSON "):])
    assert rep["bars"] == 1200 and rep["symbol"] == "MES"
    assert rep["bar_interval"] == "0 days 00:05:00"
