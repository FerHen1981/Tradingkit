"""Setup-score tests — a prior/display (framework §8), never a gate."""
from backtest.config import PRESETS
from backtest.scoring import score_strategy, grade_for, SCORE_WEIGHTS
from backtest.spec import describe_config


def test_weights_sum_to_100():
    assert sum(SCORE_WEIGHTS.values()) == 100


def test_grade_bands():
    assert grade_for(95) == "A+" and grade_for(82) == "A" and grade_for(72) == "B"
    assert grade_for(64) == "Observation" and grade_for(40) == "No-Trade"


def test_score_in_range_and_shaped():
    d = describe_config(PRESETS["EL_TORO"])
    sc = d["score"]                                 # describe_config attaches it
    assert 0 <= sc["score"] <= 100
    assert sc["grade"] in ("A+", "A", "B", "Observation", "No-Trade")
    assert abs(sum(sc["components"].values()) - sc["score"]) < 0.2


def test_regime_fit_sharpens_l1():
    d = describe_config(PRESETS["EL_TORO"])
    # a trend preset scored in a trend regime beats the same preset in a range
    hi = score_strategy(d, regime="Strong Bull Trend", setup_class="trend_pullback")
    lo = score_strategy(d, regime="Low-Volatility Range", setup_class="trend_pullback")
    assert hi["components"]["L1_regime"] > lo["components"]["L1_regime"]
    assert hi["score"] > lo["score"]


def test_confluence_gets_standalone_credit():
    d = describe_config(PRESETS["EL_TORO"])
    sc = score_strategy(d, setup_class="confluence")
    assert sc["components"]["L1_regime"] > 0.5 * SCORE_WEIGHTS["L1_regime"]
