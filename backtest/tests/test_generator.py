"""Generator (candidate sampler) tests — all samples must be valid + within policy."""
import json
import random

from backtest.generator import sample_spec, sample_batch, _sample_param
from backtest.spec import load_registry, validate_spec, _all_groups, _params

REG = load_registry()


def test_sampled_specs_validate():
    batch = sample_batch(60, REG, seed=1, base_asset="NQ")
    assert len(batch) >= 40                      # most samples are valid+distinct
    for s in batch:
        validate_spec(s, REG)                    # must not raise


def test_batch_is_distinct():
    batch = sample_batch(40, REG, seed=2)
    keys = {json.dumps(s["groups"], sort_keys=True) for s in batch}
    assert len(keys) == len(batch)


def test_price_action_only_pool():
    batch = sample_batch(30, REG, seed=3, price_action_only=True)
    groups_reg = _all_groups(REG)
    for s in batch:
        for g in s["groups"]:
            assert groups_reg[g][1].get("price_action") is True


def test_respects_max_groups():
    batch = sample_batch(30, REG, seed=4, max_groups=3)
    for s in batch:
        assert 2 <= len(s["groups"]) <= 3


def test_fixed_params_not_sampled():
    # premium_discount_ote has fixed equilibrium/ote_ideal — never emitted by the sampler
    rng = random.Random(9)
    for _ in range(200):
        s = sample_spec(REG, rng)
        pdo = s["groups"].get("premium_discount_ote")
        if pdo:
            assert "equilibrium" not in pdo and "ote_ideal" not in pdo


def test_shared_pivot_k_repaired():
    # whenever both structure groups appear, their pivot_k must match (constraint)
    for s in sample_batch(80, REG, seed=5):
        g = s["groups"]
        if "market_structure" in g and "swing_stops" in g:
            assert g["market_structure"]["pivot_k"] == g["swing_stops"]["pivot_k"]


def test_sample_param_on_grid_and_in_range():
    rng = random.Random(0)
    pdef = {"default": 4, "min": 1, "max": 40, "step": 1, "type": "opt"}
    for _ in range(50):
        v = _sample_param(rng, pdef)
        assert 1 <= v <= 40 and v == int(v)
    enum = {"default": "CE", "options": ["touch", "CE", "full"], "type": "opt"}
    assert _sample_param(rng, enum) in ("touch", "CE", "full")


def test_deterministic_seed():
    a = sample_batch(20, REG, seed=42)
    b = sample_batch(20, REG, seed=42)
    assert [s["groups"] for s in a] == [s["groups"] for s in b]
