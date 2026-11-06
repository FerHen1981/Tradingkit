"""End-to-end smoke for the trap-11 CLI — the Pijplijn portfolio runner's source.

Covers the multi-engine wiring (per-member load -> engine run -> daily P&L ->
correlation gate) and the two behaviours the gate must have: it refuses to conclude
below --min-days, and with enough days it emits a STAGE_JSON carrying the pairwise
matrix. Synthetic data, so no correlation value is asserted — only the gate logic
and shape.
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
    tmp = tmp_path_factory.mktemp("pf")
    rng = np.random.default_rng(23)
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
    f = tmp / "MES_pf.csv"
    raw.to_csv(f, index=False)
    return str(f)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch, dataset_csv):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "_dataset_path", lambda name: (dataset_csv, ""))


def _args(min_days, **over):
    base = dict(members="EL_MATADOR_MES_PROD_EOD:mes,EL_REY_MNQ_PROD_EOD:mnq",
                since="2025-01-02", until="2025-01-25", min_days=min_days,
                corr_hi=0.7, corr_lo=0.3, window_kind="validation")
    base.update(over)
    return types.SimpleNamespace(**base)


def _stage_json(capsys) -> dict:
    line = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("STAGE_JSON ")][-1]
    return json.loads(line[len("STAGE_JSON "):])


def test_below_min_days_refuses_to_claim(capsys):
    # a huge threshold no synthetic window can meet -> sufficiency gate fires
    cli.cmd_stage11(_args(min_days=9999))
    out = _stage_json(capsys)
    assert out["stage"] == 11
    assert out["status"] == "inconclusive"
    assert out["pass"] is False


def test_runs_and_emits_pairwise_matrix(capsys):
    cli.cmd_stage11(_args(min_days=1))
    out = _stage_json(capsys)
    assert out["stage"] == 11
    assert out["status"] in ("passed", "failed", "inconclusive")
    assert len(out["pairs"]) == 1                        # one pair for two engines
    p = out["pairs"][0]
    assert "corr" in p and "days_both_active" in p and "loss_overlap" in p


def test_single_member_is_rejected():
    with pytest.raises(SystemExit):
        cli.cmd_stage11(_args(min_days=1, members="EL_MATADOR_MES_PROD_EOD:mes"))
