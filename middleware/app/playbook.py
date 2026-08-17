"""Payout Playbook — the fleet Operating Schema turned into a per-account preset table.

This is NOT an optimizer. It follows the owner's doctrine (LifeOS "MEX Fleet — Operating
Schema"): funded runs ONLY the edge (El Tesoro/GC + El Rey/ES), survival-first 1 ct until
the trailing DD locks, then milking 2 ct / day-trail $150; legacy static/EOD accounts
compound at 2–3 ct GC+ES; eval accounts sprint El Minero (GC) / El Toro (NQ) at 5 ct.

Per account it decides the TRACK (trailing / static / eval) and the PHASE (survival /
milking / payout-ready / compound / eval-sprint), then shows the doctrine preset for it —
asset·strategy, contracts, day-trail — alongside the live payout progress. The owner's own
Fase Config wins where set; doctrine fills the gaps. Pure + deterministic (testable).
"""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass

from .payout_rules import APEX_TARGET, CONSISTENCY_LIMIT, MIN_TRADING_DAYS

APEX_LADDER_50K = [1_500, 1_500, 2_000, 2_500, 2_500, 3_000]   # max payout per rung 1..6

BASES = ("GC", "ES", "NQ", "YM", "CL")
_MICRO = {"GC": "MGC", "ES": "MES", "NQ": "MNQ", "YM": "MYM", "CL": "MCL"}

# Validated edges. Funded = edge only (El Tesoro/GC, El Rey/ES). Eval = El Minero (GC) /
# El Toro (NQ). NQ/YM are eval-only variance lots — never on a funded account.
FUNDED_STRAT = {"GC": "El Tesoro", "ES": "El Rey"}
EVAL_STRAT = {"GC": "El Minero", "ES": "El León", "NQ": "El Toro", "YM": "El Toro"}

# Doctrine presets per phase (contracts + $ day-trail). The Operating Schema numbers.
DOCTRINE = {
    "survival":     {"contracts": 1, "day_trail": None,
                     "note": "1 ct survival-first until the trailing DD locks — payout is won by surviving, not size."},
    "milking":      {"contracts": 2, "day_trail": 150,
                     "note": "2 ct · day-trail $150 — many small green days, keep any day <50% of total profit."},
    "payout-ready": {"contracts": 2, "day_trail": 150,
                     "note": "Threshold + min days met → request the payout, then step up the ladder."},
    "compound":     {"contracts": 2, "day_trail": None,
                     "note": "Static/EOD legacy — GC+ES parallel, 2–3 ct compound motor (roomy buffer)."},
    "eval-sprint":  {"contracts": 5, "day_trail": None,
                     "note": "Eval lot — Pass-hunter 5c / TP144, ~1 pass/day. New evals on El Minero (GC)."},
}

# lock_at = profit at which the Apex trailing DD stops trailing (floor locks at start+$100).
_APEX_RULES = {"ladder": APEX_LADDER_50K, "consistency": CONSISTENCY_LIMIT, "min_days": MIN_TRADING_DAYS,
               "eval_target": APEX_TARGET, "lock_at": 2_600, "verified": True, "note": ""}
_ASSUMED_RULES = {**_APEX_RULES, "verified": False, "note": "assumed Apex-like — set real firm rules"}
FIRM_RULES = {"Apex Trader Funding": _APEX_RULES, "Apex": _APEX_RULES}


@dataclass
class PlaybookParams:
    horizon: int = MIN_TRADING_DAYS      # 8 trading days to the payout window
    max_position: float = 10.0


def resolve_firm(firm: str | None) -> dict:
    return FIRM_RULES.get((firm or "").strip(), _ASSUMED_RULES)


def base_asset(sym: str | None) -> str | None:
    """Normalise a traded symbol to its base future: MGC1!/MGC→GC, MES→ES, ES→ES."""
    if not sym:
        return None
    s = re.sub(r"[^A-Za-z]", "", sym).upper()
    if s in BASES:
        return s
    if s.startswith("M") and s[1:] in BASES:
        return s[1:]
    return s or None


def ladder_rung(size: float | None, payouts_taken: int, ladder: list | None = None) -> float:
    base = ladder or APEX_LADDER_50K
    idx = max(0, min(int(payouts_taken or 0), len(base) - 1))
    rung = base[idx]
    if size and size != 50_000:
        rung = round(rung * (size / 50_000) / 500) * 500 or rung
    return float(rung)


def parse_size(fase_config: str | None, pos_band: str | None) -> float | None:
    """Current contract size from the owner's Notion fields. 'Milking (2c/…)' → 2."""
    if fase_config:
        m = re.search(r"(\d+(?:\.\d+)?)\s*c\b", fase_config)
        if m:
            return float(m.group(1))
    if pos_band:
        nums = [float(x) for x in re.findall(r"\d+", pos_band)]
        if len(nums) == 2:
            return round(sum(nums) / 2, 1)
        if len(nums) == 1:
            return nums[0]
    return None


