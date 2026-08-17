"""Payout Playbook — max-payout route analysis (history × rules, per-cycle)."""
import datetime as dt

from app.playbook import (account_track, base_asset, build_playbook, contract_label,
                          dd_amount, ladder_caps, ladder_rung, parse_size, recommend_setup)


def _hist(day_net: float, n: int) -> dict:
    return {dt.date(2026, 1, 1) + dt.timedelta(days=i): day_net for i in range(n)}


def _acct(**kw):
    base = {"stage": "Funded", "size": 50_000, "firm": "Apex Trader Funding",
            "dd_rule": "Trailing Equity Peak", "starting": 50_000}
    base.update(kw)
    return base


def test_ladder_and_caps_and_dd():
    assert ladder_rung(50_000, 0) == 1_500
    assert ladder_caps(50_000) == [1_500, 1_500, 2_000, 2_500, 2_500, 3_000]  # total 13k
    assert sum(ladder_caps(50_000)) == 13_000
    assert dd_amount({"dd_rule": "EOD ($2000)"}, 50_000) == 2_000          # EOD DD parsed
    assert dd_amount({"dd_rule": "Trailing"}, 50_000) == 2_500             # Apex default
    assert base_asset("MGC1!") == "GC" and parse_size("Milking (2c/day-trail $150)", None) == 2.0


def test_contract_label_keeps_micro_instrument():
    assert contract_label(2, "MGC") == "2 MGC" and contract_label(1, "MES") == "1 MES"


def test_track_classification():
    assert account_track({"stage": "Funded", "size": 50_000, "dd_rule": "Trailing Equity Peak"}) == "trailing"
    assert account_track({"stage": "Funded", "size": 250_000, "dd_rule": "Trailing"}) == "static"
    assert account_track({"stage": "Eval", "size": 50_000}) == "eval"


def test_recommend_keeps_micro_instrument():
    r = recommend_setup({}, "trailing", "MGC")
    assert r["instrument"] == "MGC" and r["strategy"] == "El Tesoro" and r["keep"]
    assert recommend_setup({}, "trailing", "NQ")["off_edge"]


def test_survival_below_safety_net():
    # +$800 profit, safety net $2,600 → survival, 1 ct, route says how much to the safety net
    a = _acct(current=50_800, buffer=1_800)
    pb = build_playbook(a, _hist(150, 4), "MGC")
    assert pb["phase"] == "survival" and pb["contracts"] == 1 and pb["profit"] == 800
    assert pb["safety"] == 2_600 and pb["withdrawable_now"] == 0
    assert "safety net" in pb["route"] and "1 MGC" in pb["route"]


def test_building_warns_it_leaves_money_on_the_table():
    # profit $3,000 → above safety ($400), but the full rung-1 cap is $1,500 (needs profit $4,100)
    a = _acct(current=53_000, buffer=2_600, payouts_taken=0,
              payout={"eligible": False, "trading_days": 6})
    pb = build_playbook(a, _hist(200, 6), "MGC")
    assert pb["phase"] == "milking" and pb["cap"] == 1_500
    assert pb["withdrawable_now"] == 400 and pb["leaving"] == 1_100 and pb["to_full"] == 1_100
    assert "FULL $1,500" in pb["route"] and "leaves $1,100" in pb["route"]


def test_full_cap_in_reach_needs_days():
    # profit $4,200 ≥ target $4,100 but only 5 trading days → hold for 3 more, then full cap
    a = _acct(current=54_200, buffer=2_600, payouts_taken=0,
              payout={"eligible": False, "trading_days": 5})
    pb = build_playbook(a, _hist(200, 5), "MGC")
    assert pb["phase"] == "milking" and "in reach" in pb["route"] and "3 more" in pb["route"]


def test_payout_ready_pulls_full_cap_and_carries_excess():
    a = _acct(current=54_200, buffer=3_000, payouts_taken=0,
              payout={"eligible": True, "trading_days": 9})
    pb = build_playbook(a, _hist(200, 9), "MGC")
    assert pb["phase"] == "payout-ready" and pb["quality"] == "payout"
    assert "PAYOUT" in pb["route"] and "FULL $1,500" in pb["route"] and "carries" in pb["route"]


def test_maxed_account_minimizes_risk():
    a = _acct(current=53_000, payout_total=13_000, payout={"eligible": False, "trading_days": 6})
    pb = build_playbook(a, _hist(200, 6), "MGC")
    assert pb["phase"] == "maxed" and "Maxed" in pb["route"] and pb["contracts"] == 1


def test_thin_buffer_flags_critical():
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
    assert pb["track"] == "eval" and pb["contracts"] == 5 and "pass" in pb["route"].lower()


def test_exact_settables_day_cap_and_dll():
    # building to the full cap: day-cap paces to_full over the window; DLL = 20% of the buffer
    a = _acct(current=53_000, buffer=2_600, payouts_taken=0,
              payout={"eligible": False, "trading_days": 6, "days_to_go": 2})
    pb = build_playbook(a, _hist(200, 6), "MGC")
    assert pb["day_cap"] == 550 and pb["days_plan"] == 2      # to_full 1100 / 2 days
    assert pb["dll"] == 520 and pb["cons_cap"] == 1_230       # 20% of 2600 ; 30% of 4100


def test_survival_settables_stay_small():
    a = _acct(current=50_800, buffer=1_800)
    pb = build_playbook(a, _hist(150, 4), "MGC")
    assert pb["day_cap"] == 150 and pb["dll"] == 360          # doctrine trail ; 20% of 1800


def test_consistency_broken_heals_as_total_wins_grow():
    # a $1,383 top day at 73% of wins → the 30% ceiling RISES as total wins grow to best/30%.
    a = _acct(current=51_898, buffer=2_000, payouts_taken=0,
              payout={"eligible": False, "trading_days": 3, "consistency_pct": 73.0, "profit": 1898})
    hist = {dt.date(2026, 1, 1): 1383, dt.date(2026, 1, 2): 300, dt.date(2026, 1, 3): 215}
    pb = build_playbook(a, hist, "MES")
    assert pb["broken"] and pb["heal_total"] == round(1383 / 0.30)   # total wins needed = 4610
    total_win = round(1383 / 0.73)                                   # denominator = SUM of wins, not net
    assert pb["heal_deficit"] == round(4610 - total_win)             # grow wins by this much
    assert pb["day_cap"] == 1383                                     # optimize UP to the outlier, not $150
    assert pb["days_to_heal"] and "run days up to" in pb["note"]     # bigger days heal faster


def test_non_apex_firm_flagged():
    a = {"stage": "Eval", "size": 50_000, "firm": "My Funded Futures", "starting": 50_000, "current": 50_000}
    pb = build_playbook(a, {}, None)
    assert pb["firm_verified"] is False and "⚠" in pb["note"]
