"""The tick-sensitivity experiment behind the twin-substitution question.

fleet.TWIN lets a mini's history stand in for its micro. That is sound for the
CONTRACT SPEC (same tick size, point value scales) but says nothing about the
BARS: ES and MES are separate order books. This module measures whether the
strategy can tell the difference — and these tests check the measurement itself
is honest, because a jitter that changes nothing would "prove" robustness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.pipeline import fleet
from backtest.pipeline.sensitivity import jitter, survival, verdict


@pytest.fixture
def frame(tmp_path):
    from backtest import data as dm
    rng = np.random.default_rng(11)
    n, sigma = 40_000, 4.0
    px = 6000 + np.cumsum(rng.normal(0, sigma, n))
    idx = pd.date_range("2025-09-02 00:00", periods=n, freq="1min",
                        tz="America/New_York")
    raw = pd.DataFrame({
        "Open": px, "Close": px + rng.normal(0, sigma * 0.7, n),
        "High": px + np.abs(rng.normal(0, sigma * 2, n)),
        "Low": px - np.abs(rng.normal(0, sigma * 2, n)),
        "Volume": rng.integers(50, 900, n).astype(float), "Delta": np.zeros(n)})
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    raw.insert(0, "DateTime", idx.strftime("%d-%m-%Y %H:%M:%S %z"))
    csv = tmp_path / "s.csv"
    raw.to_csv(csv, index=False)
    return dm.load(str(csv), cache=False)


def test_jitter_moves_prices_by_whole_ticks_only(frame):
    out = jitter(frame, 0.25, prob=1.0, seed=1)
    for col in ("Open", "Close"):
        step = (out[col].to_numpy() - frame[col].to_numpy()) / 0.25
        assert np.allclose(step, np.round(step)), f"{col} verschoof geen heel aantal ticks"
        assert np.abs(step).max() <= 1.0 + 1e-9, f"{col} verschoof meer dan een tick"


def test_jitter_keeps_bars_valid(frame):
    out = jitter(frame, 0.25, prob=0.8, seed=2)
    hi, lo = out["High"].to_numpy(), out["Low"].to_numpy()
    for col in ("Open", "Close"):
        v = out[col].to_numpy()
        assert (hi >= v - 1e-9).all() and (lo <= v + 1e-9).all(), f"{col} valt buiten High/Low"
    assert (hi >= lo - 1e-9).all()


def test_jitter_actually_changes_something(frame):
    """A no-op jitter would make every strategy look robust."""
    out = jitter(frame, 0.25, prob=0.5, seed=3)
    changed = (out["Close"].to_numpy() != frame["Close"].to_numpy()).mean()
    assert 0.2 < changed < 0.8, f"maar {changed:.0%} van de closes veranderde"


def test_zero_probability_is_a_no_op(frame):
    out = jitter(frame, 0.25, prob=0.0, seed=4)
    for col in ("Open", "High", "Low", "Close"):
        assert np.allclose(out[col].to_numpy(), frame[col].to_numpy()), col


def test_survival_of_an_unperturbed_series_is_total(frame):
    """The control: with no jitter the trade list must reproduce exactly, or the
    measurement is picking up nondeterminism rather than tick sensitivity."""
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    r = survival(frame, cfg, seeds=(1,), prob=0.0)
    assert r["baseline_trades"] > 0, "geen trades — de meting bewijst niets"
    assert r["mean_survival_pct"] == 100.0


def test_survival_drops_once_prices_move(frame):
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    r = survival(frame, cfg, seeds=(1, 2), prob=0.5)
    assert r["baseline_trades"] > 0
    assert r["mean_survival_pct"] < 100.0, "een tick verschil veranderde niets — verdacht"
    assert 0.0 <= r["min_survival_pct"] <= r["mean_survival_pct"]


@pytest.mark.parametrize("pct,expect", [(95.0, "robuust"), (80.0, "gevoelig"),
                                        (40.0, "TICK-KRITISCH")])
def test_verdict_wording_tracks_the_number(pct, expect):
    assert expect in verdict({"mean_survival_pct": pct})