def parse_day_trail(fase_config: str | None) -> float | None:
    """'Milking (2c/day-trail $150)' → 150."""
    if fase_config:
        m = re.search(r"day-?trail\s*\$?\s*(\d+)", fase_config, re.I)
        if m:
            return float(m.group(1))
    return None


def contract_label(size: float, instrument: str | None) -> str:
    """Contracts in the REAL instrument the account trades (MGC stays MGC, never GC)."""
    sym = (instrument or "").upper() or "?"
    return f"{int(round(size))} {sym}" if abs(size - round(size)) < 1e-9 else f"{size:g} {sym}"


def account_track(account: dict) -> str:
    """trailing (Apex-style 7 funded) · static (legacy 250k/300k, EOD firms) · eval."""
    if account.get("stage") != "Funded":
        return "eval"
    size = account.get("size") or 0
    dd = (account.get("dd_rule") or "").upper()
    if size >= 250_000 or "EOD" in dd or "STATIC" in dd:
        return "static"
    return "trailing"


def account_phase(track: str, account: dict) -> str:
    """Where the account sits on the survival → milking → payout path."""
    if track == "eval":
        return "eval-sprint"
    if track == "static":
        return "compound"
    pay = account.get("payout") or {}
    if pay.get("eligible"):
        return "payout-ready"
    if (pay.get("above_safety") or 0) > 0:      # trailing DD has locked → building
        return "milking"
    return "survival"


# Default instrument per track: small trailing/eval 50k accounts trade MICROS (MGC/MES);
# roomy legacy static accounts trade full minis (GC/ES). Results come from the micro, so
# we keep the real instrument the account trades and never normalise it away.
_DEFAULT_INSTRUMENT = {"trailing": "MGC", "static": "GC", "eval": "MGC"}


def recommend_setup(account: dict, track: str, current_instrument: str | None) -> dict:
    """Strategy from the allocation matrix + the ACTUAL instrument the account trades
    (micro MGC/MES kept as-is). Keep the current validated edge; else default by track."""
    inst = (current_instrument or "").upper() or None
    b = base_asset(inst)
    table = EVAL_STRAT if track == "eval" else FUNDED_STRAT
    if b in table:                                           # already on a validated edge → keep it
        return {"instrument": inst, "base": b, "strategy": table[b], "keep": True,
                "why": f"keep {inst} · {table[b]}"}
    if track == "eval":
        return {"instrument": _DEFAULT_INSTRUMENT["eval"], "base": "GC", "strategy": "El Minero",
                "keep": False, "why": "El Minero (GC) — ~25% more passes than NQ for the same work"}
    off = b in ("NQ", "YM")
    return {"instrument": _DEFAULT_INSTRUMENT[track], "base": "GC", "strategy": "El Tesoro",
            "keep": False, "off_edge": off,
            "why": ("NQ/El Toro is eval-only — move funded to MGC · El Tesoro" if off
                    else "MGC · El Tesoro — robust funded workhorse (default)")}


