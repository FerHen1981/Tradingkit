"""Regime gate — the finetune tool: entries fire ONLY in the allowed regimes
(causal, no look-ahead). Empty filter = trade every regime (a no-op)."""
import numpy as np
import pandas as pd

from backtest.config import Config, contract
from backtest import indicators as ind_mod
from backtest.engine import Engine
from backtest.metrics import kpis


def _mkdf(n=6000, seed=5):
    rng = np.random.default_rng(seed)
    seg = np.concatenate([np.linspace(0, 80, n // 2),
                          80 + np.cumsum(rng.normal(0, 0.5, n - n // 2))])
    base = 100 + seg
    o = base + rng.normal(0, .2, n)
    c = base + rng.normal(0, .2, n)
    hi = np.maximum(o, c) + np.abs(rng.normal(0, .5, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, .5, n))
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1min", tz="America/New_York")
    df = pd.DataFrame({"Open": o, "High": hi, "Low": lo, "Close": c,
                       "Volume": rng.integers(50, 200, n).astype(float),
                       "Delta": rng.normal(0, 30, n)})
    df["et"] = idx
    df["mod"] = idx.hour * 60 + idx.minute
    df["weekday"] = idx.weekday
    df["new_session"] = (idx.hour == 9) & (idx.minute == 30)
    df["session_date"] = idx.date
    return df


def _cfg(**over):
    base = dict(name="mom", use_fvg_entry=False, use_momentum=True, momentum_body_atr=0.5,
               use_gap_filter=False, use_cvd_filter=False, use_vwap_veto=False,
               contract=contract("NQ"))
    base.update(over)
    return Config(**base)


def test_regime_ok_column_membership():
    df = _mkdf()
    # empty filter -> all True (no gate)
    ind = ind_mod.compute(df, _cfg())
    assert ind["regime_ok"].all()
    # a filter -> regime_ok is exactly membership of the causal per-bar tag
    allowed = {"Strong Bull Trend", "Controlled Bull Trend"}
    cfg = _cfg(regime_filter=frozenset(allowed))
    ind = ind_mod.compute(df, cfg)
    labels = ind_mod.classify_regime(df, cfg)["regime"]
    expected = np.array([lab in allowed for lab in labels], dtype=bool)
    assert np.array_equal(ind["regime_ok"].to_numpy(), expected)


def test_empty_filter_is_a_noop():
    df = _mkdf()
    a = Engine(_cfg(), df, ind_mod.compute(df, _cfg()), research_mode=True).run()
    # explicitly-empty filter must not change anything
    cfg = _cfg(regime_filter=frozenset())
    b = Engine(cfg, df, ind_mod.compute(df, cfg), research_mode=True).run()
    assert kpis(a).get("trades") == kpis(b).get("trades")
    assert kpis(a).get("trades", 0) > 0        # the fixture actually trades


def test_gate_only_trades_allowed_regimes_and_reduces_count():
    df = _mkdf()
    base = _cfg()
    res_all = Engine(base, df, ind_mod.compute(df, base), research_mode=True).run()
    n_all = kpis(res_all).get("trades", 0)
    assert n_all > 0

    allowed = {"Strong Bull Trend", "Controlled Bull Trend"}
    cfg = _cfg(regime_filter=frozenset(allowed))
    ind = ind_mod.compute(df, cfg)
    res = Engine(cfg, df, ind, research_mode=True).run()
    labels = ind_mod.classify_regime(df, cfg)["regime"]

    # every gated trade entered in an allowed regime (causal tag at entry bar)
    outside = [t.entry_bar for t in res.trades if labels[t.entry_bar] not in allowed]
    assert outside == []
    # gating can only remove trades, never add
    assert kpis(res).get("trades", 0) <= n_all
