"""Strategy generator — the coarse mill's candidate samplers.

Two samplers feed the screen → refine → OOS funnel:

- `sample_spec`/`sample_batch` — the legacy RANDOM-SUBSET sampler: a random
  subset of indicator groups, each opt param on its step grid. Kept for A/B and
  backwards compatibility.
- `compose_strategy`/`compose_batch` — the ROLE-COMPOSING sampler (framework §4,
  see lab/FRAMEWORK.md): compose ONE slot per decision layer instead of a random
  subset. A setup-class (optionally biased by a regime hint via the §6 matrix)
  picks one primary entry; optional coherent filters are added under a redundancy
  guard (at most one group per information-category). This removes the randomness
  and makes double-counting structurally impossible — it is the default in the
  mill.

Pure Python (only spec.py + config, no pandas) so it is fully unit-testable.
Each sampled spec is ONE complete strategy carried whole through the three
lenses — the mill decides *which* candidates advance, never mixes their entries.
"""
from __future__ import annotations

import json
import random

from .spec import SpecError, _all_groups, _params, load_registry, validate_spec


def _sample_param(rng: random.Random, pdef: dict):
    if pdef.get("type") == "fixed":
        return pdef.get("default")
    if "options" in pdef:
        return rng.choice(pdef["options"])
    if "min" in pdef and "max" in pdef:
        lo, hi = pdef["min"], pdef["max"]
        step = pdef.get("step") or (1 if isinstance(lo, int) and isinstance(hi, int) else 0.1)
        k = int(round((hi - lo) / step))
        v = lo + step * rng.randint(0, max(k, 0))
        if isinstance(step, float) or isinstance(lo, float) or isinstance(hi, float):
            return round(v, 6)
        return int(v)
    if isinstance(pdef.get("default"), bool):
        return rng.choice([True, False])
    return pdef.get("default")


def _repair(spec: dict) -> dict:
    """Enforce the registry's hard constraints deterministically."""
    g = spec["groups"]
    if "market_structure" in g and "swing_stops" in g and "pivot_k" in g["swing_stops"]:
        g["market_structure"]["pivot_k"] = g["swing_stops"]["pivot_k"]
    for grp in ("macd", "ema_cross"):
        m = g.get(grp)
        if m and "fast" in m and "slow" in m and m["slow"] <= m["fast"]:
            m["slow"] = m["fast"] + (1 if grp == "macd" else 5)
    if "moving_average" in g:
        m = g["moving_average"]
        if "length_fast" in m and "length_slow" in m and m["length_slow"] <= m["length_fast"]:
            m["length_slow"] = m["length_fast"] + 5
    for grp in ("rsi", "stochastic"):
        d = g.get(grp)
        if d and "overbought" in d and "oversold" in d and d["overbought"] <= d["oversold"]:
            d["overbought"], d["oversold"] = (max(d["overbought"], d["oversold"]),
                                              min(d["overbought"], d["oversold"]))
            if d["overbought"] == d["oversold"]:
                d["overbought"] += 5
    fv = g.get("fvg")
    if fv and "gap_min_ticks" in fv and "gap_max_ticks" in fv and fv["gap_max_ticks"] <= fv["gap_min_ticks"]:
        fv["gap_max_ticks"] = fv["gap_min_ticks"] + 5
    o = g.get("premium_discount_ote")
    if o and "ote_low" in o and "ote_high" in o and o["ote_high"] <= o["ote_low"]:
        o["ote_low"], o["ote_high"] = min(o["ote_low"], o["ote_high"]), max(o["ote_low"], o["ote_high"])
    return spec


