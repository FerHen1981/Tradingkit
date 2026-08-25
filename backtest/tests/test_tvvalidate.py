"""Trap 10 — TradingView validation, the last hard deployment gate.

Trap 1 gates on trade count / PF / WR / long-short. Trap 10 adds the two
dimensions trap 1 only shows: does the exit-reason MIX agree (the account
overlay's fidelity), and do the per-trade MFE/MAE excursions agree (the intrabar
path). These tests pin that a disagreement on either one fails the gate even when
the KPIs are identical, and that the data-vendor tolerance only carries over when
the shared trades behave the same.
"""
from __future__ import annotations

import pandas as pd

from backtest.pipeline.parity import Export, _exit_sigdiag
from backtest.pipeline.tracediff import diff as trace_diff
from backtest.pipeline import tvvalidate as tv


class _Contract:
    mintick = 0.25
    pointvalue = 2.0          # MES-like
    commission_per_contract = 0.37
    slippage_ticks = 1.0


class _Cfg:
    def __init__(self):
        self.contract = _Contract()


class _T:
    """Minimal stand-in for engine.Trade."""
    def __init__(self, entry, dir_, net, reason, mfe, mae):
        self.entry_time = pd.Timestamp(entry)
        self.exit_time = self.entry_time + pd.Timedelta(minutes=30)
        self.dir, self.net, self.reason = dir_, net, reason
        self.entry_px, self.exit_px = 100.0, 101.0
        self.mfe_ticks, self.mae_ticks = mfe, mae


def _pine(rows):
    """rows: (entry, dir, net, exit_signal). Exit signal like 'TP|MFE200t|MAE20t'
    or 'Auto Flat' / 'PA Daily Loss Limit'."""
    trades = []
    for i, (e, d, net, sig) in enumerate(rows):
        t = {"n": i + 1, "dir": d, "entry_time": e, "exit_time": e,
             "entry_px": 100.0, "exit_px": 101.0, "qty": 1.0, "net": net,
             "signal": "", "exit_reason": sig, "mfe_usd": 0.0, "mae_usd": 0.0,
             "dur_bars": 10.0, **_exit_sigdiag(sig)}
        trades.append(t)
    return Export(path="x", properties={}, trades=trades, performance={})


# --- exit category mapping ----------------------------------------------------

def test_exit_categories_collapse_both_naming_schemes():
    # Pine labels
    assert tv.exit_category("TP|MFE200t|MAE20t") == "TP"
    assert tv.exit_category("SL|MFE31t|MAE119t") == "SL"
    assert tv.exit_category("Auto Flat") == "AUTO-FLAT"
    assert tv.exit_category("PA Daily Loss Limit") == "DLL"
    assert tv.exit_category("CAP-LOCK") == "CAP-LOCK"
    # simulator labels — the stop family all become SL, EOD becomes Auto-Flat
    assert tv.exit_category("TRAIL") == "SL"
    assert tv.exit_category("BE-STOP") == "SL"
    assert tv.exit_category("RECOV-TRAIL") == "SL"
    assert tv.exit_category("EOD") == "AUTO-FLAT"
    assert tv.exit_category("Day-cap") == "CAP-LOCK"


# --- exit-reason distribution -------------------------------------------------

def test_identical_exit_mix_agrees():
    rows_p = [("2025-09-02 09:30", 1, 100.0, "TP|MFE200t|MAE20t"),
              ("2025-09-03 10:15", -1, -50.0, "SL|MFE10t|MAE120t"),
              ("2025-09-04 15:00", 1, 0.0, "Auto Flat")]
    sim = [_T("2025-09-02 09:30", 1, 100.0, "TP", 200, 20),
           _T("2025-09-03 10:15", -1, -50.0, "SL", 10, 120),
           _T("2025-09-04 15:00", 1, 0.0, "EOD", 5, 5)]
    a = tv.exit_reason_agreement(sim, _pine(rows_p))
    assert a["ok"] and a["worst_gap_pp"] == 0.0


def test_a_stop_out_where_pine_auto_flats_is_a_disagreement():
    """Same entries, but our engine stops out where Pine force-flattens — the
    account overlay diverges. KPIs can be identical; the exit mix is not."""
    rows_p = [("2025-09-02 09:30", 1, -50.0, "Auto Flat"),
              ("2025-09-03 09:30", 1, -50.0, "Auto Flat")]
    sim = [_T("2025-09-02 09:30", 1, -50.0, "SL", 10, 120),
           _T("2025-09-03 09:30", 1, -50.0, "SL", 10, 120)]
    a = tv.exit_reason_agreement(sim, _pine(rows_p))
    assert not a["ok"]
    assert a["worst_gap_pp"] == 100.0


# --- MFE/MAE excursion --------------------------------------------------------

