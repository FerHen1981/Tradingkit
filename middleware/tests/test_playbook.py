"""Payout Playbook — grounded per-account route analysis (history × rules)."""
import datetime as dt

from app.playbook import (account_track, base_asset, build_playbook, contract_label,
                          ladder_rung, parse_size, recommend_setup)


def _hist(day_net: float, n: int) -> dict:
    return {dt.date(2026, 1, 1) + dt.timedelta(days=i): day_net for i in range(n)}


def test_ladder_and_parse():
    assert ladder_rung(50_000, 0) == 1_500 and ladder_rung(50_000, 2) == 2_000
    assert parse_size("Milking (2c/day-trail $150)", None) == 2.0
    assert base_asset("MGC1!") == "GC"


def test_contract_label_keeps_micro_instrument():
    assert contract_label(2, "MGC") == "2 MGC"      # NOT normalised to GC
    assert contract_label(1, "MES") == "1 MES"


def test_track_classification():
    assert account_track({"stage": "Funded", "size": 50_000, "dd_rule": "Trailing Equity Peak"}) == "trailing"
    assert account_track({"stage": "Funded", "size": 250_000, "dd_rule": "Trailing"}) == "static"
    assert account_track({"stage": "Eval", "size": 50_000}) == "eval"


def test_recommend_keeps_the_real_micro_instrument():
    r = recommend_setup({}, "trailing", "MGC")      # gold micro → El Tesoro, keep MGC
    assert r["instrument"] == "MGC" and r["strategy"] == "El Tesoro" and r["keep"]
    r2 = recommend_setup({}, "trailing", "NQ")      # NQ on funded = off-edge → MGC El Tesoro
    assert r2["instrument"] == "MGC" and r2["off_edge"]


def _acct(**kw):
    base = {"stage": "Funded", "size": 50_000, "firm": "Apex Trader Funding",
            "dd_rule": "Trailing Equity Peak", "starting": 50_000}
    base.update(kw)
    return base


def test_survival_route_when_dd_not_locked():
    # only +$800 profit → below the $2600 lock → survival, 1 ct, route says how much to lock
    a = _acct(current=50_800, buffer=1_800)
    pb = build_playbook(a, _hist(150, 4), "MGC")
    assert pb["phase"] == "survival" and pb["contracts"] == 1
    assert pb["rec_instrument"] == "MGC" and pb["rec_strategy"] == "El Tesoro"
    assert "1 MGC" in pb["route"] and "lock" in pb["route"].lower()
    assert pb["locked"] is False and pb["profit"] == 800


def test_milking_route_computes_days_and_bind():
    # locked ($2700 profit) but a HIGH rung (payouts_taken=5 → $3000) still ahead → pace plan
    a = _acct(current=52_700, buffer=2_600, payouts_taken=5,
              payout={"above_safety": 100, "eligible": False, "trading_days": 6})
    pb = build_playbook(a, _hist(200, 6), "MGC")
    assert pb["phase"] == "milking" and pb["contracts"] == 2 and pb["target"] == 3_000
    assert "to the rung" in pb["route"] and "Binds on" in pb["route"]
    assert pb["day_cap"] == round(0.30 * max(2700, 3000))     # 30% × rung = 900


def test_thin_buffer_flags_survival_drop():
    a = _acct(current=50_500, buffer=600)
    pb = build_playbook(a, _hist(120, 3), "MGC")
    assert pb["quality"] == "thin_buffer" and "critical" in pb["note"]


def test_off_edge_nq_on_funded():
    a = _acct(current=50_400, buffer=1_500)
    pb = build_playbook(a, _hist(100, 3), "NQ")
    assert pb["off_edge"] and pb["quality"] == "switch" and pb["rec_instrument"] == "MGC"


def test_eval_sprint_route():
    a = {"stage": "Eval", "size": 50_000, "firm": "Apex Trader Funding", "starting": 50_000, "current": 50_500}
    pb = build_playbook(a, _hist(100, 3), "MNQ")
    assert pb["track"] == "eval" and pb["phase"] == "eval-sprint" and pb["contracts"] == 5
    assert "pass" in pb["route"].lower()


def test_payout_ready_route():
    a = _acct(current=53_500, buffer=3_000,
              payout={"eligible": True, "withdrawable": 1500, "profit": 3500, "trading_days": 9})
    pb = build_playbook(a, _hist(200, 9), "MGC")
    assert pb["phase"] == "payout-ready" and "PAYOUT NOW" in pb["route"] and pb["quality"] == "payout"


def test_non_apex_firm_flagged():
    a = {"stage": "Eval", "size": 50_000, "firm": "My Funded Futures", "starting": 50_000, "current": 50_000}
    pb = build_playbook(a, {}, None)
    assert pb["firm_verified"] is False and "⚠" in pb["note"]
