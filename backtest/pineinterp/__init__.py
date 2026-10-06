"""A Pine interpreter for exactly the subset the MEX fleet uses — and nothing else.

WHY THIS EXISTS (spoor B, D-101). Today the backtester is a hand-written Python
*re-implementation* of the Pine logic, so two engines can drift and D-66 has to guard
CVD parity between them. Ferry's answer 14: let the backtester read the `.pine` file
itself. One implementation, no parity to guard (D-66 folds into this).

THE NON-NEGOTIABLE CONTRACT — HARD-FAIL ON THE UNKNOWN. An interpreter that silently
skips a construct it does not understand produces a *plausible and wrong* backtest —
the same failure mode as the silent fallbacks in D-68 (2500 drawdown), D-75 and D-31.
So every layer here refuses loudly on anything outside the supported subset, and the
supported subset is the enumerated one from D-100
(`validation/PINE_INVENTORY_20260928.md`), not "whatever parses".

BUILD ORDER (incremental — smallest step that reaches the goal first, D-101):
  1. lexer      — tokenize; hard-fail on any character that is not a valid token.   <-- THIS INCREMENT
  2. parser     — build an AST for the subset; hard-fail on any construct not in it.
  3. capability — check every call/name against the D-100 manifest; hard-fail on the unknown.
  4. evaluator  — run bar-by-bar, mapping ta.* onto the existing backtest/indicators.py
                  primitives (the 12 core ta functions already have equivalents there),
                  ignoring only provably visual-only output (plot/label/table/color).
  5. harness    — feed the result through the existing walk-forward / MC / stress / funded mill.

DAILY-LIMIT RULE FOR THE FUNDED SIM (D-109/D-110, and it settles the D-68 question):
when the evaluator's prop-firm overlay applies a daily loss limit it uses the FIRM value
from `data/propfirms.json` (`targets_limits.max_daily_loss`) — that is a fact about the
firm and keeps the number comparable between programs. Ferry's own brake (`owner_caps`,
the `min(sl*mult*qty, room*frac)` formula) is an operational choice, NOT a firm rule, so
it stays OUT of the simulation; modelling it would measure his behaviour instead of the
firm's. (This is why D-68 correctly reads acct_dll from the registry: that IS the firm
value; the $1000 on Apex EOD is the firm-DLL, per D-109.)

Nothing in this package may import from middleware/** or web/** (plan §spoor B).
"""
from __future__ import annotations

from .lexer import Tok, TokType, PineLexError, tokenize
from .capabilities import (UnsupportedPineError, check_supported, namespaced_calls,
                           SUPPORTED_TA, SUPPORTED_NAMESPACES)
from .parser import parse_expression, PineParseError

__all__ = ["Tok", "TokType", "PineLexError", "tokenize",
           "UnsupportedPineError", "check_supported", "namespaced_calls",
           "SUPPORTED_TA", "SUPPORTED_NAMESPACES",
           "parse_expression", "PineParseError"]
