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

from .payout_rules import (APEX_LADDER_50K, APEX_TARGET, CONSISTENCY_LIMIT, MIN_TRADING_DAYS,
                           ladder_caps)

BASES = ("GC", "ES", "NQ", "YM", "CL")
_MICRO = {"GC": "MGC", "ES": "MES", "NQ": "MNQ", "YM": "MYM", "CL": "MCL"}

# Validated edges. Funded = edge only (El Tesoro/GC, El Rey/ES). Eval = El Minero (GC) /
# El Toro (NQ). NQ/YM are eval-only variance lots — never on a funded account.
FUNDED_STRAT = {"GC": "El Tesoro", "ES": "El Rey"}
EVAL_STRAT = {"GC": "El Minero", "ES": "El León", "NQ": "El Toro", "YM": "El Toro"}

# Strategy name (Notion Accounts DB "Strategy" field) → base asset, for counting eval passes.
STRAT_ASSET = {"El Tesoro": "GC", "El Minero": "GC", "El Rey": "ES", "El León": "ES", "El Leon": "ES",
               "El Toro": "NQ", "El Matador": "NQ", "El Dorado": "NQ", "El Patrón": "NQ", "El Patron": "NQ"}

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
    reward_risk: float = 3.0             # heal day-cap ≤ this × the DLL (risk/reward-bounded)


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


# Default instrument per track — different goals, different tools:
#   funded trailing (survive/milk) → MICROS (MGC/MES), small and conservative;
#   eval (pass-hunter, hit the target fast) → full MINIS (NQ/GC/ES), aggressive;
#   legacy static (compound, roomy buffer) → full minis.
_DEFAULT_INSTRUMENT = {"trailing": "MGC", "static": "GC", "eval": "NQ"}


def recommend_setup(account: dict, track: str, current_instrument: str | None,
                    edge_stats: dict | None = None) -> dict:
    """Strategy from the allocation matrix + the ACTUAL instrument the account trades
    (micro MGC/MES kept as-is). Keep the current validated edge; else pick data-driven."""
    inst = (current_instrument or "").upper() or None
    b = base_asset(inst)
    table = EVAL_STRAT if track == "eval" else FUNDED_STRAT
    if b in table:                                           # already on a validated edge → keep it
        # eval trades the full MINI (aggressive pass-hunter); funded keeps its actual micro.
        keep_inst = b if track == "eval" else inst
        return {"instrument": keep_inst, "base": b, "strategy": table[b], "keep": True,
                "why": f"keep {keep_inst} · {table[b]}" + (" (mini)" if track == "eval" else "")}
    if track == "eval":
        # data-driven: rank eval assets by MEASURED fleet net; default order El Toro-first (NQ has
        # been the top eval passer in practice — the old El Minero default was a stale schema claim).
        es = edge_stats or {}
        order = ["NQ", "GC", "ES"]
        cand = [a for a in order if a in table]

        def rank(sym: str) -> tuple:
            s = es.get(sym) or {}
            # registered eval passes (from Notion) win; then measured net; then the El Toro default.
            return (s.get("passes") or 0, s.get("net") or -1e18, -order.index(sym))
        best = max(cand, key=rank)
        best_passes = (es.get(best, {}).get("passes") or 0)
        why = (f"{best} · {table[best]} — most eval passes ({best_passes}) [Notion]" if best_passes
               else f"{best} · {table[best]} — default eval passer (set Strategy in the Accounts DB to rank on real passes)")
        return {"instrument": best, "base": best, "strategy": table[best],   # best = the full MINI (eval = aggressive)
                "keep": False, "why": why}
    off = b in ("NQ", "YM")
    return {"instrument": _DEFAULT_INSTRUMENT[track], "base": "GC", "strategy": "El Tesoro",
            "keep": False, "off_edge": off,
            "why": ("NQ/El Toro is eval-only — move funded to MGC · El Tesoro" if off
                    else "MGC · El Tesoro — robust funded workhorse (default)")}


def edge_size(account: dict, cur_size: float | None, trading_days: int, dll: float | None,
              params: PlaybookParams) -> dict | None:
    """Size the account from what it ACTUALLY does per trade — heat (avg loss) and potential
    (expectancy) per contract — instead of a static number. Returns the risk-optimal size, the
    expected daily net at that size, and the per-contract edge, or None when data is too thin."""
    exp = account.get("expectancy")
    avg_loss = account.get("avg_loss")
    trades = account.get("trades") or 0
    if not (exp and avg_loss and cur_size and trades and trading_days) or cur_size <= 0:
        return None
    tpd = max(0.5, trades / trading_days)                 # trades per day
    exp_pc = exp / cur_size                                # potential: expected $/trade per contract
    loss_pc = abs(avg_loss) / cur_size                    # heat: $ given back per losing trade / contract
    if exp_pc <= 0 or loss_pc <= 0:
        return None
    # risk-optimal size: ~3 average losing trades should equal the daily loss limit. Whole
    # contracts of the traded instrument (a micro like MGC is already the smallest unit → min 1).
    raw = min(dll / (loss_pc * 3) if dll else params.max_position, params.max_position)
    size = max(1, round(raw))
    day_net = round(size * exp_pc * tpd)                   # expected net/day at this size
    heat_day = round(size * loss_pc * max(1.0, tpd * (1 - (account.get("win_pct") or 50) / 100)))
    return {"size": size, "day_net": day_net, "tpd": round(tpd, 1),
            "exp_pc": round(exp_pc, 1), "loss_pc": round(loss_pc, 1), "heat_day": heat_day}


