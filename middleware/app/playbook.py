"""Payout Playbook — per-account sizing so each account reaches the next payout rung
within the 8-trading-day window, WITHOUT blowing the trailing drawdown.

The idea (owner's framing): every 8 trading days there's a payout opportunity. In that
window we want to bank the current ladder rung — but "not at any cost": size is chosen as
the LARGEST that still keeps the estimated chance of breaching the trailing DD under a
budget, while giving a good chance of reaching the rung.

Pure + deterministic (seedable RNG) so it's unit-testable. It reads:
  - firm rules   → reused from payout_rules (Apex config) + the payout ladder below,
  - the rung     → account["payouts_taken"] (Notion "Payouts (0-6)"),
  - the edge     → the account's own daily realized P&L series (the real distribution),
  - current size → parsed from the Notion "Fase Config" / "Position Size" fields.

Everything is an ESTIMATE and labelled as such — firm rules carry verified=false upstream.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from .payout_rules import APEX_TARGET, CONSISTENCY_LIMIT, MIN_TRADING_DAYS

# Apex PA payout ladder (max withdrawal per payout, rungs 1..6). Verify against current terms.
# The fleet is Apex 50K today; other sizes fall back to the 50K ladder scaled by size.
APEX_LADDER_50K = [1_500, 1_500, 2_000, 2_500, 2_500, 3_000]

# Micro contract per asset (1 micro = 0.1 mini) — lets small accounts size finely.
_MICRO = {"GC": "MGC", "ES": "MES", "NQ": "MNQ", "YM": "MYM", "CL": "MCL"}

# Validated edges (3y OOS): only GC + ES carry a real funded edge (both halves PF>1).
# NQ/YM are eval-only "variance tickets" — never compound them on a funded account.
FUNDED_STRAT = {"GC": "El Tesoro", "ES": "El Rey"}
EVAL_STRAT = {"GC": "El Minero", "ES": "El León", "NQ": "El Toro", "YM": "El Toro"}
# Default preference when the fleet has no measured edge yet (GC = robust workhorse first).
_FUNDED_ORDER = ["GC", "ES"]
_EVAL_ORDER = ["GC", "ES", "NQ"]


def recommend_setup(account: dict, edge_stats: dict | None) -> dict:
    """Best asset·strategy to run this account on, given its stage and the fleet's measured edge.
    edge_stats: {asset_sym: {"expectancy": float, "pf": float|None, "n": int}}."""
    funded = account.get("stage") == "Funded"
    table = FUNDED_STRAT if funded else EVAL_STRAT
    order = _FUNDED_ORDER if funded else _EVAL_ORDER
    es = edge_stats or {}

    def rank(sym: str) -> tuple:
        s = es.get(sym) or {}
        has = 1 if (s.get("n") or 0) >= 20 else 0        # enough trades to trust the number
        return (has, s.get("expectancy") or -1e9, -order.index(sym))

    eligible = [a for a in order if a in table]
    best = max(eligible, key=rank)
    s = es.get(best) or {}
    measured = (s.get("n") or 0) >= 20
    why = (f"{best} leads the funded edges (exp ${s.get('expectancy'):.0f}/trade, PF {s.get('pf')})"
           if measured and funded else
           f"{best} — {'measured best' if measured else 'default'} for a {'funded' if funded else 'eval'} account")
    return {"asset": best, "strategy": table[best], "measured": measured, "why": why}


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


def _samples(daily_pnl: dict, min_day: float = 5.0) -> list[float]:
    """Realized net on days the account actually traded (both green and red)."""
    return [round(v, 2) for v in daily_pnl.values() if abs(v) >= min_day]


def _simulate(per_contract: list[float], size: float, horizon: int, target: float,
              buffer: float, sims: int, rng: random.Random) -> tuple[float, float]:
    """Monte-Carlo the window by bootstrapping the account's real per-contract days,
    scaled to `size` contracts. Returns (p_reach_target, p_breach_buffer)."""
    if not per_contract or size <= 0 or not buffer or buffer <= 0:
        return 0.0, 1.0
    reach = breach = 0
    for _ in range(sims):
        cum = peak = 0.0
        hit = brk = False
        for _ in range(horizon):
            cum += rng.choice(per_contract) * size
            peak = max(peak, cum)
            if peak - cum > buffer:          # gave back more than the buffer → breach
                brk = True
                break
            if cum >= target:
                hit = True
        reach += 1 if (hit or cum >= target) else 0
        breach += 1 if brk else 0
    return round(reach / sims, 3), round(breach / sims, 3)


def build_playbook(account: dict, daily_pnl: dict, asset: str | None, strategy: str | None,
                   edge_stats: dict | None = None, params: PlaybookParams | None = None) -> dict:
    """Per-account preset: which asset·strategy to run + recommended contracts + day-cap +
    SL-cap to bank the rung within the 8-day window inside the breach budget."""
    p = params or PlaybookParams()
    rec = recommend_setup(account, edge_stats)
    size_usd = account.get("size")
    stage = account.get("stage", "Eval")
    funded = stage == "Funded"
    payouts_taken = int(account.get("payouts_taken") or 0)

    # window target: funded → next ladder rung; eval → the pass target.
    if funded:
        target = ladder_rung(size_usd, payouts_taken)
        mode, target_label = "payout", f"rung {payouts_taken + 1}"
    else:
        target = float(APEX_TARGET.get(int(size_usd or 0), 3_000))
        mode, target_label = "eval-pass", "pass target"

    out: dict = {
        "mode": mode, "target": round(target, 0), "target_label": target_label,
        "asset": asset, "strategy": strategy, "rung": payouts_taken,
        "rec_asset": rec["asset"], "rec_strategy": rec["strategy"], "rec_why": rec["why"],
        "switch": bool(asset and asset.upper() != rec["asset"]),
        "rec_contracts": None, "micro": None, "day_lock": None, "day_stop": None,
        "sl_cap": None, "p_reach": None, "p_breach": None, "quality": "ok", "note": "",
    }

    cur = parse_size(account.get("fase_config"), account.get("pos_band"))
    # the LIVE remaining distance to the trailing floor — never fall back to the full DD
    # (that would overstate safety on an account already deep in its buffer).
    buffer = account.get("buffer")
    samples = _samples(daily_pnl)
    avg_loss = account.get("avg_loss")   # $ per trade at current size

    if not buffer:
        out["quality"], out["note"] = "no_buffer", "No DD buffer known — set it in the Accounts DB."
        return out
    if not cur or not samples or len(samples) < 5:
        out["quality"] = "thin_data"
        out["note"] = ("Need current size (Fase Config) + ≥5 traded days to size from the real "
                       f"edge (have size={cur}, days={len(samples)}).")
        return out

    per_contract = [s / cur for s in samples]                    # size-normalized daily edge
    step = 0.1 if p.micros else 1.0
    rng = random.Random(p.seed)

    best = None
    n = 1
    while True:
        size = round(n * step, 1)
        if size > p.max_position:
            break
        pr, pb = _simulate(per_contract, size, p.horizon, target, buffer, p.sims, rng)
        if pb <= p.breach_budget:
            best = (size, pr, pb)                                 # largest safe size so far
            if pr >= p.reach_target:
                best_meets = (size, pr, pb)                       # and it reaches the target
            n += 1
            continue
        break                                                    # breach rises with size → stop
    best_meets = locals().get("best_meets")

    chosen = best_meets or best
    if not chosen:
        out["quality"], out["note"] = "fragile", (
            "Even the smallest size breaches the budget — buffer too thin this window; rebuild first.")
        return out

    size, pr, pb = chosen
    green_days = max(2, p.horizon // 2)                           # spread over ≥ half the window
    # day-cap (profit lock): never let one day exceed the 30% consistency share, and pace to target.
    day_lock = round(min(p.consistency * target, target / green_days), 0)
    # day loss-stop: don't give back more than an even slice of the buffer in a single day.
    day_stop = round(-buffer / p.horizon, 0)
    sl_cap = round((avg_loss or 0) / cur * size, 0) if avg_loss else None

    out.update(rec_contracts=size, day_lock=day_lock, day_stop=day_stop,
               sl_cap=sl_cap, p_reach=pr, p_breach=pb)
    micro_sym = _MICRO.get((asset or rec["asset"]).upper())
    if micro_sym and abs(size - round(size)) > 1e-9:             # fractional → express in micros
        out["micro"] = f"{int(round(size * 10))} {micro_sym}"
    if not best_meets:
        out["quality"] = "target_unlikely"
        out["note"] = (f"Safe size reaches the rung only ~{int(pr*100)}% of windows — "
                       "consider a lower rung this cycle or more trading days.")
    return out
