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
from backtest.pipeline.tracediff import classify_pine_only, diff


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


# --- pine-only trades: did we place a limit there or not? ----------------------

def _placement(t, d, px=100.0, bar=0):
    return {"bar": bar, "dir": d, "time": pd.Timestamp(t), "limit": px}


def test_a_pine_only_trade_we_had_a_limit_for_counts_as_a_fill_failure():
    """We had an order resting at that moment and our bars never reached it —
    that points at the price series, not at the rules."""
    pine = _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0)])
    out = classify_pine_only([_placement("2025-09-02 09:27", 1)], pine, [], expiry_bars=6)
    assert out["pine_only"] == 1
    assert out["we_placed_but_never_filled"] == 1 and out["we_never_placed"] == 0
    assert "FILLS" in out["verdict"]


def test_a_pine_only_trade_without_any_order_counts_as_a_signal_failure():
    pine = _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0)])
    out = classify_pine_only([], pine, [], expiry_bars=6)
    assert out["we_never_placed"] == 1 and out["we_placed_but_never_filled"] == 0
    assert "SIGNALEN" in out["verdict"]


def test_a_trade_we_actually_took_is_not_pine_only():
    rows = [("2025-09-02 09:30", 1, 100.0, "TP", 101.0)]
    out = classify_pine_only([_placement("2025-09-02 09:28", 1)], _export(rows),
                             [_T(*rows[0])], expiry_bars=6)
    assert out["pine_only"] == 0


def test_a_placement_in_the_other_direction_does_not_count():
    pine = _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0)])
    out = classify_pine_only([_placement("2025-09-02 09:28", -1)], pine, [], expiry_bars=6)
    assert out["we_never_placed"] == 1


def test_a_placement_after_the_fill_does_not_count():
    """A resting limit can only fill after it was placed."""
    pine = _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0)])
    out = classify_pine_only([_placement("2025-09-02 09:40", 1)], pine, [], expiry_bars=6)
    assert out["we_never_placed"] == 1


def test_a_placement_older_than_the_expiry_window_does_not_count():
    pine = _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0)])
    out = classify_pine_only([_placement("2025-09-02 09:00", 1)], pine, [], expiry_bars=6)
    assert out["we_never_placed"] == 1, "een order van 30 min eerder was al lang verlopen"


def test_a_near_tie_is_reported_as_mixed_not_arbitrarily_resolved():
    """One of each is not evidence for either. A rule that just took the largest
    count would break the tie on ordering and send the fix somewhere on nothing."""
    pine = _export([("2025-09-02 09:30", 1, 100.0, "TP", 101.0),
                    ("2025-09-03 10:00", -1, -50.0, "SL", 99.0)])
    out = classify_pine_only([_placement("2025-09-02 09:28", 1)], pine, [], expiry_bars=6)
    assert (out["we_placed_but_never_filled"], out["we_never_placed"]) == (1, 1)
    assert "GEMENGD" in out["verdict"]


def test_a_bare_majority_is_still_mixed():
    """3 of 5 is a majority but not twice the runner-up (2) — not enough."""
    rows = [(f"2025-09-0{i} 10:00", 1, 10.0, "TP", 101.0) for i in range(1, 6)]
    placements = [_placement(f"2025-09-0{i} 09:58", 1) for i in range(1, 4)]
    out = classify_pine_only(placements, _export(rows), [], expiry_bars=6)
    assert (out["we_placed_but_never_filled"], out["we_never_placed"]) == (3, 2)
    assert "GEMENGD" in out["verdict"]


def test_a_pine_entry_inside_our_open_position_is_a_cascade_not_a_filter_gap():
    """Neither engine can enter while holding (pyramiding 1). A pine entry that
    lands inside one of OUR position windows was never available to us, so it is
    a consequence of an earlier divergence — counting it as a signal failure
    would send the fix at the filters instead of at the cause."""
    ours = _T("2025-09-02 09:00", 1, 100.0, "TP", 101.0)      # 09:00 -> 09:30
    pine = _export([("2025-09-02 09:15", -1, 50.0, "TP", 99.0)])
    out = classify_pine_only([], pine, [ours], expiry_bars=6)
    assert out["we_were_in_a_position"] == 1
    assert out["we_never_placed"] == 0
    assert "CASCADE" in out["verdict"]


def test_a_pine_entry_while_we_were_flat_is_still_a_signal_gap():
    ours = _T("2025-09-02 09:00", 1, 100.0, "TP", 101.0)      # 09:00 -> 09:30
    pine = _export([("2025-09-02 14:00", -1, 50.0, "TP", 99.0)])
    out = classify_pine_only([], pine, [ours], expiry_bars=6)
    assert out["we_never_placed"] == 1 and out["we_were_in_a_position"] == 0
    assert "SIGNALEN" in out["verdict"]