def build_playbook(account: dict, daily_pnl: dict, instrument: str | None,
                   edge_stats: dict | None = None, params: PlaybookParams | None = None) -> dict:
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
    rec = recommend_setup(account, track, cur_instrument, edge_stats)
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

    # --- max-payout mechanics: the ladder CAP + safety come from the ONE engine (payout_rules),
    # the same source L5 renders. Fallbacks only for thin unit-test payloads. ---
    _caps = ladder_caps(size_usd)
    cap = round(pay["cap"]) if pay.get("cap") else _caps[max(0, min(payouts_taken, len(_caps) - 1))]
    total_cap = round(pay["total_cap"]) if pay.get("total_cap") else sum(_caps)
    total_paid = round(account.get("payout_total") or 0)
    safety_bal = pay.get("safety_net_balance")
    dd = dd_amount(account, size_usd)
    safety = round(safety_bal - starting) if (safety_bal is not None and starting is not None) else round(dd + 100)
    above_safety = round(pay.get("above_safety")) if pay.get("above_safety") is not None \
        else round(max(0.0, profit - safety))
    withdrawable_now = round(min(above_safety, cap))         # what you can actually pull this step
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
        route = (f"Eval sprint · {rec['strategy']}. ${to_full:.0f} of ${target:.0f} to pass; "
                 "variance lot, ~1 pass/day, reset on breach.")
    elif maxed:
        phase, contracts, quality = "maxed", 1, "maxed"
        route = (f"Maxed — ${total_paid:,.0f} of ${total_cap:,.0f} ladder paid. Minimize risk: bank & hold, "
                 "shift size to newer accounts.")
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
        route = (f"Now withdrawable ${withdrawable_now:,.0f} — but +${to_full:,.0f} pulls the FULL ${cap:,.0f} cap: "
                 f"milk small days over ~{days_needed} days (never a day > ${cons_cap:,.0f} = 30% consistency). "
                 f"Banking now leaves ${leaving:,.0f} on the table.")
        if leaving > 0:
            flags.append(f"cap ${cap:,.0f} — don't bank early and leave ${leaving:,.0f}")
    else:                                                    # below the safety net → can't withdraw yet
        phase = "compound" if track == "static" else "survival"
        to_safety = round(safety - profit)
        route = (f"{'Build' if track == 'static' else 'Survival'} — +${to_safety:,.0f} to the "
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
    # SIZE + day-cap from what the account ACTUALLY does per trade (heat = avg loss, potential =
    # expectancy). es is None when trade data is too thin → fall back to the doctrine size.
    cur_size = parse_size(account.get("fase_config"), account.get("pos_band"))
    es = edge_size(account, cur_size, trading_days, dll, p)
    set_size = es["size"] if es else float(contracts)
    soft_cap = round(cons_cap * p.cons_margin)

    # consistency is a RATIO that averages out: best day ≤ 30% of TOTAL WINNING days; the ceiling
    # RISES as you earn. Heal an outlier by growing total wins to best_day / 30%.
    total_win = round(best_day / (consistency_pct / 100)) if (consistency_pct and best_day > 0) else max(profit, 0)
    broken = bool(consistency_pct is not None and limit and consistency_pct > 100 * limit)
    heal_total = round(best_day / limit) if (broken and best_day > 0 and limit) else 0
    heal_deficit = round(max(0, heal_total - total_win)) if broken else 0

    days_plan = days_to_heal = None
    risk_capped = False
    if track == "eval" or maxed:
        set_day_cap = None
    elif broken:
        # heal at the expected net/day the risk-optimal size delivers — never above the outlier.
        pace = es["day_net"] if es else (round(p.reward_risk * dll) if dll else round(best_day))
        set_day_cap = min(round(best_day), max(1, pace))
        risk_capped = set_day_cap < round(best_day)
        days_to_heal = math.ceil(heal_deficit / set_day_cap) if set_day_cap > 0 else None
    elif profit < safety:
        set_day_cap = min(es["day_net"], soft_cap) if es else round(min(day_trail or 150, soft_cap))
    elif to_full > 0:
        days_plan = max(need_days, math.ceil(to_full / soft_cap) if soft_cap > 0 else 1, 1)
        pace = es["day_net"] if es else round(to_full / days_plan)
        set_day_cap = min(max(1, pace), soft_cap)
    else:
        set_day_cap = round(min(day_trail or soft_cap, soft_cap))

    if broken:
        if quality == "ok":
            quality = "consistency"
        edge_txt = f" ({set_size:g} {inst}, exp ${es['exp_pc']:.0f}/ct × {es['tpd']:g} trades/day)" if es else ""
        tag = "SAFE day-cap" if risk_capped else "day-cap"
        flags.append(f"top day ${best_day:,.0f} = {consistency_pct:.0f}% — {tag} ${set_day_cap:,.0f}{edge_txt}; "
                     f"total wins reach ${heal_total:,.0f} (+${heal_deficit:,.0f} ≈ {days_to_heal}d to clear 30%)")
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
        "contracts": set_size, "contracts_label": contract_label(set_size, inst),
        # exact settables for the alert: edge-derived size + day-cap (profit) + DLL (loss)
        "day_cap": set_day_cap, "dll": dll, "days_plan": days_plan,
        "exp_pc": es["exp_pc"] if es else None, "loss_pc": es["loss_pc"] if es else None,
        "tpd": es["tpd"] if es else None, "day_net": es["day_net"] if es else None,
        "day_trail": day_trail, "cons_cap": cons_cap, "consistency_limit": limit,
        "broken": broken, "heal_total": heal_total or None, "heal_deficit": heal_deficit or None,
        "days_to_heal": days_to_heal, "risk_capped": risk_capped,
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
