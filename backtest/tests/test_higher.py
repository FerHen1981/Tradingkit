"""Stages 3-9: from a validated mechanic to a funded engine.

These test the MEASUREMENT and the VERDICT walls, not specific numbers (which
are data-dependent). The frozen config is never optimised here — each stage only
asks whether the frozen mechanic survives its own question.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest import data as dm
from backtest.pipeline import fleet, higher


@pytest.fixture(scope="module")
def frame(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("h")
    rng = np.random.default_rng(5)
    n, sigma = 120_000, 4.0
    px = 6000 + np.cumsum(rng.normal(0.02, sigma, n))     # gentle up-drift
    idx = pd.date_range("2023-08-24", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"),
        "Open": px, "Close": px + rng.normal(0, sigma * 0.7, n),
        "High": px + np.abs(rng.normal(0, sigma * 2, n)),
        "Low": px - np.abs(rng.normal(0, sigma * 2, n)),
        "Volume": rng.integers(50, 900, n).astype(float), "Delta": np.zeros(n)})
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    f = tmp / "d.csv"
    raw.to_csv(f, index=False)
    return dm.load(str(f), cache=False)


@pytest.fixture(scope="module")
def cfg():
    return fleet.engine_config("EL_MATADOR_MES_PROD_EOD")


VALID = {"passed", "inconclusive", "failed"}


@pytest.mark.parametrize("n", [3, 4, 5, 6, 7, 8, 9])
def test_every_stage_returns_a_status_and_verdict(frame, cfg, n):
    rep = getattr(higher, f"stage{n}")(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    assert rep["status"] in VALID
    assert rep["verdict"] and isinstance(rep["verdict"], str)


def test_stage3_reports_in_out_per_regime_and_flags_concentration(frame, cfg):
    rep = higher.stage3(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    for reg, r in rep["by_regime"].items():
        assert "in" in r and "out" in r and "share_pct" in r
    if rep["best_share_pct"] and rep["best_share_pct"] > 70 and len(rep["by_regime"]) > 1:
        assert rep["status"] == "inconclusive"


def test_stage4_neighbourhood_actually_perturbs_parameters(frame, cfg):
    rep = higher.stage4(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    assert rep["neighbourhood"], "geen parameterburen gemeten"
    params = {x["param"] for x in rep["neighbourhood"]}
    assert {"fixed_stop_ticks", "r_multiple", "gap_min_ticks", "gap_max_ticks"} <= params
    # a passed plateau must actually have most neighbours profitable
    if rep["status"] == "passed":
        prof = sum(1 for x in rep["neighbourhood"] if x["pf"] > 1.0)
        assert prof >= 0.7 * len(rep["neighbourhood"])


def test_stage5_stop_fits_check_uses_real_contract_math(frame, cfg):
    rep = higher.stage5(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    ct = cfg.contract
    expect = float(cfg.max_stop_ticks) * ct.mintick * ct.pointvalue * cfg.contract_size
    assert abs(rep["stop_usd_total"] - expect) < 1e-6
    assert rep["fits_under_dll"] == (rep["worst_case_usd"] < rep["dll"] or rep["dll"] <= 0)


def test_stage5_pf_is_size_invariant_for_a_real_engine(frame, cfg):
    """The per-contract edge may not depend on how many contracts you trade."""
    rep = higher.stage5(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    if rep["pf_1"] and rep["pf_n"]:
        assert abs(rep["pf_1"] - rep["pf_n"]) / rep["pf_1"] <= 0.15


def test_stage6_is_inconclusive_when_neither_variant_banks(frame, cfg):
    rep = higher.stage6(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    b0 = rep["without_day_mgmt"]["banked_per_account_day"]
    b1 = rep["with_day_mgmt"]["banked_per_account_day"]
    if b0 <= 0 and b1 <= 0:
        assert rep["status"] == "inconclusive"


def test_stage7_runs_both_drawdown_models(frame, cfg):
    rep = higher.stage7(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    assert "eod" in rep and "intraday" in rep
    assert rep["intended_model"] in ("EOD", "Intraday")
    assert "conservatief" in rep["note"]


def test_stage8_reports_the_objective_metric(frame, cfg):
    rep = higher.stage8(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    assert "banked_per_account_day" in rep and "dll_hits" in rep
    assert rep["status"] == ("passed" if (rep["banked_per_account_day"] > 0
                                          and not rep["breached"]) else rep["status"])


def test_stage9_neutralises_the_hour_and_day_mask(frame, cfg):
    """The cherry-pick guard must actually widen the gates, or it proves nothing."""
    rep = higher.stage9(cfg, frame, "EL_MATADOR_MES_PROD_EOD")
    assert "with_filter" in rep and "without_filter" in rep
    if rep["status"] == "failed":
        assert not (rep["without_filter"]["expectancy"] > 0
                    and rep["without_filter"]["pf"] > 1.0)
