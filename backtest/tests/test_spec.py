"""Spec validator tests — the governance gate in front of every backtest run."""
import copy
import os

import pytest

from backtest.spec import (
    REGISTRY_PATH, SpecError, load_registry, validate_spec, validate_file,
)

REG = load_registry()


def _spec(**over):
    """A minimal valid price-action spec; override via kwargs on the top level."""
    base = {
        "name": "T",
        "groups": {
            "fvg": {"gap_min_ticks": 9, "gap_max_ticks": 12},
            "market_structure": {"pivot_k": 3},
            "swing_stops": {"pivot_k": 3},
        },
    }
    base.update(over)
    return copy.deepcopy(base)


# --- happy path ------------------------------------------------------------ #
def test_valid_spec_resolves():
    r = validate_spec(_spec(), REG)
    assert r.name == "T"
    assert r.groups["fvg"]["gap_min_ticks"] == 9
    # defaults are filled for params the spec did not set
    assert r.groups["fvg"]["mitigation_mode"] == "CE"
    assert r.families["fvg"] == "price_action"


def test_example_file_validates():
    path = os.path.join(os.path.dirname(REGISTRY_PATH), "specs", "el_toro_pa.yaml")
    r = validate_file(path, REG)
    assert r.name == "El_Toro_v7_PAonly"
    assert r.policy["price_action_only"] is True


# --- structural errors ----------------------------------------------------- #
def test_missing_name():
    s = _spec(); del s["name"]
    with pytest.raises(SpecError):
        validate_spec(s, REG)


def test_unknown_group():
    with pytest.raises(SpecError, match="unknown group"):
        validate_spec(_spec(groups={"not_a_group": {}}), REG)


def test_unknown_param():
    with pytest.raises(SpecError, match="unknown param"):
        validate_spec(_spec(groups={"fvg": {"nope": 1}}), REG)


# --- value validation ------------------------------------------------------ #
def test_out_of_range_high():
    with pytest.raises(SpecError, match="out of range"):
        validate_spec(_spec(groups={"fvg": {"gap_min_ticks": 999}}), REG)


def test_out_of_range_low():
    with pytest.raises(SpecError, match="out of range"):
        validate_spec(_spec(groups={"rsi": {"length": 1}, }, policy={"price_action_only": False}), REG)


def test_enum_rejected():
    with pytest.raises(SpecError, match="options"):
        validate_spec(_spec(groups={"fvg": {"mitigation_mode": "banana"}}), REG)


def test_enum_accepted():
    r = validate_spec(_spec(groups={"fvg": {"mitigation_mode": "touch"}}), REG)
    assert r.groups["fvg"]["mitigation_mode"] == "touch"


def test_step_not_enforced_on_spec():
    # gap_max_ticks step is 5 but a hand value of 12 (in-range) must be accepted.
    r = validate_spec(_spec(groups={"fvg": {"gap_max_ticks": 12}}), REG)
    assert r.groups["fvg"]["gap_max_ticks"] == 12


# --- policy ---------------------------------------------------------------- #
def test_price_action_only_blocks_classic():
    s = _spec(policy={"price_action_only": True},
              groups={"rsi": {"length": 14}})
    with pytest.raises(SpecError, match="not price-action"):
        validate_spec(s, REG)


def test_classic_allowed_without_pa_policy():
    s = _spec(policy={"price_action_only": False},
              groups={"rsi": {"length": 14}, "macd": {}})
    r = validate_spec(s, REG)
    assert r.families["rsi"] == "classic"


def test_max_active_groups():
    s = _spec(policy={"max_active_groups": 2})  # base has 3 groups
    with pytest.raises(SpecError, match="max_active_groups"):
        validate_spec(s, REG)


# --- constraints ----------------------------------------------------------- #
def test_shared_pivot_k_constraint():
    s = _spec(groups={"market_structure": {"pivot_k": 4}, "swing_stops": {"pivot_k": 3}})
    with pytest.raises(SpecError, match="constraint violated"):
        validate_spec(s, REG)


def test_macd_slow_gt_fast_constraint():
    s = _spec(policy={"price_action_only": False},
              groups={"macd": {"fast": 20, "slow": 20}})  # slow not > fast
    with pytest.raises(SpecError, match="constraint violated"):
        validate_spec(s, REG)


def test_constraint_skipped_when_group_unused():
    # macd not in spec -> its constraint must not fire
    r = validate_spec(_spec(), REG)
    assert "macd" not in r.groups
