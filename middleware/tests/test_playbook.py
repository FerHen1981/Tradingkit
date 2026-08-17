"""Payout Playbook sizing engine — deterministic checks on synthetic accounts."""
from app.playbook import (PlaybookParams, base_asset, build_playbook, contract_label,
                          ladder_rung, parse_size, recommend_setup)


def test_ladder_rung_progression():
    assert ladder_rung(50_000, 0) == 1_500
    assert ladder_rung(50_000, 2) == 2_000
    assert ladder_rung(50_000, 99) == 3_000        # clamps at the top rung


def test_parse_size_from_notion_fields():
    assert parse_size("Milking (2c/day-trail $150)", None) == 2.0
    assert parse_size("Pass-hunter (5c/TP144)", None) == 5.0
    assert parse_size(None, "2-4 contracts") == 3.0
    assert parse_size(None, "10 contracts") == 10.0
    assert parse_size(None, None) is None


def test_base_asset_normalises_micros():
    assert base_asset("MGC") == "GC" and base_asset("MGC1!") == "GC"
    assert base_asset("MES") == "ES" and base_asset("ES") == "ES"
    assert base_asset(None) is None


def test_contract_label_whole_and_micros():
    assert contract_label(0.7, "GC") == "7 MGC"        # sub-mini → micros
    assert contract_label(7.5, "ES") == "7 ES + 5 MES"  # minis + micros
    assert contract_label(3.0, "ES") == "3 ES"          # whole
    assert contract_label(2.0, "MGC") == "2 GC"         # normalises the asset


def test_recommend_keeps_current_validated_edge():
    # account already running gold (micro) → keep GC · El Tesoro, no switch
    rec = recommend_setup({"stage": "Funded"}, None, current_asset="MGC")
    assert rec["asset"] == "GC" and rec["strategy"] == "El Tesoro" and rec["keep"]


def test_recommend_funded_defaults_to_gc_workhorse():
    # no current edge, ES measured higher — still default to the robust GC workhorse
    edge = {"GC": {"expectancy": 40, "pf": 1.2, "n": 200},
            "ES": {"expectancy": 90, "pf": 1.3, "n": 200}}
    rec = recommend_setup({"stage": "Funded"}, edge, current_asset=None)
    assert rec["asset"] == "GC" and rec["strategy"] == "El Tesoro" and not rec["keep"]


def _daily(base: float, n: int = 40) -> dict:
    out = {}
    for i in range(n):
        out[f"2026-01-{i+1:02d}"] = base + (90 if i % 2 else -70)   # real winners AND losers
    return out


def test_healthy_gold_account_keeps_el_tesoro_and_sizes():
    acct = {"size": 50_000, "stage": "Funded", "payouts_taken": 0, "buffer": 2_500,
            "avg_loss": 140.0, "fase_config": "Milking (2c/day-trail $150)"}
    pb = build_playbook(acct, _daily(60), "MGC", "El Tesoro",
                        edge_stats={"GC": {"expectancy": 60, "pf": 1.3, "n": 200}},
                        params=PlaybookParams(sims=400))
    assert pb["rec_asset"] == "GC" and pb["rec_strategy"] == "El Tesoro" and not pb["switch"]
    assert pb["source"] == "edge" and pb["contracts_label"]
    assert pb["p_breach"] <= 0.15
    assert pb["day_lock"] <= 0.30 * 1_500 + 1 and pb["sl_cap"]


def test_thin_data_falls_back_to_phase_default():
    acct = {"size": 50_000, "stage": "Funded", "payouts_taken": 1, "buffer": 2_500,
            "fase_config": "Milking (2c/day-trail $150)"}
    pb = build_playbook(acct, {"2026-01-01": 100.0}, "GC", "El Tesoro",
                        params=PlaybookParams(sims=200))
    assert pb["source"] == "default" and pb["quality"] == "default"
    assert pb["contracts"] == 2.0 and pb["contracts_label"] == "2 GC"   # the Milking default


def test_fresh_eval_gets_passhunter_default():
    acct = {"size": 50_000, "stage": "Eval", "payouts_taken": 0, "buffer": 2_500}
    pb = build_playbook(acct, {}, None, None, params=PlaybookParams(sims=200))
    assert pb["source"] == "default" and pb["contracts"] == 5.0     # Pass-hunter 5c
    assert pb["target"] == 3_000 and pb["mode"] == "eval-pass"
