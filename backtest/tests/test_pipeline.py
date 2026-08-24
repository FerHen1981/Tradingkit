"""Pipeline v7 — spine, fleet transcription, stage 0 and stage 1."""
import numpy as np
import pandas as pd
import pytest

from backtest.pipeline import fleet
from backtest.pipeline.audit import audit
from backtest.pipeline.parity import compare
from backtest.pipeline.stages import BY_KEY, GROUND_RULES, STAGES


def test_twelve_stages_with_two_hard_gates():
    assert [s.n for s in STAGES] == list(range(12))
    assert [s.key for s in STAGES if s.hard] == ["parity", "tv_validation"]
    assert len(GROUND_RULES) == 12
    assert BY_KEY["parity"].n == 1


def test_fleet_matches_released_pine_inputs():
    """Spot-check the transcription against MEX_FLEET_PACKAGE_2026-08-23."""
    assert len(fleet.names()) == 9
    c = fleet.engine_config("EL_TESORO_MGC_CON_EOD")
    assert (c.contract.symbol, c.contract_size) == ("MGC", 7.0)
    assert (c.gap_min_ticks, c.gap_max_ticks, c.cvd_trend_count) == (11.0, 16.0, 6)
    assert (c.fixed_stop_ticks, c.r_multiple, c.expiry_bars) == (140.0, 2.25, 12)
    m = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    assert (m.gap_min_ticks, m.gap_max_ticks, m.cvd_trend_count) == (10.0, 22.0, 6)
    assert (m.fixed_stop_ticks, m.r_multiple) == (120.0, 1.75)


def test_fleet_is_uniform_where_the_scripts_are():
    """Every released script has CVD+FVG on, BE/trail off, R-multiple, fixed stop."""
    for n in fleet.names():
        c = fleet.engine_config(n)
        assert c.use_cvd_filter and c.use_cvd_streak and c.use_gap_filter
        assert not c.use_breakeven and not c.use_trail
        assert c.tp_mode == "R-multiple" and c.stop_swing is False
        assert c.cvd_source == "proxy"          # ground rule 4
        assert c.day_trail_model.startswith("Activation")


def _frame(n=600, bad=False):
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 0.05, n))
    high = close + 0.1
    low = close - 0.1
    open_ = close.copy() if not bad else close + 5.0      # bad: open outside [low, high]
    idx = pd.date_range("2026-01-05", periods=n, freq="min", tz="America/New_York")
    df = pd.DataFrame({"et": idx, "Open": open_, "High": high, "Low": low, "Close": close,
                       "Volume": 1.0, "Delta": rng.integers(-5, 5, n).astype(float)})
    from backtest.data import _derive
    return _derive(df)


def test_stage0_reports_shape_and_passes_clean_data():
    r = audit(_frame(), "GC")
    assert r["bars"] == 600 and r["ohlc_violations"] == 0
    assert "New_York" in r["timezone"]
    assert not [f for f in r["findings"] if f["severity"] == "high"]


def test_stage0_flags_broken_ohlc():
    r = audit(_frame(bad=True), "GC")
    assert r["ohlc_violations"] > 0
    assert any(f["severity"] == "high" for f in r["findings"])


def test_stage0_flags_a_dead_delta_column():
    """A Delta column of zeros would silently gate every trade (this is D-09)."""
    df = _frame()
    df["Delta"] = 0.0
    r = audit(df, "GC")
    assert any("Delta column is effectively empty" in f["message"] for f in r["findings"])


class _Exp:
    """Minimal stand-in for a parsed TradingView export."""
    def __init__(self, trades):
        self._t = trades

    def stats(self):
        nets = [t["net"] for t in self._t]
        wins = [x for x in nets if x > 0]
        gl = -sum(x for x in nets if x <= 0)
        return {"trades": len(nets), "net": sum(nets),
                "win_rate_pct": round(100 * len(wins) / len(nets), 1),
                "profit_factor": round(sum(wins) / gl, 2) if gl else float("inf"),
                "longs": sum(1 for t in self._t if t["dir"] > 0),
                "shorts": sum(1 for t in self._t if t["dir"] < 0)}


