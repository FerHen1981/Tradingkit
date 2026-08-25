"""End-to-end smoke for the scorecard CLI — the Analysis view's data source.

Covers the wiring (dataset load -> engine run -> scorecard JSON) that the unit
tests in test_scorecard.py do not: that cmd_scorecard runs an engine on real
loaded bars and emits a SCORECARD_JSON line carrying the full card. Synthetic
data, so no numbers are asserted — only shape and that both postures run.
"""
from __future__ import annotations

import json
import types

import numpy as np
import pandas as pd
import pytest

from backtest.pipeline import cli


@pytest.fixture(scope="module")
def dataset_csv(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sc")
    rng = np.random.default_rng(11)
    n, sigma = 40_000, 4.0
    px = 6000 + np.cumsum(rng.normal(0.02, sigma, n))
    idx = pd.date_range("2025-01-02", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"),
        "Open": px, "Close": px + rng.normal(0, sigma * 0.7, n),
        "High": px + np.abs(rng.normal(0, sigma * 2, n)),
        "Low": px - np.abs(rng.normal(0, sigma * 2, n)),
        "Volume": rng.integers(50, 900, n).astype(float), "Delta": np.zeros(n)})
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    f = tmp / "MES_sc.csv"
    raw.to_csv(f, index=False)
    return str(f)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch, dataset_csv):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "_dataset_path", lambda name: (dataset_csv, "MES"))


def _args(raw=False):
    return types.SimpleNamespace(
        dataset="MES_sc", engine="EL_MATADOR_MES_PROD_EOD",
        since="2025-01-02", until="2025-01-25", raw=raw)


def _card(capsys) -> dict:
    line = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("SCORECARD_JSON ")][-1]
    return json.loads(line[len("SCORECARD_JSON "):])


def test_scorecard_deploy_posture_emits_full_card(capsys):
    cli.cmd_scorecard(_args(raw=False))
    card = _card(capsys)
    assert card["posture"] == "deploy"
    # the sections the Analysis tab renders must all be present
    for key in ("kpis", "equity_curve", "streaks", "best_trade", "worst_trade",
                "by_direction", "excursion", "hold_time_bars", "exit_reason_edge", "days"):
        assert key in card, f"missing {key}"


def test_scorecard_raw_posture_runs(capsys):
    cli.cmd_scorecard(_args(raw=True))
    card = _card(capsys)
    assert card["posture"] == "raw"
    assert "kpis" in card
