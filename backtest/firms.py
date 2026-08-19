"""Prop-firm / account-rule registry — the generic, callable module.

The account rules (profit target, drawdown type, daily loss, consistency, payout)
were hard-coded for Apex inside the strategy. Here they live as DATA, one entry
per firm × program × account-size, so the backtester (and, later, the Pine side)
can run ANY firm/asset instead of just Apex-futures.

⚠️ VERIFY BEFORE USE. Prop-firm rules change frequently and vary per plan/promo.
Every entry carries a `source` and an as-of note. Treat these as a seed to
confirm against the firm, not gospel. Add/correct entries freely — this is a
living data file. Cross-check at https://propfirmmatch.com/ and the firm's own
rulebook.

Coverage note: the current backtest account overlay (`engine._account`) models
**trailing-drawdown** firms (Apex / Topstep style). **Static-drawdown** firms
(FTMO and most forex/CFD firms: fixed max-loss + daily-loss, no trailing) are
captured here as DATA but need the dedicated FTMO/static overlay to execute — a
separate, planned build. `drawdown_type` tells you which is which.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Program:
    firm: str
    key: str                      # unique id, e.g. "apex_50k_intraday"
    asset_class: str              # "futures" | "forex" | "cfd" | "crypto" | "stocks"
    stage: str                    # "eval" | "funded"
    account_size: float
    profit_target: Optional[float]        # $ (None for funded)
    max_daily_loss: Optional[float]       # $ (None = no DLL)
    drawdown: float                       # $ trailing or static max loss
    drawdown_type: str                    # "intraday_trailing" | "eod_trailing" | "static"
    trailing_locks_at: Optional[float]    # $ profit where the trail stops (None = never / n.a.)
    min_days: int = 0
    consistency_pct: Optional[float] = None
    profit_split: float = 1.0             # funded split, e.g. 0.9
    activation_fee: Optional[float] = None
    payout_cadence: str = ""
    default_contract: str = ""            # a sensible symbol for this asset class
    notes: str = ""
    source: str = ""
    as_of: str = "2026-07"

    @property
    def executable_now(self) -> bool:
        """Whether the engine can run this firm: trailing (Apex/Topstep) or
        static (FTMO) — both overlays now exist. 'scaling' is not modelled yet."""
        return self.drawdown_type in ("intraday_trailing", "eod_trailing", "static")


# ---------------------------------------------------------------------------
# SEED REGISTRY — well-known firms. VERIFY each before trading a real eval.
# Numbers below are representative as of ~2026-07; confirm current plan rules.
# ---------------------------------------------------------------------------
_APEX_SIZES = {           # account_size: (profit_target, trailing_dd)
    25_000: (1_500, 1_500),
    50_000: (3_000, 2_500),
    100_000: (6_000, 3_000),
    150_000: (9_000, 5_000),
    250_000: (15_000, 6_500),
    300_000: (20_000, 7_500),
}

def _apex_programs():
    out = []
    for size, (tgt, dd) in _APEX_SIZES.items():
        for ddt in ("intraday_trailing", "eod_trailing"):
            tag = "intraday" if ddt == "intraday_trailing" else "eod"
            out.append(Program(
                firm="Apex", key=f"apex_{size//1000}k_{tag}", asset_class="futures",
                stage="eval", account_size=size, profit_target=float(tgt),
                max_daily_loss=None, drawdown=float(dd), drawdown_type=ddt,
                trailing_locks_at=float(dd) + 100, min_days=1, consistency_pct=None,
                profit_split=1.0, payout_cadence="on demand (caps apply)",
                default_contract="NQ",
                notes="One-step eval -> PA. 50% consistency applies on the PA/payout side. "
                      "Apex 4.0 (Mar 2026): no overnight, per-account payout cap, DLL added on newer plans.",
                source="propfirmmatch.com; velotrade/tradetanto/quantcrawler reviews 2026"))
            # matching funded (PA) program
            out.append(Program(
                firm="Apex", key=f"apex_{size//1000}k_{tag}_pa", asset_class="futures",
                stage="funded", account_size=size, profit_target=None,
                max_daily_loss=None, drawdown=float(dd), drawdown_type=ddt,
                trailing_locks_at=float(dd) + 100, min_days=1, consistency_pct=50.0,
                profit_split=0.90, payout_cadence="6-step ladder, then unlimited (caps)",
                default_contract="NQ",
                notes="PA: trailing until lock, 50% consistency, min payout $500, ladder caps "
                      "[1500,1500,2000,2500,2500,3000]. 100% of first $25k then 90/10.",
                source="propfirmmatch.com; Apex rulebook 2026"))
    return out

_SEED = _apex_programs() + [
    # Topstep (futures) — EOD trailing, floor locks at start balance.
    Program(firm="Topstep", key="topstep_50k_eval", asset_class="futures", stage="eval",
            account_size=50_000, profit_target=3_000, max_daily_loss=1_000, drawdown=2_000,
            drawdown_type="eod_trailing", trailing_locks_at=2_000, min_days=2,
            consistency_pct=None, profit_split=0.90, activation_fee=None,
            payout_cadence="after funded, 50/50 then 90/10", default_contract="NQ",
            notes="50k Combine: $2k max loss (EOD trailing), optional $1k DLL, floor locks at "
                  "start balance. VERIFY size table for 100k/150k.",
            source="propfirmmatch.com; phidias/velotrade 2026"),
    # FTMO (forex/CFD) — STATIC max loss + daily loss (NOT trailing). Needs FTMO overlay.
    Program(firm="FTMO", key="ftmo_100k_challenge", asset_class="forex", stage="eval",
            account_size=100_000, profit_target=10_000, max_daily_loss=5_000, drawdown=10_000,
            drawdown_type="static", trailing_locks_at=None, min_days=0, consistency_pct=None,
            profit_split=0.90, activation_fee=None, payout_cadence="on demand (funded)",
            default_contract="EURUSD",
            notes="10% target, 5% daily loss, 10% max loss (STATIC from initial balance). "
                  "2-phase historically; verify current single/two-step + exact %s.",
            source="propfirmmatch.com; lune/journalplus FTMO reviews 2026"),
    Program(firm="FTMO", key="ftmo_50k_challenge", asset_class="forex", stage="eval",
            account_size=50_000, profit_target=5_000, max_daily_loss=2_500, drawdown=5_000,
            drawdown_type="static", trailing_locks_at=None, min_days=0, consistency_pct=None,
            profit_split=0.90, payout_cadence="on demand (funded)", default_contract="EURUSD",
            notes="10% target / 5% daily / 10% static max loss. VERIFY (some sources cite $1,500 "
                  "daily — confirm current plan).",
            source="propfirmmatch.com; lune FTMO review 2026"),
]

def _amt_usd(a, size):
    """Convert an {value,unit} amount to USD given the account size."""
    if a is None:
        return None
    return a["value"] if a["unit"] == "usd" else a["value"] / 100.0 * size


def _program_from_json(rec: dict) -> Program:
    size = rec["account"]["size"]
    tl = rec["targets_limits"]
    tr = rec.get("trading_rules") or {}
    fu = rec.get("funded") or {}
    ex = rec["execution"]
    cons = tr.get("consistency")
    return Program(
        firm=rec["firm"], key=rec["key"], asset_class=rec["asset_class"], stage=rec["stage"],
        account_size=size,
        profit_target=_amt_usd(tl.get("profit_target"), size),
        max_daily_loss=_amt_usd(tl.get("max_daily_loss"), size),
        drawdown=_amt_usd(tl["max_overall_loss"], size),
        drawdown_type=tl["drawdown_type"],
        trailing_locks_at=_amt_usd(tl.get("trailing_locks_at"), size),
        min_days=tr.get("min_trading_days") or 0,
        consistency_pct=(cons["value"] if cons else None),
        profit_split=fu.get("profit_split") or 1.0,
        activation_fee=rec["account"].get("fee"),
        payout_cadence=fu.get("payout_cadence") or "",
        default_contract=ex.get("default_symbol") or "",
        notes=rec["meta"].get("notes", ""), source=rec["meta"].get("source", ""),
        as_of=rec["meta"].get("as_of", ""))


def _load_doc() -> dict:
    """The registry JSON as-is ({} if missing/unreadable). Kept alongside the slim
    Program view for consumers that need fields the dataclass doesn't carry
    (payout ladder, min-profitable-days, min payout — used by funded.py)."""
    import json as _json
    import os as _os
    path = _os.path.join(_os.path.dirname(__file__), "..", "data", "propfirms.json")
    try:
        with open(path) as f:
            return _json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


_DOC = _load_doc()


def raw_programs(firm: str = None, stage: str = None, size: int = None) -> list[dict]:
    """Raw registry program records (dicts straight from data/propfirms.json),
    optionally filtered. Empty list when the registry file is absent."""
    out = []
    for r in _DOC.get("programs", []):
        if firm and str(r.get("firm", "")).lower() != firm.lower():
            continue
        if stage and r.get("stage") != stage:
            continue
        if size is not None and int(((r.get("account") or {}).get("size")) or 0) != int(size):
            continue
        out.append(r)
    return out


def _load_json_registry() -> dict:
    """Programs from data/propfirms.json (the single source of truth) if present;
    else the built-in seed. The JSON is the canonical registry consumed by the
    Pine generator and the middleware too."""
    try:
        if _DOC.get("programs"):
            progs = [_program_from_json(r) for r in _DOC["programs"]]
            return {p.key: p for p in progs}
    except (KeyError, ValueError):
        pass
    return {p.key: p for p in _SEED}


REGISTRY = _load_json_registry()


def program(key: str) -> Program:
    if key not in REGISTRY:
        raise KeyError(f"unknown program {key!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[key]


def firms() -> list[str]:
    return sorted({p.firm for p in REGISTRY.values()})


def programs_for(firm: str = None, asset_class: str = None, stage: str = None) -> list[Program]:
    out = REGISTRY.values()
    if firm:
        out = [p for p in out if p.firm.lower() == firm.lower()]
    if asset_class:
        out = [p for p in out if p.asset_class == asset_class]
    if stage:
        out = [p for p in out if p.stage == stage]
    return sorted(out, key=lambda p: p.key)


def to_overlay(p: Program) -> dict:
    """Map a firm Program onto the engine's account-overlay Config kwargs.

    Only trailing-drawdown firms map cleanly onto the current overlay; static
    firms return phase='Research' (no overlay) until the FTMO/static overlay ships.
    """
    if not p.executable_now:
        return {"phase": "Research", "initial_capital": p.account_size}
    if p.drawdown_type == "static":            # FTMO-style
        phase = "FTMO Challenge" if p.stage == "eval" else "FTMO Funded"
        ov = {
            "phase": phase,
            "dd_model": "Static",
            "initial_capital": p.account_size,
            "acct_trail_dd": p.drawdown,        # fixed max overall loss ($)
            "acct_goal": p.profit_target if p.profit_target else 0.0,
            "acct_dll": p.max_daily_loss if p.max_daily_loss else 0.0,
        }
        # forex/CFD firms size in lots/%-risk, not fixed contracts
        if p.asset_class in ("forex", "cfd", "crypto"):
            ov.update(sizing_mode="pct_risk", fractional_qty=True)
        return ov
    dd_model = "EOD" if p.drawdown_type == "eod_trailing" else "Intraday"
    phase = "Apex Eval" if p.stage == "eval" else "Apex PA"
    return {
        "phase": phase,
        "dd_model": dd_model,
        "initial_capital": p.account_size,
        "acct_trail_dd": p.drawdown,
        "acct_goal": p.profit_target if p.profit_target else 3_000.0,
        "acct_dll": p.max_daily_loss if p.max_daily_loss else 1_000.0,
        # 0 = no rule. Consistency is a funded-account rule: an evaluation has none, so
        # defaulting it to 50 puts a ceiling on the overlay that the firm never set.
        "consistency_pct": p.consistency_pct or (0.0 if p.stage == "eval" else 50.0),
    }
