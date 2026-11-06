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


def test_wired_only_restricts_pool():
    from backtest.spec import WIRED_GROUPS
    for s in sample_batch(40, REG, seed=11, wired_only=True):
        assert all(g in WIRED_GROUPS for g in s["groups"])


def test_effective_signature_collapses_inert_params():
    from backtest.spec import spec_to_config, effective_signature
    base = {"name": "a", "base_asset": "NQ", "base_preset": "EL_TORO",
            "policy": {"price_action_only": False, "max_active_groups": 6},
            "groups": {"cvd_delta": {"cvd_trend_count": 4, "cvd_slope_lookback": 20}}}
    other = json.loads(json.dumps(base))
    other["groups"]["cvd_delta"]["cvd_slope_lookback"] = 55        # inert (unwired) knob
    ca, _ = spec_to_config(validate_spec(base, REG))
    cb, _ = spec_to_config(validate_spec(other, REG))
    assert effective_signature(ca) == effective_signature(cb)     # same effective strategy
    # but changing a WIRED knob must change the signature
    other["groups"]["cvd_delta"]["cvd_trend_count"] = 7
    cc, _ = spec_to_config(validate_spec(other, REG))
    assert effective_signature(cc) != effective_signature(ca)


# --- role-composing sampler (framework §4) --------------------------------- #
def test_composed_specs_validate_and_configure():
    from backtest.generator import compose_batch
    from backtest.spec import spec_to_config
    batch = compose_batch(80, REG, seed=1, base_asset="NQ")
    assert len(batch) >= 60
    for s in batch:
        spec_to_config(validate_spec(s, REG))          # validates + configures, no raise


def test_composer_redundancy_guard_one_per_category():
    # the core guarantee: no two groups share an information-category
    from backtest.generator import compose_batch
    groups_reg = _all_groups(REG)
    for s in compose_batch(120, REG, seed=2):
        cats = [groups_reg[g][1].get("info_category") for g in s["groups"]]
        cats = [c for c in cats if c]
        assert len(cats) == len(set(cats)), f"category collision in {list(s['groups'])}"


def test_composer_exactly_one_primary_entry():
    import random
    from backtest.generator import compose_strategy
    from backtest.spec import spec_to_config, describe_config
    rng = random.Random(5)
    for _ in range(150):
        s = compose_strategy(REG, rng)
        cfg, _ = spec_to_config(validate_spec(s, REG))
        entries = describe_config(cfg)["entries"]
        if s["setup_class"] != "confluence":
            assert len(entries) == 1                    # one thesis, never a stack
        assert "swing_stops" in s["groups"]             # always a protective stop


def test_composer_regime_biases_setup_class():
    import random, collections
    from backtest.generator import compose_strategy
    rng = random.Random(3)
    lo = collections.Counter(compose_strategy(REG, rng, regime="Low-Volatility Range")["setup_class"]
                             for _ in range(300))
    rng = random.Random(3)
    tr = collections.Counter(compose_strategy(REG, rng, regime="Strong Bull Trend")["setup_class"]
                             for _ in range(300))
    # §6 matrix: range favours mean-reversion, strong trend favours trend/breakout
    assert lo["mean_reversion"] > lo["breakout"]
    assert (tr["trend_pullback"] + tr["breakout"]) > (tr["mean_reversion"] + tr["reversal"])


def test_composer_deterministic_and_distinct():
    from backtest.generator import compose_batch
    a = compose_batch(25, REG, seed=42)
    b = compose_batch(25, REG, seed=42)
    assert [s["groups"] for s in a] == [s["groups"] for s in b]
    keys = {json.dumps(s["groups"], sort_keys=True) for s in a}
    assert len(keys) == len(a)


def test_composer_price_action_only():
    from backtest.generator import compose_batch
    groups_reg = _all_groups(REG)
    for s in compose_batch(40, REG, seed=8, price_action_only=True):
        for g in s["groups"]:
            assert groups_reg[g][1].get("price_action") is True


# --- builder: deterministic spec_from_selection (framework §4, step 6) ------ #
def test_spec_from_selection_valid_and_deterministic():
    from backtest.generator import spec_from_selection
    from backtest.spec import spec_to_config
    a = spec_from_selection(REG, setup_class="breakout", entry="donchian",
                            filters=["vwap", "cvd_delta"], name="c1")
    b = spec_from_selection(REG, setup_class="breakout", entry="donchian",
                            filters=["vwap", "cvd_delta"], name="c1")
    assert a["groups"] == b["groups"]              # defaults, not random
    assert set(a["groups"]) == {"donchian", "vwap", "cvd_delta", "swing_stops"}
    spec_to_config(validate_spec(a, REG))          # validates + configures


def test_spec_from_selection_redundancy_guard():
    from backtest.generator import spec_from_selection
    from backtest.spec import SpecError
    import pytest
    # liquidity_eqhl entry is L4 location; a vwap filter is also location -> reject
    with pytest.raises(SpecError, match="redundancy"):
        spec_from_selection(REG, setup_class="reversal", entry="liquidity_eqhl",
                            filters=["vwap"])


def test_spec_regime_filter_persists_to_config():
    from backtest.generator import spec_from_selection
    from backtest.spec import spec_to_config
    import yaml
    gate = ["Strong Bull Trend", "Controlled Bull Trend"]
    s = spec_from_selection(REG, setup_class="breakout", entry="momentum",
                            regime_filter=gate, name="g1")
    cfg, _ = spec_to_config(validate_spec(s, REG))
    assert cfg.regime_filter == frozenset(gate)
    # survives a YAML round-trip (as a saved spec would)
    cfg2, _ = spec_to_config(validate_spec(yaml.safe_load(yaml.safe_dump(s)), REG))
    assert cfg2.regime_filter == frozenset(gate)
