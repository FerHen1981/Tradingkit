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
               "eval_target": APEX_TARGET, "lock_at": 2_600, "min_payout": 500, "days_reset": True,
               "verified": True, "note": ""}
_ASSUMED_RULES = {**_APEX_RULES, "verified": False, "note": "assumed Apex-like — set real firm rules"}
FIRM_RULES = {"Apex Trader Funding": _APEX_RULES, "Apex": _APEX_RULES}


@dataclass
class PlaybookParams:
    horizon: int = MIN_TRADING_DAYS      # 8 trading days to the payout window
    max_position: float = 10.0
    dll_pct: float = 0.20                # daily loss limit = this share of the remaining buffer
    cons_margin: float = 0.67            # pace to ~this × the 30% ceiling → margin under the wall


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


def dd_amount(account: dict, size: float | None) -> float:
    """The account's drawdown $ — drives the safety net. From DD Amount $, else the EOD/Static
    number in the Drawdown Rule ('EOD ($2000)' → 2000), else the Apex default for its size."""
    from .payout_rules import APEX_DD
    a = account.get("dd_amount")
    if a:
        return float(a)
    m = re.search(r"\$?\s*(\d{3,6})", account.get("dd_rule") or "")
    if m:
        return float(m.group(1))
    return float(APEX_DD.get(int(size or 0), 2_500))


