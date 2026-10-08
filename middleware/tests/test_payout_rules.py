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
    # 8 qualifying days, best day 400/3000 = 13% (<30%), balance above safety net.
    # D-149 — zonder geverifieerd programma mag `evaluate` NIET stilzwijgend een cap
    # verzinnen. We draaien het verified Apex-50K-legacy-PA-programma; dat is de
    # enige set die D-148-correct is in de registry.
    prog = firm_rules.rules("apex_50k_legacy_pa")
    daily = _days([450, 450, 450, 450, 450, 450, 450, 450])   # sums 3600, 8 days
    p = evaluate(50000, 50000, 53200, "Funded", daily, program=prog)
    assert p.stage == "Funded"
    assert p.trading_days == 8
    assert p.safety_net_balance == 52600            # 50000 + 2500 + 100
    assert p.withdrawable == 600                    # 53200 - 52600, above min_payout 500
    assert p.eligible is True
    # D-148: legacy-PA draagt een VASTE cap $2.000 tot payout 5, uncapped vanaf 6.
    assert p.cap == 2000.0 and p.cap_unlimited is False


def test_funded_without_verified_terms_refuses_to_quote_a_cap():
    # D-149 — zonder `payout_terms_verified: true` of een echte ladder in de registry
    # geeft evaluate GEEN cap-getal en WEIGERT het de payout. Dat is de harde regel:
    # geen plausibel-maar-ongefundeerd plafond.
    daily = _days([400, 400, 400, 400, 400, 400, 400, 200])
    p = evaluate(50000, 50000, 53000, "Funded", daily)   # geen program
    assert p.eligible is False and p.withdrawable == 0.0
    assert p.cap == 0.0 and p.total_cap == 0.0
    assert any(r.name == "Payout terms" and r.ok is False for r in p.rules)


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


# --- D-149: payout-cap-vorm uit de registry — vast cap + uncapped_from (D-148) ------------------

def test_fixed_cap_uncapped_from_payout_six():
    """D-148: Apex legacy-PA kent GEEN oplopende ladder — vast $2.000 t/m payout 5,
    daarna uncapped. De oude ladder [1500,1500,2000,2500,2500,3000] is weerlegd."""
    prog = _prog()
    daily = _days([700] * 8)                             # profit $5.600, binnen de regels
    # Payout #1: cap vast op $2.000, niet $1.500 (oude ladder).
    first = evaluate(50000, 50000, 55600, "Funded", daily, 0, prog)
    assert first.cap == 2000.0 and first.cap_unlimited is False
    # Payout #5: nog gewoon $2.000.
    fifth = evaluate(50000, 50000, 55600, "Funded", daily, 5, prog)
    assert fifth.cap == 2000.0 and fifth.cap_unlimited is False
    # Payout #6: cap vervalt (`payout_cap_uncapped_from: 6`); de kop is `above_safety`.
    sixth = evaluate(50000, 50000, 55600, "Funded", daily, 6, prog)
    assert sixth.cap_unlimited is True
    assert sixth.cap == sixth.above_safety               # geen plafond meer


def test_unverified_payout_terms_refuse_a_cap_from_a_registry_hit():
    """D-149: een programma dat IN de registry staat maar `payout_terms_verified: false` draagt
    (bv. apex_50k_eod_pa vóór owner-bevestiging) MAG geen cap-getal invullen."""
    prog = firm_rules.rules("apex_50k_eod_pa")           # verified: false in propfirms.json
    assert prog is not None and prog["payout_terms_verified"] is False
    daily = _days([700] * 8)
    p = evaluate(50000, 50000, 55600, "Funded", daily, 0, prog)
    assert p.eligible is False and p.withdrawable == 0.0
    assert p.cap == 0.0
    assert any(r.name == "Payout terms" and r.ok is False for r in p.rules)
