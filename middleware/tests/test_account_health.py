"""Survival-buffer + health math tests (Apex trailing + EOD lock)."""
from app.account_health import compute, dd_threshold


def test_thresholds():
    assert dd_threshold(50000, "Trailing Equity Peak") == 2500
    assert dd_threshold(25000, "Trailing Equity Peak") == 1500
    assert dd_threshold(50000, "EOD ($2000)") == 2000
    assert dd_threshold(50000, "EOD ($2500)") == 2500


def test_fresh_apex_50k_full_buffer():
    h = compute(50000, 50000, 50000, None, "Trailing Equity Peak", "Apex Trader Funding", "Funded Account")
    assert h.threshold == 2500
    assert h.buffer_usd == 2500 and h.buffer_pct == 100.0
    assert h.status == "Healthy"


def test_apex_trailing_gives_back_cushion():
    # peaked at +3000 (locked, >2600), now back to +1000 → floor locked at start+100
    h = compute(50000, 50000, 51000, 53000, "Trailing Equity Peak", "Apex Trader Funding", "Funded Account")
    assert h.floor == 50100          # locked at start + $100
    assert h.buffer_usd == 900       # 51000 - 50100
    assert h.status == "Watch"       # 36%


def test_apex_near_breach_is_critical():
    h = compute(50000, 50000, 50200, 52700, "Trailing Equity Peak", "Apex Trader Funding", "Active Eval")
    assert h.buffer_usd == 100 and h.buffer_pct < 15
    assert h.status == "Critical"


def test_breached_status_wins():
    h = compute(50000, 50000, 51000, 51000, "Trailing Equity Peak", "Apex Trader Funding", "Breached")
    assert h.status == "Breached"


def test_below_floor_is_breached():
    # floor = 50000 - 2500 = 47500; balance below it → breached (being below START alone is not)
    h = compute(50000, 50000, 47000, 50000, "Trailing Equity Peak", "Apex Trader Funding", "Active Eval")
    assert h.floor == 47500 and h.buffer_usd <= 0 and h.status == "Breached"


def test_down_but_within_cushion_is_healthy():
    # down $1000 but still $1500 of the $2500 cushion left → not a breach
    h = compute(50000, 50000, 49000, 50000, "Trailing Equity Peak", "Apex Trader Funding", "Active Eval")
    assert h.buffer_usd == 1500 and h.status == "Healthy"


def test_eod_firm_locks_at_start():
    # MFFU EOD $2000: once up $2500 the floor locks at START (not start+100)
    h = compute(50000, 50000, 52500, 52500, "EOD ($2000)", "My Funded Futures", "Funded Account")
    assert h.threshold == 2000
    assert h.floor == 50000          # locked at start
    assert h.buffer_usd == 2500


def test_eval_never_locks():
    # Apex EVAL: floor trails the peak with NO lock (214: peak 53,034.50 → floor 50,534.50)
    h = compute(50000, 50000, 53034.50, 53034.50, "Legacy 50k", "Apex Trader Funding",
                "Active Eval", stage="eval")
    assert h.floor == 50534.50 and h.buffer_usd == 2500.0


def test_funded_locks_at_start_plus_100():
    # Apex FUNDED, past the lock: floor caps at start + $100
    h = compute(50000, 50000, 55470.08, 55470.08, "Legacy 50k", "Apex Trader Funding",
                "Funded Account", stage="funded")
    assert h.floor == 50100.0 and h.buffer_usd == 5370.08


def test_dd_floor_seed_is_exact():
    # EOD-trail account we can't fully reconstruct: the broker floor seed is used exactly
    h = compute(50000, 50000, 51897.60, 51897.60, "50k Tradovate EOD Trail", "Apex Trader Funding",
                "Funded Account", stage="funded", dd_floor=48331.70)
    assert h.floor == 48331.70 and h.buffer_usd == 3565.90


def test_dd_amount_override():
    h = compute(50000, 50000, 50000, 50000, "Intraday Trail", "Apex Trader Funding",
                "Active Eval", stage="eval", dd_amount=2000)
    assert h.threshold == 2000 and h.floor == 48000.0


def test_missing_balances_returns_none():
    assert compute(50000, None, None, None, "Trailing Equity Peak", "Apex", "x") is None