def _export(n=100, pf_net=(200, -100)):
    t = []
    for i in range(n):
        win = i % 2 == 0
        t.append({"net": pf_net[0] if win else pf_net[1], "dir": 1 if i % 3 else -1})
    return _Exp(t)


def test_stage1_passes_when_the_simulator_matches():
    exp = _export()
    s = exp.stats()
    sim = {"trades": s["trades"], "profit_factor": s["profit_factor"],
           "win_rate_pct": s["win_rate_pct"], "longs": s["longs"], "shorts": s["shorts"]}
    assert compare(sim, exp)["pass"]


def test_stage1_fails_on_a_materially_different_trade_count():
    exp = _export(100)
    s = exp.stats()
    sim = {"trades": 40, "profit_factor": s["profit_factor"],
           "win_rate_pct": s["win_rate_pct"], "longs": s["longs"], "shorts": s["shorts"]}
    out = compare(sim, exp)
    assert not out["pass"]
    assert not [c for c in out["checks"] if c["name"] == "trade count"][0]["ok"]
    assert "NOT at parity" in out["verdict"]


# --- price-series substitution (mini stands in for its micro) -------------------

def test_every_fleet_market_has_a_known_twin():
    from backtest.pipeline import fleet
    for n in fleet.names():
        own, twin = fleet.acceptable_symbols(n)
        assert twin, f"{n}: markt {own} heeft geen twin — trap 1 verliest die route"
        assert fleet.TWIN[twin] == own, "twin-map is niet symmetrisch"


def test_twin_shares_tick_size_but_not_point_value():
    """The whole substitution rests on this: same ticks (so identical FVG bands,
    stops and R-targets) but a different dollar multiplier."""
    from backtest.config import CONTRACTS
    from backtest.pipeline import fleet
    for micro, mini in fleet.TWIN.items():
        a, b = CONTRACTS.get(micro), CONTRACTS.get(mini)
        if not a or not b:
            continue
        assert a.mintick == b.mintick, f"{micro}/{mini}: tick size verschilt"
        assert a.pointvalue != b.pointvalue, f"{micro}/{mini}: geen twin maar hetzelfde contract"


def test_a_micro_and_its_mini_produce_the_same_trade_sequence(tmp_path):
    """The measured claim behind fleet.TWIN. Point value scales the dollars; it
    must not move the trade count, win rate or long/short split — those are the
    checks stage 1 gates on."""
    import dataclasses

    import numpy as np
    import pandas as pd

    from backtest import data as dm, indicators as im
    from backtest.config import contract
    from backtest.engine import Engine
    from backtest.metrics import kpis
    from backtest.pipeline import fleet

    # volatile enough that FVGs land inside MATADOR's 10-22 tick band; a quiet
    # random walk produces zero trades and would make this test vacuous.
    rng = np.random.default_rng(7)
    n, sigma = 60_000, 4.0
    px = 6000 + np.cumsum(rng.normal(0, sigma, n))
    idx = pd.date_range("2025-09-02 00:00", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "Open": px, "Close": px + rng.normal(0, sigma * 0.7, n),
        "High": px + np.abs(rng.normal(0, sigma * 2, n)),
        "Low": px - np.abs(rng.normal(0, sigma * 2, n)),
        "Volume": rng.integers(50, 900, n).astype(float),
        "Delta": np.zeros(n),
    })
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    raw.insert(0, "DateTime", idx.strftime("%d-%m-%Y %H:%M:%S %z"))
    csv = tmp_path / "twin.csv"
    raw.to_csv(csv, index=False)
    df = dm.load(str(csv), cache=False)

    base = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    out = {}
    for sym in ("MES", "ES"):
        cfg = dataclasses.replace(base, contract=contract(sym))
        out[sym] = kpis(Engine(cfg, df, im.compute(df, cfg), research_mode=True).run())

    assert out["MES"]["trades"] >= 10, "te weinig trades — de test bewijst dan niets"
    for key in ("trades", "win_rate_pct", "longs", "shorts"):
        assert out["MES"][key] == out["ES"][key], (
            f"{key} verschilt tussen micro en mini: "
            f"{out['MES'][key]} vs {out['ES'][key]}")


