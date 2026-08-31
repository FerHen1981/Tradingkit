"""Stage 1 against the real TradingView exports committed in validation/exports.

These three files are the ground truth for what was actually validated on
2026-08-23. The tests below lock in two things: that the harness reads them
correctly, and that the divergences it found stay found. A silent regression
here would let an engine claim parity against a config it never ran.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backtest.pipeline import fleet
from backtest.pipeline.parity import (audit_environment, audit_properties,
                                      export_window, read_export)

EXPORTS = Path(__file__).resolve().parents[2] / "validation" / "exports"

# export file -> the engine it was run for (identified by its Properties, not
# by the filename: TradingView wrote a stale bot name into all three).
PAIRS = {
    "MATADOR_MES_PROD_EOD_MES1m_2026-08-23.xlsx": "EL_MATADOR_MES_PROD_EOD",
    "LEON_MYM_PROD_EOD_MYM1m_2026-08-23.xlsx":    "EL_LEON_MYM_PROD_EOD",
    "REY_MNQ_PROD_INTRA_MNQ1m_2026-08-23.xlsx":   "EL_REY_MNQ_PROD_INTRA",
}

pytestmark = pytest.mark.skipif(not EXPORTS.is_dir(),
                                reason="validation/exports niet aanwezig")


def _load(fname):
    return read_export(str(EXPORTS / fname))


@pytest.mark.parametrize("fname,engine", sorted(PAIRS.items()))
def test_export_parses(fname, engine):
    e = _load(fname)
    assert e.n_trades > 50, "geen gepaarde trades uit de Trades-sheet"
    s = e.stats()
    assert s["longs"] + s["shorts"] == s["trades"]
    assert e.properties["Timeframe"] == "1 minute"


@pytest.mark.parametrize("fname", sorted(PAIRS))
def test_window_comes_from_the_backtesting_range(fname):
    """Not from "Start date/time (measure from)" — that input reads Jan 1 2025
    while TradingView actually loaded Aug 2025 onward. Mistaking the one for the
    other turns a one-year data requirement into a nonexistent multi-year one."""
    e = _load(fname)
    a, b = export_window(e)
    assert a is not None and b is not None
    assert (a.year, a.month) == (2025, 8), a
    assert (b.year, b.month) == (2026, 8), b
    assert str(e.properties["Start date/time (measure from)"]).startswith("Jan 1, 2025")


@pytest.mark.parametrize("fname,engine", sorted(PAIRS.items()))
def test_properties_coverage_is_complete(fname, engine):
    """Every field the harness knows how to check is present in these sheets, so
    a low mismatch count means agreement — not an unread sheet."""
    a = audit_properties(_load(fname), fleet.engine_config(engine))
    assert a["missing"] == [], a["missing"]
    assert a["coverage_pct"] == 100.0
    assert a["checked"] >= 25


def test_symbol_mismatch_is_caught():
    """A MES engine held against the MYM export must not audit clean."""
    e = _load("LEON_MYM_PROD_EOD_MYM1m_2026-08-23.xlsx")
    env = audit_environment(e, fleet.engine_config("EL_MATADOR_MES_PROD_EOD"))
    sym = next(r for r in env if r["label"] == "Symbol")
    assert not sym["ok"], "verkeerde markt werd niet opgemerkt"


@pytest.mark.parametrize("fname,engine", sorted(PAIRS.items()))
def test_commission_divergence_is_reported(fname, engine):
    """All three exports ran commission 0.51 while CONTRACTS carries the
    per-symbol value. Costs move PF directly, so this may not pass silently."""
    a = audit_properties(_load(fname), fleet.engine_config(engine))
    com = next(r for r in a["environment"] if r["label"] == "Commission")
    assert com["export"] == 0.51
    if com["export"] != com["config"]:
        assert not com["ok"]


def test_leon_export_ran_a_different_firm_program():
    """Ground rule 10 in action: LEON_MYM_PROD_EOD's source ships
    apex_50k_eod_pa, but the validated export ran apex_50k_intraday_pa — so the
    engine named PROD_EOD was validated under an Intraday drawdown."""
    a = audit_properties(_load("LEON_MYM_PROD_EOD_MYM1m_2026-08-23.xlsx"),
                         fleet.engine_config("EL_LEON_MYM_PROD_EOD"))
    prog = next(r for r in a["environment"] if r["label"] == "Firm program")
    assert prog["export"] == "apex_50k_intraday_pa"
    assert prog["config"] == "apex_50k_eod_pa"
    assert not prog["ok"]
    dd = next(r for r in a["rows"] if r["label"] == "Drawdown Model")
    assert (dd["export"], dd["config"]) == ("Intraday", "EOD")


def test_rey_export_ran_a_different_day_profit_block():
    """The MNQ export ran Trail + cap with activation 750 / giveback 100 /
    cap 1000; the source ships the block Off with 500 / 150 / 750."""
    a = audit_properties(_load("REY_MNQ_PROD_INTRA_MNQ1m_2026-08-23.xlsx"),
                         fleet.engine_config("EL_REY_MNQ_PROD_INTRA"))
    got = {r["label"]: (r["export"], r["config"]) for r in a["rows"] if not r["ok"]}
    assert got["Day-profit exit mode"] == ("Trail + cap", "Off")
    assert got["Day-trail activation ($)"] == (750.0, 500.0)
    assert got["Day-trail giveback ($)"] == (100.0, 150.0)
    assert got["Day-cap hard target ($)"] == (1000.0, 750.0)


def test_matador_export_matches_its_engine_inputs():
    """The counter-example that makes the tests above meaningful: MATADOR's
    export agrees with the mirror on every strategy input, including the
    EOD drawdown that comes from its firm program."""
    a = audit_properties(_load("MATADOR_MES_PROD_EOD_MES1m_2026-08-23.xlsx"),
                         fleet.engine_config("EL_MATADOR_MES_PROD_EOD"))
    assert a["mismatches"] == 0, [r for r in a["rows"] if not r["ok"]]
    dd = next(r for r in a["rows"] if r["label"] == "Drawdown Model")
    assert dd["export"] == dd["config"] == "EOD"


# --- coverage: does the cockpit tell the truth about what can run? --------------

def _fake_dataset(root, name, symbol, first, last, rows=1000):
    """A dataset dir the lab will list: a canonical.csv plus a manifest."""
    import json
    d = root / "datasets" / name
    d.mkdir(parents=True)
    (d / "canonical.csv").write_text("DateTime,Open,High,Low,Close,Volume,Delta\n")
    (d / "manifest.json").write_text(json.dumps(
        {"symbol": symbol, "rows": rows, "first_dt": first, "last_dt": last}))


def test_coverage_accepts_a_twin_but_only_when_the_window_reaches(tmp_path, monkeypatch):
    """Three cases at once: an exact-market dataset that covers, a twin that
    covers, and a twin that stops short. The last one is the failure this guards
    — a 20-year file that ends before the export's end date is NOT usable, and
    reporting it as usable would send someone into a meaningless parity run."""
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    _fake_dataset(tmp_path, "ES_20y", "ES", "02-01-2006 00:00:00 -05:00",
                  "23-08-2026 20:00:00 -04:00")           # twin for MES, reaches
    _fake_dataset(tmp_path, "YM_20y", "YM", "02-01-2006 00:00:00 -05:00",
                  "31-12-2025 17:00:00 -05:00")           # twin for MYM, too short
    _fake_dataset(tmp_path, "MNQ_now", "MNQ", "01-08-2025 00:00:00 -04:00",
                  "23-08-2026 20:00:00 -04:00")           # exact market, reaches

    from backtest.lab import lab_viewer as lv
    cov = {c["market"]: c for c in lv._stage1_coverage()}

    assert cov["MES"]["runnable"] is True
    assert any("ES_20y" in x for x in cov["MES"]["datasets"])
    assert cov["MNQ"]["runnable"] is True
    assert cov["MNQ"]["datasets"] == ["MNQ_now"]
    assert cov["MYM"]["runnable"] is False, "een te korte twin mag niet bruikbaar heten"
    assert any("YM_20y" in x for x in cov["MYM"]["too_short"])


def test_coverage_accepts_a_dataset_that_is_only_days_short(tmp_path, monkeypatch):
    """The live VPS case: the 20-year files stop 2026-08-16 while the exports run
    through 2026-08-23. Eight days on a one-year window is under stage 1's trade
    tolerance, so this must read as usable-with-a-note, not as blocked."""
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    for name, sym in (("ES_20y", "ES"), ("NQ_20y", "NQ"), ("YM_20y", "YM")):
        _fake_dataset(tmp_path, name, sym, "04-12-2011 00:00:00 -05:00",
                      "16-08-2026 17:00:00 -04:00")

    from backtest.lab import lab_viewer as lv
    cov = {c["market"]: c for c in lv._stage1_coverage()}
    assert set(cov) == {"MES", "MNQ", "MYM"}
    for market, expected in (("MES", "ES_20y"), ("MNQ", "NQ_20y"), ("MYM", "YM_20y")):
        c = cov[market]
        assert c["runnable"] is True, f"{market} zou bruikbaar moeten zijn"
        assert c["too_short"] == []
        assert any(expected in x for x in c["datasets"])
        assert 0 < c["missing_days"] <= 10, c["missing_days"]


def test_coverage_reports_nothing_runnable_without_datasets(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    from backtest.lab import lab_viewer as lv
    cov = lv._stage1_coverage()
    assert len(cov) == 3
    assert not any(c["runnable"] for c in cov)
    assert all(c["twin"] for c in cov), "elke vlootmarkt hoort een twin-route te hebben"


# --- --as-tested: measure the engine even when the export ran other inputs -----

def test_as_tested_is_a_no_op_when_nothing_differs():
    """MATADOR agrees with its export on every input, so there is nothing to
    adopt — and adopting nothing must not quietly rewrite the config."""
    from backtest.pipeline.parity import as_tested
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    a = audit_properties(_load("MATADOR_MES_PROD_EOD_MES1m_2026-08-23.xlsx"), cfg)
    out, changes = as_tested(cfg, a)
    assert changes == {}
    assert out is cfg


def test_as_tested_adopts_the_leon_drawdown_model():
    from backtest.pipeline.parity import as_tested
    cfg = fleet.engine_config("EL_LEON_MYM_PROD_EOD")
    e = _load("LEON_MYM_PROD_EOD_MYM1m_2026-08-23.xlsx")
    out, changes = as_tested(cfg, audit_properties(e, cfg))
    assert changes["dd_model"] == ("EOD", "Intraday")
    assert out.dd_model == "Intraday"
    assert cfg.dd_model == "EOD", "de oorspronkelijke config is gemuteerd"
    assert audit_properties(e, out)["mismatches"] == 0


def test_as_tested_adopts_the_whole_rey_day_profit_block_with_types_intact():
    from backtest.pipeline.parity import as_tested
    cfg = fleet.engine_config("EL_REY_MNQ_PROD_INTRA")
    e = _load("REY_MNQ_PROD_INTRA_MNQ1m_2026-08-23.xlsx")
    out, changes = as_tested(cfg, audit_properties(e, cfg))
    assert set(changes) == {"day_exit_mode", "day_trail_activation_usd",
                            "day_trail_giveback_usd", "day_cap_usd"}
    assert out.day_exit_mode == "Trail + cap"
    for attr, want in (("day_trail_activation_usd", 750.0),
                       ("day_trail_giveback_usd", 100.0),
                       ("day_cap_usd", 1000.0)):
        got = getattr(out, attr)
        assert got == want and isinstance(got, float), (attr, got)
    assert audit_properties(e, out)["mismatches"] == 0


def test_as_tested_keeps_booleans_boolean():
    """The audit renders enum-as-bool rows as "Limit @ 50% FVG -> True", so the
    adoption has to parse that back rather than store the label as a string."""
    import dataclasses

    from backtest.pipeline.parity import as_tested
    cfg = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    flipped = dataclasses.replace(cfg, entry_limit_mode=False, use_breakeven=True)
    e = _load("MATADOR_MES_PROD_EOD_MES1m_2026-08-23.xlsx")
    out, changes = as_tested(flipped, audit_properties(e, flipped))
    assert changes["entry_limit_mode"] == (False, True)
    assert out.entry_limit_mode is True and isinstance(out.entry_limit_mode, bool)
    assert out.use_breakeven is False and isinstance(out.use_breakeven, bool)


# --- UI artifact detail: the deep numbers reach the browser -------------------

def test_artifact_detail_trims_each_stage_to_its_key_numbers(tmp_path, monkeypatch):
    """The Pijplijn tab reads these; each stage must expose the fields its
    renderer needs, and nothing must throw on a missing stage."""
    import json as _json

    monkeypatch.setenv("LAB_DIR", str(tmp_path))
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "EL_MATADOR_MES_PROD_EOD_trap8_time_for_money_20260824.json").write_text(_json.dumps({
        "banked_per_account_day": 42.5, "payouts": 2, "days_to_first_payout": 30,
        "dll_hits": 1, "trading_days": 120, "breached": False,
        "withdrawable": 5100.0, "per_month": 1200.0, "status": "passed"}))
    (art / "EL_MATADOR_MES_PROD_EOD_trap3_regimes_20260824.json").write_text(_json.dumps({
        "total": {"trades": 100}, "by_regime": {"X": {"in": {}, "out": {}, "share_pct": 50}},
        "best_regime": "X", "best_share_pct": 40, "status": "passed"}))

    from backtest.lab import lab_viewer as lv
    d8 = lv._artifact_detail("EL_MATADOR_MES_PROD_EOD", "8")
    assert d8["found"] and d8["data"]["banked_per_account_day"] == 42.5
    assert d8["data"]["dll_hits"] == 1
    d3 = lv._artifact_detail("EL_MATADOR_MES_PROD_EOD", "3")
    assert d3["found"] and d3["data"]["best_regime"] == "X"
    # a stage with no artifact returns found=False, does not raise
    assert lv._artifact_detail("EL_MATADOR_MES_PROD_EOD", "5")["found"] is False
    assert lv._artifact_detail("EL_NOPE", "8")["found"] is False


def test_firm_program_label_does_not_block_when_the_drawdown_model_matches():
    """LEON_PROD's export ran apex_50k_intraday_pa while its frozen program is
    apex_50k_eod_pa. --as-tested adopts the dd_model (EOD->Intraday), which is
    the material effect; the program LABEL still differs but the behaviour
    matches. That cosmetic label may not keep the environment audit dirty and so
    must not, on its own, block data-parity."""
    import dataclasses

    from backtest.pipeline import fleet
    from backtest.pipeline.parity import as_tested, audit_environment, audit_properties

    cfg = fleet.engine_config("EL_LEON_MYM_PROD_EOD")
    assert fleet.firm_program("EL_LEON_MYM_PROD_EOD") == "apex_50k_eod_pa"
    e = _load("LEON_MYM_PROD_EOD_MYM1m_2026-08-23.xlsx")

    # before as-tested: dd_model differs (EOD vs Intraday) -> firm program flagged
    env0 = {r["label"]: r for r in audit_environment(e, cfg)}
    assert env0["Firm program"]["ok"] is False

    # after adopting costs + as-tested inputs, the dd_model matches -> firm
    # program reconciled, environment clean
    cfg = dataclasses.replace(cfg, contract=dataclasses.replace(
        cfg.contract, commission_per_contract=0.51))
    cfg2, _ = as_tested(cfg, audit_properties(e, cfg))
    a2 = audit_properties(e, cfg2)
    assert a2["environment_mismatches"] == 0, [r for r in a2["environment"] if not r["ok"]]
    assert a2["mismatches"] == 0 and a2["missing"] == []