def build_playbook(account: dict, daily_pnl: dict, instrument: str | None,
                   params: PlaybookParams | None = None) -> dict:
    """Per-account ROUTE to payout: read the account's own history against its firm rules and
    decide the best next move. Not a preset lookup — a grounded, decisive plan."""
    p = params or PlaybookParams()
    funded = account.get("stage") == "Funded"
    size_usd = account.get("size")
    firm = account.get("firm")
    rules = resolve_firm(firm)
    limit = rules["consistency"] or 0.30
    min_days = rules["min_days"]
    lock_at = rules.get("lock_at", 2_600)
    payouts_taken = int(account.get("payouts_taken") or 0)
    cur_instrument = (instrument or "").upper() or None
    track = account_track(account)
    rec = recommend_setup(account, track, cur_instrument)
    inst = rec["instrument"]

    if funded:
        target, target_label = ladder_rung(size_usd, payouts_taken, rules["ladder"]), f"rung {payouts_taken + 1}"
    else:
        target, target_label = float(rules["eval_target"].get(int(size_usd or 0), 3_000)), "pass target"

    # --- state read from the account's OWN history + ledger ---
    daily = daily_pnl or {}
    green = sorted((v for v in daily.values() if v >= 50), reverse=True)
    trading_days = len(green)
    best_day = green[0] if green else 0.0
    daily_rate = statistics.median(green) if green else None            # realistic $/green-day
    pay = account.get("payout") or {}
    current, starting = account.get("current"), account.get("starting")
    profit = round((current - starting) if (current is not None and starting is not None)
                   else (pay.get("profit") or 0.0), 0)
    consistency_pct = round(100 * best_day / profit) if profit > 0 else None
    buffer = account.get("buffer")
    locked = profit >= lock_at
    eligible = bool(pay.get("eligible"))
    day_cap = round(limit * max(profit, target))                         # max single day (consistency)

    quality, flags = "ok", []

    # --- decide the phase and the decisive route from where the account actually stands ---
    if track == "eval":
        phase, contracts = "eval-sprint", 5
        remaining = round(target - profit)
        route = (f"Eval sprint — {contracts} {inst} · {rec['strategy']}. ${remaining:.0f} of ${target:.0f} to pass; "
                 "variance lot, aim ~1 pass/day, reset on breach.")
    elif track == "static":
        phase, contracts = "compound", (3 if (size_usd or 0) >= 300_000 else 2)
        remaining = round(target - profit)
        route = (f"Compound — {contracts} {inst} GC+ES parallel, roomy buffer. ${remaining:.0f} to the rung; "
                 f"consistency slack (keep any day ≤ ${day_cap:.0f}).")
    elif eligible:
        phase, contracts, quality = "payout-ready", 2, "payout"
        w = round(pay.get("withdrawable") or pay.get("above_safety") or 0)
        route = (f"PAYOUT NOW — request ${w:.0f}, then reset to rung {payouts_taken + 2}. "
                 f"Hold 1–2 {inst} to protect the floor meanwhile.")
    elif not locked:
        phase, contracts = "survival", 1
        to_lock = round(max(0, lock_at - profit))
        route = (f"Survival — 1 {inst} only. +${to_lock:.0f} profit to lock the trailing DD "
                 f"(buffer ${int(buffer) if buffer is not None else 0}). Small green days ≤ ${day_cap:.0f}; surviving IS the job.")
        if buffer is not None and buffer < 700:
            quality = "thin_buffer"
            flags.append(f"buffer ${int(buffer)} critical — one bad day breaches")
    else:
        phase, contracts = "milking", 2
        remaining = round(max(0, target - profit))
        need_days = max(0, min_days - trading_days)
        if remaining <= 0:                              # rung already earned → only days + consistency left
            route = (f"Milking — 2 {inst}. Rung ${target:.0f} already banked (P/L ${profit:.0f}). "
                     f"{need_days} more trading day(s) + keep any day ≤ ${day_cap:.0f} (consistency), then withdraw.")
        else:
            rate = daily_rate or day_cap * 0.5
            by_rate = math.ceil(remaining / rate) if rate > 0 else 0
            by_cons = math.ceil(remaining / day_cap) if day_cap > 0 else 0
            days_needed = max(need_days, by_rate, by_cons, 1)
            per_day = round(remaining / days_needed)
            if need_days >= max(by_rate, by_cons):
                bind = f"the {min_days}-day minimum ({trading_days}/{min_days} done)"
            elif by_cons > by_rate:
                bind = f"consistency (no day > ${day_cap:.0f})"
            else:
                bind = "your pace"
            route = (f"Milking — 2 {inst}. ${remaining:.0f} to the rung over ~{days_needed} more day(s) "
                     f"(~${per_day:.0f}/day, cap ${day_cap:.0f}). Binds on {bind}.")
        if buffer is not None and buffer < 1_000:
            quality = "thin_buffer"
            flags.append(f"buffer ${int(buffer)} thin — drop to 1 {inst} until it re-locks")

    if rec.get("off_edge"):
        quality = "switch"
        flags.insert(0, f"running {cur_instrument} on funded — move to {inst} ({rec['strategy']})")
    if not rules["verified"]:
        quality = quality if quality != "ok" else "firm"
        flags.append(f"⚠ {firm or 'firm'} rules {rules['note']}")

    return {
        "track": track, "phase": phase, "firm": firm, "firm_verified": rules["verified"],
        "target": round(target), "target_label": target_label, "route": route,
        "cur_instrument": cur_instrument, "rec_instrument": inst, "rec_base": rec.get("base"),
        "rec_strategy": rec["strategy"], "rec_why": rec["why"],
        "switch": not rec["keep"] and cur_instrument is not None, "off_edge": bool(rec.get("off_edge")),
        "contracts": contracts, "contracts_label": contract_label(contracts, inst),
        "day_cap": day_cap, "consistency_limit": limit,
        "profit": profit, "trading_days": trading_days, "best_day": round(best_day),
        "consistency_pct": consistency_pct, "daily_rate": round(daily_rate) if daily_rate else None,
        "buffer": buffer, "eligible": eligible, "locked": locked,
        "quality": quality, "note": " · ".join(flags),
    }
