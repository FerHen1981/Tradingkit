"""The role boundary is the portal's one security-critical property, so it is
tested from the outside: build a fleet that definitely contains money, then
assert that a viewer's payload contains none of it — by key name and by value.

The value check matters as much as the key check. A field could be renamed to
something innocuous and still carry dollars; comparing against the actual
amounts in the fixture catches that.

Overgenomen uit `web/handover/mex_units/tests/test_roles.py` bij de handover
naar Middleware App (D-17). Imports aangepast op de nieuwe locatie.
"""
from __future__ import annotations

import pytest

from app.mex_units import roles as stats, units
from app.mex_units.roles import assert_no_currency


#: Every currency amount in the fixture carries non-zero cents, and published
#: unit counts are whole numbers. That makes the value-collision check below
#: exact: an integer unit total can never equal one of these amounts by
#: coincidence, so a match is always a real leak.
TRADES = [
    {"ts": 1_750_000_000, "symbol": "GC1!", "realized_usd": 20.37, "realized_r": 0.8,
     "fill_qty": 1, "slippage_ticks": 0.3, "hold_s": 420},
    {"ts": 1_752_000_000, "symbol": "GC1!", "realized_usd": -50.63, "realized_r": -1.0,
     "fill_qty": 1, "slippage_ticks": 0.5, "hold_s": 300},
    {"ts": 1_755_000_000, "symbol": "ES1!", "realized_usd": 125.41, "realized_r": 2.5,
     "fill_qty": 1, "slippage_ticks": 0.25, "hold_s": 900},
    # A micro: rolls up into GC, but converts at its own $1/tick.
    {"ts": 1_757_000_000, "symbol": "MGC1!", "realized_usd": 10.29, "realized_r": 0.4,
     "fill_qty": 1, "slippage_ticks": 0.1, "hold_s": 200},
]

ACCOUNTS = [
    {"account": "PAAPEX123", "realized": 105.44, "open_pnl": 12.11, "total_val": 50_105.44},
    {"account": "APEX999", "realized": -50.63, "open_pnl": 3.17, "total_val": 49_950.63},
]

MONEY_VALUES = {
    20.37, -50.63, 125.41, 10.29,
    105.44, 12.11, 50_105.44, 49_950.63, 3.17,
}


@pytest.fixture
def fleet():
    return stats.build(TRADES, ACCOUNTS)


def _walk(node, path="$"):
    """Yield (path, key, value) for every leaf in a nested structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f"{path}[{i}]")
    else:
        yield path, node


# --- units -----------------------------------------------------------------


def test_dollar_to_ticks_uses_the_contract_spec():
    # $20 on GC at $10/tick
    assert units.to_units(20.0, "GC1!", 1) == pytest.approx(2.0)
    # $125 on ES at $12.50/tick
    assert units.to_units(125.0, "ES1!", 1) == pytest.approx(10.0)
    # A micro is not its parent: $10 on MGC at $1/tick
    assert units.to_units(10.0, "MGC1!", 1) == pytest.approx(10.0)


def test_unknown_symbol_returns_none_not_a_guess():
    assert units.to_units(100.0, "WHEAT", 1) is None
    assert units.price_to_units(1.0, "WHEAT") is None


def test_symbol_normalisation_strips_chart_and_expiry_suffixes():
    assert units.normalise("GC1!") == "GC"
    assert units.normalise("COMEX:MGC1!") == "MGC"
    assert units.normalise("ES") == "ES"


def test_micros_roll_up_into_the_parent_market():
    assert units.group_key("MGC1!") == "GC"
    assert units.group_key("MES1!") == "ES"


def test_quantity_scales_the_conversion():
    # $40 on two GC contracts is still 2 ticks per contract, not 4.
    assert units.to_units(40.0, "GC1!", 2) == pytest.approx(2.0)


# --- aggregation -----------------------------------------------------------


def test_markets_roll_up_and_r_totals_add(fleet):
    assert set(fleet.markets) == {"GC", "ES"}
    assert fleet.markets["GC"].trades == 3  # 2 GC + 1 MGC
    assert fleet.r_total == pytest.approx(2.7)  # 0.8 - 1.0 + 2.5 + 0.4


def test_win_rate_ignores_flat_trades():
    flat = [{"ts": 1, "symbol": "GC1!", "realized_usd": 0.0, "realized_r": 0.0, "fill_qty": 1}]
    f = stats.build(TRADES + flat, ACCOUNTS)
    assert f.wins == 3
    assert f.losses == 1
    assert f.win_rate == pytest.approx(75.0)


def test_profit_factor_comes_from_r_not_currency(fleet):
    # gross win 3.7R / gross loss 1.0R
    assert fleet.profit_factor == pytest.approx(3.7)


def test_equity_curve_is_anchored_at_zero(fleet):
    assert fleet.equity[0][1] == 0.0
    assert fleet.equity[-1][1] == pytest.approx(2.7)


# --- the role boundary -----------------------------------------------------


def test_viewer_payload_has_no_currency_key(fleet):
    payload = stats.serialise(fleet, "viewer")
    for path, _ in _walk(payload):
        lowered = path.lower()
        assert "usd" not in lowered, f"currency key leaked at {path}"
        assert "money" not in lowered, f"currency key leaked at {path}"
        assert "balance" not in lowered, f"currency key leaked at {path}"


def test_viewer_payload_contains_no_currency_value(fleet):
    payload = stats.serialise(fleet, "viewer")
    for path, value in _walk(payload):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            assert float(value) not in MONEY_VALUES, (
                f"a currency amount surfaced at {path}: {value}"
            )


def test_viewer_never_sees_account_identifiers(fleet):
    payload = stats.serialise(fleet, "viewer")
    rendered = repr(payload)
    assert "PAAPEX123" not in rendered
    assert "APEX999" not in rendered


def test_public_payload_passes_the_publish_gate(fleet):
    assert_no_currency(stats.for_public(fleet))


def test_public_payload_would_fail_the_gate_if_money_were_added(fleet):
    payload = stats.for_public(fleet)
    payload["headline"]["net_usd"] = 105.44
    with pytest.raises(ValueError, match="net_usd"):
        assert_no_currency(payload)


def test_owner_does_see_currency(fleet):
    payload = stats.serialise(fleet, "owner")
    assert payload["headline"]["net_usd"] == pytest.approx(105.44)
    assert payload["accounts"][0]["account"] == "PAAPEX123"


def test_partner_sees_currency_but_is_labelled_separately(fleet):
    payload = stats.serialise(fleet, "partner")
    assert payload["role"] == "partner"
    assert "net_usd" in payload["headline"]


def test_unknown_role_falls_back_to_the_most_restrictive_view(fleet):
    payload = stats.serialise(fleet, "typo-role")  # type: ignore[arg-type]
    assert payload["role"] == "viewer"
