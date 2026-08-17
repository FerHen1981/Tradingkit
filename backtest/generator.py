"""Strategy generator — the coarse mill's candidate sampler.

Draws random, valid strategy specs from the registry: a random subset of
indicator groups, each opt param sampled on its step grid (fixed params keep
their default, per `optimizer_skips_fixed`), then repaired to satisfy the hard
constraints and validated. Feeds the screen → refine → OOS funnel.

Pure Python (only spec.py + config, no pandas) so it is fully unit-testable.
Each sampled spec is ONE complete strategy; it is carried whole through the
three lenses — the mill decides *which* candidates advance, never mixes their
indicators.
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
    if "macd" in g:
        m = g["macd"]
        if "fast" in m and "slow" in m and m["slow"] <= m["fast"]:
            m["slow"] = m["fast"] + 1
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
            and _params(gd) and not gd.get("requires_data")]     # skip data-gated (footprint)
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
    """Return up to `n` distinct, valid candidate specs."""
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
