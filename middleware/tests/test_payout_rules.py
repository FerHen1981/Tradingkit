"""Payout & prop-firm rule engine tests (Apex ruleset)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.payout_rules import evaluate  # noqa: E402


def _days(vals):
    base = dt.date(2026, 8, 1)
    return {base + dt.timedelta(days=i): v for i, v in enumerate(vals)}


def test_eval_reaches_target():
    p = evaluate(50000, 50000, 53000, "Eval", _days([3000]))
    assert p.stage == "Eval" and p.target == 3000
    assert p.eligible is True                      # profit 3000 >= target
    assert p.rules[0].ok is True


def test_eval_below_target():
    p = evaluate(50000, 50000, 51500, "Eval", _days([1500]))
    assert p.eligible is False and p.rules[0].ok is False


def test_funded_eligible():
    # 8 qualifying days, best day 400/3000 = 13% (<30%), balance above safety net
    daily = _days([400, 400, 400, 400, 400, 400, 400, 200])   # sums 3000, 8 days
    p = evaluate(50000, 50000, 53000, "Funded", daily)
    assert p.stage == "Funded"
    assert p.trading_days == 8
    assert p.safety_net_balance == 52600            # 50000 + 2500 + 100
    assert p.withdrawable == 400                    # 53000 - 52600
    assert p.eligible is True


def test_funded_too_few_days():
    p = evaluate(50000, 50000, 53000, "Funded", _days([1500, 1500]))   # 2 days only
    assert p.trading_days == 2 and p.eligible is False
    assert any(r.name.startswith("≥") and r.ok is False for r in p.rules)
    # not all rules met → no pay day: withdrawable is 0, potential is tracked separately
    assert p.withdrawable == 0.0 and p.above_safety == 400.0


def test_funded_consistency_fail():
    # one huge day dominates → best day > 30% of total → fails consistency
    daily = _days([2600, 60, 60, 60, 60, 60, 60, 60])          # best 2600 / 3020 = 86%
    p = evaluate(50000, 50000, 53020, "Funded", daily)
    assert p.consistency_pct > 30 and p.eligible is False


def test_missing_inputs_returns_none():
    assert evaluate(None, 50000, 53000, "Funded", {}) is None
