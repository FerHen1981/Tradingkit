"""Payout & prop-firm rule engine — what can be withdrawn, and which rules still to satisfy.

Pure + deterministic so it's unit-testable against known accounts. The fleet is all Apex today,
so the Apex ruleset is encoded here as CONFIG (verify against Apex's current terms — these are
the values we operate on, not gospel):

  Eval  → pass = reach the profit target without breaching.
  Funded (PA) → to request a payout:
    1. ≥ 8 trading days (a day counts when its realized P&L ≥ $50)
    2. 30% consistency: the best single winning day ≤ 30% of total profit
    3. Safety-net balance: balance ≥ start + (drawdown + $100)
    4. Withdrawable = balance above that safety net

Everything is driven by the account's daily realized P&L (from the trade log) + its balance
(from the ledger). No firm API needed.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

# ---- Apex config (verify against current Apex terms) ---------------------------------
APEX_TARGET = {25_000: 1_500, 50_000: 3_000, 75_000: 4_250, 100_000: 6_000,
               150_000: 9_000, 250_000: 15_000, 300_000: 20_000}
APEX_DD = {25_000: 1_500, 50_000: 2_500, 100_000: 3_000, 150_000: 5_000,
           250_000: 6_500, 300_000: 7_500}
SAFETY_NET = {sz: dd + 100 for sz, dd in APEX_DD.items()}   # min profit to leave in on payout

# Apex PA payout ladder — max withdrawal per payout, rungs 1..6 (50k; scaled for other sizes).
APEX_LADDER_50K = [1_500, 1_500, 2_000, 2_500, 2_500, 3_000]

MIN_TRADING_DAYS = 8
MIN_DAY_PROFIT = 50.0
CONSISTENCY_LIMIT = 0.30                                    # best day ≤ 30% of total profit


def ladder_caps(size) -> list:
    """Max payout per rung, scaled from the Apex 50k ladder for other account sizes."""
    scale = (int(size) if size else 50_000) / 50_000
    return [round(x * scale) for x in APEX_LADDER_50K]


@dataclass
class Rule:
    name: str
    ok: bool | None          # True pass · False fail · None = N/A / not-yet
    detail: str


@dataclass
class Payout:
    stage: str
    profit: float
    target: float | None
    trading_days: int
    consistency_pct: float | None
    safety_net_balance: float | None
    withdrawable: float          # only > 0 when it's a PA account AND every rule is met (capped at the rung)
    eligible: bool
    above_safety: float = 0.0    # $ above the safety net (the total room, before the rung cap)
    days_to_go: int = 0          # trading days still needed
    safety_gap: float = 0.0      # $ still needed to reach the safety-net balance
    cap: float = 0.0             # max withdrawal THIS payout (ladder rung)
    total_cap: float = 0.0       # total the ladder pays over all rungs
    rung: int = 0                # current rung index (payouts taken)
    rules: list = field(default_factory=list)


def evaluate(size, starting, current, stage, daily_pnl: dict, payouts_taken: int = 0,
             program: dict | None = None) -> Payout | None:
    """daily_pnl: {date: realized_net} for this account. stage: 'Funded' | 'Eval'.
    payouts_taken: rungs already banked → selects the ladder cap on the withdrawable.
    program: the account's firm-program rules (from data/propfirms.json, THE single source
    of truth) — supplies min_days / consistency / drawdown / target / ladder per program;
    each field falls back to the Apex-50k default when the program doesn't set it."""
    if size is None or starting is None or current is None:
        return None
    size = int(size)
    prog = program or {}
    min_days = int(prog.get("min_days") or MIN_TRADING_DAYS)
    cons_limit = prog["consistency"] if prog.get("consistency") is not None else CONSISTENCY_LIMIT
    dd_amt = prog.get("drawdown") or APEX_DD.get(size, 0)
    safety = (dd_amt + 100) if dd_amt else SAFETY_NET.get(size, 0)
    caps = prog.get("payout_ladder") or ladder_caps(size)
    profit = round(current - starting, 2)
    funded = str(stage).lower().startswith("fund")
    days = [d for d, v in daily_pnl.items() if v >= MIN_DAY_PROFIT]
    trading_days = len(days)
    wins = [v for v in daily_pnl.values() if v > 0]
    best_day = max(wins) if wins else 0.0
    total_win = sum(wins)
    consistency = (best_day / total_win) if total_win > 0 else None

    rules: list[Rule] = []
    if not funded:
        target = prog["profit_target"] if prog.get("profit_target") is not None else APEX_TARGET.get(size)
        passed = target is not None and profit >= target
        rules.append(Rule("Profit target", None if target is None else passed,
                           f"${profit:,.0f} / ${target:,.0f}" if target else f"${profit:,.0f}"))
        rules.append(Rule("Not breached", current > starting - dd_amt,
                          "above the floor" if current > starting - dd_amt else "breached"))
        return Payout("Eval", profit, target, trading_days,
                      None if consistency is None else round(100 * consistency, 1),
                      None, 0.0, passed, rules=rules)   # eval = not a PA → never withdrawable

    # funded payout checklist
    safety_bal = starting + safety
    above_safety = round(max(0.0, current - safety_bal), 2)     # the potential (gated by rules)
    days_to_go = max(0, min_days - trading_days)
    safety_gap = round(max(0.0, safety_bal - current), 2)
    meets_days = trading_days >= min_days
    meets_cons = consistency is None or consistency <= cons_limit
    meets_safety = current >= safety_bal
    cons_txt = f"{cons_limit * 100:.0f}%"

    rules.append(Rule("Trading days", meets_days,
                      f"{trading_days}/{min_days} met"
                      if meets_days else f"{days_to_go} more to go ({trading_days}/{min_days})"))
    rules.append(Rule("Consistency", meets_cons,
                      "n/a" if consistency is None else
                      (f"best day {100*consistency:.0f}% (under {cons_txt})" if meets_cons
                       else f"best day {100*consistency:.0f}% — spread more (max {cons_txt})")))
    rules.append(Rule("Safety net", meets_safety,
                      f"balance ${current:,.0f} above ${safety_bal:,.0f}"
                      if meets_safety else f"${safety_gap:,.0f} to go → ${safety_bal:,.0f}"))
    # ladder: you can only withdraw up to the current rung's cap per payout.
    rung = max(0, min(int(payouts_taken or 0), len(caps) - 1))
    cap = float(caps[rung])
    # PA account AND every rule met → withdrawable (capped at the rung); otherwise no pay day (0).
    eligible = meets_days and meets_cons and meets_safety and above_safety > 0
    withdrawable = round(min(above_safety, cap), 2) if eligible else 0.0
    return Payout("Funded", profit, None, trading_days,
                  None if consistency is None else round(100 * consistency, 1),
                  round(safety_bal, 2), withdrawable, eligible, above_safety=above_safety,
                  days_to_go=days_to_go, safety_gap=safety_gap,
                  cap=cap, total_cap=float(sum(caps)), rung=rung, rules=rules)
