"""Payout Playbook — max-payout route analysis (history × rules, per-cycle)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))   # run this file on its own

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


def test_eval_default_is_el_toro_on_mini():
    # no current asset, no data → default eval passer is NQ · El Toro on the full MINI (not micro)
    r = recommend_setup({"stage": "Eval"}, "eval", None)
    assert r["base"] == "NQ" and r["strategy"] == "El Toro" and r["instrument"] == "NQ"


def test_eval_keeps_mini_even_if_on_micro():
    # eval should run the mini; a micro-traded eval account is normalised up to the mini
    r = recommend_setup({"stage": "Eval"}, "eval", "MNQ")
    assert r["instrument"] == "NQ" and r["strategy"] == "El Toro"


def test_eval_ranks_by_registered_passes():
    # registered eval passes (from Notion) win over net: NQ has more passes → El Toro, despite lower net
    edge = {"NQ": {"net": 1000, "passes": 12, "n": 200}, "GC": {"net": 9000, "passes": 3, "n": 200}}
    r = recommend_setup({"stage": "Eval"}, "eval", None, edge)
    assert r["base"] == "NQ" and r["strategy"] == "El Toro" and "passes (12)" in r["why"]


def test_survival_below_safety_net():
    # +$800 profit, safety net $2,600 → survival, 1 ct, route says how much to the safety net
    a = _acct(current=50_800, buffer=1_800)
    pb = build_playbook(a, _hist(150, 4), "MGC")
    assert pb["phase"] == "survival" and pb["contracts"] == 1 and pb["profit"] == 800
    assert pb["safety"] == 2_600 and pb["withdrawable_now"] == 0
    assert "safety net" in pb["route"] and "Survival" in pb["route"]


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
    # buffer $2,000 → DLL $400 → safe heal day-cap = min(best 1383, 3×400) = 1200 (risk/reward-bounded)
    assert pb["day_cap"] == 1200 and pb["risk_capped"] and "SAFE" in pb["note"]
    assert pb["days_to_heal"]


def test_broken_heal_uses_full_outlier_when_buffer_is_roomy():
    a = _acct(current=51_898, buffer=8_000, payouts_taken=0,       # roomy buffer → DLL $1,600, 3:1 = $4,800 > best
              payout={"eligible": False, "trading_days": 3, "consistency_pct": 73.0, "profit": 1898})
    hist = {dt.date(2026, 1, 1): 1383, dt.date(2026, 1, 2): 300, dt.date(2026, 1, 3): 215}
    pb = build_playbook(a, hist, "MES")
    assert pb["day_cap"] == 1383 and not pb["risk_capped"] and "day-cap" in pb["note"]


def test_edge_size_from_per_trade_stats():
    from app.playbook import PlaybookParams, edge_size
    acct = {"expectancy": 60, "avg_loss": 200, "win_pct": 55, "trades": 40}   # at 2-contract size
    es = edge_size(acct, 2.0, 8, dll=400, params=PlaybookParams())
    assert es["exp_pc"] == 30 and es["loss_pc"] == 100 and es["tpd"] == 5      # per contract, trades/day
    assert es["size"] == 1 and es["day_net"] == 150                            # round(400/300)=1; 1×30×5


def test_build_uses_edge_size_when_stats_present():
    a = _acct(current=53_000, buffer=2_000, expectancy=60, avg_loss=200, win_pct=55, trades=40,
              fase_config="Milking (2c/day-trail $150)",
              payout={"eligible": False, "trading_days": 8, "consistency_pct": 20})
    pb = build_playbook(a, _hist(300, 8), "MGC")
    assert pb["exp_pc"] == 30 and pb["contracts"] == 1 and pb["day_cap"] == 150     # data-driven whole size


def test_non_apex_firm_flagged():
    a = {"stage": "Eval", "size": 50_000, "firm": "My Funded Futures", "starting": 50_000, "current": 50_000}
    pb = build_playbook(a, {}, None)
    assert pb["firm_verified"] is False and "⚠" in pb["note"]


# --- consistency belongs to the account type, not to every account ------------------------------

def _eval_acct(**kw):
    a = {"id": "214", "full": "APEX27002500000214", "firm": "Apex Trader Funding", "stage": "Eval",
         "size": 50_000, "starting": 50_000, "current": 52_000, "dd_rule": "Trailing Equity Peak",
         "firm_program": "apex_50k_legacy_eval",
         "payout": {"stage": "Eval", "profit": 2_000, "target": 3_000, "trading_days": 6,
                    "eligible": False, "days_to_go": 1, "consistency_pct": 40.0}}
    a.update(kw)
    return a


def test_an_evaluation_carries_no_consistency_rule():
    """The firm-name fallback handed every account Apex's 30%. On an evaluation there is no such
    rule, so a 40% day is not 'broken' — and the cockpit must not quote a ceiling that does not
    exist."""
    pb = build_playbook(_eval_acct(), _hist(300, 6), "MGC")
    assert pb["broken"] is False
    assert pb["consistency_limit"] is None
    assert "consistency" not in pb["note"]


def test_broken_consistency_without_a_day_cap_does_not_crash():
    """track 'eval' and 'maxed' both leave set_day_cap at None, and the broken-consistency flag
    formatted it — TypeError, and the whole playbook for that account was dropped."""
    a = _acct(current=63_000, buffer=2_600, payouts_taken=6, payout_total=13_000,
              firm_program="apex_50k_legacy_pa",
              payout={"eligible": True, "trading_days": 9, "days_to_go": 0,
                      "consistency_pct": 42.0, "cap": 3_000, "total_cap": 13_000,
                      "above_safety": 10_400})
    pb = build_playbook(a, _hist(1_200, 9), "MGC")
    assert pb["phase"] == "maxed" and pb["broken"] is True
    assert "total wins reach" in pb["note"]        # and it did not raise


def test_the_coaching_text_quotes_the_account_types_own_ceiling():
    a = _acct(current=53_000, buffer=2_600, firm_program="apex_50k_eod_pa",
              payout={"eligible": False, "trading_days": 6, "days_to_go": 0,
                      "consistency_pct": 67.0})
    pb = build_playbook(a, _hist(200, 6), "MGC")
    assert pb["consistency_limit"] == 0.50
    assert "30%" not in pb["note"]        # 30 is the legacy number, not this account type's
