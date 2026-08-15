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

MIN_TRADING_DAYS = 8
MIN_DAY_PROFIT = 50.0
CONSISTENCY_LIMIT = 0.30                                    # best day ≤ 30% of total profit


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
    withdrawable: float
    eligible: bool
    rules: list = field(default_factory=list)


def evaluate(size, starting, current, stage, daily_pnl: dict) -> Payout | None:
    """daily_pnl: {date: realized_net} for this account. stage: 'Funded' | 'Eval'."""
    if size is None or starting is None or current is None:
        return None
    size = int(size)
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
        target = APEX_TARGET.get(size)
        passed = target is not None and profit >= target
        rules.append(Rule("Profit target", None if target is None else passed,
                           f"${profit:,.0f} / ${target:,.0f}" if target else f"${profit:,.0f}"))
        rules.append(Rule("Niet breached", current > starting - APEX_DD.get(size, 0),
                          "boven de floor" if current > starting - APEX_DD.get(size, 0) else "breached"))
        return Payout("Eval", profit, target, trading_days, None if consistency is None else round(100 * consistency, 1),
                      None, 0.0, passed, rules)

    # funded payout checklist
    safety = SAFETY_NET.get(size, 0)
    safety_bal = starting + safety
    meets_days = trading_days >= MIN_TRADING_DAYS
    meets_cons = consistency is None or consistency <= CONSISTENCY_LIMIT
    meets_safety = current >= safety_bal
    withdrawable = round(max(0.0, current - safety_bal), 2)

    rules.append(Rule(f"≥ {MIN_TRADING_DAYS} handelsdagen", meets_days,
                      f"{trading_days} / {MIN_TRADING_DAYS} dagen (≥ ${MIN_DAY_PROFIT:.0f})"))
    rules.append(Rule("30% consistency", meets_cons,
                      "n.v.t." if consistency is None else f"beste dag {100*consistency:.0f}% van winst (≤ 30%)"))
    rules.append(Rule("Safety-net balans", meets_safety,
                      f"${current:,.0f} / ${safety_bal:,.0f}"))
    eligible = meets_days and meets_cons and meets_safety and withdrawable > 0
    return Payout("Funded", profit, None, trading_days,
                  None if consistency is None else round(100 * consistency, 1),
                  round(safety_bal, 2), withdrawable, eligible, rules)