# --- window coverage: a short tail is not the same as a missing dataset ---------

def test_window_overlap_grades_a_short_tail_apart_from_a_real_gap():
    """The VPS case: 20-year files that stop 8 days before the export's end must
    read as usable, while a dataset ending months early must not."""
    from datetime import datetime

    from backtest.pipeline.cli import window_overlap

    a, b = datetime(2025, 8, 24), datetime(2026, 8, 23)
    near = window_overlap(datetime(2011, 12, 4), datetime(2026, 8, 16), a, b)
    assert near["verdict"] == "bijna volledig"
    assert near["missing_days"] == 7 or near["missing_days"] == 8, near
    assert near["missing_frac"] < 0.05

    full = window_overlap(datetime(2011, 12, 4), datetime(2026, 9, 1), a, b)
    assert full["verdict"] == "volledig"
    assert full["missing_days"] == 0

    short = window_overlap(datetime(2011, 12, 4), datetime(2025, 12, 31), a, b)
    assert short["verdict"] == "te kort"
    assert short["missing_frac"] > 0.5

    late = window_overlap(datetime(2026, 6, 1), datetime(2026, 8, 23), a, b)
    assert late["verdict"] == "te kort", "een dataset die pas laat begint mist het begin"
    assert late["first_gap_days"] > 200

    assert window_overlap(None, None, a, b)["verdict"] == "onbekend"


def test_short_tail_tolerance_stays_under_the_stage1_trade_tolerance():
    """The 5% line only means anything while it is below the gate it defends."""
    import inspect

    from backtest.pipeline import parity
    from backtest.pipeline.cli import SHORT_TAIL_TOLERANCE

    trade_tol = inspect.signature(parity.compare).parameters["trade_tol"].default
    assert SHORT_TAIL_TOLERANCE < trade_tol


# --- the account layer must be ACTIVE during a parity run ----------------------

def _pa_frame(tmp_path, n=60_000, sigma=4.0, seed=7):
    import numpy as np
    import pandas as pd

    from backtest import data as dm
    rng = np.random.default_rng(seed)
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
    csv = tmp_path / "pa.csv"
    raw.to_csv(csv, index=False)
    return dm.load(str(csv), cache=False)


def test_research_mode_switches_off_the_account_layer(tmp_path):
    """The bug behind MATADOR's exit mix: `research_mode=True` disables the whole
    account overlay, so the PA daily loss limit never closes a position and every
    DLL exit becomes a full stop-out instead. Stage 1 must therefore run with the
    overlay ON, because the Pine script does."""
    from collections import Counter

    from backtest import indicators as im
    from backtest.engine import Engine
    from backtest.pipeline import fleet

    df = _pa_frame(tmp_path)
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    assert cfg.is_pa and cfg.phase_on, "de config is geen PA-account, test bewijst niets"

    def reasons(research):
        r = Engine(cfg, df, im.compute(df, cfg), research_mode=research).run()
        assert r.trades, "geen trades — de test bewijst niets"
        return Counter(t.reason for t in r.trades)

    off = reasons(True)
    on = reasons(False)
    assert off["PA Daily Loss Limit"] == 0, "research_mode zou de accountlaag uit moeten zetten"
    assert on["PA Daily Loss Limit"] > 0, "de DLL sluit geen enkele positie met de laag AAN"
    assert on != off, "de exit-mix veranderde niet — de laag doet niets"
    # A DLL close REPLACES another exit rather than adding a trade, and a day
    # halt can only block later entries. Which exit type it displaces depends on
    # the data, so that is deliberately not asserted here.
    assert sum(on.values()) <= sum(off.values())
    assert sum(on.values()) - on["PA Daily Loss Limit"] < sum(off.values())


