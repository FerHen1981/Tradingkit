"""Strategy spec loader + validator — the gate in front of every backtest run.

A spec (``specs/<name>.yaml``) declares which indicator GROUPS a strategy uses
and sets values for their params. Before any run it is validated against
``registry.yaml``:

  * unknown group or param           -> SpecError
  * numeric value outside [min,max]   -> SpecError
  * value not in an enum's options    -> SpecError
  * wrong type for a boolean switch   -> SpecError
  * policy breach (price_action_only, max_active_groups) -> SpecError
  * cross-param constraint violated   -> SpecError

Design note: ``step`` in the registry is the OPTIMIZER's grid, NOT a constraint
on hand-authored specs. A spec value need only fall within [min,max]; the
optimizer (separately) only *moves* params on the step grid. So this validator
checks range/enum/type/policy/constraints, never step.

The three engines (classic / eval / funded) consume the SAME resolved spec and
may only optimize WITHIN these registry bounds — this module is what makes
"operate within parameters, don't take exact instructions" enforceable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path(__file__).with_name("registry.yaml")

# Keys under a group that are metadata, not tunable params.
_GROUP_META = {"desc", "price_action", "provenance", "engine", "optimize", "note",
               "canonical_menu", "classic_pairs", "classic_menu", "windows_ET",
               "requires_data", "params"}


class SpecError(ValueError):
    """A spec failed validation against the registry."""


@dataclass
class ResolvedSpec:
    name: str
    base_asset: str | None
    policy: dict[str, Any]
    groups: dict[str, dict[str, Any]]   # group -> {param: value}, defaults filled
    families: dict[str, str] = field(default_factory=dict)  # group -> "price_action"|"classic"
    base_preset: str | None = None                          # optional engine Config to start from
    timeframe: str | None = None                            # optional aggregation timeframe (1m..1d)
    explicit: dict[str, set] = field(default_factory=dict)  # group -> {params the spec set by hand}


# --------------------------------------------------------------------------- #
# Registry access
# --------------------------------------------------------------------------- #
def load_registry(path: str | Path = REGISTRY_PATH) -> dict:
    with open(path) as fh:
        reg = yaml.safe_load(fh)
    if "price_action" not in reg or "classic" not in reg:
        raise SpecError("registry missing 'price_action' / 'classic' families")
    return reg


def _all_groups(registry: dict) -> dict[str, tuple[str, dict]]:
    """group name -> (family, group-dict). Errors on a name collision across families."""
    out: dict[str, tuple[str, dict]] = {}
    for family in ("price_action", "classic"):
        for gname, gdef in (registry.get(family) or {}).items():
            if gname in out:
                raise SpecError(f"group {gname!r} defined in two families")
            out[gname] = (family, gdef)
    return out


def _params(gdef: dict) -> dict[str, dict]:
    return gdef.get("params") or {}


# --------------------------------------------------------------------------- #
# Spec loading + validation
# --------------------------------------------------------------------------- #
def load_spec(path: str | Path) -> dict:
    with open(path) as fh:
        spec = yaml.safe_load(fh)
    if not isinstance(spec, dict):
        raise SpecError(f"spec {path} is not a mapping")
    return spec


def validate_spec(spec: dict, registry: dict | None = None) -> ResolvedSpec:
    """Validate `spec` against `registry`; return a ResolvedSpec (defaults filled)."""
    registry = registry or load_registry()
    groups_reg = _all_groups(registry)

    name = spec.get("name")
    if not name:
        raise SpecError("spec must have a 'name'")

    # Effective policy = registry defaults overlaid with the spec's overrides.
    policy = dict(registry.get("policy") or {})
    policy.update(spec.get("policy") or {})

    timeframe = spec.get("timeframe")
    if timeframe is not None:
        from .config import TIMEFRAMES
        if str(timeframe).lower() not in TIMEFRAMES:
            raise SpecError(f"unknown timeframe {timeframe!r}; known: {list(TIMEFRAMES)}")

    spec_groups = spec.get("groups")
    if not isinstance(spec_groups, dict) or not spec_groups:
        raise SpecError("spec must declare a non-empty 'groups' mapping")

    max_groups = policy.get("max_active_groups")
    if max_groups is not None and len(spec_groups) > max_groups:
        raise SpecError(
            f"spec uses {len(spec_groups)} groups but policy.max_active_groups={max_groups}")

    pa_only = bool(policy.get("price_action_only", False))
    resolved: dict[str, dict[str, Any]] = {}
    families: dict[str, str] = {}
    explicit: dict[str, set] = {}

    for gname, overrides in spec_groups.items():
        if gname not in groups_reg:
            raise SpecError(f"unknown group {gname!r} (not in registry)")
        family, gdef = groups_reg[gname]
        families[gname] = family

        if pa_only and not gdef.get("price_action", False):
            raise SpecError(
                f"group {gname!r} is not price-action but policy.price_action_only is set")

        pdefs = _params(gdef)
        overrides = overrides or {}
        if not isinstance(overrides, dict):
            raise SpecError(f"group {gname!r} overrides must be a mapping")

        # Start from defaults, then apply + validate each override.
        values: dict[str, Any] = {p: pd.get("default") for p, pd in pdefs.items()}
        for pname, val in overrides.items():
            if pname not in pdefs:
                raise SpecError(f"unknown param {gname}.{pname!r} (not in registry)")
            _validate_value(gname, pname, pdefs[pname], val)
            values[pname] = val
        resolved[gname] = values
        explicit[gname] = set(overrides.keys())

    _check_constraints(registry.get("constraints") or [], resolved)

    return ResolvedSpec(name=name, base_asset=spec.get("base_asset"),
                        policy=policy, groups=resolved, families=families,
                        base_preset=spec.get("base_preset"), timeframe=timeframe,
                        explicit=explicit)


def _validate_value(gname: str, pname: str, pdef: dict, val: Any) -> None:
    where = f"{gname}.{pname}"
    # Enum
    if "options" in pdef:
        if val not in pdef["options"]:
            raise SpecError(f"{where}={val!r} not in options {pdef['options']}")
        return
    # Numeric with range
    if "min" in pdef and "max" in pdef:
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise SpecError(f"{where}={val!r} must be numeric")
        lo, hi = pdef["min"], pdef["max"]
        if val < lo or val > hi:
            raise SpecError(f"{where}={val} out of range [{lo}, {hi}]")
        return
    # Boolean switch (default is a bool, no range/options)
    if isinstance(pdef.get("default"), bool):
        if not isinstance(val, bool):
            raise SpecError(f"{where}={val!r} must be true/false")
        return
    # Fixed constant without range/options — allow (A/B switch), type-match the default.
    dft = pdef.get("default")
    if dft is not None and type(val) is not type(dft) and not (
            isinstance(val, (int, float)) and isinstance(dft, (int, float))):
        raise SpecError(f"{where}={val!r} type mismatch (expected {type(dft).__name__})")


# --------------------------------------------------------------------------- #
# Cross-param constraints  (e.g. "macd.slow > macd.fast")
# --------------------------------------------------------------------------- #
_OPS = [(">=", lambda a, b: a >= b), ("<=", lambda a, b: a <= b),
        ("==", lambda a, b: a == b), (">", lambda a, b: a > b),
        ("<", lambda a, b: a < b)]


def _operand(tok: str, resolved: dict) -> tuple[Any, bool]:
    tok = tok.strip()
    # number?
    try:
        return (float(tok), True)
    except ValueError:
        pass
    if "." in tok:
        g, _, p = tok.partition(".")
        if g in resolved and p in resolved[g]:
            return (resolved[g][p], True)
    return (None, False)   # references an unused group -> skip the constraint


def _check_constraints(constraints: list[str], resolved: dict) -> None:
    for raw in constraints:
        expr = raw.split("#", 1)[0].strip()   # strip inline comment
        if not expr:
            continue
        for sym, fn in _OPS:
            if sym in expr:
                lhs, rhs = expr.split(sym, 1)
                a, ok_a = _operand(lhs, resolved)
                b, ok_b = _operand(rhs, resolved)
                if ok_a and ok_b and not fn(a, b):
                    raise SpecError(f"constraint violated: {expr}  ({a} {sym} {b} is false)")
                break


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #
def validate_file(path: str | Path, registry: dict | None = None) -> ResolvedSpec:
    return validate_spec(load_spec(path), registry)


# --------------------------------------------------------------------------- #
# Spec -> engine Config
# --------------------------------------------------------------------------- #
# Registry (group, param) -> Config field. ONLY params the engine already
# implements (engine: implemented|partial). Everything else stays unmapped and
# is reported, so a spec can never *silently* change behaviour the engine ignores.
_PARAM_MAP: dict[tuple[str, str], str] = {
    ("fvg", "gap_min_ticks"):        "gap_min_ticks",
    ("fvg", "gap_max_ticks"):        "gap_max_ticks",
    ("cvd_delta", "cvd_trend_count"): "cvd_trend_count",
    ("market_structure", "pivot_k"): "pivot_k",
    ("swing_stops", "pivot_k"):      "pivot_k",       # same field; constraint keeps them equal
    ("swing_stops", "stop_buffer_ticks"): "swing_buf_ticks",
    ("atr", "length"):               "atr_len",
    ("ema_cross", "fast"):           "ema_fast",
    ("ema_cross", "slow"):           "ema_slow",
}
# Params consumed by a group-presence toggle below — not "unmapped" though absent from _PARAM_MAP.
_TOGGLE_CONSUMED: set[tuple[str, str]] = {("vwap", "vwap_veto")}

# Groups whose presence/params actually change engine behaviour TODAY (via
# _PARAM_MAP + the toggles). Everything else is engine:todo and inert until
# wired, so the generator restricts its honest search to these.
WIRED_GROUPS: tuple[str, ...] = ("fvg", "cvd_delta", "vwap", "swing_stops",
                                 "ema_cross", "market_structure")


def effective_signature(cfg) -> tuple:
    """The engine fields that genuinely change behaviour — used to collapse
    candidates that differ only in inert (unwired) knobs, so the search is honest."""
    return (bool(cfg.use_fvg_entry), bool(cfg.use_gap_filter), round(float(cfg.gap_min_ticks), 3),
            round(float(cfg.gap_max_ticks), 3), bool(cfg.use_cvd_filter),
            bool(cfg.use_cvd_streak), int(cfg.cvd_trend_count), bool(cfg.use_vwap_veto),
            bool(cfg.stop_swing), int(cfg.pivot_k), round(float(cfg.swing_buf_ticks), 3),
            bool(cfg.use_ema_cross), int(cfg.ema_fast), int(cfg.ema_slow),
            bool(cfg.use_bos_entry))


def spec_to_config(rspec: ResolvedSpec):
    """Turn a validated spec into an engine Config.

    Returns (Config, unmapped) where `unmapped` lists group.param that the spec
    set by hand but the engine does not yet wire (engine: todo) — the caller
    should surface these so nothing is silently dropped.

    The spec is declarative for the INDICATOR layer: including a group toggles
    its filter on and its (explicit or registry-default) values become
    authoritative; omitting a governable group toggles that filter off. Non-
    indicator mechanics (entry/TP/sizing/account phase) come from `base_preset`
    or Config defaults and are set later by the engine lens.
    """
    from dataclasses import replace
    from .config import Config, PRESETS, contract as get_contract

    if rspec.base_preset:
        if rspec.base_preset not in PRESETS:
            raise SpecError(f"unknown base_preset {rspec.base_preset!r}; "
                            f"known: {sorted(PRESETS)}")
        base = PRESETS[rspec.base_preset]
    else:
        base = Config(name=rspec.name)

    g = rspec.groups
    over: dict[str, Any] = {"name": rspec.name}
    if rspec.base_asset:
        over["contract"] = get_contract(rspec.base_asset)

    # Group-presence toggles (declarative on/off for the indicator filters).
    over["use_gap_filter"] = "fvg" in g
    over["use_cvd_filter"] = "cvd_delta" in g
    if "cvd_delta" in g:
        over["use_cvd_streak"] = True
    over["stop_swing"] = "swing_stops" in g
    over["use_vwap_veto"] = "vwap" in g and bool(g["vwap"].get("vwap_veto", True))

    # Entry generators (Level B). Presence of an explicit entry group turns its
    # generator on: ema_cross -> EMA crossover, market_structure -> break-of-
    # structure (BOS). A spec that declares any explicit entry but NO fvg group is
    # a non-FVG strategy, so the default FVG entry is switched off (otherwise FVG
    # stays on and the generators stack, in priority order). Specs/presets with no
    # entry group at all keep the default FVG entry.
    _ENTRY_GROUPS = {"ema_cross", "market_structure"}
    if "ema_cross" in g:
        over["use_ema_cross"] = True
    if "market_structure" in g:
        over["use_bos_entry"] = True
    if (_ENTRY_GROUPS & set(g)) and "fvg" not in g:
        over["use_fvg_entry"] = False

    # Direct param maps (resolved values include registry defaults).
    for (grp, param), field_name in _PARAM_MAP.items():
        if grp in g and param in g[grp]:
            over[field_name] = g[grp][param]

    cfg = replace(base, **over)

    # Report explicit params the engine does not (yet) wire.
    unmapped: list[str] = []
    for grp, params in rspec.explicit.items():
        for p in params:
            if (grp, p) in _PARAM_MAP or (grp, p) in _TOGGLE_CONSUMED:
                continue
            unmapped.append(f"{grp}.{p}")
    return cfg, sorted(unmapped)
