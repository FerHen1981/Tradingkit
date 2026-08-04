"""Reconciliation engine — measure the discrepancy between the INTENDED trade (the
TradingView signal the middleware fanned out) and the ACTUAL fills at each venue
(Tradovate for futures, MT5/MetaAPI for FX). Pure functions here; the Reconciler that
pulls fills and writes to LifeOS lives in reconciler.py.

Per matched (intended, fill) it computes:
  - slippage: fill price vs intended price, in price / ticks / % / $ (if pointvalue known)
  - latency: seconds between the signal and the actual fill
  - qty diff: filled qty vs intended qty (partial fill / rejection)

P&L-deviation needs the paired exit fill (realized vs expected R); it is computed by the
Reconciler when both entry and exit fills for a position are matched, and left null here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# symbol -> (mintick, point_value_$) for $-slippage. Extend as needed; unknown -> $ skipped.
INSTRUMENTS = {
    "NQ": (0.25, 20.0), "MNQ": (0.25, 2.0),
    "ES": (0.25, 50.0), "MES": (0.25, 5.0),
    "GC": (0.10, 100.0), "MGC": (0.10, 10.0),
    "YM": (1.0, 5.0), "MYM": (1.0, 0.5),
    "SI": (0.005, 5000.0),
}

# MT5/broker symbol -> our strategy base, so cross-venue fills pair to the right signal.
# Extend with your broker's symbols. (MT5 price scales differ from futures, so $/tick
# slippage is only computed for the futures venue; price/% is computed for both.)
ALIASES = {"US500": "ES", "US100": "NQ", "US30": "YM", "XAUUSD": "GC", "XAGUSD": "SI"}


def _norm(symbol: str) -> str:
    s = symbol.upper()
    if s in ALIASES:               # broker symbol like "US500" -> "ES" (before digit-stripping)
        return ALIASES[s]
    base = s.rstrip("!0123456789")  # "GC1!" -> "GC", "MNQ1!" -> "MNQ"
    return ALIASES.get(base, base)


def _instrument(symbol: str):
    return INSTRUMENTS.get(_norm(symbol))


@dataclass
class Fill:
    venue: str          # "tradovate" | "mt5"
    account: str
    symbol: str
    side: str           # "buy" | "sell"
    price: float
    qty: float
    ts: float           # epoch seconds
    order_ref: str = ""


def compute_discrepancies(intended: dict, fill: Fill) -> dict:
    """intended: {strategy, symbol, side, price, qty, ts}. Returns the discrepancy metrics."""
    signed = 1.0 if fill.side == "buy" else -1.0
    # slippage: positive = filled WORSE than intended (paid more on a buy / less on a sell)
    slip_price = (fill.price - intended["price"]) * signed
    # tick/$ slippage only for the futures venue (MT5 price scales differ; price/% stay valid)
    inst = _instrument(fill.symbol) if fill.venue == "tradovate" else None
    slip_ticks = slip_price / inst[0] if inst else None
    slip_usd = slip_price * inst[1] * fill.qty if inst else None
    slip_pct = (slip_price / intended["price"] * 100.0) if intended.get("price") else None
    return {
        "strategy": intended.get("strategy"),
        "venue": fill.venue,
        "account": fill.account,
        "symbol": fill.symbol,
        "side": fill.side,
        "intended_price": intended.get("price"),
        "fill_price": fill.price,
        "slippage_price": round(slip_price, 6),
        "slippage_ticks": round(slip_ticks, 2) if slip_ticks is not None else None,
        "slippage_usd": round(slip_usd, 2) if slip_usd is not None else None,
        "slippage_pct": round(slip_pct, 4) if slip_pct is not None else None,
        "latency_s": round(fill.ts - intended["ts"], 3) if intended.get("ts") else None,
        "intended_qty": intended.get("qty"),
        "fill_qty": fill.qty,
        "qty_diff": (fill.qty - intended["qty"]) if intended.get("qty") is not None else None,
        "fill_ts": fill.ts,
    }


def find_intended(fill: Fill, intended_list: list[dict], window_s: float = 90.0) -> dict | None:
    """The intended signal that best matches a fill (same side + symbol base + closest time)."""
    fbase = _norm(fill.symbol)
    best, best_dt = None, None
    for sig in intended_list:
        if sig.get("side") != fill.side or _norm(sig["symbol"]) != fbase:
            continue
        dt = abs(fill.ts - sig.get("ts", fill.ts))
        if dt <= window_s and (best_dt is None or dt < best_dt):
            best, best_dt = sig, dt
    return best


def pair_roundtrips(fills: list[Fill]) -> list[dict]:
    """FIFO-pair opening and closing fills per (venue, account, symbol) into round-trips.
    Simple 1-lot-oriented netting (a fill of the opposite side closes the oldest open one);
    good enough for the common single-contract case, refine for partials later."""
    from collections import defaultdict, deque
    books: dict = defaultdict(deque)
    trips: list[dict] = []
    for f in sorted(fills, key=lambda x: x.ts):
        key = (f.venue, f.account, _norm(f.symbol))
        book = books[key]
        if book and book[0].side != f.side:
            entry = book.popleft()
            trips.append({"venue": f.venue, "account": f.account, "symbol": entry.symbol,
                          "side": entry.side, "entry": entry, "exit": f})
        else:
            book.append(f)
    return trips


def roundtrip_pnl(rt: dict, intended_entry: dict | None) -> dict:
    """Realized P&L + realized R (vs expected R from the entry signal's SL/TP)."""
    entry, exit = rt["entry"], rt["exit"]
    signed = 1.0 if entry.side == "buy" else -1.0
    realized_price = (exit.price - entry.price) * signed
    inst = _instrument(entry.symbol) if entry.venue == "tradovate" else None
    realized_usd = realized_price * inst[1] * entry.qty if inst else None
    realized_r = expected_r = None
    if intended_entry:
        dsl = intended_entry.get("dollar_sl")      # SL distance in price (== 1R risk in price)
        dtp = intended_entry.get("dollar_tp")
        if dsl:                                     # R is venue-agnostic: price move / stop distance
            realized_r = round(realized_price / dsl, 3)
            if dtp:
                expected_r = round(dtp / dsl, 3)
    return {
        "venue": rt["venue"], "account": rt["account"], "symbol": entry.symbol, "side": entry.side,
        "entry_price": entry.price, "exit_price": exit.price, "qty": entry.qty,
        "realized_price": round(realized_price, 6),
        "realized_usd": round(realized_usd, 2) if realized_usd is not None else None,
        "realized_r": realized_r, "expected_r": expected_r,
        "hold_s": round(exit.ts - entry.ts, 1),
        "matched": True, "fill_ts": exit.ts,
    }


def match_fills(intended_list: list[dict], fills: list[Fill], window_s: float = 90.0) -> list[dict]:
    """Match each fill to the closest-in-time intended signal with the same symbol base and
    side, within window_s. Greedy by time proximity; each intended matched once per venue.
    Returns a list of discrepancy dicts (unmatched fills are reported with matched=False)."""
    used: set = set()
    out: list[dict] = []
    for fill in fills:
        fbase = _norm(fill.symbol)
        best_i, best_dt = None, None
        for i, sig in enumerate(intended_list):
            key = (i, fill.venue)
            if key in used:
                continue
            if sig.get("side") != fill.side:
                continue
            if _norm(sig["symbol"]) != fbase:
                continue
            dt = abs(fill.ts - sig.get("ts", fill.ts))
            if dt <= window_s and (best_dt is None or dt < best_dt):
                best_i, best_dt = i, dt
        if best_i is None:
            out.append({"matched": False, "venue": fill.venue, "account": fill.account,
                        "symbol": fill.symbol, "side": fill.side, "fill_price": fill.price,
                        "fill_qty": fill.qty, "fill_ts": fill.ts})
        else:
            used.add((best_i, fill.venue))
            d = compute_discrepancies(intended_list[best_i], fill)
            d["matched"] = True
            out.append(d)
    return out
