"""D-68 — the account rules come from data/propfirms.json, never hardcoded.

Before D-68 the fleet mirror carried `acct_trail_dd=2000, acct_dll=1000,
consistency_pct=50` as literals and `higher._funded` fell back to a magic 2500.
Those passed only because the numbers happened to equal the registry (D-67 showed
the registry itself had been wrong for half a year). These tests pin the new
contract: read from the registry, and fail HARD on a missing rule.
"""
from __future__ import annotations

import dataclasses
import types

import pytest

from backtest import firms
from backtest.pipeline import fleet
from backtest.pipeline import higher


def test_engine_config_sources_acct_rules_from_registry():
    for name in fleet.names():
        cfg = fleet.engine_config(name)
        prog = firms.program(fleet.firm_program(name))
        assert cfg.acct_trail_dd == float(prog.drawdown)
        assert cfg.acct_dll == float(prog.max_daily_loss)
        assert cfg.consistency_pct == float(prog.consistency_pct)


def test_acct_rules_fails_hard_on_unknown_program():
    with pytest.raises(ValueError, match="not in data/propfirms.json"):
        fleet._acct_rules("no_such_program_key", "TEST_ENGINE")


def test_acct_rules_fails_hard_on_missing_rule(monkeypatch):
    """A program that exists but lacks a funded rule must raise, not fall back."""
    stub = types.SimpleNamespace(drawdown=2000.0, max_daily_loss=None,
                                 consistency_pct=50.0)
    monkeypatch.setattr(firms, "program", lambda key: stub)
    with pytest.raises(ValueError, match="max_daily_loss"):
        fleet._acct_rules("apex_50k_eod_pa", "TEST_ENGINE")


def test_funded_refuses_a_zero_trailing_drawdown():
    """No silent fallback to 2500: a missing trailing DD is a hard error."""
    cfg = dataclasses.replace(fleet.engine_config("EL_MATADOR_MES_PROD_EOD"),
                              acct_trail_dd=0.0)
    fake_res = types.SimpleNamespace(trades=[])
    with pytest.raises(ValueError, match="acct_trail_dd"):
        higher._funded(fake_res, cfg, "eod_trailing")
