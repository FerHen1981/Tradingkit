"""Payout Playbook sizing engine — deterministic checks on synthetic accounts."""
from app.playbook import (PlaybookParams, build_playbook, ladder_rung,
                          parse_size, recommend_setup)


def test_ladder_rung_progression():
    assert ladder_rung(50_000, 0) == 1_500      # first payout
    assert ladder_rung(50_000, 2) == 2_000      # third rung
    assert ladder_rung(50_000, 99) == 3_000     # clamps at the top rung


def test_parse_size_from_notion_fields():
    assert parse_size("Milking (2c/day-trail $150)", None) == 2.0
    assert parse_size("Pass-hunter (5c/TP144)", None) == 5.0
    assert parse_size(None, "2-4 contracts") == 3.0
    assert parse_size(None, "10 contracts") == 10.0
    assert parse_size(None, None) is None


def test_recommend_prefers_measured_funded_edge():
    acct = {"stage": "Funded"}
    edge = {"GC": {"expectancy": 40, "pf": 1.2, "n": 200},
            "ES": {"expectancy": 90, "pf": 1.3, "n": 200}}
    rec = recommend_setup(acct, edge)
    assert rec["asset"] == "ES" and rec["strategy"] == "El Rey" and rec["measured"]


def test_recommend_defaults_to_gc_without_data():
    rec = recommend_setup({"stage": "Funded"}, None)
    assert rec["asset"] == "GC" and rec["strategy"] == "El Tesoro" and not rec["measured"]


def _daily(mean: float, n: int = 40) -> dict:
    """A steady per-2-contract daily series: alternating win/loss around `mean`."""
    out = {}
    for i in range(n):
        out[f"2026-01-{i+1:02d}"] = mean + (60 if i % 2 else -40)
    return out


def test_healthy_account_gets_a_size_and_caps():
    acct = {"size": 50_000, "stage": "Funded", "payouts_taken": 0,
            "buffer": 2_500, "avg_loss": 120.0,
            "fase_config": "Milking (2c/day-trail $150)"}
    pb = build_playbook(acct, _daily(120), "GC", "El Tesoro",
                        edge_stats={"GC": {"expectancy": 60, "pf": 1.3, "n": 200}},
                        params=PlaybookParams(sims=400))
    assert pb["target"] == 1_500 and pb["mode"] == "payout"
    assert pb["rec_contracts"] and pb["rec_contracts"] <= 10
    assert pb["p_breach"] <= 0.15                       # respects the breach budget
    assert pb["day_lock"] and pb["day_lock"] <= 0.30 * 1_500 + 1   # 30% consistency cap
    assert pb["sl_cap"] and pb["day_stop"] < 0


def test_thin_data_is_flagged_not_faked():
    acct = {"size": 50_000, "stage": "Funded", "payouts_taken": 1,
            "buffer": 2_500, "fase_config": "Milking (2c/day-trail $150)"}
    pb = build_playbook(acct, {"2026-01-01": 100.0}, "GC", "El Tesoro",
                        params=PlaybookParams(sims=200))
    assert pb["quality"] == "thin_data" and pb["rec_contracts"] is None


def test_no_buffer_is_flagged():
    acct = {"size": 50_000, "stage": "Funded", "payouts_taken": 0,
            "fase_config": "Milking (2c/day-trail $150)"}
    pb = build_playbook(acct, _daily(120), "GC", "El Tesoro",
                        params=PlaybookParams(sims=200))
    assert pb["quality"] == "no_buffer"
