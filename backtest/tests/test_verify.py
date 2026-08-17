"""OOS verdict logic tests (pure — the overfit gate)."""
from backtest.verify import _verdict


def test_holds_out_of_sample():
    v = _verdict({"profit_factor": 1.4}, {"profit_factor": 1.25, "trades": 40},
                 min_trades=20, min_pf=1.05, retain=0.6)
    assert v["pass"] and v["retain"] == round(1.25 / 1.4, 2) and "holds" in v["reason"]


def test_edge_decayed():
    # OOS PF collapses relative to IS -> fails the retain ratio
    v = _verdict({"profit_factor": 1.8}, {"profit_factor": 1.0, "trades": 50},
                 min_trades=20, min_pf=1.05, retain=0.6)
    assert not v["pass"] and "decayed" in v["reason"]


def test_too_few_oos_trades():
    v = _verdict({"profit_factor": 1.4}, {"profit_factor": 1.5, "trades": 5},
                 min_trades=20, min_pf=1.05, retain=0.6)
    assert not v["pass"] and "few OOS trades" in v["reason"]


def test_oos_below_pf_floor():
    v = _verdict({"profit_factor": 1.4}, {"profit_factor": 0.95, "trades": 40},
                 min_trades=20, min_pf=1.05, retain=0.6)
    assert not v["pass"] and "< 1.05" in v["reason"]
