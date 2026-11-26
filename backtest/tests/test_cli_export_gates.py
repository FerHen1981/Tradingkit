"""End-to-end smoke test for the two export-comparison gates (trap 1 & trap 10).

The trap-10 logic has its own unit tests (test_tvvalidate.py); this covers the
CLI wiring and the shared `_prepare_export_run` front-matter they both lean on —
the layer no unit test touches, and where the ds_sym unpack bug hid. It does not
assert parity numbers (synthetic data never reproduces the export); it asserts
both commands run to a recorded STAGE_JSON verdict without raising.
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
    tmp = tmp_path_factory.mktemp("cli")
    rng = np.random.default_rng(7)
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
    f = tmp / "MES_smoke.csv"
    raw.to_csv(f, index=False)
    return str(f)


_EXPORT = "validation/exports/MATADOR_MES_PROD_EOD_MES1m_2026-08-23.xlsx"


def _args(dataset_csv):
    # explicit window so the export's own (2025+) range is not adopted and the
    # synthetic bars are not trimmed to empty
    return types.SimpleNamespace(
        dataset="MES_smoke", engine="EL_MATADOR_MES_PROD_EOD", export=_EXPORT,
        since="2025-01-02", until="2025-01-25", as_tested=True, diff=False)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch, dataset_csv):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))          # state/artifacts -> tmp
    monkeypatch.setattr(cli, "_dataset_path", lambda name: (dataset_csv, "MES"))
    monkeypatch.setattr(cli, "_resolve_export", lambda name: _EXPORT)


def _last_stage_json(capsys) -> dict:
    line = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("STAGE_JSON ")][-1]
    return json.loads(line[len("STAGE_JSON "):])


def test_stage1_runs_end_to_end(dataset_csv, capsys):
    cli.cmd_stage1(_args(dataset_csv))
    j = _last_stage_json(capsys)
    assert j["stage"] == 1 and "comparison" in j


def test_stage10_runs_end_to_end_and_records_all_dimensions(dataset_csv, capsys):
    cli.cmd_stage10(_args(dataset_csv))
    j = _last_stage_json(capsys)
    assert j["stage"] == 10
    # the four gate dimensions must all be present and reported
    assert set(j["dimensions"]) == {"kpi", "timing", "exit_reasons", "excursion"}
    assert j["status"] in ("passed", "data_parity", "failed")


def test_stage10_records_state_under_tv_validation(dataset_csv):
    from backtest.pipeline import state
    cli.cmd_stage10(_args(dataset_csv))
    rec = state.load().get("EL_MATADOR_MES_PROD_EOD", {}).get("tv_validation")
    assert rec and rec["status"] in ("passed", "data_parity", "failed")