def test_a_pa_breach_resets_instead_of_halting(tmp_path):
    """Pine runs with "PA backtest mode (breach marks, does NOT close perma)", so
    the simulator may not stop trading at the first trailing breach — that would
    silently truncate the comparison window."""
    from backtest import indicators as im
    from backtest.engine import Engine
    from backtest.pipeline import fleet

    df = _pa_frame(tmp_path)
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    res = Engine(cfg, df, im.compute(df, cfg), research_mode=False).run()
    assert res.resolve_bar == -1, "PA-account halte permanent — mag niet in backtest mode"
    last = max(t.exit_bar for t in res.trades)
    assert last > 0.5 * len(df), "handel stopte in de eerste helft — waarschijnlijk gehalteerd"


def test_the_account_inputs_are_transcribed_not_inherited():
    """These values drive the DLL that closes positions, so they may not quietly
    come from whatever Config's defaults happen to be."""
    from backtest.pipeline import fleet
    for n in fleet.names():
        c = fleet.engine_config(n)
        assert (c.acct_trail_dd, c.acct_dll) == (2000.0, 1000.0), n
        assert (c.consistency_pct, c.min_payout, c.payout_buffer) == (50.0, 500.0, 500.0), n
        assert c.use_wait_for_cap is True and c.use_mae_guard is False, n


def test_report_reads_stage1_artifacts_back(tmp_path, monkeypatch, capsys):
    """Ground rule 11 says every stage leaves an artifact; this checks the
    evidence is actually answerable afterwards, without re-simulating."""
    import json

    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "EL_MATADOR_MES_PROD_EOD_trap1_pariteit_20260824.json").write_text(json.dumps({
        "dataset": "ES_20y_1m_CVD", "price_series_borrowed_from": "ES",
        "as_tested": False, "as_tested_changes": {},
        "window": {"bars": 515101, "coverage": {"missing_frac": 0.022}},
        "comparison": {"sim": {"trades": 120, "profit_factor": 1.4, "win_rate_pct": 43.3},
                       "pine": {"trades": 121, "profit_factor": 1.82, "win_rate_pct": 52.1},
                       "checks": [{"name": "trade count", "sim": 120, "pine": 121,
                                   "ok": True, "detail": "0.8% apart"},
                                  {"name": "profit factor", "sim": 1.4, "pine": 1.82,
                                   "ok": False, "detail": "23.1% apart"}]},
        "trade_diff": {"matched": 46, "sim_trades": 109, "sim_only": 63, "pine_only": 75,
                       "matched_with_a_different_result": 1,
                       "sim_exit_reasons": {"SL": 47, "TP": 32},
                       "pine_exit_reasons": {"SL|MFE1t": 20, "SL|MFE2t": 19, "TP|MFE9t": 37}}},
        default=str))

    from backtest.pipeline.cli import cmd_report
    cmd_report(None)
    out = capsys.readouterr().out
    assert "MATADOR_MES_PROD_EOD" in out
    assert "120/121" in out and "1.4/1.82" in out
    assert "42%" in out, "gepaard-percentage ontbreekt (46/109)"
    assert "prijsreeks geleend van ES" in out
    assert "SL 59%" in out, "pine-exits moeten op hoofdreden samengevoegd worden"


def test_report_says_so_when_there_is_nothing_to_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    from backtest.pipeline.cli import cmd_report
    cmd_report(None)
    assert "geen trap-1 artefacten" in capsys.readouterr().out


def test_order_lifecycle_is_counted_and_adds_up(tmp_path):
    """Where an order went once placed — the other half of "why fewer trades
    than Pine". veto_counts explains why a signal never became an order; without
    this the two halves cannot be told apart."""
    from backtest import indicators as im
    from backtest.engine import Engine
    from backtest.pipeline import fleet

    df = _pa_frame(tmp_path)
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    res = Engine(cfg, df, im.compute(df, cfg), research_mode=False).run()
    oc = res.order_counts
    assert oc is not None and oc["placed"] > 0, "geen orders — de test bewijst niets"
    assert oc["filled"] == len(res.trades), "gevulde orders != trades"
    resolved = (oc["filled"] + oc["expired"] + oc["cancelled_flat"]
                + oc["cancelled_halt"] + oc["replaced"] + oc["open_at_end"])
    assert resolved == oc["placed"], (
        f"orders lekken weg: {oc['placed']} geplaatst, {resolved} verantwoord ({oc})")


