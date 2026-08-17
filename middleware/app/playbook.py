"""Payout Playbook — per-account setup + sizing so each account banks the next payout
rung within the 8-trading-day window WITHOUT blowing the trailing drawdown.

Owner's framing: every 8 trading days there's a payout opportunity; in that window we
want to bank the current ladder rung, "not at any cost" — size is the LARGEST that keeps
the estimated chance of breaching the trailing DD under a budget.

Design rules baked in from real fleet feedback:
  - Keep the account's CURRENT validated edge (GC=El Tesoro / ES=El Rey). Never churn a
    working gold account onto ES on window noise. Micro symbols normalise (MGC→GC).
  - Contracts are tradeable: whole minis + micros (0.7 → "7 MGC", 7.5 → "7 ES + 5 MES").
  - Every account gets a row. With enough of its own edge we SIZE it; otherwise we fall
    back to the known phase-start DEFAULTS (funded Milking 2c/day-trail $150, eval
    Pass-hunter 5c/TP144) — the picture is always complete.

Pure + deterministic (seedable RNG) so it's unit-testable. Apex rules are reused from
payout_rules (verified=false upstream — verify against current terms).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .payout_rules import APEX_TARGET, CONSISTENCY_LIMIT, MIN_TRADING_DAYS

APEX_LADDER_50K = [1_500, 1_500, 2_000, 2_500, 2_500, 3_000]   # max payout per rung 1..6

BASES = ("GC", "ES", "NQ", "YM", "CL")
_MICRO = {"GC": "MGC", "ES": "MES", "NQ": "MNQ", "YM": "MYM", "CL": "MCL"}

# Validated edges (3y OOS): only GC + ES carry a real funded edge (both halves PF>1).
# NQ/YM are eval-only "variance tickets" — never compound them on a funded account.
FUNDED_STRAT = {"GC": "El Tesoro", "ES": "El Rey"}
EVAL_STRAT = {"GC": "El Minero", "ES": "El León", "NQ": "El Toro", "YM": "El Toro"}

# Known phase-start presets (the owner's Fase Config defaults) for accounts without edge yet.
PHASE_DEFAULTS = {
    "Funded": {"contracts": 2.0, "day_lock": 150.0, "label": "Milking default · 2c / day-trail $150"},
    "Eval": {"contracts": 5.0, "day_lock": None, "label": "Pass-hunter default · 5c / TP144"},
}


@dataclass
class PlaybookParams:
    horizon: int = MIN_TRADING_DAYS      # 8 trading days to the payout window
    breach_budget: float = 0.15          # max estimated P(breach trailing DD) in the window
    reach_target: float = 0.70           # desired P(reach the rung) at the chosen size
    consistency: float = CONSISTENCY_LIMIT   # 30% — best day ≤ this share of total profit
    max_position: float = 10.0           # firm max contracts
    micros: bool = True                  # allow 0.1-contract (micro) granularity
    sims: int = 1500
    seed: int = 12345


def base_asset(sym: str | None) -> str | None:
    """Normalise a traded symbol to its base future: MGC1!/MGC→GC, MES→ES, ES→ES."""
    if not sym:
        return None
    s = re.sub(r"[^A-Za-z]", "", sym).upper()
    if s in BASES:
        return s
    if s.startswith("M") and s[1:] in BASES:      # micro → base
        return s[1:]
    return s or None


def ladder_rung(size: float | None, payouts_taken: int) -> float:
    """Max payout for the current step. payouts_taken=0 → first rung."""
    base = APEX_LADDER_50K
    idx = max(0, min(int(payouts_taken or 0), len(base) - 1))
    rung = base[idx]
    if size and size != 50_000:
        rung = round(rung * (size / 50_000) / 500) * 500 or rung
    return float(rung)


def parse_size(fase_config: str | None, pos_band: str | None) -> float | None:
    """Current contract size from the owner's Notion fields.
    'Milking (2c/day-trail $150)' → 2 ; 'Pass-hunter (5c/TP144)' → 5 ; '2-4 contracts' → 3."""
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


def contract_label(size: float, asset: str | None) -> str:
    """Tradeable form: whole minis + micros. 0.7 GC → '7 MGC'; 7.5 ES → '7 ES + 5 MES'."""
    b = base_asset(asset) or (asset or "").upper()
    micro = _MICRO.get(b)
    minis = int(size + 1e-9)
    micros = int(round((size - minis) * 10))
    if micros == 10:
        minis, micros = minis + 1, 0
    parts = []
    if minis:
        parts.append(f"{minis} {b}")
    if micros:
        parts.append(f"{micros} {micro or b + '(micro)'}")
    return " + ".join(parts) if parts else f"0 {b}"


def recommend_setup(account: dict, edge_stats: dict | None, current_asset: str | None = None) -> dict:
    """Best asset·strategy to run. Keep the account's current validated edge; otherwise
    default to the robust workhorse (GC) for funded, or the measured best for eval."""
    funded = account.get("stage") == "Funded"
    table = FUNDED_STRAT if funded else EVAL_STRAT
    cur = base_asset(current_asset)

    if cur in table:                                  # already on a validated edge → keep it
        return {"asset": cur, "strategy": table[cur], "keep": True, "measured": True,
                "why": f"keep {cur} · {table[cur]} — validated {'funded' if funded else 'eval'} edge"}

    es = edge_stats or {}
    if funded:                                        # workhorse default (GC = El Tesoro)
        best = "GC"
        why = "GC · El Tesoro — robust funded workhorse (default)"
    else:
        order = ["GC", "ES", "NQ"]

        def rank(sym: str) -> tuple:
            s = es.get(sym) or {}
            return (1 if (s.get("n") or 0) >= 20 else 0, s.get("expectancy") or -1e9, -order.index(sym))
        best = max([a for a in order if a in table], key=rank)
        why = f"{best} · {table[best]} — {'measured best' if (es.get(best, {}).get('n') or 0) >= 20 else 'default'} eval pick"
    return {"asset": best, "strategy": table[best], "keep": False,
            "measured": (es.get(best, {}).get("n") or 0) >= 20, "why": why}


def _samples(daily_pnl: dict, min_day: float = 5.0) -> list[float]:
    return [round(v, 2) for v in daily_pnl.values() if abs(v) >= min_day]


def _simulate(per_contract: list[float], size: float, horizon: int, target: float,
              buffer: float, sims: int, rng: random.Random) -> tuple[float, float]:
    """Bootstrap the account's real per-contract days, scaled to `size`. → (p_reach, p_breach)."""
    if not per_contract or size <= 0 or not buffer or buffer <= 0:
        return 0.0, 1.0
    reach = breach = 0
    for _ in range(sims):
        cum = peak = 0.0
        brk = False
        for _ in range(horizon):
            cum += rng.choice(per_contract) * size
            peak = max(peak, cum)
            if peak - cum > buffer:
                brk = True
                break
        reach += 1 if cum >= target else 0
        breach += 1 if brk else 0
    return round(reach / sims, 3), round(breach / sims, 3)


