"""Payout Playbook — per-account route to the maximum payout, from the SOURCES.

The brand table (merk → markt) komt uit `CLAUDE.md`; de programma-regels komen uit
`data/propfirms.json` via `firm_rules.py`; de contract-doctrine komt uit het
fleet-doc (`docs/state.md`, A-84/A-85/A-90). Dit bestand draagt GEEN eigen
doctrine meer — een regel die hier staat zonder brontverwijzing is een bug.

De schaling in A-90 is ruimte-gebaseerd, niet saldo-gebaseerd: vers draait 1
contract tot de trailing-DD vergrendelt (de "lock"); daarna schaalt het aantal
op de room boven de floor (2 ct vanaf $3.000, 3 ct vanaf $4.500). Een ruimte-
klasse onder $1.300 blijft 1 contract mét dagstop. Eval is een pass-hunter: de
volle MINI op 5 ct, led by El Toro (NQ).
"""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass

from .payout_rules import (APEX_LADDER_50K, APEX_TARGET, CONSISTENCY_LIMIT, MIN_TRADING_DAYS,
                           ladder_caps)

BASES = ("GC", "NQ", "ES", "YM", "CL")
# Merk → micro-instrument, uit de merkentabel in `CLAUDE.md`. De 24-08-regel
# "NQ/YM = eval-only" is INGETROKKEN; El Rey/El Principe draaien MNQ en El
# Leon/El Bandido draaien MYM, ook funded.
_MICRO = {"GC": "MGC", "NQ": "MNQ", "ES": "MES", "YM": "MYM", "CL": "MCL"}

# Validated edges per markt — uit `CLAUDE.md` (herijkt 24-08). Elke regel heeft
# een merk + markt in dat document; iets wat hier staat zonder bronregel is
# een bug. El Minero staat *gereserveerd* en is bewust nog niet in beeld.
FUNDED_STRAT = {"GC": "El Tesoro", "NQ": "El Rey", "ES": "El Matador", "YM": "El Leon"}
EVAL_STRAT = {"NQ": "El Toro", "GC": "El Tesoro", "ES": "El Matador", "YM": "El Leon"}

# Strategie-naam (Notion Accounts DB "Strategy") → base asset — volgt `CLAUDE.md`.
STRAT_ASSET = {
    "El Tesoro": "GC", "El Patron": "GC", "El Patrón": "GC",
    "El Rey": "NQ", "El Principe": "NQ", "El Príncipe": "NQ", "El Toro": "NQ",
    "El Matador": "ES",
    "El Leon": "YM", "El León": "YM", "El Bandido": "YM",
}

# A-90 ruimte-doctrine (fleet-doc, `docs/state.md`). Schaal op *room above floor*,
# niet op saldo. Vers (profit < safety) blijft 1 contract tot de DD vergrendelt;
# daarna schaalt het op de ruimte, met dagstop onder de ondergrens.
A90_LOCKED_LADDER = (
    (4_500, 3),   # ruimte ≥ $4.500 → 3 contracten
    (3_000, 2),   # ruimte ≥ $3.000 → 2 contracten
)
A90_THIN_ROOM = 1_300           # ruimteklasse < $1.300 → 1 contract + dagstop
A90_DAY_TRAIL_USD = 150         # milking day-trail — fleet-doc A-85


def contracts_for_room(room: float | None) -> int:
    """A-90: room boven de floor → aantal contracten (post-lock). Zonder room → 1."""
    if room is None:
        return 1
    for threshold, qty in A90_LOCKED_LADDER:
        if room >= threshold:
            return qty
    return 1