def sample_spec(registry: dict, rng: random.Random, *, base_asset: str = "NQ",
                timeframe: str | None = None, price_action_only: bool = False,
                min_groups: int = 2, max_groups: int | None = None,
                base_preset: str | None = None, wired_only: bool = False) -> dict:
    from .spec import WIRED_GROUPS
    groups_reg = _all_groups(registry)
    pool = [g for g, (fam, gd) in groups_reg.items()
            if (not price_action_only or gd.get("price_action"))
            and _params(gd) and not gd.get("requires_data")]     # skip any data-gated group
    if wired_only:
        pool = [g for g in pool if g in WIRED_GROUPS]            # only genuinely-wired indicators
    maxg = max_groups or (registry.get("policy") or {}).get("max_active_groups", 8)
    lo = min(min_groups, len(pool))
    hi = min(maxg, len(pool))
    k = rng.randint(lo, hi) if hi >= lo else len(pool)
    chosen = rng.sample(pool, k)

    groups: dict = {}
    for gname in chosen:
        pdefs = _params(groups_reg[gname][1])
        groups[gname] = {p: _sample_param(rng, pd) for p, pd in pdefs.items()
                         if pd.get("type") != "fixed"}
    spec = {"name": "gen", "base_asset": base_asset, "groups": groups,
            "policy": {"price_action_only": price_action_only, "max_active_groups": maxg}}
    if timeframe:
        spec["timeframe"] = timeframe
    if base_preset:
        spec["base_preset"] = base_preset
    return _repair(spec)


