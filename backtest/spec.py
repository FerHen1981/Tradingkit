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

    _check_constraints(registry.get("constraints") or [], resolved)

    return ResolvedSpec(name=name, base_asset=spec.get("base_asset"),
                        policy=policy, groups=resolved, families=families)


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
