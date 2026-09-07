"""Setup-quality score — a PRIOR and a DISPLAY, never a gate (framework §8).

Turns a strategy's decision stack (describe_config output) into a 0-100 grade
that says how complete and regime-aligned the *setup* is. It deliberately does
NOT judge edge: a lean strategy can score modestly here and still have a strong
realized edge. The OOS funnel (PF/expectancy on holdout) stays the only judge of
whether a candidate advances; this score only ranks and labels.

Weights follow FRAMEWORK.md §8. On single-instrument data L0 (cross-market) is a
neutral stub, so it contributes a fixed neutral baseline rather than a penalty.
"""
from __future__ import annotations

# Component weights (sum to 100), keyed by layer.
SCORE_WEIGHTS = {
    "L0_cross_market": 10, "L1_regime": 15, "L2_direction": 10, "L3_structure": 15,
    "L4_location": 15, "L5_participation": 10, "L6_momentum": 5, "L7_volatility": 10,
    "L9_trigger": 5, "L10_risk": 5,
}


def grade_for(score: float) -> str:
    return ("A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 70
            else "Observation" if score >= 60 else "No-Trade")


def _regime_fit(regime: str | None, setup_class: str | None) -> float:
    """0..1 — how well the setup-class suits the (target/observed) regime, from
    the §6 matrix. Neutral 0.5 when unknown; confluence is a strong standalone."""
    if setup_class == "confluence":
        return 0.7
    if not regime or not setup_class:
        return 0.5
    try:
        from .generator import REGIME_SETUP_WEIGHTS
    except Exception:
        return 0.5
    w = REGIME_SETUP_WEIGHTS.get(regime, {}).get(setup_class)
    return (w / 5.0) if w else 0.4       # w in 1..5 -> 0.2..1.0; miss -> 0.4


def score_strategy(desc: dict, *, regime: str | None = None,
                   setup_class: str | None = None) -> dict:
    """Score the decision stack in `desc` (a describe_config result). Returns
    {score, grade, components, note}. `regime`/`setup_class` (from the spec or a
    run's dominant regime) sharpen the L1 regime-fit term; without them L1 is
    scored neutrally."""
    stack = {r["layer"]: r for r in (desc.get("stack") or [])}
    family = desc.get("family")
    if setup_class is None and family == "confluence":
        setup_class = "confluence"                # a confluence spec grades as one

    def active(layer: str) -> bool:
        return bool(stack.get(layer, {}).get("active"))

    # The Silver Bullet encodes several layers inside one group (FVG structure +
    # prior sweep + VWAP bias + kill-zone), so credit those from desc.confluence.
    conf = desc.get("confluence") or {}
    req = set(conf.get("require") or [])
    is_conf = family == "confluence"
    conf_structure = is_conf                                   # FVG imbalance = structure
    conf_location = is_conf and (bool(conf.get("killzones")) or "VWAP bias side" in req)
    conf_bias = is_conf and "VWAP bias side" in req

    W = SCORE_WEIGHTS
    comp: dict[str, float] = {}

    # L0 cross-market: neutral stub on single-instrument data (never a penalty).
    comp["L0_cross_market"] = 0.5 * W["L0_cross_market"]

    # L1 regime: fit of the setup-class to the regime (the framework's spine).
    fit = _regime_fit(regime, setup_class)
    if regime is None and setup_class is None and active("L1"):
        fit = max(fit, 0.8)              # an explicit regime group present
    comp["L1_regime"] = fit * W["L1_regime"]

    # L2 direction: an explicit bias group, or a directional thesis.
    directional = (family in ("trend", "momentum") or conf_bias
                   or setup_class in ("trend_pullback", "breakout"))
    comp["L2_direction"] = W["L2_direction"] * (1.0 if (active("L2") or directional) else 0.4)

    # Structural/confluence layers. A FILLED layer earns full weight; an UNFILLED
    # optional layer earns a neutral baseline, not zero — a lean strategy simply
    # doesn't use that dimension (the framework's redundancy ethos: more isn't
    # better). Location weighs a touch heavier since where you enter matters.
    _NEUTRAL = {"L3_structure": 0.4, "L4_location": 0.5, "L5_participation": 0.4,
                "L6_momentum": 0.4, "L7_volatility": 0.4}
    comp["L3_structure"] = W["L3_structure"] * (1.0 if (active("L3") or conf_structure) else _NEUTRAL["L3_structure"])
    comp["L4_location"] = W["L4_location"] * (1.0 if (active("L4") or conf_location) else _NEUTRAL["L4_location"])
    for layer, key in (("L5", "L5_participation"), ("L6", "L6_momentum"),
                       ("L7", "L7_volatility")):
        comp[key] = W[key] * (1.0 if active(layer) else _NEUTRAL[key])

    # L9 trigger: every runnable strategy has an entry.
    has_entry = bool(desc.get("entries")) or active("L9") or is_conf
    comp["L9_trigger"] = float(W["L9_trigger"]) if has_entry else 0.0

    # L10 risk: a structural (swing) stop is the quality bar; fixed stop = half.
    stop = str((desc.get("exit") or {}).get("stop", ""))
    comp["L10_risk"] = W["L10_risk"] if ("swing" in stop or active("L10")) else 0.5 * W["L10_risk"]

    score = round(sum(comp.values()), 1)
    return {"score": score, "grade": grade_for(score),
            "components": {k: round(v, 1) for k, v in comp.items()},
            "note": "prior/display only — the OOS funnel is the judge"}