# NOODVAL alleen — `firm_rules.rules_for_account()` leidt. Deze tabel vuurt wanneer een
# account geen `firm_program` draagt (dus geen regel in `data/propfirms.json` resolvet)
# en de firma-naam de firm-name-fallback raakt.
#
# D-149 — géén `ladder` meer in de fallback. De historische `APEX_LADDER_50K` is weerlegd
# door D-148 (vast $2.000 t/m payout 5, uncapped vanaf 6); hem hier opnemen zou precies de
# stilte zijn die D-149 verbiedt (plausibel-maar-onbestaand plafond). `verified: False`
# betekent dat de playbook deze fallback expliciet markeert als onvolledig — zet een
# `firm_program` op het account om een echte, geverifieerde regel te krijgen.
_APEX_FALLBACK = {"ladder": None, "consistency": CONSISTENCY_LIMIT, "min_days": MIN_TRADING_DAYS,
                  "eval_target": APEX_TARGET, "lock_at": 2_600, "min_payout": 500, "days_reset": True,
                  "verified": False, "note": "no firm_program set — propfirms.json entry nodig voor payout-vorm"}
_ASSUMED_RULES = {**_APEX_FALLBACK, "note": "assumed Apex-like — set real firm rules"}
FIRM_RULES = {"Apex Trader Funding": _APEX_FALLBACK, "Apex": _APEX_FALLBACK}


@dataclass
class PlaybookParams:
    horizon: int = MIN_TRADING_DAYS      # 8 trading days to the payout window
    max_position: float = 10.0
    dll_pct: float = 0.20                # daily loss limit = this share of the remaining buffer
    cons_margin: float = 0.67            # pace to ~this × the 30% ceiling → margin under the wall
    reward_risk: float = 3.0             # heal day-cap ≤ this × the DLL (risk/reward-bounded)


def resolve_firm(firm: str | None) -> dict:
    return FIRM_RULES.get((firm or "").strip(), _ASSUMED_RULES)


