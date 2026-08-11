"""Goal metrics on hand-built outcomes, where every expected number is arithmetic
rather than whatever the engine happened to produce."""
import math

import pandas as pd
import pytest

from backtest import data, goals
from backtest.funnel import FunnelOutcome


def _outcome(result, resolve=-1, trades=10, payouts=0, banked=0.0, breaches=0, milks=0):
    return FunnelOutcome(
        start_bar=0, start_time=pd.Timestamp("2024-01-02", tz="America/New_York"),
        result=result, trades=trades, net_profit=0.0, bars=1000,
        resolve_sessions=resolve, payouts=payouts, banked=banked,
        breaches=breaches, milks=milks)


# --------------------------------------------------------------- Goal A
def _eval_set():
    return ([_outcome("PASS", resolve=r) for r in (10, 20, 30, 40)]
            + [_outcome("BREACH", resolve=5) for _ in range(4)]
            + [_outcome("TIMEOUT") for _ in range(2)])


def test_eval_rates_split_all_starts_from_resolved():
    m = goals.eval_throughput(_eval_set(), horizon_sessions=50)
    assert m["starts"] == 10
    assert (m["pass"], m["breach"], m["timeout"]) == (4, 4, 2)
    assert m["pass_rate_pct"] == 40.0            # of every attempt
    assert m["pass_rate_of_resolved_pct"] == 50.0  # of the ones that finished


def test_eval_time_to_pass_uses_only_passers():
    m = goals.eval_throughput(_eval_set(), horizon_sessions=50)
    assert m["sessions_to_pass"]["median"] == 25.0
    assert m["sessions_to_breach"]["median"] == 5.0


def test_eval_timeouts_are_priced_at_the_full_horizon():
    # 4*10+4*5 resolved = 120 sessions, plus 2 timeouts at the 50-session horizon
    # = 220 over 10 attempts = 22 per attempt; 1/0.4 = 2.5 attempts to fund.
    m = goals.eval_throughput(_eval_set(), horizon_sessions=50)
    assert m["expected_attempts_per_funded"] == 2.5
    assert m["expected_sessions_to_funded"] == pytest.approx(55.0)
    assert m["expected_weeks_to_funded"] == pytest.approx(11.0)


def test_eval_fee_scales_with_attempts_not_starts():
    m = goals.eval_throughput(_eval_set(), eval_fee=147, horizon_sessions=50)
    assert m["expected_cost_per_funded"] == pytest.approx(2.5 * 147)


def test_eval_never_passing_is_infinite_not_zero():
    m = goals.eval_throughput([_outcome("BREACH", resolve=3) for _ in range(5)],
                              eval_fee=147, horizon_sessions=50)
    assert m["pass_rate_pct"] == 0.0
    assert math.isinf(m["expected_attempts_per_funded"])
    assert math.isinf(m["expected_cost_per_funded"])


def test_eval_empty_is_reported_not_crashed():
    assert goals.eval_throughput([]) == {"starts": 0}


# --------------------------------------------------------------- Goal B
def _payout_set():
    return [
        _outcome("TIMEOUT", payouts=0, banked=0.0, breaches=2),
        _outcome("TIMEOUT", payouts=3, banked=3000.0, breaches=1),
        _outcome("TIMEOUT", payouts=6, banked=7000.0, breaches=0, milks=1),
        _outcome("TIMEOUT", payouts=9, banked=11000.0, breaches=0, milks=1),
    ]


def test_payout_ladder_probabilities():
    m = goals.payout_throughput(_payout_set(), acct_trail_dd=2000.0, horizon_sessions=126)
    assert m["p_any_payout_pct"] == 75.0     # 3 of 4 banked something
    assert m["p_full_ladder_pct"] == 50.0    # 2 of 4 reached six
    assert m["completed_ladders"] == 2


def test_payout_rates_scale_a_half_year_window_to_a_year():
    m = goals.payout_throughput(_payout_set(), acct_trail_dd=2000.0, horizon_sessions=126)
    assert m["payouts"]["median"] == 4.5
    # mean is also 4.5 here; a 126-session window is half a year, so it doubles
    assert m["payouts_per_account_year"] == pytest.approx(9.0)
    assert m["banked_per_account_year"] == pytest.approx(10500.0)
    assert m["breaches_per_account_year"] == pytest.approx(1.5)


def test_payout_survival_counts_untouched_accounts():
    m = goals.payout_throughput(_payout_set(), acct_trail_dd=2000.0, horizon_sessions=126)
    assert m["survival_rate_pct"] == 50.0


def test_banked_is_expressed_in_dd_units():
    # mean banked 5250 against a 2000 trailing allowance
    m = goals.payout_throughput(_payout_set(), acct_trail_dd=2000.0, horizon_sessions=126)
    assert m["banked_mean_dd_units"] == pytest.approx(2.63, abs=0.01)


def test_payout_empty_is_reported_not_crashed():
    assert goals.payout_throughput([], acct_trail_dd=2000.0, horizon_sessions=126) == {"starts": 0}


# --------------------------------------------------------------- loader
def test_loader_survives_a_dst_boundary():
    """A multi-year ET export carries both -05:00 and -04:00; pandas raises on
    that rather than coercing, so the loader has to normalise via UTC."""
    s = pd.Series(["15-01-2024 09:30:00 -05:00", "15-07-2024 09:30:00 -04:00"])
    et = data._parse(s, "%d-%m-%Y %H:%M:%S %z")
    assert et.notna().all()
    et = et.dt.tz_convert("America/New_York")
    assert [t.hour for t in et] == [9, 9]
