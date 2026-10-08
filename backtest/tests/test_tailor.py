"""tailor.py scoring-core tests (Release 3b).

These pin the parts that are fully specified and data-free: the 24-set grid and its
scaling, and the haal/breach/score arithmetic over hand-built daily-P&L windows (so every
expected number is arithmetic, not whatever the engine produced). The engine-generation
layer and the A-84 reproduction on 013/018/022 need the MGC year-stream (D-141) and are
intentionally NOT asserted here.
"""
from __future__ import annotations

import datetime as dt

from backtest.tailor import (Guards, candidate_sets, score_set, rank, tailor_account,
                             AccountProfile, GUARD_FAMILIES, QTYS)


def _days(vals, start=dt.date(2026, 1, 5)):
    return {start + dt.timedelta(days=i): v for i, v in enumerate(vals)}


# --- the candidate grid ------------------------------------------------------
def test_grid_is_24_sets():
    sets = candidate_sets()
    assert len(sets) == len(QTYS) * len(GUARD_FAMILIES) * 2 == 24
    assert len({(g.qty, g.act, g.gb, g.cap, g.daystop) for g in sets}) == 24


def test_guards_scale_per_contract_and_daystop_is_the_cap():
    g = Guards(qty=2, act=150, gb=50, cap=300, daystop=True)
    assert g.scaled() == (300.0, 100.0, 600.0, 600.0)        # x2, DLL = scaled cap
    assert Guards(2, 150, 50, 300, daystop=False).scaled()[3] is None


# --- scoring arithmetic ------------------------------------------------------
_PROFILE = AccountProfile(
    name="TEST", account_size=50_000, room_to_liq=2_500, locked=False,
    best_day_since=700, next_cap=500, consistency_pct=100.0, min_qual_usd=50.0,
    min_qual_days=5, min_trading_days=8,
)


def _reach_window():
    # 8 x $700: qualifies (>=5 days >=$50), balance 55,600 >= safety 52,600, banks the $500 step.
    return _days([700] * 8)


def _breach_window():
    # one -$3,000 day: balance 47,000 < trailing floor 47,500 -> breach.
    return _days([-3_000])


def _neither_window():
    # tiny days below the $50 qualifier: never a payout, never a breach.
    return _days([10] * 60)


def test_score_set_arithmetic():
    windows = [_reach_window(), _reach_window(), _breach_window(), _neither_window()]
    sc = score_set(windows, _PROFILE, guards=Guards(2, 150, 50, 300, True))
    assert sc.windows == 4
    assert abs(sc.haal[40] - 0.5) < 1e-9          # 2 of 4 reached the step within 40d
    assert abs(sc.breach[40] - 0.25) < 1e-9       # 1 of 4 breached
    assert abs(sc.score - (0.5 - 0.5 * 0.25)) < 1e-9   # 0.375
    assert sc.median_days == 5                    # both reachers banked on the 5th qualifying day


def test_reach_requires_hitting_the_step_cap_not_a_partial():
    # next_cap 5,000 but the window only ever gets $3,000 above safety -> NOT reached.
    prof = AccountProfile(name="T", account_size=50_000, room_to_liq=2_500, locked=False,
                          best_day_since=700, next_cap=5_000, consistency_pct=100.0,
                          min_qual_usd=50.0, min_qual_days=5, min_trading_days=8)
    sc = score_set([_reach_window()], prof, guards=Guards(1, 150, 50, 300, True))
    assert sc.haal[40] == 0.0


def test_uncapped_step_counts_any_payout():
    prof = AccountProfile(name="T", account_size=50_000, room_to_liq=2_500, locked=False,
                          best_day_since=700, next_cap=None, consistency_pct=100.0,
                          min_qual_usd=50.0, min_qual_days=5, min_trading_days=8)
    sc = score_set([_reach_window()], prof, guards=Guards(1, 150, 50, 300, True))
    assert sc.haal[40] == 1.0


# --- ranking / cockpit record ------------------------------------------------
def test_rank_and_tailor_pick_the_highest_score():
    good = Guards(2, 150, 50, 300, True)
    bad = Guards(1, 320, 100, 900, False)
    windows_by_set = {
        good: [_reach_window(), _reach_window(), _neither_window()],   # 2/3 reach, 0 breach
        bad: [_breach_window(), _breach_window(), _neither_window()],  # 0 reach, 2/3 breach
    }
    ranked = rank(windows_by_set, _PROFILE)
    assert ranked[0].guards == good and ranked[0].score > ranked[1].score

    rec = tailor_account(windows_by_set, _PROFILE)
    assert rec["account"] == "TEST"
    assert rec["chosen"]["qty"] == 2 and rec["chosen"]["cap"] == 600.0
    assert rec["chosen"]["day_stop"] == 600.0
    # Apex consistency formula surfaced for the cockpit: best_day / 0.30.
    assert rec["inputs"]["min_total_win_for_consistency"] is not None