def ladder_caps(size: float | None, ladder: list | None = None) -> list:
    """Max payout per rung, scaled from the Apex 50k ladder for other sizes."""
    base = ladder or APEX_LADDER_50K
    scale = (size or 50_000) / 50_000
    return [round(x * scale) for x in base]


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

    # --- state: consume the Payout engine (SAME rules as the L5 Payout panel), plus history ---
    pay = account.get("payout") or {}
    current, starting = account.get("current"), account.get("starting")
    profit = round(pay.get("profit") if pay.get("profit") is not None
                   else ((current - starting) if (current is not None and starting is not None) else 0.0))
    trading_days = pay.get("trading_days") or 0
    consistency_pct = pay.get("consistency_pct")
    days_to_go = pay.get("days_to_go")
    eligible = bool(pay.get("eligible"))
    buffer = account.get("buffer")
    green = sorted((v for v in (daily_pnl or {}).values() if v >= 50), reverse=True)
    daily_rate = statistics.median(green) if green else None            # $/green-day, for pacing only
    best_day = green[0] if green else 0.0

    # --- max-payout mechanics: put the ladder CAP on top of the engine's above-safety figure ---
    caps = ladder_caps(size_usd, rules["ladder"])
    cap = caps[min(payouts_taken, len(caps) - 1)]           # max withdrawal THIS step (L5 is uncapped)
    total_cap, total_paid = sum(caps), round(account.get("payout_total") or 0)
    safety_bal = pay.get("safety_net_balance")
    dd = dd_amount(account, size_usd)
    safety = round(safety_bal - starting) if (safety_bal is not None and starting is not None) else round(dd + 100)
    above_safety = round(pay.get("above_safety")) if pay.get("above_safety") is not None \
        else round(max(0.0, profit - safety))
    withdrawable_now = round(min(above_safety, cap))
    maxed = total_cap > 0 and total_paid >= total_cap
    need_days = days_to_go if days_to_go is not None else max(0, min_days - trading_days)

    if funded:
        target, target_label = float(safety + cap), f"rung {payouts_taken + 1} · ${cap:,.0f}"   # profit for FULL cap
    else:
        target, target_label = float(rules["eval_target"].get(int(size_usd or 0), 3_000)), "pass target"
    to_full = round(max(0.0, target - profit))
    leaving = round(max(0.0, cap - withdrawable_now))
    # TWO distinct daily numbers, deliberately kept apart:
    #  - day_trail: how you RUN a day (doctrine milking $150 / your Fase Config) — small.
    #  - cons_cap:  the consistency CEILING you must never exceed = 30% of the eventual total.
    day_trail = parse_day_trail(account.get("fase_config")) or (150 if funded else None)
    cons_cap = round(limit * (target if funded else max(profit, target)))
    day_cap = cons_cap                                          # back-compat alias

    if track == "eval":
        contracts = 5
    elif track == "static":
        contracts = 3 if (size_usd or 0) >= 300_000 else 2
    else:                                                   # trailing
        contracts = 1 if profit < safety else 2
    mname = "compound" if track == "static" else "milking"
    quality, flags = "ok", []

    # --- decide the phase + the decisive route from where the account actually stands ---
    if track == "eval":
        phase = "eval-sprint"
        route = (f"Eval sprint — 5 {inst} · {rec['strategy']}. ${to_full:.0f} of ${target:.0f} to pass; "
                 "variance lot, ~1 pass/day, reset on breach.")
    elif maxed:
        phase, contracts, quality = "maxed", 1, "maxed"
        route = (f"Maxed — ${total_paid:,.0f} of ${total_cap:,.0f} ladder paid. Minimize risk: bank & hold "
                 f"1 {inst}, shift size to newer accounts.")
    elif eligible and above_safety >= cap:
        phase, quality = "payout-ready", "payout"
        extra = round(above_safety - cap)
        route = (f"PAYOUT — pull the FULL ${cap:,.0f} now"
                 + (f" (${extra:,.0f} above the cap carries to next cycle)" if extra > 0 else "")
                 + f", then reset to rung {payouts_taken + 2}.")
    elif profit >= target:                                   # enough for the full cap; days/consistency pending
        phase = mname
        route = (f"Full ${cap:,.0f} in reach (P/L ${profit:,.0f} ≥ ${target:,.0f}). {need_days} more small trading day(s) "
                 f"(keep every day < ${cons_cap:,.0f} = 30% consistency), then withdraw the full ${cap:,.0f}.")
    elif profit >= safety:                                   # can withdraw now, but building to the full cap
        phase = mname
        rate = daily_rate or (day_trail or cons_cap * 0.3)
        days_needed = max(need_days, math.ceil(to_full / rate) if rate > 0 else 0, 1)
        trail_txt = f"milk ~${day_trail:,.0f}/day" if day_trail else "small days"
        route = (f"Now withdrawable ${withdrawable_now:,.0f} — but +${to_full:,.0f} pulls the FULL ${cap:,.0f} cap: "
                 f"{trail_txt} over ~{days_needed} days (never a day > ${cons_cap:,.0f} = 30% consistency). "
                 f"Banking now leaves ${leaving:,.0f} on the table.")
        if leaving > 0:
            flags.append(f"cap ${cap:,.0f} — don't bank early and leave ${leaving:,.0f}")
    else:                                                    # below the safety net → can't withdraw yet
        phase = "compound" if track == "static" else "survival"
        to_safety = round(safety - profit)
        route = (f"{'Build' if track == 'static' else 'Survival'} — {contracts} {inst}. +${to_safety:,.0f} to the "
                 f"safety net (${safety:,.0f}); withdrawals unlock there, then build to the full ${cap:,.0f} cap. "
                 f"Keep days small (well under the ${cons_cap:,.0f} consistency ceiling).")
        if track != "static" and buffer is not None and buffer < 700:
            quality = "thin_buffer"
            flags.append(f"buffer ${int(buffer)} critical — one bad day breaches")

    if track == "trailing" and phase in ("milking", "payout-ready") and buffer is not None and buffer < 1_000:
        if quality == "ok":
            quality = "thin_buffer"
        flags.append(f"buffer ${int(buffer)} thin — 1 {inst} until it re-locks")

    if rec.get("off_edge"):
        quality = "switch"
        flags.insert(0, f"running {cur_instrument} on funded — move to {inst} ({rec['strategy']})")
    if not rules["verified"]:
        quality = quality if quality != "ok" else "firm"
        flags.append(f"⚠ {firm or 'firm'} rules {rules['note']}")

    # --- exact, status-based settables to paste straight into the alert ---
    # DLL (daily loss limit): never risk more than ~20% of the remaining buffer in a day,
    # and respect the firm's daily-loss cap (Daily Buffer $) when it's tracked.
    dll = None
    if buffer:
        dll = round(p.dll_pct * buffer)
        if account.get("daily_buffer"):
            dll = min(dll, round(account["daily_buffer"]))
    # day-cap (daily profit target/trail to set): pace so every day stays at a CONSERVATIVE soft
    # target (~cons_margin × the 30% ceiling) — margin under the wall, spread over more days.
    soft_cap = round(cons_cap * p.cons_margin)

    # consistency is a RATIO that averages out: best day ≤ 30% of TOTAL WINNING days, and that
    # ceiling RISES as you earn. Heal an outlier by growing total wins to best_day/30% — and the
    # FASTER route is BIGGER days (up to, never over, the outlier), not micro-caps.
    total_win = round(best_day / (consistency_pct / 100)) if (consistency_pct and best_day > 0) else max(profit, 0)
    broken = bool(consistency_pct is not None and limit and consistency_pct > 100 * limit)
    heal_total = round(best_day / limit) if (broken and best_day > 0 and limit) else 0        # total wins to clear 30%
    heal_deficit = round(max(0, heal_total - total_win)) if broken else 0

    days_plan = days_to_heal = None
    if track == "eval" or maxed:
        set_day_cap = None
    elif broken:
        set_day_cap = round(best_day)                    # optimize UP — run days up to the outlier, never over
        days_to_heal = math.ceil(heal_deficit / best_day) if best_day > 0 else None
    elif profit < safety:
        set_day_cap = round(min(day_trail or 150, soft_cap))
    elif to_full > 0:
        days_plan = max(need_days, math.ceil(to_full / soft_cap) if soft_cap > 0 else 1, 1)
        set_day_cap = min(round(to_full / days_plan), soft_cap)
    else:
        set_day_cap = round(min(day_trail or soft_cap, soft_cap))

    if broken:
        if quality == "ok":
            quality = "consistency"
        risk = (f" — but buffer ${int(buffer)} is thin for days that big; resetting may be safer"
                if (buffer is not None and buffer < 2 * best_day) else "")
        flags.append(f"top day ${best_day:,.0f} = {consistency_pct:.0f}% of wins — heal FAST: run days up to ${best_day:,.0f} "
                     f"(never over) so total wins reach ${heal_total:,.0f} (+${heal_deficit:,.0f} ≈ {days_to_heal}d){risk}")
    elif consistency_pct is not None and consistency_pct >= 100 * limit * 0.67:
        if quality == "ok":
            quality = "consistency"
        flags.append(f"consistency {consistency_pct:.0f}% of wins on one day — keep spreading (the 30% ceiling rises as you earn)")

    return {
        "track": track, "phase": phase, "firm": firm, "firm_verified": rules["verified"],
        "target": round(target), "target_label": target_label, "route": route,
        "cur_instrument": cur_instrument, "rec_instrument": inst, "rec_base": rec.get("base"),
        "rec_strategy": rec["strategy"], "rec_why": rec["why"],
        "switch": not rec["keep"] and cur_instrument is not None, "off_edge": bool(rec.get("off_edge")),
        "contracts": contracts, "contracts_label": contract_label(contracts, inst),
        # exact settables for the alert: status-based day-cap (profit) + DLL (loss) + the 30% ceiling
        "day_cap": set_day_cap, "dll": dll, "days_plan": days_plan,
        "day_trail": day_trail, "cons_cap": cons_cap, "consistency_limit": limit,
        "broken": broken, "heal_total": heal_total or None, "heal_deficit": heal_deficit or None,
        "days_to_heal": days_to_heal,
        "profit": profit, "trading_days": trading_days, "best_day": round(best_day),
        "consistency_pct": consistency_pct, "daily_rate": round(daily_rate) if daily_rate else None,
        "buffer": buffer, "eligible": eligible,
        # max-payout fields
        "cap": cap if funded else None, "safety": safety if funded else None,
        "above_safety": above_safety if funded else None, "withdrawable_now": withdrawable_now if funded else None,
        "to_full": to_full, "leaving": leaving if funded else None,
        "total_paid": total_paid if funded else None, "total_cap": total_cap if funded else None,
        "maxed": bool(maxed), "quality": quality, "note": " · ".join(flags),
    }