def resolve_account_rules(account: dict) -> dict:
    """The account's rules, program-first. Start from the firm-name fallback, then
    overlay the exact firm-program from data/propfirms.json (THE single source of
    truth) resolved via the Notion 'Account Type → Firm Program' key. Only fields
    the program actually specifies override the fallback; the rest keep the default."""
    base = dict(resolve_firm(account.get("firm")))
    try:
        from . import firm_rules
        prog = firm_rules.rules_for_account(account)
    except Exception:
        prog = None
    if not prog:
        return base
    base["program"] = prog["key"]
    base["program_name"] = prog.get("display_name")
    base["drawdown_type"] = prog.get("drawdown_type")
    base["max_position"] = prog.get("max_position")
    base["program_drawdown"] = prog.get("drawdown")
    base["program_target"] = prog.get("profit_target")
    base["max_daily_loss"] = prog.get("max_daily_loss")
    base["safety_net_payouts"] = prog.get("safety_net_payouts")
    if prog.get("consistency") is not None:
        base["consistency"] = prog["consistency"]
    elif prog.get("stage") == "eval":
        base["consistency"] = None      # consistency is a funded-account rule; an eval has none
    if prog.get("min_days") is not None:
        base["min_days"] = prog["min_days"]
    if prog.get("trailing_locks_at") is not None:
        base["lock_at"] = prog["trailing_locks_at"]
    if prog.get("min_payout") is not None:
        base["min_payout"] = prog["min_payout"]
    # D-149 — payout-vorm uit de registry; GEEN stille val op `APEX_LADDER_50K` meer.
    # Twee vormen worden erkend; `payout_terms_verified` bepaalt of de playbook iets
    # mag invullen. `false` = de playbook mag géén cap-getal verzinnen.
    if prog.get("payout_ladder"):
        base["ladder"] = prog["payout_ladder"]
    else:
        base["ladder"] = None
    base["payout_cap"] = prog.get("payout_cap")
    base["payout_cap_uncapped_from"] = prog.get("payout_cap_uncapped_from")
    base["payout_terms_verified"] = bool(prog.get("payout_terms_verified"))
    # `verified` dekt het hele programma; `payout_terms_verified` dekt uitsluitend de cap-
    # vorm. Beide moeten waar zijn voordat de playbook een cap-getal toont — dat is de
    # weigering die D-149 vraagt.
    base["verified"] = bool(prog.get("verified")) and base["payout_terms_verified"]
    if not prog.get("verified"):
        base["note"] = f"program {prog['key']} unverified — VERIFY"
    elif not base["payout_terms_verified"]:
        base["note"] = f"program {prog['key']} payout terms NOT verified — set payout_terms_verified"
    else:
        base["note"] = ""
    return base


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
    number in the Drawdown Rule ('EOD ($2000)' → 2000), else the account's OWN firm program,
    else the Apex default for its size.

    The program step matters off Apex: DayTraders Static 25k caps at $750, and falling straight
    through to the Apex 25k default of $1,500 hands that account twice the room it has."""
    from .payout_rules import APEX_DD
    a = account.get("dd_amount")
    if a:
        return float(a)
    m = re.search(r"\$?\s*(\d{3,6})", account.get("dd_rule") or "")
    if m:
        return float(m.group(1))
    try:
        from . import firm_rules
        prog = firm_rules.rules_for_account(account) or {}
        if prog.get("drawdown"):
            return float(prog["drawdown"])
    except Exception:                       # never let the registry break the playbook
        pass
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
    """trailing (Apex/MFFU-style, DD follows equity) · static (fixed max-loss: FTMO /
    legacy 250k) · eval. Prefers the firm-program drawdown_type when known; else falls
    back to stage + size + the Drawdown Rule text."""
    if account.get("stage") not in ("Funded", "funded", "instant"):
        return "eval"
    ddt = (account.get("drawdown_type") or "").lower()
    if ddt:                                              # program is authoritative
        return "static" if ddt == "static" else "trailing"
    size = account.get("size") or 0
    dd = (account.get("dd_rule") or "").upper()
    if size >= 250_000 or "STATIC" in dd:
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
    size_usd = account.get("size")
    firm = account.get("firm")
    rules = resolve_account_rules(account)                  # program-first, single-source
    # limit doubles as a PACING number (how small to keep a day), so it keeps a default even
    # where no rule exists. has_cons is the separate question: does this account type actually
    # carry a consistency rule the firm enforces? An evaluation does not.
    limit = rules["consistency"] or 0.30
    has_cons = rules.get("consistency") is not None
    min_days = rules["min_days"] or MIN_TRADING_DAYS
    lock_at = rules.get("lock_at", 2_600)
    payouts_taken = int(account.get("payouts_taken") or 0)
    cur_instrument = (instrument or "").upper() or None
    track = account_track({**account, "drawdown_type": rules.get("drawdown_type")})
    funded = track != "eval"                                # trailing/static = a live funded account
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

    # --- max-payout mechanics: cap + safety komen uit ÉÉN engine (payout_rules), zelfde bron
    # als L5. D-149 — zonder geverifieerde payout-vorm KRIJGT de cockpit géén cap-getal: dan
    # staat `cap = None` en toont het scherm een expliciet "unknown". De historische
    # `ladder_caps(size_usd)` is NIET meer de stille val — hij wordt alleen gebruikt wanneer
    # het programma een echte ladder heeft (verified door bestaan) en de live engine daarvan
    # een rung heeft bepaald. Zie `_payout_shape` in payout_rules.
    _caps = rules.get("ladder")
    _fixed_cap = rules.get("payout_cap")
    _unc_from = rules.get("payout_cap_uncapped_from")
    terms_known = bool(rules.get("payout_terms_verified"))
    if not terms_known and _caps is None and not _fixed_cap:
        # D-149 — unverified of ongeldige cap-vorm. Zelfs als `pay["cap"]` een getal
        # draagt (bv. 0.0 van de evaluator): niet renderen.
        cap = None
    elif pay.get("cap") is not None and pay.get("cap") != 0:
        cap = round(pay["cap"])                         # live engine already resolved it
    elif _caps:                                         # klassieke ladder uit de registry
        cap = _caps[max(0, min(payouts_taken, len(_caps) - 1))]
    elif _fixed_cap and terms_known:                    # D-148-vorm, uncapped vanaf _unc_from
        cap = 0 if (_unc_from and payouts_taken >= _unc_from) else int(_fixed_cap)
    else:
        cap = None                                      # D-149 — niet raden
    if pay.get("total_cap") is not None:
        total_cap = round(pay["total_cap"])
    elif _caps:
        total_cap = sum(_caps)
    elif _fixed_cap and terms_known and _unc_from:
        total_cap = int(_fixed_cap) * int(_unc_from)
    else:
        total_cap = None
    if cap is None:
        # Zonder cap kan er geen "withdrawable" of "to full" berekend worden.
        cap_for_math = 0
    else:
        cap_for_math = cap
    total_paid = round(account.get("payout_total") or 0)
    safety_bal = pay.get("safety_net_balance")
    dd = rules.get("program_drawdown") or dd_amount(account, size_usd)
    safety = round(safety_bal - starting) if (safety_bal is not None and starting is not None) else round(dd + 100)
    above_safety = round(pay.get("above_safety")) if pay.get("above_safety") is not None \
        else round(max(0.0, profit - safety))
    withdrawable_now = round(min(above_safety, cap_for_math))   # what you can actually pull this step
    maxed = (total_cap or 0) > 0 and total_paid >= (total_cap or 0)
    need_days = days_to_go if days_to_go is not None else max(0, min_days - trading_days)

    if funded:
        if cap is None:
            # D-149 — zonder cap kan de "profit for FULL cap"-regel niet worden berekend;
            # we laten de target op above_safety (de brekende grens) staan en labelen hem
            # expliciet "unverified".
            target, target_label = float(safety + above_safety), "cap unverified — set payout_terms_verified"
        else:
            target, target_label = float(safety + cap_for_math), f"rung {payouts_taken + 1} · ${cap:,.0f}"
    else:
        et = rules.get("program_target")
        if et is None:
            et = rules["eval_target"].get(int(size_usd or 0), 3_000)
        target, target_label = float(et), "pass target"
    to_full = round(max(0.0, target - profit))
    leaving = round(max(0.0, cap_for_math - withdrawable_now))
    # TWO distinct daily numbers, deliberately kept apart:
    #  - day_trail: how you RUN a day (doctrine milking $150 / your Fase Config) — small.
    #  - cons_cap:  the consistency CEILING you must never exceed = 30% of the eventual total.
    day_trail = parse_day_trail(account.get("fase_config")) or (150 if funded else None)
    cons_cap = round(limit * (target if funded else max(profit, target)))
    day_cap = cons_cap                                          # back-compat alias

    # Vers = profit < safety (DD trailt nog mee); gelockt = DD staat vast op −safety.
    locked = profit >= safety
    # Ruimte boven de floor: hoeveel $ er nog zit tussen hier en de breach.
    #   gelockt → safety is de breach-afstand (vast = $2.600 bij 50K trailing).
    #   vers    → `buffer` draagt de live afstand; valt die weg: safety − |profit vóór safety|.
    if locked:
        room = float(safety)
    elif buffer is not None:
        room = max(0.0, float(buffer))
    else:
        room = max(0.0, float(safety) + float(profit))
    thin_room = room < A90_THIN_ROOM

    if track == "eval":
        contracts = 5
    elif track == "static":
        contracts = 3 if (size_usd or 0) >= 300_000 else 2
    elif locked:                                             # trailing, DD gelockt
        contracts = contracts_for_room(room)                 # A-90 room-ladder
    else:                                                    # trailing, vers
        contracts = 1
    mname = "compound" if track == "static" else "milking"
    quality, flags = "ok", []

    # --- decide the phase + the decisive route from where the account actually stands ---
    if track == "eval":
        phase = "eval-sprint"
        route = (f"Eval sprint · {rec['strategy']}. ${to_full:.0f} of ${target:.0f} to pass; "
                 "variance lot, ~1 pass/day, reset on breach.")
    elif maxed:
        phase, contracts, quality = "maxed", 1, "maxed"
        _tc = f"${total_cap:,.0f}" if total_cap is not None else "cap-ladder"
        route = (f"Maxed — ${total_paid:,.0f} of {_tc} paid. Minimize risk: bank & hold, "
                 "shift size to newer accounts.")
    elif cap is None:                                        # D-149 — cap unverified
        phase, quality = mname if funded else "eval-sprint", "unverified_terms"
        route = (f"Payout-vorm is niet geverifieerd voor dit programma. Zet "
                 f"`payout_terms_verified: true` in `data/propfirms.json` nadat Ferry de "
                 f"regels bij de firma heeft bevestigd; tot dan toont de cockpit geen cap.")
        flags.append("payout terms unverified — propfirms.json entry mist of `payout_terms_verified: false`")
    elif eligible and above_safety >= cap_for_math:
        phase, quality = "payout-ready", "payout"
        extra = round(above_safety - cap_for_math)
        route = (f"PAYOUT — pull the FULL ${cap:,.0f} now"
                 + (f" (${extra:,.0f} above the cap carries to next cycle)" if extra > 0 else "")
                 + f", then reset to rung {payouts_taken + 2}.")
    elif profit >= target:                                   # enough for the full cap; days/consistency pending
        phase = mname
        route = (f"Full ${cap:,.0f} in reach (P/L ${profit:,.0f} ≥ ${target:,.0f}). {need_days} more small trading day(s) "
                 f"(keep every day < ${cons_cap:,.0f} = {100 * limit:.0f}% consistency), then withdraw the full ${cap:,.0f}.")
    elif profit >= safety:                                   # can withdraw now, but building to the full cap
        phase = mname
        rate = daily_rate or (day_trail or cons_cap * 0.3)
        days_needed = max(need_days, math.ceil(to_full / rate) if rate > 0 else 0, 1)
        route = (f"Now withdrawable ${withdrawable_now:,.0f} — but +${to_full:,.0f} pulls the FULL ${cap:,.0f} cap: "
                 f"milk small days over ~{days_needed} days (never a day > ${cons_cap:,.0f} = {100 * limit:.0f}% consistency). "
                 f"Banking now leaves ${leaving:,.0f} on the table.")
        if leaving > 0:
            flags.append(f"cap ${cap:,.0f} — don't bank early and leave ${leaving:,.0f}")
    else:                                                    # below the safety net → can't withdraw yet
        phase = "compound" if track == "static" else "survival"
        to_safety = round(safety - profit)
        _cap_txt = f"${cap:,.0f}" if cap is not None else "cap-ladder"
        route = (f"{'Build' if track == 'static' else 'Survival'} — +${to_safety:,.0f} to the "
                 f"safety net (${safety:,.0f}); withdrawals unlock there, then build to the full {_cap_txt} cap. "
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
    # eval is a pass-hunter: keep the AGGRESSIVE doctrine size (5c), never the conservative
    # risk-optimal edge size. Funded milking/survival uses the edge size.
    set_size = float(contracts) if track == "eval" else (es["size"] if es else float(contracts))
    max_pos = rules.get("max_position")                    # program's contract ceiling (from the registry)
    if max_pos and set_size > max_pos:
        set_size = float(max_pos)
    soft_cap = round(cons_cap * p.cons_margin)

    # consistency is a RATIO that averages out: best day ≤ 30% of TOTAL WINNING days; the ceiling
    # RISES as you earn. Heal an outlier by growing total wins to best_day / 30%.
    total_win = round(best_day / (consistency_pct / 100)) if (consistency_pct and best_day > 0) else max(profit, 0)
    broken = bool(has_cons and consistency_pct is not None and limit and consistency_pct > 100 * limit)
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

    if broken and set_day_cap is not None:
        if quality == "ok":
            quality = "consistency"
        edge_txt = f" ({set_size:g} {inst}, exp ${es['exp_pc']:.0f}/ct × {es['tpd']:g} trades/day)" if es else ""
        tag = "SAFE day-cap" if risk_capped else "day-cap"
        flags.append(f"top day ${best_day:,.0f} = {consistency_pct:.0f}% — {tag} ${set_day_cap:,.0f}{edge_txt}; "
                     f"total wins reach ${heal_total:,.0f} (+${heal_deficit:,.0f} ≈ {days_to_heal}d "
                     f"to clear {100 * limit:.0f}%)")
    elif broken:
        # a maxed account has no day-cap to set, but the ceiling still decides the payout
        if quality == "ok":
            quality = "consistency"
        flags.append(f"top day ${best_day:,.0f} = {consistency_pct:.0f}% — total wins reach "
                     f"${heal_total:,.0f} (+${heal_deficit:,.0f}) before this clears {100 * limit:.0f}%")
    elif has_cons and consistency_pct is not None and consistency_pct >= 100 * limit * 0.67:
        if quality == "ok":
            quality = "consistency"
        flags.append(f"consistency {consistency_pct:.0f}% of wins on one day — keep spreading "
                     f"(the {100 * limit:.0f}% ceiling rises as you earn)")

    # --- de ZES invoer-getallen van de fleet-berekening (`tailor.py`, A-84/A-85) ---
    # Zie `docs/state.md` A-84: dit zijn de input-signalen; de score + voorstel
    # komt uit Backtest Setup (Release 3b), niet uit de cockpit.
    #   1. ruimte tot liquidatie      → room (post-lock) / buffer (vers)
    #   2. gelockt of vers            → locked
    #   3. beste dag sinds payout     → best_day (al gemeten in daily_pnl)
    #   4. eerstvolgende cap          → cap (uit payout_rules → propfirms.json)
    #   5. kwalificatiedagen          → {done: trading_days, nodig: min_days, nog: need_days}
    #   6. consistency-ruimte         → heal_total: hoogste winstdag ÷ consistency-%
    inputs = {
        "room": round(room),                 # ruimte boven de floor
        "locked": bool(locked),              # gelockt of vers (trailing-DD)
        "best_day": round(best_day or 0),    # hoogste winstdag deze cycle
        # D-149 — None wanneer de registry geen geverifieerde cap-vorm draagt. De cockpit
        # moet "cap: —" tonen i.p.v. een plausibel-maar-ongefundeerd getal.
        "next_cap": (round(cap) if (funded and cap is not None) else None),
        "payout_terms_verified": bool(rules.get("payout_terms_verified")) if funded else None,
        "min_days": min_days,
        "trading_days": trading_days,
        "days_to_go": int(need_days),
        # Consistency-ruimte zoals Apex hem zelf formuleert in `propfirms.json`
        # (`formula: hoogste winstdag / 0,3 = minimaal vereiste totale winst`).
        # Zonder cons-regel (eval, legacy post-6): None, dan quoten we niets.
        "consistency_min_total":
            round((best_day or 0) / limit) if (has_cons and limit and (best_day or 0) > 0) else None,
        "consistency_limit": limit if has_cons else None,
        "thin_room": bool(thin_room),
    }

    return {
        "track": track, "phase": phase, "firm": firm, "firm_verified": rules["verified"],
        "program": rules.get("program"), "program_name": rules.get("program_name"),
        "drawdown_type": rules.get("drawdown_type"), "max_position": rules.get("max_position"),
        "min_days": min_days, "target": round(target), "target_label": target_label, "route": route,
        "inputs": inputs,                     # D-142 — de invoer van `tailor.py` live
        "cur_instrument": cur_instrument, "rec_instrument": inst, "rec_base": rec.get("base"),
        "rec_strategy": rec["strategy"], "rec_why": rec["why"],
        "switch": not rec["keep"] and cur_instrument is not None, "off_edge": bool(rec.get("off_edge")),
        "contracts": set_size, "contracts_label": contract_label(set_size, inst),
        # exact settables for the alert: edge-derived size + day-cap (profit) + DLL (loss)
        "day_cap": set_day_cap, "dll": dll, "days_plan": days_plan,
        "exp_pc": es["exp_pc"] if es else None, "loss_pc": es["loss_pc"] if es else None,
        "tpd": es["tpd"] if es else None, "day_net": es["day_net"] if es else None,
        "day_trail": day_trail, "cons_cap": cons_cap,
        # the ceiling the FIRM enforces — None where the account type has no such rule,
        # so the cockpit stops quoting Apex's 30% at an evaluation that has none.
        "consistency_limit": limit if has_cons else None,
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
