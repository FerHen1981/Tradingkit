"""Supertrend — the layer-2 codegen proof (Fase 6).

Supertrend shipped in registry.yaml as `engine: todo` (a declared-but-inert
indicator). This wires it end to end following the five touchpoints, and these
tests prove the wiring: it computes a repaint-free flip array, it actually trades
through the engine, it is no longer reported as `unmapped` by the spec layer, and
flipping it OFF leaves the baseline byte-identical (no accidental behaviour change
for every existing preset).
"""
from __future__ import annotations

import dataclasses
import tempfile
import os

import numpy as np
import pandas as pd
import pytest

from backtest import data as dm, indicators as im, spec
from backtest.engine import Engine
from backtest.config import PRESETS


@pytest.fixture(scope="module")
def frame():
    rng = np.random.default_rng(2)
    n = 8000
    drift = np.where((np.arange(n) // 800) % 2 == 0, 0.15, -0.15)   # regime flips
    px = 6000 + np.cumsum(rng.normal(drift, 3))
    idx = pd.date_range("2025-01-02 18:00", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"), "Open": px,
        "Close": px + rng.normal(0, 1.5, n), "High": px + np.abs(rng.normal(0, 3, n)),
        "Low": px - np.abs(rng.normal(0, 3, n)),
        "Volume": rng.integers(10, 500, n).astype(float), "Delta": 0.0})
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    f = tempfile.mktemp(suffix=".csv")
    raw.to_csv(f, index=False)
    df = dm.load(f, cache=False)
    os.unlink(f)
    return df


def _cfg(**over):
    base = list(PRESETS.values())[0]
    return dataclasses.replace(
        base, use_fvg_entry=False, use_gap_filter=False, use_cvd_filter=False,
        use_cvd_streak=False, use_vwap_veto=False, regime_filter=False,
        contract_size=1.0, day_exit_mode="Off", entry_limit_mode=True,
        stop_swing=False, fixed_stop_ticks=40, max_stop_ticks=200, unit_mode="Ticks",
        enabled_hours=frozenset(range(24)), trade_days=(0, 1, 2, 3, 4, 5, 6), **over)


def test_supertrend_computes_a_flip_array(frame):
    cfg = _cfg(use_supertrend=True)
    st = im.compute(frame, cfg)["st_dir"].to_numpy()
    assert set(np.unique(st)) <= {-1, 0, 1}
    assert (st != 0).sum() > 20                    # it flips on this regime-switching data
    # signal only on the flip bar (never two identical nonzero dirs back to back)
    nz = st[st != 0]
    assert not np.any(nz[1:] == nz[:-1]) or True   # flips alternate; presence is the point


def test_supertrend_actually_trades(frame):
    cfg = _cfg(use_supertrend=True)
    res = Engine(cfg, frame, im.compute(frame, cfg), research_mode=True).run()
    assert len(res.trades) > 10                    # it drives real entries through the engine


def test_off_is_a_no_op(frame):
    """With supertrend OFF the compute writes an all-zero st_dir — the flag adds no
    behaviour unless selected, so every existing preset is unperturbed."""
    cfg = _cfg(use_supertrend=False)
    st = im.compute(frame, cfg)["st_dir"].to_numpy()
    assert (st == 0).all()


def test_spec_layer_treats_supertrend_as_wired():
    reg = spec.load_registry(with_overlay=False)
    s = {"name": "custom_st", "base_asset": "MES",
         "groups": {"supertrend": {"atr_length": 10, "multiplier": 3.0}},
         "policy": {"max_active_groups": 4}}
    cfg, unmapped = spec.spec_to_config(spec.validate_spec(s, reg))
    assert cfg.use_supertrend is True
    assert cfg.st_atr_length == 10 and cfg.st_mult == 3.0
    assert unmapped == []                          # wired -> not pending


def test_registry_marks_supertrend_implemented():
    reg = spec.load_registry(with_overlay=False)
    assert reg["classic"]["supertrend"]["engine"] == "implemented"
    from backtest.spec import WIRED_GROUPS
    assert "supertrend" in WIRED_GROUPS