def _caps(target: float, buffer: float | None, avg_loss: float | None, cur_size: float | None,
          size: float, p: PlaybookParams, day_lock_override: float | None) -> tuple:
    green = max(2, p.horizon // 2)
    day_lock = day_lock_override if day_lock_override is not None else target / green
    day_lock = round(min(p.consistency * target, day_lock), 0)               # 30% consistency cap
    day_stop = round(-buffer / p.horizon, 0) if buffer else None
    sl_cap = round((avg_loss or 0) / cur_size * size, 0) if (avg_loss and cur_size) else None
    return day_lock, day_stop, sl_cap


def build_playbook(account: dict, daily_pnl: dict, asset: str | None, strategy: str | None,
                   edge_stats: dict | None = None, params: PlaybookParams | None = None) -> dict:
    p = params or PlaybookParams()
    stage = account.get("stage", "Eval")
    funded = stage == "Funded"
    size_usd = account.get("size")
    payouts_taken = int(account.get("payouts_taken") or 0)
    cur_asset = base_asset(asset)
    rec = recommend_setup(account, edge_stats, cur_asset)

    if funded:
        target, mode, target_label = ladder_rung(size_usd, payouts_taken), "payout", f"rung {payouts_taken + 1}"
    else:
        target, mode, target_label = float(APEX_TARGET.get(int(size_usd or 0), 3_000)), "eval-pass", "pass target"

    out: dict = {
        "mode": mode, "target": round(target, 0), "target_label": target_label,
        "cur_asset": cur_asset, "rec_asset": rec["asset"], "rec_strategy": rec["strategy"],
        "rec_why": rec["why"], "switch": not rec["keep"] and cur_asset is not None,
        "rung": payouts_taken, "source": None, "contracts": None, "contracts_label": None,
        "day_lock": None, "day_stop": None, "sl_cap": None,
        "p_reach": None, "p_breach": None, "quality": "ok", "note": "",
    }

    cur_size = parse_size(account.get("fase_config"), account.get("pos_band"))
    buffer = account.get("buffer")
    samples = _samples(daily_pnl)
    avg_loss = account.get("avg_loss")

    # 1) edge-based sizing when we have a live buffer + current size + enough traded days.
    if buffer and buffer > 0 and cur_size and len(samples) >= 5:
        per_contract = [s / cur_size for s in samples]
        step = 0.1 if p.micros else 1.0
        rng = random.Random(p.seed)
        best = best_meets = None
        n = 1
        while round(n * step, 1) <= p.max_position:
            size = round(n * step, 1)
            pr, pb = _simulate(per_contract, size, p.horizon, target, buffer, p.sims, rng)
            if pb <= p.breach_budget:
                best = (size, pr, pb)
                if pr >= p.reach_target:
                    best_meets = (size, pr, pb)
                n += 1
                continue
            break                                    # breach rises with size → stop
        chosen = best_meets or best
        if chosen:
            size, pr, pb = chosen
            dl, ds, sl = _caps(target, buffer, avg_loss, cur_size, size, p, None)
            out.update(source="edge", contracts=size, contracts_label=contract_label(size, rec["asset"]),
                       day_lock=dl, day_stop=ds, sl_cap=sl, p_reach=pr, p_breach=pb)
            if not best_meets:
                out["quality"] = "target_unlikely"
                out["note"] = (f"Safe size reaches the rung only ~{int(pr*100)}% of windows — "
                               "consider a lower rung this cycle or more trading days.")
            return out
        # even the smallest size breaches the budget → fall through to the default, flagged fragile.
        out["quality"], out["note"] = "fragile", "Buffer too thin to size from the edge — showing the phase default."

    # 2) phase-start default (fresh account / thin data / fragile) — the picture stays complete.
    d = PHASE_DEFAULTS["Funded" if funded else "Eval"]
    size = min(d["contracts"], p.max_position)
    dl, ds, sl = _caps(target, buffer, avg_loss, cur_size or size, size, p, d["day_lock"])
    out.update(source="default", contracts=size, contracts_label=contract_label(size, rec["asset"]),
               day_lock=dl, day_stop=ds, sl_cap=sl)
    if out["quality"] != "fragile":
        out["quality"] = "default"
    out["note"] = (out["note"] + " · " if out["note"] else "") + d["label"]
    return out
