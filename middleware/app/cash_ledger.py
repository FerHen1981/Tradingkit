"""Parse Tradovate Cash_History exports → the exact per-account ledger (source of truth).

Cash_History is the master ledger: every cash event with the running balance and a
`Cash Change Type`. From it we get, exactly (no reconstruction drift):

  balance        the latest running Amount  (= Tradovate's real cash)
  commissions    Σ of Commission deltas
  trade_pnl      Σ of Trade Paired deltas   (gross of commission)
  funding        Σ of Fund Transaction deltas (initial + resets/activations if typed so)
  payouts        Σ of Payout/Withdrawal deltas (negative = paid out)
  by_type        the full breakdown per Cash Change Type

The drawdown FLOOR (STOP) + account TYPE come from the Apex PA-Charts dashboard, not this
file; buffer = balance − STOP. Exports are per-account (like the Fills), so one file = one
account.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field


def _money(s: str) -> float:
    s = (s or "").strip().replace(",", "").replace("$", "")
    if not s:
        return 0.0
    neg = s.startswith("(") and s.endswith(")")   # $(210.00) style
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def _is_funding(t: str) -> bool:
    return "fund transaction" in t.lower()


def _is_payout(t: str) -> bool:
    return any(w in t.lower() for w in ("payout", "withdraw"))


@dataclass
class AccountLedger:
    account: str
    balance: float = 0.0
    n_events: int = 0
    n_payouts: int = 0                                             # count of payout/withdrawal events
    by_type: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    # net realized per calendar date (Trade Paired + Commission + fees; NOT funding/payouts) —
    # the exact daily P&L the consistency / profit-day rules run on, straight from the broker ledger.
    daily_realized: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def commissions(self) -> float:
        return round(-self.by_type.get("Commission", 0.0), 2)      # positive cost

    @property
    def trade_pnl(self) -> float:
        return round(self.by_type.get("Trade Paired", 0.0), 2)

    @property
    def funding(self) -> float:
        return round(sum(v for k, v in self.by_type.items() if _is_funding(k)), 2)

    @property
    def payouts(self) -> float:
        # any withdrawal/payout-styled type (negative delta = money out)
        return round(sum(v for k, v in self.by_type.items() if _is_payout(k)), 2)

    @property
    def daily(self) -> dict[str, float]:
        return {d: round(v, 2) for d, v in self.daily_realized.items()}


def parse_cash_history(path: str) -> dict[str, AccountLedger]:
    """Aggregate a Cash_History CSV into per-account ledgers (keeps the last running balance)."""
    out: dict[str, AccountLedger] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            acct = (row.get("Account") or "").strip()
            if not acct:
                continue
            led = out.setdefault(acct, AccountLedger(account=acct))
            typ = (row.get("Cash Change Type") or "").strip()
            delta = _money(row.get("Delta"))
            led.by_type[typ] += delta
            if _is_payout(typ):
                led.n_payouts += 1
            elif not _is_funding(typ):                # trading deltas (Trade Paired, Commission, fees)
                date = (row.get("Date") or "").strip()
                if date:
                    led.daily_realized[date] += delta
            amt = _money(row.get("Amount"))
            if amt:
                led.balance = amt          # rows are chronological → last wins
            led.n_events += 1
    for led in out.values():
        led.balance = round(led.balance, 2)
    return out


def parse_balance_history(path: str) -> dict[str, list[tuple[str, float, float]]]:
    """Account_Balance_History → per account a daily series of (date, total_amount, realized).
    The running peak = max(total_amount) gives the exact base for the trailing floor."""
    out: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            acct = (row.get("Account Name") or row.get("Account ID") or "").strip()
            if not acct:
                continue
            out[acct].append((
                (row.get("Trade Date") or "").strip(),
                _money(row.get("Total Amount")),
                _money(row.get("Total Realized PNL")),
            ))
    return dict(out)


def peak_balance(series: list[tuple[str, float, float]]) -> float:
    return round(max((b for _, b, _ in series), default=0.0), 2)
