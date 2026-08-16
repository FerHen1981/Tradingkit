"""Funded-overlay (third lens) tests — payout cycle, breach, consistency."""
import datetime as dt

from backtest.funded import simulate_funded, summarize, daily_from_trades


def _days(vals, start=dt.date(2026, 1, 5)):
    return {start + dt.timedelta(days=i): v for i, v in enumerate(vals)}


def test_no_payout_before_min_days():
    # 7 qualifying days, big enough balance, but < 8 days -> no payout
    r = simulate_funded(_days([500] * 7), account_size=50_000)
    assert r.num_payouts == 0 and not r.breached


def test_payout_after_eight_consistent_days():
    # 8 days x $500 = $4000 profit; balance 54,000 >= safety 52,600; best day 500/4000=12.5% (<30%)
    r = simulate_funded(_days([500] * 8), account_size=50_000)
    assert r.num_payouts == 1
    p = r.payouts[0]
    assert p.amount > 0
    # safety net = 50,000 + 2,500 + 100 = 52,600; above = 1,400; capped by first ladder 1,500 -> 1,400
    assert abs(p.amount - 1_400) < 1e-6
    assert r.days_to_first_payout == 8


def test_consistency_blocks_payout():
    # one dominant day (3000) vs seven tiny ($60) -> best day > 30% of wins -> no payout yet
    r = simulate_funded(_days([3_000] + [60] * 7), account_size=50_000)
    assert r.num_payouts == 0 and not r.breached


def test_trailing_breach():
    # ramp up then a crash below the trailing floor
    r = simulate_funded(_days([300, 300, 300, -4_000]), account_size=50_000)
    assert r.breached and "floor" in r.breach_reason


def test_daily_loss_limit_breach():
    r = simulate_funded(_days([200, -1_500]), account_size=50_000, daily_loss_limit=1_000)
    assert r.breached and "DLL" in r.breach_reason


def test_static_drawdown_floor():
    # static: floor = start - dd fixed; a -2,600 day from flat breaches a 2,500 static dd
    r = simulate_funded(_days([-2_600]), account_size=50_000,
                        drawdown_type="static", drawdown=2_500)
    assert r.breached


def test_profit_split_applied():
    r = simulate_funded(_days([500] * 8), account_size=50_000, profit_split=0.9)
    assert abs(r.payouts[0].amount - 1_400 * 0.9) < 1e-6


def test_summarize_shape():
    s = summarize(simulate_funded(_days([500] * 8), account_size=50_000))
    assert s["payouts"] == 1 and s["withdrawable"] > 0 and s["breached"] is False
    assert "per_month" in s and "days_to_first_payout" in s


def test_daily_from_trades():
    class T:
        def __init__(self, d, net):
            self.exit_time = d; self.net = net
    d1, d2 = dt.datetime(2026, 1, 5, 10), dt.datetime(2026, 1, 5, 14)
    d3 = dt.datetime(2026, 1, 6, 11)
    daily = daily_from_trades([T(d1, 100), T(d2, -30), T(d3, 50)])
    assert daily[dt.date(2026, 1, 5)] == 70 and daily[dt.date(2026, 1, 6)] == 50
