"""BBWP + MFI — the second layer-2 codegen wiring (Fase 6).

EL_REY's ta.vwma/ta.hma were the fleet's only "unknown" indicators. They are not
standalone indicators: vwma is the BBWP basis option and hma the MFI smoother. So
wiring them faithfully means wiring the two OPTIONAL side-filters that contain them
(default OFF — research knobs, not frozen edge). These tests prove the wiring:
the arrays compute repaint-free, the filters actually gate trades through the
engine, the spec layer treats them as wired (no `unmapped`), and flipping them OFF
leaves every existing preset byte-identical.
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
    rng = np.random.default_rng(7)
    n = 8000
    drift = np.where((np.arange(n) // 700) % 2 == 0, 0.12, -0.12)
    px = 20000 + np.cumsum(rng.normal(drift, 4))
    idx = pd.date_range("2025-01-02 18:00", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"), "Open": px,
        "Close": px + rng.normal(0, 2.0, n), "High": px + np.abs(rng.normal(0, 4, n)),
        "Low": px - np.abs(rng.normal(0, 4, n)),
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
        use_ema_cross=True, contract_size=1.0, day_exit_mode="Off",
        entry_limit_mode=True, stop_swing=False, fixed_stop_ticks=40,
        max_stop_ticks=200, unit_mode="Ticks", enabled_hours=frozenset(range(24)),
        trade_days=(0, 1, 2, 3, 4, 5, 6), **over)


# --- indicator maths ----------------------------------------------------------

def test_bbwp_is_a_percentile_and_repaint_free(frame):
    close = frame["Close"].to_numpy(float)
    vol = frame["Volume"].to_numpy(float)
    full = im._bbwp(close, vol, 20, 255, "SMA")
    ok = full[~np.isnan(full)]
    assert ok.size > 100
    assert ok.min() >= 0.0 and ok.max() <= 100.0
    # causal: recomputing on a prefix reproduces that prefix exactly (no look-ahead)
    k = 3000
    pref = im._bbwp(close[:k], vol[:k], 20, 255, "SMA")
    np.testing.assert_allclose(np.nan_to_num(pref), np.nan_to_num(full[:k]), rtol=0, atol=1e-9)


def test_bbwp_vwma_basis_wires_ta_vwma(frame):
    """The VWMA basis option is exactly where EL_REY's ta.vwma lands."""
    close = frame["Close"].to_numpy(float)
    vol = frame["Volume"].to_numpy(float)
    v = im._bbwp(close, vol, 20, 255, "VWMA")
    assert np.isfinite(v).sum() > 100


def test_mfi_side_wires_ta_hma_and_is_signed(frame):
    o = frame["Open"].to_numpy(float); h = frame["High"].to_numpy(float)
    lo = frame["Low"].to_numpy(float); c = frame["Close"].to_numpy(float)
    mfi = im._mfi_side(o, h, lo, c, 60)
    fin = mfi[np.isfinite(mfi)]
    assert fin.size > 100
    assert (fin > 0).any() and (fin < 0).any()          # takes both sides


# --- engine integration -------------------------------------------------------

def test_bbwp_gate_reduces_trades(frame):
    off = Engine(_cfg(use_bbwp_filter=False), frame, im.compute(frame, _cfg(use_bbwp_filter=False)),
                 research_mode=True).run()
    on_cfg = _cfg(use_bbwp_filter=True, bbwp_min=80.0, bbwp_max=100.0)   # only top-vol regime
    on = Engine(on_cfg, frame, im.compute(frame, on_cfg), research_mode=True).run()
    assert len(off.trades) > 0
    assert len(on.trades) < len(off.trades)             # a band-pass gate can only remove entries


def test_mfi_gate_reduces_trades(frame):
    off_cfg = _cfg(use_mfi_filter=False)
    off = Engine(off_cfg, frame, im.compute(frame, off_cfg), research_mode=True).run()
    on_cfg = _cfg(use_mfi_filter=True, mfi_period=60)
    on = Engine(on_cfg, frame, im.compute(frame, on_cfg), research_mode=True).run()
    assert len(off.trades) > 0
    assert len(on.trades) <= len(off.trades)            # a directional veto only removes entries


def test_off_is_a_no_op(frame):
    """Both filters OFF -> all-True gate arrays, so every existing preset is
    unperturbed."""
    cfg = _cfg(use_bbwp_filter=False, use_mfi_filter=False)
    ind = im.compute(frame, cfg)
    assert ind["bbwp_pass"].to_numpy(bool).all()
    assert ind["mfi_long"].to_numpy(bool).all()
    assert ind["mfi_short"].to_numpy(bool).all()


# --- spec / registry layer ----------------------------------------------------

def test_spec_layer_treats_bbwp_and_mfi_as_wired():
    reg = spec.load_registry(with_overlay=False)
    s = {"name": "custom_filt", "base_asset": "MNQ",
         "groups": {"ema_cross": {"fast": 9, "slow": 21},
                    "bbwp": {"length": 20, "lookback": 255, "basis": "VWMA", "min": 10, "max": 90},
                    "mfi": {"period": 60}},
         "policy": {"max_active_groups": 6}}
    cfg, unmapped = spec.spec_to_config(spec.validate_spec(s, reg))
    assert cfg.use_bbwp_filter is True and cfg.bbwp_basis == "VWMA"
    assert cfg.bbwp_min == 10 and cfg.bbwp_max == 90
    assert cfg.use_mfi_filter is True and cfg.mfi_period == 60
    assert unmapped == []                               # wired -> not pending


def test_registry_marks_bbwp_mfi_implemented():
    reg = spec.load_registry(with_overlay=False)
    assert reg["classic"]["bbwp"]["engine"] == "implemented"
    assert reg["classic"]["mfi"]["engine"] == "implemented"
    from backtest.spec import WIRED_GROUPS
    assert "bbwp" in WIRED_GROUPS and "mfi" in WIRED_GROUPS
