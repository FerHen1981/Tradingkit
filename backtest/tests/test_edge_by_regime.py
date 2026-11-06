"""Per-regime edge attribution — the unbiased discovery. Each trade is tagged by
the OBJECTIVE regime at its entry bar (causal, no look-ahead)."""
import numpy as np
import pandas as pd

from backtest.config import Config
from backtest.engine import Trade, Result
from backtest.indicators import classify_regime
from backtest.metrics import edge_by_regime


def _res(trades):
    r = Result(cfg_name="t")
    r.trades = trades
    return r


def _t(entry_bar, net):
    return Trade(dir=1, qty=1, entry_bar=entry_bar,
                 entry_time=pd.Timestamp("2024-01-02"), entry_px=100.0, net=net)


def test_trades_bucketed_by_entry_bar_regime():
    labels = np.array(["Strong Bull Trend"] * 5 + ["Low-Volatility Range"] * 5, dtype=object)
    res = _res([_t(0, 100), _t(1, 50), _t(2, -30),          # bull bucket
               _t(7, -40), _t(8, -60)])                      # range bucket
    edge = edge_by_regime(res, labels)
    assert edge["Strong Bull Trend"]["trades"] == 3
    assert edge["Strong Bull Trend"]["net"] == 120.0
    assert edge["Low-Volatility Range"]["trades"] == 2
    assert edge["Low-Volatility Range"]["net"] == -100.0
    # profit factor: bull 150/30 = 5.0
    assert edge["Strong Bull Trend"]["profit_factor"] == 5.0


def test_counts_sum_to_total_and_out_of_range_is_unknown():
    labels = np.array(["Compression"] * 3, dtype=object)
    res = _res([_t(0, 10), _t(2, -5), _t(99, 7)])            # entry_bar 99 is out of range
    edge = edge_by_regime(res, labels)
    assert edge["Compression"]["trades"] == 2
    assert edge["Unknown"]["trades"] == 1
    assert sum(m["trades"] for m in edge.values()) == 3


def test_attribution_uses_causal_labels_no_lookahead():
    # The regime label a trade is attributed to must be identical whether we
    # classify on the prefix (data up to entry) or the full history — proving the
    # attribution carries no look-ahead.
    cfg = Config(name="t")
    rng = np.random.default_rng(0)
    n = 1200
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({"High": base + 1, "Low": base - 1, "Close": base})
    full = classify_regime(df, cfg)["regime"]
    entry = 900
    prefix = classify_regime(df.iloc[:entry + 1].copy(), cfg)["regime"]
    # a trade entered at bar `entry` gets the same regime tag either way
    assert full[entry] == prefix[entry]
