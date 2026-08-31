"""Payout & prop-firm rule engine tests (Apex ruleset)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import firm_rules  # noqa: E402
from app.payout_rules import APEX_DD, APEX_TARGET, evaluate  # noqa: E402


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
    assert any(r.name == "Trading days" and r.ok is False for r in p.rules)
    assert p.days_to_go == 6                              # 8 − 2
    # not all rules met → no pay day: withdrawable is 0, potential is tracked separately
    assert p.withdrawable == 0.0 and p.above_safety == 400.0


def test_funded_consistency_fail():
    # one huge day dominates → best day > 30% of total → fails consistency
    daily = _days([2600, 60, 60, 60, 60, 60, 60, 60])          # best 2600 / 3020 = 86%
    p = evaluate(50000, 50000, 53020, "Funded", daily)
    assert p.consistency_pct > 30 and p.eligible is False


def test_missing_inputs_returns_none():
    assert evaluate(None, 50000, 53000, "Funded", {}) is None


# --- two day counters, not one ------------------------------------------------------------------

LEGACY = "apex_50k_legacy_pa"


def _prog(key=LEGACY):
    return firm_rules.rules(key)


def test_the_registry_carries_both_day_counters():
    r = _prog()
    assert (r["min_days"], r["profit_days"], r["profit_day_min"]) == (8, 5, 50.0)


def test_days_with_fills_and_days_over_the_bar_are_scored_apart():
    """Apex legacy wants 8 days traded AND 5 over $50. Demanding 8 days that each cleared $50 is
    stricter than the firm and pushed every payout further away than it was."""
    daily = _days([120] * 5 + [-40, -30, -25])            # 8 traded, 5 green over $50
    p = evaluate(50000, 50000, 53000, "Funded", daily, 0, _prog())
    assert p.trading_days == 8 and p.profit_days == 5
    assert p.days_to_go == 0
    assert [r for r in p.rules if r.name == "Trading days"][0].ok is True


def test_the_profitable_counter_can_be_the_one_that_binds():
    daily = _days([120] * 3 + [10] * 7)                   # 10 traded, only 3 over $50
    p = evaluate(50000, 50000, 53000, "Funded", daily, 0, _prog())
    assert (p.trading_days, p.profit_days) == (10, 3)
    assert p.profit_days_to_go == 2 and p.eligible is False


def test_the_fill_counter_can_be_the_one_that_binds():
    daily = _days([300] * 6)                              # 6 traded, all green
    p = evaluate(50000, 50000, 53000, "Funded", daily, 0, _prog())
    assert p.profit_days_to_go == 0 and p.days_to_go == 2
    assert p.eligible is False


# --- fallbacks that decide money ----------------------------------------------------------------

def test_every_apex_size_has_a_drawdown_fallback():
    """APEX_TARGET listed 75K while APEX_DD did not, and both are read with .get(size, 0).
    A 75K account without a program therefore ran with a zero floor and a zero safety net."""
    assert set(APEX_TARGET) == set(APEX_DD)
    assert APEX_DD[75_000] == 2_750
    assert APEX_TARGET[75_000] == 4_500 and APEX_TARGET[300_000] == 18_000


def test_the_safety_net_stops_applying_after_three_payouts():
    daily = _days([500] * 10)
    third = evaluate(50000, 50000, 54000, "Funded", daily, 2, _prog())
    fourth = evaluate(50000, 50000, 54000, "Funded", daily, 3, _prog())
    assert third.safety_net_balance == 52_600          # 50,000 + 2,500 + 100
    assert fourth.safety_net_balance == 50_000         # the net no longer holds
    assert fourth.above_safety > third.above_safety


def test_past_the_last_rung_the_firm_caps_no_further():
    daily = _days([1_000] * 10)
    sixth = evaluate(50000, 50000, 62000, "Funded", daily, 6, _prog())
    assert sixth.cap_unlimited is True
    assert sixth.withdrawable == sixth.above_safety     # nothing clipped it


def test_a_payout_under_the_minimum_is_not_a_payout():
    daily = _days([120] * 8)
    p = evaluate(50000, 50000, 52_700, "Funded", daily, 0, _prog())   # $100 above the net
    assert p.eligible is False
    assert [r for r in p.rules if r.name == "Minimum payout"][0].ok is False


def test_the_result_names_the_rule_set_it_scored_against():
    p = evaluate(50000, 50000, 53000, "Funded", _days([400] * 8), 0, _prog())
    assert p.ruleset == LEGACY
