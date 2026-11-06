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


def test_survival_reports_the_fill_ratio_spread(frame):
    """The fill ratio is the mechanism under suspicion: a limit at 50% of the gap
    either gets touched or does not, and one tick decides it. Knowing how far
    that ratio drifts on tick noise alone tells you whether a fill-rate gap
    against Pine is data or engine."""
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    r = survival(frame, cfg, seeds=(1, 2, 3), prob=0.4)
    assert r["baseline_placed"] and r["baseline_placed"] >= r["baseline_trades"]
    assert 0 < r["baseline_fill_pct"] <= 100
    lo, hi = r["fill_pct_range"]
    assert 0 < lo <= hi <= 100
    assert all(run["fill_pct"] is not None for run in r["runs"])


def test_survival_runs_with_the_account_layer_on(frame):
    """It must measure the same engine stage 1 runs, overlay included — otherwise
    the number describes a configuration nobody is comparing against."""
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    assert cfg.is_pa
    r = survival(frame, cfg, seeds=(1,), prob=0.0)
    assert r["mean_survival_pct"] == 100.0
    assert r["runs"][0]["fill_pct"] == r["baseline_fill_pct"]


# --- the instrument must not measure itself -----------------------------------

def test_shift_mode_preserves_each_bar_range_exactly(frame):
    """The bias that invalidated the first fill-ratio band: jittering O/H/L/C
    independently and repairing with max/min widens bars and adds noise to every
    gap size. Noise measured against a NARROW band (FVG 10-22 ticks) pushes net
    mass out of it, so placements fall and the fill ratio rises for a reason that
    has nothing to do with the data."""
    out = jitter(frame, 0.25, prob=0.6, seed=5, mode="shift")
    base_rng = (frame["High"] - frame["Low"]).to_numpy()
    got_rng = (out["High"] - out["Low"]).to_numpy()
    assert np.allclose(base_rng, got_rng), "bar-range veranderde onder shift-modus"


def test_shift_mode_moves_whole_bars_by_one_tick(frame):
    out = jitter(frame, 0.25, prob=1.0, seed=6, mode="shift")
    steps = [(out[c].to_numpy() - frame[c].to_numpy()) for c in
             ("Open", "High", "Low", "Close")]
    for s in steps[1:]:
        assert np.allclose(s, steps[0]), "velden binnen een bar schoven verschillend"
    q = steps[0] / 0.25
    assert np.allclose(q, np.round(q)) and np.abs(q).max() <= 1.0 + 1e-9


def test_independent_mode_is_the_biased_one_and_stays_labelled(frame):
    """Kept for comparison, and its bias is a measured fact rather than a note."""
    wide = jitter(frame, 0.25, prob=0.35, seed=7, mode="independent")
    base = (frame["High"] - frame["Low"]).to_numpy().mean()
    assert (wide["High"] - wide["Low"]).to_numpy().mean() > base, (
        "independent-modus verbreedt bars niet meer — dan klopt de waarschuwing niet")
    assert "not neutral" in jitter.__doc__


def test_an_unknown_mode_is_refused(frame):
    with pytest.raises(ValueError, match="unknown jitter mode"):
        jitter(frame, 0.25, mode="whatever")


def test_shift_mode_keeps_the_placement_count_centred(frame):
    """If the instrument itself moves the number of placements, its fill-ratio
    band describes the instrument rather than the data — which is exactly what
    went wrong with the independent-jitter version.

    The bound is sample-size aware on purpose: this fixture yields only a handful
    of placements, and at n=9 a spread of 6-11 is ordinary counting noise. A flat
    percentage would either pass vacuously on large samples or fail on noise
    here, so the tolerance is a few standard errors of a count."""
    import math

    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    r = survival(frame, cfg, seeds=(1, 2, 3), prob=0.35, mode="shift")
    lo, hi = r["placed_range"]
    mid, base = (lo + hi) / 2, r["baseline_placed"]
    assert base, "geen plaatsingen — de test bewijst niets"
    tol = max(3.0 * math.sqrt(base), 0.05 * base)
    assert abs(mid - base) <= tol, (
        f"plaatsingen drijven weg: basis {base}, jitter {lo}-{hi}, "
        f"toegestaan +/-{tol:.1f}")


def test_survival_reports_the_trade_count_spread(frame):
    """The number that makes the trade-count gate readable: if a one-tick jitter
    on the instrument's own bars already moves the count by more than the gate's
    10%, a count difference within that spread is data, not an engine defect."""
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    r = survival(frame, cfg, seeds=(1, 2, 3), prob=0.35)
    lo, hi = r["trade_count_range"]
    assert 0 < lo <= hi
    assert r["trade_count_spread_pct"] is not None and r["trade_count_spread_pct"] >= 0
