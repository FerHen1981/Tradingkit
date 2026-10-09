"""Capability gate — increment 2 of the interpreter (D-101).

The interpreter supports EXACTLY the Pine surface the fleet uses (D-100), and refuses
everything else. This module is that refusal, enforced on the token stream so it is not
fooled by text inside comments or strings: it walks the tokens, finds every namespaced
call (`ns.fn(...)`), and HARD-FAILS with the offending names + line numbers if any lies
outside the manifest. A silent pass on an unknown call is the crack that lets a wrong
backtest look right (D-68/D-75/D-31), so there is no "warn and continue" here.

The manifest below is the D-100 inventory (`validation/PINE_INVENTORY_20260928.md`),
curated by hand. It is deliberately FROZEN: when Pine Dev later adds a construct a script
did not use before, this gate catches it, and the interpreter is only ever built for what
is listed here. Widening the interpreter therefore means widening this manifest on purpose
— never by accident.

This gate checks NAMESPACED calls (the compute core; `ta.*` per-function, other namespaces
per-namespace). Bare user-function calls need the parser to tell them from built-ins, so
they are increment 3, not here.
"""
from __future__ import annotations

from .lexer import Tok, TokType, tokenize


class UnsupportedPineError(Exception):
    """A construct outside the supported subset. Never swallowed (see module docstring)."""


# The 13 ta.* functions the fleet uses (D-100). The evaluator maps each onto an existing
# backtest/indicators.py primitive. ta.requestVolumeDelta appears only in PATRON/TESORO
# (the non-canonical TradingView delta) — supported, but flagged there by design.
SUPPORTED_TA: frozenset[str] = frozenset({
    "highest", "lowest", "barssince", "ema", "atr", "hma", "pivothigh", "pivotlow",
    "sma", "stdev", "vwap", "vwma", "requestVolumeDelta",
})

# The EXACT set of root namespaces the 13 scripts use (D-100 — measured, not guessed).
# Split by what the evaluator will do with each, but for the GATE all that matters is that
# the namespace is known: anything outside this frozen set is unknown -> hard fail, which
# is how a genuinely new Pine feature (or a typo) gets caught.
#   compute  — the evaluator implements these (ta is checked per-function below)
_COMPUTE_NS = {"ta", "math", "str", "array", "input", "strategy", "request",
               "timeframe", "syminfo", "barstate", "dayofweek"}
#   visual / enum-constant — the headless evaluator ignores these (plot/label/box/table
#   drawing and the enum namespaces used as their arguments: display.none, size.tiny, …)
_VISUAL_NS = {"color", "chart", "alert", "plot", "line", "label", "box", "table",
              "display", "format", "position", "location", "shape", "size", "text"}
SUPPORTED_NAMESPACES: frozenset[str] = frozenset(_COMPUTE_NS | _VISUAL_NS)


def namespaced_calls(toks: list[Tok]) -> list[tuple[str, str, int]]:
    """Every `ns.fn` in the token stream as (namespace, function, line). A call is an
    IDENT followed by DOT and IDENT; strings and comments are already gone from the
    stream, so this never matches text inside them."""
    out = []
    for i in range(len(toks) - 2):
        a, dot, b = toks[i], toks[i + 1], toks[i + 2]
        if a.type == TokType.IDENT and dot.type == TokType.DOT and b.type == TokType.IDENT:
            # skip member access chained off another member (x.y.z -> only y.z would also
            # match, but we only care whether the ROOT namespace is a known top-level one)
            if i > 0 and toks[i - 1].type == TokType.DOT:
                continue
            out.append((a.value, b.value, a.line))
    return out


def check_supported(src: str, name: str = "<pine>") -> dict:
    """Verify a Pine source uses only the supported namespaced surface. Returns a small
    report {name, ta_used, namespaces_used} on success; raises UnsupportedPineError listing
    every offending call (with line) otherwise. Also raises PineLexError via tokenize()."""
    toks = tokenize(src, name=name)
    calls = namespaced_calls(toks)

    unknown: list[str] = []
    ta_used, ns_used = set(), set()
    for ns, fn, line in calls:
        if ns == "ta":
            ta_used.add(fn)
            if fn not in SUPPORTED_TA:
                unknown.append(f"{name}:{line}: unsupported ta.{fn} (not in the D-100 manifest)")
        else:
            ns_used.add(ns)
            if ns not in SUPPORTED_NAMESPACES:
                unknown.append(f"{name}:{line}: unsupported namespace {ns!r} ({ns}.{fn})")

    if unknown:
        raise UnsupportedPineError(
            f"{name}: {len(unknown)} construct(s) outside the supported subset — the "
            f"interpreter refuses rather than model them wrongly:\n  " + "\n  ".join(unknown))
    return {"name": name, "ta_used": sorted(ta_used), "namespaces_used": sorted(ns_used)}