# --- data-parity gate: a strict wall, not a softer synonym for "close" --------

def _dp_inputs(**over):
    """A baseline where data-parity SHOULD trip, plus overrides to break it."""
    cmp_ = {"pass": False, "checks": [
        {"name": "trade count", "sim": 103, "pine": 121, "ok": False},
        {"name": "profit factor", "sim": 1.57, "pine": 1.82, "ok": True},
        {"name": "win rate", "sim": 48.5, "pine": 52.1, "ok": True},
        {"name": "long/short split", "sim": "40/63", "pine": "51/70", "ok": True}]}
    pa = {"mismatches": 0, "environment_mismatches": 0, "missing": []}
    td = {"matched": 56, "sim_trades": 103, "matched_exactly": 39,
          "matched_within_cost_noise": 16}
    po = {"_explain": {"checked": 25, "near_roll": 9, "away_from_roll": 16,
                       "reasons": {"geen FVG van die richting in het venster": 25}}}
    clean = True
    d = {"cmp_": cmp_, "pa": pa, "td": td, "po": po, "clean": clean}
    d.update(over)
    return d


def test_data_parity_trips_on_clean_data_source_evidence():
    from backtest.pipeline.cli import _data_parity_evidence
    d = _dp_inputs()
    out = _data_parity_evidence(d["cmp_"], d["pa"], d["td"], d["po"], d["clean"])
    assert out["eligible"] is True
    assert out["blocked"] is None
    assert any("identiek" in r for r in out["reasons"])


def test_data_parity_refuses_when_profit_factor_also_fails():
    from backtest.pipeline.cli import _data_parity_evidence
    d = _dp_inputs()
    d["cmp_"]["checks"][1]["ok"] = False           # PF fails too
    out = _data_parity_evidence(d["cmp_"], d["pa"], d["td"], d["po"], d["clean"])
    assert out["eligible"] is False


def test_data_parity_refuses_when_we_take_more_trades():
    """A surplus is not a missing-gap story."""
    from backtest.pipeline.cli import _data_parity_evidence
    d = _dp_inputs()
    d["cmp_"]["checks"][0].update(sim=140, pine=121)
    out = _data_parity_evidence(d["cmp_"], d["pa"], d["td"], d["po"], d["clean"])
    assert out["eligible"] is False


def test_data_parity_refuses_when_matched_trades_disagree():
    """If the trades we DO share don't agree, the engine is not proven equal."""
    from backtest.pipeline.cli import _data_parity_evidence
    d = _dp_inputs()
    d["td"].update(matched_exactly=10, matched_within_cost_noise=5)   # 15/56
    out = _data_parity_evidence(d["cmp_"], d["pa"], d["td"], d["po"], d["clean"])
    assert out["eligible"] is False


def test_data_parity_refuses_when_a_missing_signal_is_engine_side():
    """A band or streak disagreement is the engine, not the data — the whole
    point of the gate is to keep those out."""
    from backtest.pipeline.cli import _data_parity_evidence
    d = _dp_inputs()
    d["po"]["_explain"]["reasons"] = {
        "geen FVG van die richting in het venster": 20,
        "FVG gedetecteerd maar buiten de maatband": 5}
    out = _data_parity_evidence(d["cmp_"], d["pa"], d["td"], d["po"], d["clean"])
    assert out["eligible"] is False
    assert "engine" in out["blocked"]


def test_data_parity_refuses_on_a_dirty_audit():
    from backtest.pipeline.cli import _data_parity_evidence
    d = _dp_inputs()
    out = _data_parity_evidence(d["cmp_"], d["pa"], d["td"], d["po"], clean=False)
    assert out["eligible"] is False


def test_data_parity_status_satisfies_the_hard_gate_but_stays_distinct():
    from backtest.pipeline import state
    assert "data_parity" in state._VALID
    assert "data_parity" in state._SATISFIES_HARD
    assert "passed" in state._SATISFIES_HARD
    assert "failed" not in state._SATISFIES_HARD
