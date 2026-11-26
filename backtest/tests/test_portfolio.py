"""Trap 11 — portfolio-diversification maths + gate.

The load-bearing property is the SUFFICIENCY gate: no decorrelation may be claimed
below min_days of shared active days, whatever the correlation reads. And the sign
matters — a strong negative correlation is a hedge (passes), only strong positive
correlation fails.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from backtest.pipeline import portfolio as pf


def _days(n, start=_dt.date(2025, 1, 1)):
    return [start + _dt.timedelta(days=i) for i in range(n)]


def _series(vals, start=_dt.date(2025, 1, 1)):
    return {start + _dt.timedelta(days=i): v for i, v in enumerate(vals)}


# --- maths --------------------------------------------------------------------

def test_pearson_perfect_and_anti():
    a = [1.0, 2.0, 3.0, 4.0]
    assert pf._pearson(a, [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pf._pearson(a, [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert pf._pearson(a, [5, 5, 5, 5]) is None          # flat -> undefined


def test_align_zero_fills_the_union():
    a = {_dt.date(2025, 1, 1): 10.0}
    b = {_dt.date(2025, 1, 2): -5.0}
    dates, cols = pf._align({"A": a, "B": b})
    assert dates == _days(2)
    assert cols["A"] == [10.0, 0.0] and cols["B"] == [0.0, -5.0]


# --- gate: sufficiency dominates ---------------------------------------------

def test_below_min_days_is_inconclusive_regardless_of_correlation():
    # perfectly correlated but only 5 shared days -> NOT allowed to conclude
    a = _series([1, -1, 2, -2, 3])
    b = _series([2, -2, 4, -4, 6])
    rep = pf.assess({"A": a, "B": b}, min_days=20)
    assert rep["status"] == "inconclusive"
    assert "onvoldoende" in rep["verdict"].lower()
    assert rep["min_pair_days"] == 5


def test_high_positive_correlation_fails_with_enough_days():
    vals = [((-1) ** i) * (i % 7 + 1) for i in range(40)]
    a = _series(vals)
    b = _series([v * 1.5 for v in vals])                 # same shape -> r ~ +1
    rep = pf.assess({"A": a, "B": b}, min_days=20)
    assert rep["status"] == "failed"
    assert rep["max_corr"] > 0.7


def test_negative_correlation_is_a_hedge_and_passes():
    vals = [((-1) ** i) * (i % 5 + 1) for i in range(40)]
    a = _series(vals)
    b = _series([-v for v in vals])                       # perfect hedge -> r ~ -1
    rep = pf.assess({"A": a, "B": b}, min_days=20)
    assert rep["status"] == "passed"                     # signed gate: hedge is good
    assert rep["max_corr"] <= 0.3


def test_partial_correlation_is_inconclusive():
    import random
    rng = random.Random(4)
    base = [rng.gauss(0, 1) for _ in range(60)]
    a = _series(base)
    b = _series([0.5 * base[i] + rng.gauss(0, 1) for i in range(60)])  # ~0.4-0.5
    rep = pf.assess({"A": a, "B": b}, min_days=20, corr_lo=0.3, corr_hi=0.7)
    assert rep["status"] == "inconclusive"
    assert 0.3 < rep["max_corr"] < 0.7


# --- overlap + breach ---------------------------------------------------------

def test_loss_and_breach_overlap_counted():
    a = _series([-100, -100, 50, -100])
    b = _series([-100, 50, -100, -100])                  # share loss on day 0 and 3
    rep = pf.assess({"A": a, "B": b}, min_days=1,
                    dll_by_engine={"A": 90, "B": 90})
    pair = rep["pairs"][0]
    assert pair["loss_overlap"]["both"] == 2
    assert pair["breach_overlap"]["both"] == 2           # both <= -90 on days 0 and 3


def test_single_engine_is_rejected():
    rep = pf.assess({"solo": _series([1, 2, 3])}, min_days=1)
    assert rep["status"] == "inconclusive"
    assert "minstens twee" in rep["verdict"]
