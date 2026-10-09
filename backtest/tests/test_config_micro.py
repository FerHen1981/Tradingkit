"""Micro-contract twins — same price grid, 1/10 multiplier."""
from backtest.config import contract, micro_twin


def test_twins_map():
    assert micro_twin("NQ") == "MNQ" and micro_twin("ES") == "MES"
    assert micro_twin("GC") == "MGC" and micro_twin("YM") == "MYM"
    assert micro_twin("XYZ") is None


def test_micro_is_tenth_multiplier_same_grid():
    for mini, mic in (("NQ", "MNQ"), ("ES", "MES"), ("GC", "MGC")):
        a, b = contract(mini), contract(mic)
        assert b.pointvalue == a.pointvalue / 10       # 1/10 the dollars
        assert b.mintick == a.mintick                  # identical price grid (same course)


def test_micro_pf_would_match_mini():
    # PF/win% are contract-independent (ratios); only $ P&L scales — so the classic
    # lens is identical and micro only matters at the eval/funded lens.
    nq, mnq = contract("NQ"), contract("MNQ")
    assert nq.tickvalue == 0.25 * 20 and mnq.tickvalue == 0.25 * 2
