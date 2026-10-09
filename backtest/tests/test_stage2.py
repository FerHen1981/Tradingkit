"""Stage 2 — structural edge on 1 contract, no account overlay.

Stage 1 proves we reproduce Pine; stage 2 asks whether the thing we reproduce
makes money on its own before account mechanics. These tests fix the contract:
one contract, no day caps, no PA sizing, costs on — and a verdict that does not
call a one-year fluke a structural edge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _csv(tmp_path, n=80_000, sigma=4.0, drift=0.0, seed=1):
    rng = np.random.default_rng(seed)
    px = 6000 + np.cumsum(rng.normal(drift, sigma, n))
    idx = pd.date_range("2024-01-02", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"),
        "Open": px, "Close": px + rng.normal(0, sigma * 0.7, n),
        "High": px + np.abs(rng.normal(0, sigma * 2, n)),
        "Low": px - np.abs(rng.normal(0, sigma * 2, n)),
        "Volume": rng.integers(50, 900, n).astype(float), "Delta": np.zeros(n)})
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    f = tmp_path / "d.csv"
    raw.to_csv(f, index=False)
    return str(f)


def _run(tmp_path, monkeypatch, dataset_csv):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    import types

    from backtest.pipeline import cli
    monkeypatch.setattr(cli, "_dataset_path", lambda name: (dataset_csv, "MES"))
    args = types.SimpleNamespace(dataset="d", engine="EL_MATADOR_MES_PROD_EOD",
                                 since=None, until=None)
    cli.cmd_stage2(args)
    # read what it recorded
    from backtest.pipeline import state
    return {v["key"]: v for v in state.engine_view("EL_MATADOR_MES_PROD_EOD")}["structural_edge"]


def test_stage2_runs_one_contract_without_account_overlay(tmp_path, monkeypatch, capsys):
    rec = _run(tmp_path, monkeypatch, _csv(tmp_path))
    out = capsys.readouterr().out
    assert "1 contract" in out and "geen dagcaps" in out
    assert "per kalenderjaar" in out
    assert rec["status"] in ("passed", "inconclusive", "failed")


def test_stage2_warns_when_stage1_is_open(tmp_path, monkeypatch, capsys):
    """Ground rule 1 is advisory here, but must be visible."""
    _run(tmp_path, monkeypatch, _csv(tmp_path))
    assert "grondregel 1" in capsys.readouterr().out


def test_stage2_records_a_status_and_artifact(tmp_path, monkeypatch):
    rec = _run(tmp_path, monkeypatch, _csv(tmp_path))
    assert rec["artifact"] and rec["summary"]


def test_stage2_verdict_matches_the_numbers(tmp_path, monkeypatch, capsys):
    """A passed verdict must actually have positive expectancy and PF>1 — the
    label may not drift from the measurement."""
    import json
    rec = _run(tmp_path, monkeypatch, _csv(tmp_path))
    art = json.loads(open(rec["artifact"]).read())
    k = art["kpis"]
    if art["status"] == "passed":
        assert k["expectancy"] > 0 and k["profit_factor"] > 1.0
    if art["status"] == "failed" and k.get("trades"):
        assert not (k["expectancy"] > 0 and k["profit_factor"] > 1.0) or \
               art["verdict"].startswith("ZWAK") is False


def test_stage2_needs_positive_years_not_just_positive_total(tmp_path, monkeypatch):
    """The robustness half of the verdict: an edge carried by one year is
    'inconclusive', not 'passed'. Verified against the recorded by_year data."""
    import json
    rec = _run(tmp_path, monkeypatch, _csv(tmp_path))
    art = json.loads(open(rec["artifact"]).read())
    years = art["by_year"]
    pos = sum(1 for r in years.values() if r["expectancy"] > 0)
    if art["status"] == "passed":
        assert pos >= max(1, round(0.6 * len(years)))
