"""The trade-level diff behind stage 1's "investigate the divergent trades".

The tool's whole value is that the SHAPE of the disagreement names the cause, so
these tests check that each shape is reported as itself: a missing session shows
up as pine-only trades on one weekday, a timing difference shows up as matched-
on-a-different-bar rather than as two missing trades, and an exit-semantics
difference shows up as matched-with-a-different-result.
"""
from __future__ import annotations

import pandas as pd

from backtest.pipeline.parity import Export
from backtest.pipeline.tracediff import diff


class _T:
    """Minimal stand-in for engine.Trade."""
    def __init__(self, entry, dir_, net, reason="TP", exit_px=100.0):
        self.entry_time = pd.Timestamp(entry)
        self.exit_time = self.entry_time + pd.Timedelta(minutes=30)
        self.dir, self.net, self.reason = dir_, net, reason
        self.entry_px, self.exit_px = 100.0, exit_px


def _export(rows):
    trades = [{"n": i + 1, "dir": d, "entry_time": e,
               "exit_time": e, "entry_px": 100.0, "exit_px": xp,
               "qty": 1.0, "net": net, "signal": "", "exit_reason": reason}
              for i, (e, d, net, reason, xp) in enumerate(rows)]
    return Export(path="x", properties={}, trades=trades, performance={})


def test_identical_lists_align_completely():
    rows = [("2025-09-02 09:30", 1, 100.0, "TP", 101.0),
            ("2025-09-03 10:15", -1, -50.0, "SL", 99.0)]
    sim = [_T(e, d, n, r, xp) for e, d, n, r, xp in rows]
    d = diff(sim, _export(rows))
    assert (d["matched"], d["sim_only"], d["pine_only"]) == (2, 0, 0)
    assert d["matched_with_a_different_result"] == 0
    assert d["matched_on_a_different_bar"] == 0


def test_a_missing_session_shows_up_as_pine_only_on_one_weekday():
    """The MATADOR case: the mirror inherited Mon-Fri while the script trades the
    Sunday Globex open, so every Sunday entry was absent."""
    shared = [("2025-09-02 09:30", 1, 100.0, "TP", 101.0)]
    sundays = [("2025-09-07 18:30", 1, 60.0, "TP", 101.0),
               ("2025-09-14 19:05", -1, -40.0, "SL", 99.0)]
    sim = [_T(*r) for r in shared]
    d = diff(sim, _export(shared + sundays))
    assert d["pine_only"] == 2 and d["sim_only"] == 0
    assert d["pine_only_by_weekday"] == {"Sunday": 2}


def test_a_one_bar_timing_difference_is_a_match_not_a_miss():
    sim = [_T("2025-09-02 09:31", 1, 100.0, "TP", 101.0)]
    d = diff(sim, _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0)]))
    assert d["matched"] == 1 and d["pine_only"] == 0
    assert d["matched_on_a_different_bar"] == 1


def test_a_far_apart_entry_is_not_matched():
    sim = [_T("2025-09-02 14:00", 1, 100.0, "TP", 101.0)]
    d = diff(sim, _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0)]))
    assert d["matched"] == 0 and d["sim_only"] == 1 and d["pine_only"] == 1


def test_opposite_directions_never_match():
    sim = [_T("2025-09-02 09:30", 1, 100.0, "TP", 101.0)]
    d = diff(sim, _export([("2025-09-02 09:30", -1, 100.0, "TP", 101.0)]))
    assert d["matched"] == 0


def test_same_entry_different_exit_is_reported_with_both_reasons():
    """The exit-semantics shape: same trades taken, different money made."""
    sim = [_T("2025-09-02 09:30", 1, 40.0, "AUTO-FLAT", 100.4)]
    d = diff(sim, _export([("2025-09-02 09:30", 1, 210.0, "TP|MFE209t", 102.1)]))
    assert d["matched"] == 1
    assert d["matched_with_a_different_result"] == 1
    g = d["first_result_gaps"][0]
    assert (g["sim_net"], g["pine_net"]) == (40.0, 210.0)
    assert g["sim_exit"] == "AUTO-FLAT" and g["pine_exit"].startswith("TP")
    assert d["avg_net_matched_sim"] == 40.0
    assert d["avg_net_matched_pine"] == 210.0


def test_exit_reason_distributions_are_reported_for_both_sides():
    rows = [("2025-09-02 09:30", 1, 10.0, "Auto Flat", 100.1),
            ("2025-09-03 09:30", 1, 10.0, "Auto Flat", 100.1),
            ("2025-09-04 09:30", 1, -10.0, "PA Daily Loss Limit", 99.9)]
    sim = [_T(e, d_, n, "SL", xp) for e, d_, n, _r, xp in rows]
    d = diff(sim, _export(rows))
    assert d["sim_exit_reasons"] == {"SL": 3}
    assert d["pine_exit_reasons"]["Auto Flat"] == 2
    assert d["pine_exit_reasons"]["PA Daily Loss Limit"] == 1


def test_open_trades_are_ignored_on_both_sides():
    sim = [_T("2025-09-02 09:30", 1, 100.0, "TP", 101.0)]
    sim[0].exit_time = None
    d = diff(sim, _export([]))
    assert d["sim_trades"] == 0 and d["matched"] == 0
