"""Payout-cap sourcing and the D-148 shape (D-130).

Before D-130 the cap was a hardcoded Apex-50K ladder in `config.py:ladder_cap()`,
used by the engine with no per-program path, and `funded.py` silently fell back to
that same ladder when a program carried no `payout_ladder`. These tests pin:

  * the single cap resolver (ladder shape, fixed-cap shape, the D-148 lapse to
    uncapped, and the hard-fail that replaced the silent fallback);
  * that fleet engine configs read the cap from the registry, not a constant;
  * that the funded sim applies the fixed $2,000 Apex-legacy cap on payout #1
    (not the old $1,500) and goes UNCAPPED from the sixth payout.
"""
from __future__ import annotations

import datetime as dt

import pytest

from backtest.config import resolve_payout_cap, Config
from backtest.funded import simulate_funded


# --- the resolver ------------------------------------------------------------
def test_resolver_ladder_shape_clamps_at_the_last_rung():
    L = (1500, 1500, 2000, 2500, 2500, 3000)
    assert resolve_payout_cap(1, ladder=L) == 1500
    assert resolve_payout_cap(6, ladder=L) == 3000
    assert resolve_payout_cap(9, ladder=L) == 3000       # beyond the list -> last rung


def test_resolver_fixed_cap_lapses_to_uncapped():
    # Apex legacy after D-148: $2,000 through payout 5, then NO maximum.
    assert resolve_payout_cap(1, cap=2000, cap_until=5) == 2000
    assert resolve_payout_cap(5, cap=2000, cap_until=5) == 2000
    assert resolve_payout_cap(6, cap=2000, cap_until=5) is None
    assert resolve_payout_cap(99, cap=2000, cap_until=5) is None


def test_resolver_fixed_cap_without_lapse_never_expires():
    assert resolve_payout_cap(50, cap=2500, cap_until=0) == 2500


def test_resolver_hard_fails_when_no_shape_given():
    # This is the silent Apex-50K fallback D-130 removed.
    with pytest.raises(ValueError, match="no payout cap shape"):
        resolve_payout_cap(1)


# --- config method + fleet wiring --------------------------------------------
def test_config_method_delegates_to_resolver():
    c = Config(name="t", payout_ladder=(), payout_cap=2000.0, payout_cap_until=5)
    assert c.payout_cap_for(1) == 2000.0 and c.payout_cap_for(6) is None


def test_fleet_config_reads_cap_from_registry():
    from backtest.config import DEFAULT_PAYOUT_LADDER
    from backtest.pipeline import fleet
    # the fleet maps to apex_50k_eod_pa; its payout shape is nulled in the registry
    # pending Ferry (D-144), so the fleet config falls back to Apex's own ladder.
    # The point of D-130 holds: the cap comes through the registry path, and when a
    # shape IS present it is used verbatim (see the legacy-cap test below).
    c = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    assert c.payout_ladder == DEFAULT_PAYOUT_LADDER and c.payout_cap == 0.0
    assert c.payout_cap_for(1) == 1500.0


def test_fleet_uses_the_registry_shape_when_one_is_present():
    from backtest.pipeline import fleet
    # A program that carries a fixed cap (Apex legacy) comes through as a cap, not
    # the default ladder — proving the registry shape wins where it exists.
    ladder, cap, until = fleet._payout_cap_fields("apex_50k_legacy_pa", "test")
    assert ladder == () and cap == 2000.0 and until == 5


def test_fleet_cap_fields_raise_for_an_unknown_program():
    from backtest.pipeline import fleet
    # A program not in the registry at all is still a hard error (no silent guess).
    with pytest.raises(ValueError, match="not in data/propfirms.json"):
        fleet._payout_cap_fields("does_not_exist_pa", "test")


# --- funded sim: the D-148 Apex-legacy shape ---------------------------------
def _days(vals, start=dt.date(2026, 1, 5)):
    return {start + dt.timedelta(days=i): v for i, v in enumerate(vals)}


# dd pinned small and consistency disabled so the cap is the ONLY thing under test.
_LEGACY_CAP = {"drawdown": 2_500.0, "min_qual_days": 8, "min_day_profit": 50.0,
               "consistency_limit": 1.0, "safety_buffer": 100.0,
               "cap": 2_000.0, "cap_until": 5, "ladder": None,
               "min_payout": 0.0, "profit_split": 1.0, "daily_loss_limit": None}
_OLD_LADDER = {**_LEGACY_CAP, "cap": 0.0, "cap_until": 0,
               "ladder": [1_500, 1_500, 2_000, 2_500, 2_500, 3_000]}


def test_first_payout_caps_at_2000_not_1500():
    # 8 x $700 = $5,600; safety 52,600; above $3,000. Old ladder caps #1 at $1,500;
    # the corrected Apex-legacy fixed cap allows $2,000.
    old = simulate_funded(_days([700] * 8), account_size=50_000, rules=_OLD_LADDER)
    new = simulate_funded(_days([700] * 8), account_size=50_000, rules=_LEGACY_CAP)
    assert abs(old.payouts[0].amount - 1_500) < 1e-6
    assert abs(new.payouts[0].amount - 2_000) < 1e-6


def test_sixth_payout_is_uncapped():
    # Drive six payouts with a short qualifying cycle; payouts 1..5 cap at $2,000,
    # the sixth takes the full amount above the safety balance (> $2,000).
    rules = {**_LEGACY_CAP, "min_qual_days": 1, "drawdown": 100.0, "safety_buffer": 0.0}
    res = simulate_funded(_days([2_500] * 6), account_size=50_000, rules=rules)
    assert res.num_payouts == 6
    assert all(abs(p.amount - 2_000) < 1e-6 for p in res.payouts[:5])
    assert res.payouts[5].amount > 2_000      # uncapped from the sixth


def test_sim_hard_fails_when_rules_carry_no_cap_shape():
    # A rule set with neither a ladder nor a cap must refuse at the first payout,
    # not silently bank an Apex-50K amount.
    rules = {**_LEGACY_CAP, "cap": 0.0, "cap_until": 0, "ladder": None}
    with pytest.raises(ValueError, match="no payout cap shape"):
        simulate_funded(_days([700] * 8), account_size=50_000, rules=rules)
