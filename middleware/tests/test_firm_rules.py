"""Firm-program rules read from data/propfirms.json (THE single source of truth)."""
import datetime as dt

from app import firm_rules
from app.payout_rules import evaluate
from app.playbook import build_playbook


def _hist(day_net, n):
    return {dt.date(2026, 1, 1) + dt.timedelta(days=i): day_net for i in range(n)}


def test_resolve_size_agnostic_family_to_concrete_key():
    # Notion families are size-agnostic; the JSON keys are size-specific.
    assert firm_rules.resolve_key("apex_legacy_pa", 50_000) == "apex_50k_legacy_pa"
    assert firm_rules.resolve_key("apex_intraday_pa", 50_000) == "apex_50k_intraday_pa"
    assert firm_rules.resolve_key("apex_legacy_eval", 25_000) == "apex_25k_legacy_eval"
    assert firm_rules.resolve_key("apex_legacy_eval", 250_000) == "apex_250k_legacy_eval"
    # already-concrete keys pass through; unknowns → None
    assert firm_rules.resolve_key("apex_50k_eod_pa", 50_000) == "apex_50k_eod_pa"
    assert firm_rules.resolve_key("mffu_50k_eval", 50_000) == "mffu_50k_eval"
    assert firm_rules.resolve_key("does_not_exist", 50_000) is None
    assert firm_rules.resolve_key(None, 50_000) is None


def test_rules_dict_from_registry():
    r = firm_rules.rules("apex_50k_legacy_pa")
    assert r["firm"] == "Apex" and r["stage"] == "funded"
    assert r["consistency"] == 0.30 and r["min_days"] == 8          # legacy: 30% / 8 days
    assert r["drawdown"] == 2500 and r["trailing_locks_at"] == 2600
    assert r["max_position"] == 10 and r["min_payout"] == 500
    assert r["payout_ladder"] == [1500, 1500, 2000, 2500, 2500, 3000]
    assert r["drawdown_type"] == "eod_trailing" and r["verified"] is True   # owner-confirmed
    r2 = firm_rules.rules("apex_50k_intraday_pa")
    assert r2["consistency"] == 0.50 and r2["min_days"] == 5        # intraday: 50% / 5 days
    assert firm_rules.rules("nope") is None


def test_playbook_uses_program_rules_over_apex_default():
    # legacy_pa vs intraday_pa differ ONLY by their program → the playbook must reflect it.
    base = {"stage": "Funded", "size": 50_000, "firm": "Apex Trader Funding", "starting": 50_000,
            "current": 53_000, "buffer": 2_000, "payouts_taken": 0,
            "payout": {"eligible": False, "trading_days": 6}}
    legacy = build_playbook({**base, "firm_program": "apex_50k_legacy_pa"}, _hist(200, 6), "MGC")
    intraday = build_playbook({**base, "firm_program": "apex_50k_intraday_pa"}, _hist(200, 6), "MGC")
    assert legacy["consistency_limit"] == 0.30 and legacy["min_days"] == 8
    assert intraday["consistency_limit"] == 0.50 and intraday["min_days"] == 5
    assert intraday["cons_cap"] > legacy["cons_cap"]               # 50% ceiling is higher than 30%
    assert legacy["program"] == "apex_50k_legacy_pa"


def test_program_caps_size_to_max_position():
    # 25k legacy eval maxes at 4 contracts → the aggressive 5c eval size is capped to 4.
    a = {"stage": "Eval", "size": 25_000, "firm": "Apex Trader Funding", "starting": 25_000,
         "current": 25_500, "firm_program": "apex_25k_legacy_eval"}
    pb = build_playbook(a, _hist(100, 3), "MNQ")
    assert pb["track"] == "eval" and pb["contracts"] == 4 and pb["target"] == 1_500


def test_drawdown_type_drives_track():
    from app.playbook import account_track
    # the program's drawdown_type is authoritative for the trailing/static split on a funded account
    assert account_track({"stage": "Funded", "drawdown_type": "static", "size": 50_000}) == "static"
    assert account_track({"stage": "Funded", "drawdown_type": "eod_trailing", "size": 50_000}) == "trailing"
    assert account_track({"stage": "Funded", "drawdown_type": "intraday_trailing", "size": 50_000}) == "trailing"
    assert account_track({"stage": "Eval", "drawdown_type": "static", "size": 25_000}) == "eval"
    assert account_track({"stage": "Funded", "size": 250_000}) == "static"   # no dd_type → size fallback


def test_evaluate_program_override_changes_gates():
    # same numbers, different program → different min-days + consistency gates (L5 == L10 source).
    prog_legacy = firm_rules.rules("apex_50k_legacy_pa")            # 30% / 8
    prog_intra = firm_rules.rules("apex_50k_intraday_pa")           # 50% / 5
    hist = _hist(300, 6)
    a = evaluate(50_000, 50_000, 53_000, "Funded", hist, 0, program=prog_legacy)
    b = evaluate(50_000, 50_000, 53_000, "Funded", hist, 0, program=prog_intra)
    days_a = next(r for r in a.rules if r.name == "Trading days")
    days_b = next(r for r in b.rules if r.name == "Trading days")
    assert not days_a.ok and "6/8" in days_a.detail                # legacy needs 8
    assert days_b.ok and "6/5" in days_b.detail                    # intraday needs 5