def sample_batch(n: int, registry: dict | None = None, seed: int = 0, **kw) -> list[dict]:
    """Return up to `n` distinct, valid candidate specs (random-subset sampler)."""
    registry = registry or load_registry()
    rng = random.Random(seed)
    out, seen, tries = [], set(), 0
    while len(out) < n and tries < n * 40:
        tries += 1
        spec = sample_spec(registry, rng, **kw)
        try:
            validate_spec(spec, registry)
        except SpecError:
            continue
        key = json.dumps(spec["groups"], sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        spec = dict(spec)
        spec["name"] = f"gen_{seed}_{len(out):04d}"
        out.append(spec)
    return out


# =========================================================================== #
# Role-composing sampler (framework §4) — compose ONE slot per layer instead of
# a random subset. Removes the randomness and makes double-counting impossible.
# =========================================================================== #

# A setup-class picks exactly ONE primary entry generator; the class is the
# strategy's thesis (framework §7). Each option carries any params needed to
# select the right engine mechanism (e.g. market_structure mode bos vs choch).
SETUP_ENTRIES: dict[str, list[tuple[str, dict]]] = {
    "trend_pullback": [("moving_average", {}), ("order_block", {}), ("fvg", {})],
    "breakout":       [("donchian", {}), ("market_structure", {"mode": "bos"}),
                       ("momentum", {}), ("ema_cross", {})],
    "mean_reversion": [("rsi", {}), ("bollinger_bands", {})],
    "reversal":       [("liquidity_eqhl", {}), ("divergence", {"osc_source": "cvd"}),
                       ("market_structure", {"mode": "choch"})],
}

# Regime -> setup-class weights (framework §6 matrix). The composer, given a
# regime hint, biases which setup-class it builds for. Keys match the L1
# classifier's REGIME_LABELS (indicators.classify_regime).
REGIME_SETUP_WEIGHTS: dict[str, dict[str, int]] = {
    "Strong Bull Trend":     {"trend_pullback": 5, "breakout": 5, "mean_reversion": 1, "reversal": 1},
    "Strong Bear Trend":     {"trend_pullback": 5, "breakout": 5, "mean_reversion": 1, "reversal": 1},
    "Controlled Bull Trend": {"trend_pullback": 5, "breakout": 3, "mean_reversion": 2, "reversal": 1},
    "Controlled Bear Trend": {"trend_pullback": 5, "breakout": 3, "mean_reversion": 2, "reversal": 1},
    "Compression":           {"trend_pullback": 1, "breakout": 4, "mean_reversion": 3, "reversal": 1},
    "Low-Volatility Range":  {"trend_pullback": 1, "breakout": 1, "mean_reversion": 5, "reversal": 3},
    "High-Volatility Range": {"trend_pullback": 2, "breakout": 1, "mean_reversion": 4, "reversal": 3},
}

# Optional coherent FILTERS the composer may add — each a distinct engine
# mechanism in its own information-category (never a second entry).
_FILTER_GROUPS = ("vwap", "cvd_delta")     # location veto, participation


def _weighted_choice(rng: random.Random, items: list, weights: list[int]):
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    r = rng.uniform(0, total)
    upto = 0.0
    for it, w in zip(items, weights):
        upto += w
        if r <= upto:
            return it
    return items[-1]


def compose_strategy(registry: dict, rng: random.Random, *, base_asset: str = "NQ",
                     timeframe: str | None = None, base_preset: str | None = None,
                     regime: str | None = None, setup_class: str | None = None,
                     price_action_only: bool = False, p_confluence: float = 0.12,
                     p_filter_location: float = 0.5, p_filter_participation: float = 0.5) -> dict:
    """Compose ONE coherent strategy by role (framework §4).

    Picks a setup-class (optionally biased by a `regime` hint via the §6 matrix),
    then exactly one primary entry generator for that class, then optional
    coherent filters — enforcing the redundancy guard: at most one group per
    information-category. Always adds a protective swing stop (L10).

    The stop/target MECHANICS are also DISCOVERED, not assumed: when `base_preset`
    is not pinned, one of the neutral MECHANICS_PRESETS is sampled per candidate,
    so the coarse test reveals which mechanics fits — never derived from the asset.
    Returns a spec dict (validated by the caller) tagged with its setup_class."""
    groups_reg = _all_groups(registry)
    info_used: set[str] = set()
    groups: dict[str, dict] = {}

    def _add(gname: str, seed_params: dict | None = None):
        gd = groups_reg[gname][1]
        pdefs = _params(gd)
        vals = {p: _sample_param(rng, pd) for p, pd in pdefs.items()
                if pd.get("type") != "fixed"}
        if seed_params:
            vals.update(seed_params)
        groups[gname] = vals
        cat = gd.get("info_category")
        if cat:
            info_used.add(cat)

    def _can_add(gname: str) -> bool:
        gd = groups_reg[gname][1]
        if price_action_only and not gd.get("price_action"):
            return False
        return gd.get("info_category") not in info_used

    # Entry options, price-action filtered so PA-only never proposes a classic
    # entry (which validation would reject). Classes with no PA-valid entry drop.
    def _pa_ok(gname: str) -> bool:
        return not price_action_only or groups_reg[gname][1].get("price_action")
    entry_opts = {sc: [(g, s) for (g, s) in opts if _pa_ok(g)]
                  for sc, opts in SETUP_ENTRIES.items()}
    entry_opts = {sc: opts for sc, opts in entry_opts.items() if opts}

    # 1) setup-class: explicit > confluence roll > regime-weighted > uniform
    if setup_class is None and rng.random() < p_confluence:
        setup_class = "confluence"
    if setup_class is None:
        classes = list(entry_opts)
        weights = REGIME_SETUP_WEIGHTS.get(regime) if regime else None
        setup_class = (_weighted_choice(rng, classes, [weights[c] for c in classes])
                       if weights else rng.choice(classes))

    # 2) primary entry (the thesis)
    if setup_class == "confluence":
        _add("silver_bullet")
        _add("fvg")                       # confluence primary; keep gap sizing tunable
    else:
        entry_group, seed = rng.choice(entry_opts[setup_class])
        _add(entry_group, seed)

    # 3) optional coherent filters (distinct info-category, price-action aware)
    if _can_add("vwap") and rng.random() < p_filter_location:
        _add("vwap")
    if _can_add("cvd_delta") and rng.random() < p_filter_participation:
        _add("cvd_delta")

    # 4) risk: always a protective swing stop
    _add("swing_stops")

    maxg = (registry.get("policy") or {}).get("max_active_groups", 8)
    spec = {"name": "gen", "base_asset": base_asset, "groups": groups,
            "policy": {"price_action_only": price_action_only, "max_active_groups": maxg},
            "setup_class": setup_class}
    if regime:
        spec["target_regime"] = regime
    if timeframe:
        spec["timeframe"] = timeframe
    # Mechanics: pinned if given, else SAMPLED (a discovered dimension, not assumed).
    if base_preset:
        spec["base_preset"] = base_preset
    else:
        from .config import MECHANICS_PRESETS
        spec["base_preset"] = rng.choice(MECHANICS_PRESETS)
    return _repair(spec)


def spec_from_selection(registry: dict, *, setup_class: str, entry: str | None = None,
                        filters=(), regime_filter=(), base_asset: str = "NQ",
                        base_preset: str | None = None, name: str = "custom",
                        timeframe: str | None = None) -> dict:
    """Build a spec from EXPLICIT builder choices (registry defaults, not random)
    so the preview is stable. Same role structure as compose_strategy: one primary
    entry for the setup-class, optional coherent filters, always a swing stop.
    Raises SpecError on an unknown setup-class or a filter that collides with the
    entry's information-category (redundancy guard)."""
    groups_reg = _all_groups(registry)
    info_used: set[str] = set()
    groups: dict[str, dict] = {}

    def _add(gname: str, seed_params: dict | None = None):
        groups[gname] = dict(seed_params or {})           # defaults fill in validate
        cat = groups_reg[gname][1].get("info_category")
        if cat:
            info_used.add(cat)

    if setup_class == "confluence":
        _add("silver_bullet")
        _add("fvg")
    else:
        opts = SETUP_ENTRIES.get(setup_class)
        if not opts:
            raise SpecError(f"unknown setup_class {setup_class!r}; "
                            f"known: {sorted(SETUP_ENTRIES)} + 'confluence'")
        table = {g: s for g, s in opts}
        entry = entry or opts[0][0]
        if entry not in table:
            raise SpecError(f"entry {entry!r} not valid for {setup_class!r}; "
                            f"choose from {list(table)}")
        _add(entry, table[entry])

    for f in filters:
        if f not in ("vwap", "cvd_delta"):
            raise SpecError(f"unknown filter {f!r} (allowed: vwap, cvd_delta)")
        cat = groups_reg[f][1].get("info_category")
        if cat in info_used:
            raise SpecError(f"filter {f!r} collides with the entry's "
                            f"information-category {cat!r} (redundancy guard)")
        _add(f)

    _add("swing_stops")

    maxg = (registry.get("policy") or {}).get("max_active_groups", 8)
    spec = {"name": name, "base_asset": base_asset, "groups": groups,
            "policy": {"price_action_only": False, "max_active_groups": maxg},
            "setup_class": setup_class}
    if regime_filter:
        spec["regime_filter"] = sorted(regime_filter)
    if timeframe:
        spec["timeframe"] = timeframe
    if base_preset:
        spec["base_preset"] = base_preset
    return _repair(spec)


def compose_batch(n: int, registry: dict | None = None, seed: int = 0, *,
                  regimes: list[str] | None = None, **kw) -> list[dict]:
    """Return up to `n` distinct, valid role-composed specs. If `regimes` is
    given, candidates are spread across those regime hints (round-robin) so the
    batch covers the setup-classes each regime favours."""
    registry = registry or load_registry()
    rng = random.Random(seed)
    out, seen, tries = [], set(), 0
    while len(out) < n and tries < n * 40:
        tries += 1
        regime = regimes[len(out) % len(regimes)] if regimes else kw.get("regime")
        call_kw = {k: v for k, v in kw.items() if k != "regime"}
        spec = compose_strategy(registry, rng, regime=regime, **call_kw)
        try:
            validate_spec(spec, registry)
        except SpecError:
            continue
        key = json.dumps({"g": spec["groups"], "s": spec.get("setup_class"),
                          "m": spec.get("base_preset")}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        spec = dict(spec)
        spec["name"] = f"cmp_{seed}_{len(out):04d}"
        out.append(spec)
    return out
