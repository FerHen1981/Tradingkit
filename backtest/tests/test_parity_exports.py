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
