"""Funded-account payout overlay — the third lens.

Given a strategy's daily realized P&L, simulate a funded prop account over time:
apply the trailing/static drawdown floor, the (optional) daily loss limit, and
the Apex payout cycle (>=8 qualifying trading days, 30% consistency, safety-net
balance, laddered payout caps). Answers "once funded, does it survive and pay
out, and how much per month?".

Pure Python (no pandas) so it is unit-testable. The classic lens says whether
there's an edge; the eval funnel says how reliably it funds; this says what a
funded account actually yields.

Apex config below is what we operate on — verify against Apex's current terms.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# FALLBACK constants only — used when data/propfirms.json lacks the account size.
# The registry (via backtest.firms) is the single source; see apex_rules().
APEX_DD = {25_000: 1_500, 50_000: 2_500, 100_000: 3_000,
           150_000: 5_000, 250_000: 6_500, 300_000: 7_500}
MIN_TRADING_DAYS = 8
MIN_DAY_PROFIT = 50.0
CONSISTENCY_LIMIT = 0.30          # best winning day <= 30% of the cycle's total wins
SAFETY_BUFFER = 100.0            # leave start + drawdown + this in on a payout
LADDER = [1_500, 1_500, 2_000, 2_500, 2_500, 3_000]   # per-payout caps (Apex 50k-ish)


def _val(x):
    return x.get("value") if isinstance(x, dict) else x


def apex_rules(account_size: float = 50_000) -> dict:
    """Funded-account rules for this size, read from data/propfirms.json via
    backtest.firms (the single source of truth). Prefers the EOD-DD PA program
    (the fleet's drawdown model); falls back to the eval program of the same size
    for the drawdown; falls back to the module constants when the registry lacks
    the size entirely. `source` names which registry key supplied the rules."""
    rules = {"drawdown": float(APEX_DD.get(int(account_size), 2_500)),
             "min_qual_days": MIN_TRADING_DAYS, "min_day_profit": MIN_DAY_PROFIT,
             "consistency_limit": CONSISTENCY_LIMIT, "safety_buffer": SAFETY_BUFFER,
             "ladder": list(LADDER), "min_payout": 0.0, "profit_split": 1.0,
             "daily_loss_limit": None, "source": "fallback-constants"}
    try:
        from .firms import raw_programs
        apex = raw_programs(firm="Apex", size=int(account_size))
    except Exception:
        return rules
    funded = sorted((r for r in apex if r.get("stage") == "funded"),
                    key=lambda r: 0 if "eod" in r.get("key", "") else 1)
    src = funded[0] if funded else (apex[0] if apex else None)
    if src is None:
        return rules
    tl = src.get("targets_limits") or {}
    dd = _val(tl.get("max_overall_loss"))
    if dd:
        rules["drawdown"] = float(dd)
        locks = _val(tl.get("trailing_locks_at"))
        if locks:
            rules["safety_buffer"] = max(float(locks) - float(dd), 0.0)
    tr = src.get("trading_rules") or {}
    cons = tr.get("consistency") or {}
    if cons.get("type") == "max_day_pct_of_total" and cons.get("value"):
        rules["consistency_limit"] = float(cons["value"]) / 100.0
    mpd = tr.get("min_profitable_days") or {}
    if mpd.get("days"):
        rules["min_qual_days"] = int(mpd["days"])
    me = _val(mpd.get("min_each"))
    if me:
        rules["min_day_profit"] = float(me)
    if funded:                        # payout & risk rules exist only on the PA side
        mdl = _val(tl.get("max_daily_loss"))
        if mdl:
            rules["daily_loss_limit"] = float(mdl)
        fu = src.get("funded") or {}
        if fu.get("payout_ladder"):
            rules["ladder"] = [float(x) for x in fu["payout_ladder"]]
        if fu.get("min_payout"):
            rules["min_payout"] = float(fu["min_payout"])
        if fu.get("profit_split"):
            rules["profit_split"] = float(fu["profit_split"])
    rules["source"] = src.get("key", "?")
    return rules


def account_drawdown(account_size: float = 50_000) -> float:
    """Trailing drawdown for this account size, registry-first."""
    return apex_rules(account_size)["drawdown"]


@dataclass
class Payout:
    date: object
    amount: float            # net to the trader (after profit split)
    balance_after: float
    cycle_days: int


@dataclass
class FundedResult:
    account_size: float
    drawdown_type: str
    drawdown: float
    payouts: list = field(default_factory=list)
    total_withdrawn: float = 0.0
    num_payouts: int = 0
    breached: bool = False
    breach_date: object = None
    breach_reason: str = ""
    trading_days: int = 0
    qualifying_days: int = 0
    final_balance: float = 0.0
    days_to_first_payout: int | None = None
    months: float = 0.0
    per_month: float = 0.0


def simulate_funded(daily_pnl: dict, account_size: float = 50_000,
                    drawdown_type: str = "eod_trailing", drawdown: float | None = None,
                    daily_loss_limit: float | None = None, profit_split: float | None = None
                    ) -> FundedResult:
    """daily_pnl: {date: realized_net}. Walks it chronologically. All account
    rules come from data/propfirms.json via apex_rules() — explicit arguments
    override the registry; profit_split/daily_loss_limit left at None take the
    registry's value (pass 0 to disable the DLL explicitly)."""
    rules = apex_rules(account_size)
    dd = float(drawdown if drawdown is not None else rules["drawdown"])
    if daily_loss_limit is None:
        daily_loss_limit = rules["daily_loss_limit"]
    if profit_split is None:
        profit_split = rules["profit_split"]
    ladder = rules["ladder"]
    start = float(account_size)
    safety_bal = start + dd + rules["safety_buffer"]   # balance to leave in on payout
    floor_cap = start + rules["safety_buffer"]         # trailing floor locks here
    res = FundedResult(account_size=start, drawdown_type=drawdown_type, drawdown=dd)

    series = sorted(daily_pnl.items())
    if not series:
        res.final_balance = start
        return res

    balance = peak = start
    floor = start - dd
    cyc_qual, cyc_wins, cyc_days = 0, [], 0
    first_date = series[0][0]

    for d, pnl in series:
        pnl = float(pnl)
        if daily_loss_limit and pnl <= -abs(daily_loss_limit):
            res.breached, res.breach_date = True, d
            res.breach_reason = f"daily loss ${pnl:,.0f} exceeded DLL ${daily_loss_limit:,.0f}"
            break

        balance += pnl
        res.trading_days += 1
        cyc_days += 1
        if pnl >= rules["min_day_profit"]:
            res.qualifying_days += 1
            cyc_qual += 1
        if pnl > 0:
            cyc_wins.append(pnl)

        if drawdown_type != "static":
            peak = max(peak, balance)
            floor = min(peak - dd, floor_cap)

        if balance <= floor:
            res.breached, res.breach_date = True, d
            res.breach_reason = f"balance ${balance:,.0f} hit floor ${floor:,.0f}"
            break

        best = max(cyc_wins) if cyc_wins else 0.0
        total_win = sum(cyc_wins)
        cons_ok = total_win <= 0 or best / total_win <= rules["consistency_limit"]
        if cyc_qual >= rules["min_qual_days"] and cons_ok and balance >= safety_bal:
            above = balance - safety_bal
            cap = ladder[min(res.num_payouts, len(ladder) - 1)]
            gross = min(above, cap)
            if gross < rules["min_payout"]:
                continue                       # registry minimum payout not met yet
            balance -= gross
            net = round(gross * profit_split, 2)
            res.payouts.append(Payout(d, net, round(balance, 2), cyc_days))
            res.total_withdrawn = round(res.total_withdrawn + net, 2)
            res.num_payouts += 1
            if res.days_to_first_payout is None:
                res.days_to_first_payout = res.trading_days
            cyc_qual, cyc_wins, cyc_days = 0, [], 0     # fresh cycle after a payout

    res.final_balance = round(balance, 2)
    last_date = series[min(res.trading_days, len(series)) - 1][0] if res.trading_days else first_date
    try:
        months = max((last_date - first_date).days / 30.44, 1 / 30.44)
    except Exception:
        months = 0.0
    res.months = round(months, 2)
    res.per_month = round(res.total_withdrawn / months, 2) if months > 0 else 0.0
    return res


def summarize(res: FundedResult) -> dict:
    """Compact dict for the run registry / Journey."""
    return {
        "payouts": res.num_payouts,
        "withdrawable": res.total_withdrawn,      # total taken over the sim
        "per_month": res.per_month,
        "months": res.months,
        "breached": res.breached,
        "breach_reason": res.breach_reason,
        "trading_days": res.trading_days,
        "qualifying_days": res.qualifying_days,
        "days_to_first_payout": res.days_to_first_payout,
        "final_balance": res.final_balance,
        "account_size": res.account_size,
    }


def daily_from_trades(trades) -> dict:
    """Aggregate a list of engine Trade objects into {date: net}."""
    out: dict = {}
    for t in trades:
        xt = getattr(t, "exit_time", None)
        if xt is None:
            continue
        day = xt.date() if hasattr(xt, "date") else xt
        out[day] = out.get(day, 0.0) + float(getattr(t, "net", 0.0) or 0.0)
    return out
