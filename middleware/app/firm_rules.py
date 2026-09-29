"""Firm-program rules — read from data/propfirms.json (THE single source of truth).

The registry lives at data/propfirms.json and is consumed by the backtester
(backtest/firms.py), the Pine generator (tools/gen_pine_firms.py) and here. This
module is a thin, dependency-free reader so the middleware uses the SAME rules as
everything else — no second copy of the numbers.

Each account carries a firm-program KEY, resolved from the Notion Accounts DB
"Account Type" relation → its "Firm Program" field. Notion families are
size-agnostic (apex_legacy_eval covers 25k/50k/250k); the JSON keys are
size-specific. resolve_key() bridges the two; rules() returns a flat dict the
playbook consumes.
"""
from __future__ import annotations

import functools
import json
import os

# Notion "Firm Program" families that are size-agnostic → expand to a concrete
# size-specific JSON key using the account size (apex_legacy_eval → apex_50k_legacy_eval).
_SIZE_FAMILIES = {"apex_legacy_pa", "apex_intraday_pa", "apex_legacy_eval"}


def _candidate_paths() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.join(here, "..", "..", "data", "propfirms.json"),   # repo: middleware/app -> repo/data
        os.path.join(here, "..", "data", "propfirms.json"),         # middleware/data (if vendored)
        os.path.join(os.getcwd(), "data", "propfirms.json"),
        os.path.join(os.getcwd(), "..", "data", "propfirms.json"),
    ]


@functools.lru_cache(maxsize=1)
def _registry() -> dict:
    for path in _candidate_paths():
        try:
            with open(path) as f:
                doc = json.load(f)
            return {r["key"]: r for r in doc.get("programs", []) if r.get("key")}
        except (FileNotFoundError, KeyError, ValueError):
            continue
    return {}


def _amt_usd(a: dict | None, size: float | None) -> float | None:
    """{value,unit} → USD given the account size ('pct' is % of size)."""
    if not a or size is None:
        return a["value"] if a and a.get("unit") == "usd" else None
    return a["value"] if a.get("unit") == "usd" else a["value"] / 100.0 * size


def resolve_key(family: str | None, size: float | None) -> str | None:
    """Notion Firm Program family (+ account size) → a concrete propfirms.json key."""
    if not family:
        return None
    reg = _registry()
    if family in reg:
        return family
    if family in _SIZE_FAMILIES and size:
        key = family.replace("apex_", f"apex_{int(round(size / 1000))}k_", 1)
        if key in reg:
            return key
    return None


def rules(key: str | None) -> dict | None:
    """Flat rules dict for the playbook, or None when the key is unknown.

    Consistency is returned as a FRACTION (0.30), amounts in USD. None fields mean
    'the program doesn't specify' → the caller keeps its own default.
    """
    rec = _registry().get(key or "")
    if not rec:
        return None
    size = (rec.get("account") or {}).get("size")
    tl = rec.get("targets_limits") or {}
    tr = rec.get("trading_rules") or {}
    fu = rec.get("funded") or {}
    cons = tr.get("consistency")
    mp = tr.get("max_position")
    mpd = tr.get("min_profitable_days") or {}
    return {
        "key": rec["key"], "firm": rec.get("firm"), "display_name": rec.get("display_name"),
        "stage": rec.get("stage"), "size": size, "drawdown_type": tl.get("drawdown_type"),
        "profit_target": _amt_usd(tl.get("profit_target"), size),
        "max_daily_loss": _amt_usd(tl.get("max_daily_loss"), size),
        "drawdown": _amt_usd(tl.get("max_overall_loss"), size),
        "trailing_locks_at": _amt_usd(tl.get("trailing_locks_at"), size),
        # TWO day counters, and they are not the same number: min_days counts days with FILLS,
        # profit_days counts days that cleared profit_day_min. Apex legacy: 8 and 5 x $50.
        "min_days": tr.get("min_trading_days"),
        "profit_days": mpd.get("days") or 0,
        "profit_day_min": _amt_usd(mpd.get("min_each"), size),
        "consistency": (cons["value"] / 100.0 if cons and cons.get("value") else None),
        "max_position": (mp["value"] if mp else None),
        "payout_ladder": fu.get("payout_ladder"),
        "min_payout": fu.get("min_payout"),
        "safety_net_payouts": fu.get("safety_net_payouts"),
        "converts_to": rec.get("converts_to"),
        "verified": bool((rec.get("meta") or {}).get("verified")),
        "notes": (rec.get("meta") or {}).get("notes", ""),
    }


def rules_for_account(account: dict) -> dict | None:
    """Convenience: resolve an account's rules from its firm_program key (+ size).
    Accepts either a pre-resolved key ('firm_program') or a raw Notion family."""
    key = account.get("firm_program") or resolve_key(account.get("firm_program_family"),
                                                      account.get("size"))
    return rules(key)