def test_matching_excursions_agree_using_the_tick_fingerprint():
    rows_p = [("2025-09-02 09:30", 1, 100.0, "TP|MFE200t|MAE20t"),
              ("2025-09-03 10:15", -1, -50.0, "SL|MFE10t|MAE120t")]
    sim = [_T("2025-09-02 09:30", 1, 100.0, "TP", 201, 21),
           _T("2025-09-03 10:15", -1, -50.0, "SL", 11, 119)]
    e = tv.excursion_agreement(sim, _pine(rows_p), _Cfg())
    assert e["ok"] and e["paired"] == 2
    assert e["median_mfe_diff_ticks"] <= 4 and e["median_mae_diff_ticks"] <= 4


def test_a_different_intrabar_path_fails_the_excursion_gate():
    rows_p = [("2025-09-02 09:30", 1, 100.0, "TP|MFE200t|MAE20t"),
              ("2025-09-03 10:15", -1, -50.0, "SL|MFE10t|MAE120t")]
    # our excursions are far off — same endpoints, different path
    sim = [_T("2025-09-02 09:30", 1, 100.0, "TP", 120, 90),
           _T("2025-09-03 10:15", -1, -50.0, "SL", 80, 40)]
    e = tv.excursion_agreement(sim, _pine(rows_p), _Cfg())
    assert not e["ok"]


def test_excursion_falls_back_to_usd_when_no_fingerprint():
    """Auto Flat exits carry no MFE/MAE fingerprint; the USD columns convert to
    ticks via point value × tick × qty (2.0 × 0.25 = $0.50/tick here)."""
    exp = _pine([("2025-09-02 09:30", 1, 0.0, "Auto Flat")])
    exp.trades[0]["mfe_usd"] = 25.0     # 25 / 0.5 = 50 ticks
    exp.trades[0]["mae_usd"] = -10.0    # 20 ticks
    sim = [_T("2025-09-02 09:30", 1, 0.0, "EOD", 50, 20)]
    e = tv.excursion_agreement(sim, exp, _Cfg())
    assert e["ok"] and e["paired"] == 1


# --- full verdict -------------------------------------------------------------

def _kpi(passed, checks):
    return {"pass": passed, "checks": checks}

_ALL_OK = [{"name": n, "ok": True} for n in
           ("trade count", "profit factor", "win rate", "long/short split")]


def test_full_agreement_passes_the_deployment_gate():
    rows_p = [(f"2025-09-{2+i:02d} 09:30", 1, 100.0, "TP|MFE200t|MAE20t")
              for i in range(25)]
    sim = [_T(f"2025-09-{2+i:02d} 09:30", 1, 100.0, "TP", 201, 21) for i in range(25)]
    exp = _pine(rows_p)
    ev = tv.evaluate(sim, _Cfg(), exp, _kpi(True, _ALL_OK),
                     trace_diff(sim, exp), {"eligible": False})
    assert ev["status"] == "passed"
    assert all(d["ok"] for d in ev["dimensions"].values())


def test_exit_mix_disagreement_fails_even_with_matching_kpis():
    rows_p = [(f"2025-09-{2+i:02d} 09:30", 1, -50.0, "Auto Flat") for i in range(25)]
    sim = [_T(f"2025-09-{2+i:02d} 09:30", 1, -50.0, "SL", 10, 120) for i in range(25)]
    exp = _pine(rows_p)
    ev = tv.evaluate(sim, _Cfg(), exp, _kpi(True, _ALL_OK),
                     trace_diff(sim, exp), {"eligible": False})
    assert ev["status"] == "failed"
    assert not ev["dimensions"]["exit_reasons"]["ok"]


def test_data_parity_carries_over_only_when_shared_trades_behave():
    """KPI fails on trade count only, the residual is provably the vendor, and the
    exit mix + excursions agree on the trades both take -> accepted, data-parity."""
    # pine has 26 trades, sim has 24 of them (2 vendor-missing gaps)
    rows_p = [(f"2025-09-{2+i:02d} 09:30", 1, 100.0, "TP|MFE200t|MAE20t")
              for i in range(26)]
    sim = [_T(f"2025-09-{2+i:02d} 09:30", 1, 100.0, "TP", 201, 21) for i in range(24)]
    exp = _pine(rows_p)
    checks = [{"name": "trade count", "ok": False}] + \
             [{"name": n, "ok": True} for n in ("profit factor", "win rate", "long/short split")]
    ev = tv.evaluate(sim, _Cfg(), exp, _kpi(False, checks),
                     trace_diff(sim, exp), {"eligible": True})
    assert ev["status"] == "data_parity"
    assert ev["data_parity"] is True


def test_data_parity_refused_when_exit_mix_also_diverges():
    rows_p = [(f"2025-09-{2+i:02d} 09:30", 1, -50.0, "Auto Flat") for i in range(26)]
    sim = [_T(f"2025-09-{2+i:02d} 09:30", 1, -50.0, "SL", 10, 120) for i in range(24)]
    exp = _pine(rows_p)
    checks = [{"name": "trade count", "ok": False}] + \
             [{"name": n, "ok": True} for n in ("profit factor", "win rate", "long/short split")]
    ev = tv.evaluate(sim, _Cfg(), exp, _kpi(False, checks),
                     trace_diff(sim, exp), {"eligible": True})
    assert ev["status"] == "failed"
