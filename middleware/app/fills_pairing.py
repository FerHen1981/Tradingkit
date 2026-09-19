"""Pair raw Tradovate Fills-CSV rows into completed trades (one per matched entry+exit).

Input: the per-account daily export `YYYYMMDD_<AccountId>_Fills.csv` that lands in
/root/exports on mex-mw-01. Each row is a single fill. This module runs FIFO position
pairing (splitting quantities when a fill matches several opposite fills) to reconstruct
the same completed trades the LifeOS Trade Journal holds — keyed `{acct3}_{buyFill}_{sellFill}`.

Output feeds `notion_journal.TradeRecord` → `NotionTradeJournal.upsert` (idempotent), so a
processor loop can turn freshly-downloaded fills into live Trade Journal rows.

Pure + deterministic → validated against the real exported data.
"""
from __future__ import annotations

import csv
import datetime as dt
from collections import deque
from dataclasses import dataclass
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# Product root -> $ per full price point (per contract). From the middleware's instrument
# table; extend as needed. Used for gross P&L = price_move * qty * point_value.
POINT_VALUE = {
    "NQ": 20.0, "MNQ": 2.0, "ES": 50.0, "MES": 5.0,
    "GC": 100.0, "MGC": 10.0, "YM": 5.0, "MYM": 0.5,
    "RTY": 50.0, "M2K": 5.0, "CL": 1000.0, "MCL": 100.0, "SI": 5000.0,
}


@dataclass
class Fill:
    fill_id: str
    order_id: str
    ts: dt.datetime          # UTC
    action: int              # 0 = buy, 1 = sell
    qty: int
    price: float
    account: str
    contract: str            # e.g. MGCZ6
    product: str             # e.g. MGC
    tick_size: float
    commission: float
    trade_date: "dt.date | None" = None   # the broker's OWN session label (_tradeDate)

    @property
    def is_buy(self) -> bool:
        return self.action == 0


@dataclass
class CompletedTrade:
    account: str
    buy_fill_id: str         # the buy-side fill (entry if long, exit if short)
    sell_fill_id: str        # the sell-side fill
    direction: str           # "BUY" (long) | "SELL" (short) — the side that OPENED
    qty: int
    entry_price: float
    exit_price: float
    entry_ts: dt.datetime
    exit_ts: dt.datetime
    contract: str
    product: str
    tick_size: float
    gross_pnl: float
    commissions: float
    session_date: "dt.date | None" = None   # trading session the trade CLOSED in (see SESSION_ROLL_ET)


# The CME day rolls at 18:00 ET: the session that opens Sunday 18:00 is Monday's. 17:00-18:00 ET
# is the maintenance break, so nothing trades across the boundary and the exact minute is moot.
# Tradovate labels every fill with that session itself (_tradeDate) — we prefer the broker's label
# and only derive it for sources that have none (the routed-log). Bucketing on the CALENDAR day
# instead puts every trade after 18:00 ET on the wrong day, which silently breaks the firm's
# trading-day count, the profit-day count and the consistency ratio.
SESSION_ROLL_ET = 18


def session_date(ts: dt.datetime) -> dt.date:
    """The trading-session date a timestamp belongs to (18:00 ET rolls into the next session)."""
    et = ts.astimezone(_ET)
    return et.date() + dt.timedelta(days=1) if et.hour >= SESSION_ROLL_ET else et.date()


def _parse_date(s: str) -> "dt.date | None":
    s = (s or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_ts(s: str) -> dt.datetime:
    s = s.strip().replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s)


def parse_fills_csv(path: str) -> list[Fill]:
    out: list[Fill] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                out.append(Fill(
                    fill_id=(r.get("Fill ID") or r["_id"]).strip(),
                    order_id=(r.get("Order ID") or r.get("_orderId", "")).strip(),
                    ts=_parse_ts(r["_timestamp"]),
                    action=int(r["_action"]),
                    qty=int(float(r.get("_qty") or r["Quantity"])),
                    price=float(r.get("_price") or r["Price"]),
                    account=(r.get("Account") or r.get("_accountId", "")).strip(),
                    contract=(r.get("Contract") or "").strip(),
                    product=(r.get("Product") or "").strip(),
                    tick_size=float(r.get("_tickSize") or 0) or 0.0,
                    commission=float(r.get("commission") or 0) or 0.0,
                    trade_date=_parse_date(r.get("_tradeDate") or r.get("Trade Date") or ""),
                ))
            except (KeyError, ValueError):
                continue
    out.sort(key=lambda x: (x.ts, x.fill_id))
    return out


def _emit(entry: Fill, exit_: Fill, qty: int, long: bool) -> CompletedTrade:
    pv = POINT_VALUE.get(entry.product.upper())
    move = (exit_.price - entry.price) if long else (entry.price - exit_.price)
    gross = round(move * qty * pv, 2) if pv else 0.0
    # commission is the matched-share of each leg's fill commission
    comm = round(entry.commission * qty / entry.qty + exit_.commission * qty / exit_.qty, 2)
    buy_fill, sell_fill = (entry, exit_) if long else (exit_, entry)
    return CompletedTrade(
        account=entry.account, buy_fill_id=buy_fill.fill_id, sell_fill_id=sell_fill.fill_id,
        direction="BUY" if long else "SELL", qty=qty,
        entry_price=entry.price, exit_price=exit_.price, entry_ts=entry.ts, exit_ts=exit_.ts,
        contract=entry.contract, product=entry.product, tick_size=entry.tick_size,
        gross_pnl=gross, commissions=comm,
        session_date=exit_.trade_date or session_date(exit_.ts),
    )


def pair_fills(fills: list[Fill]) -> list[CompletedTrade]:
    """FIFO pairing per account. Assumes fills are for one account (or groups by account).
    Splits a fill across several opposite fills, and flips position when a fill overfills."""
    by_acct: dict[str, list[Fill]] = {}
    for f in fills:
        by_acct.setdefault(f.account, []).append(f)

    trades: list[CompletedTrade] = []
    for acct_fills in by_acct.values():
        open_lots: deque[list] = deque()   # each item: [remaining_qty, Fill]; all same side
        open_side: int | None = None       # 0 buy-position (long), 1 sell-position (short)
        for f in acct_fills:
            remaining = f.qty
            # opposite side → close existing lots FIFO
            if open_side is not None and f.action != open_side:
                while remaining > 0 and open_lots:
                    lot = open_lots[0]
                    matched = min(lot[0], remaining)
                    entry_fill, exit_fill = lot[1], f
                    trades.append(_emit(entry_fill, exit_fill, matched, long=(open_side == 0)))
                    lot[0] -= matched
                    remaining -= matched
                    if lot[0] == 0:
                        open_lots.popleft()
                if not open_lots:
                    open_side = None
            # any remainder opens / extends a position on this fill's side
            if remaining > 0:
                if open_side is None:
                    open_side = f.action
                open_lots.append([remaining, f])
    return trades