def test_a_resting_limit_outranks_the_position_window():
    """If we had an order there, that is the more specific fact."""
    ours = _T("2025-09-02 09:00", 1, 100.0, "TP", 101.0)
    pine = _export([("2025-09-02 09:15", -1, 50.0, "TP", 99.0)])
    out = classify_pine_only([_placement("2025-09-02 09:12", -1)], pine, [ours],
                             expiry_bars=6)
    assert out["we_placed_but_never_filled"] == 1
    assert out["we_were_in_a_position"] == 0


def test_the_three_categories_always_add_up():
    pine = _export([("2025-09-02 09:15", -1, 50.0, "TP", 99.0),
                    ("2025-09-02 14:00", 1, 10.0, "TP", 101.0),
                    ("2025-09-03 11:00", 1, 20.0, "TP", 101.0)])
    ours = _T("2025-09-02 09:00", 1, 100.0, "TP", 101.0)
    out = classify_pine_only([_placement("2025-09-03 10:58", 1)], pine, [ours],
                             expiry_bars=6)
    assert (out["we_placed_but_never_filled"] + out["we_were_in_a_position"]
            + out["we_never_placed"]) == out["pine_only"] == 3


# --- explain_missing: name the condition that differs -------------------------

def _frame_and_ind(tmp_path, cfg):
    import numpy as np
    from backtest import data as dm, indicators as im
    rng = np.random.default_rng(3)
    n, sigma = 20_000, 4.0
    px = 6000 + np.cumsum(rng.normal(0, sigma, n))
    idx = pd.date_range("2025-09-02 00:00", periods=n, freq="1min",
                        tz="America/New_York")
    raw = pd.DataFrame({
        "Open": px, "Close": px + rng.normal(0, sigma * 0.7, n),
        "High": px + np.abs(rng.normal(0, sigma * 2, n)),
        "Low": px - np.abs(rng.normal(0, sigma * 2, n)),
        "Volume": rng.integers(50, 900, n).astype(float), "Delta": np.zeros(n)})
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    raw.insert(0, "DateTime", idx.strftime("%d-%m-%Y %H:%M:%S %z"))
    csv = tmp_path / "x.csv"
    raw.to_csv(csv, index=False)
    df = dm.load(str(csv), cache=False)
    return df, im.compute(df, cfg)


def test_explain_missing_names_a_bar_with_no_gap_at_all(tmp_path):
    from backtest.pipeline import fleet
    from backtest.pipeline.tracediff import explain_missing
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    df, ind = _frame_and_ind(tmp_path, cfg)
    far = {"t": int(pd.Timestamp("2030-01-01 12:00").value // 60_000_000_000),
           "dir": 1, "entry_time": "2030-01-01 12:00", "pine_fvg_ticks": 12}
    out = explain_missing(df, ind, cfg, [far], expiry_bars=6)
    assert out["checked"] == 1
    assert "geen FVG van die richting in het venster" in out["reasons"]


def test_explain_missing_separates_band_from_streak(tmp_path):
    """Every case must land in exactly one named bucket — an unexplained
    remainder would send the search back to guessing."""
    import numpy as np

    from backtest.pipeline import fleet
    from backtest.pipeline.tracediff import explain_missing
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    df, ind = _frame_and_ind(tmp_path, cfg)
    et = pd.DatetimeIndex(df["et"]).tz_localize(None)
    mins = et.asi8 // 60_000_000_000

    rows = []
    for i in np.where(np.asarray(ind["fvg_dir"]) != 0)[0][:40]:
        rows.append({"t": int(mins[i]) + 1, "dir": int(ind["fvg_dir"][i]),
                     "entry_time": str(et[i]), "pine_fvg_ticks": 12,
                     "pine_cvd_streak": 6})
    out = explain_missing(df, ind, cfg, rows, expiry_bars=6)
    assert out["checked"] == len(rows)
    assert sum(out["reasons"].values()) == len(rows), "gevallen verdwenen uit de telling"
    assert set(out["reasons"]) <= {
        "geen FVG van die richting in het venster",
        "FVG gedetecteerd maar buiten de maatband",
        "FVG ok maar CVD-streak niet gehaald",
        "FVG en CVD ok — geblokkeerd door tijd/dag/halte"}
    # Which buckets actually occur is data-dependent; the invariant is that every
    # case lands in exactly one and that a band case, when it occurs, reports the
    # sizes we measured — that number is what makes the finding actionable.
    for e in out["examples"]:
        if e["reason"] == "maatband":
            assert e["ons_fvg_ticks"], "onze tickgroottes worden niet gerapporteerd"
