"""Live Trade Journal from the executor's own routed-event log (no browser, no CSV).

The executor already writes `/root/intent-store/routed_YYYYMMDD.jsonl`, and that log carries
the whole per-account trade lifecycle in its Discord cards:

  📥 FILL LONG    "PA015-0k-260813 | 5ct @ 4403.1 | SL 4413.1 | TP 4378.1"   → entry (real fill)
  📤 EXIT 🟢      "PA015-… | short closed @ 4397.7 | TRAIL | PnL +$263.3 | MFE 79t · MAE 3t" → exit
  📈 LONG LIMIT   "Entry 4449.8 | Stop 4439.8 | TP 4474.8 | Qty 8 | Contraction"  → intended entry

and the `pmt` records carry the full account id (so the short codes PA015/AP209 in the cards
resolve to PAAPEX2700250000015 / APEX27002500000209). We pair each FILL with its EXIT per
(account, symbol, direction) and upsert one row per trade into the Notion Trade Journal — the
row appears when the trade OPENS and is completed when it CLOSES, with the real fill/exit
prices, realized P&L, MFE/MAE, and entry slippage vs the intended (LIMIT) price.

This is the LIVE layer: it runs on a ~1-minute timer, needs nothing but the server's own log,
and can't break from a Tradovate UI change. The daily Fills-CSV pass (app.journal_sync) stays
available only as an optional cross-check / commission backfill.

EXECUTION GATE (besluit Ferry 24-08). A card is only a trade if the ORDER demonstrably left
the system and PickMyTrade accepted the request: there must be a `pmt` record for the same
account + symbol + direction, shortly before the fill, whose `result` reads `sent 200`.

Read that label honestly. `sent 200` is the HTTP status of OUR POST to PMT, not PMT's verdict
on the order -- PMT's response body is not stored today. So this journal holds ACCEPTED ORDERS,
not confirmed broker fills. An order PMT accepts and Tradovate then rejects, or a limit that
never fills, still lands here. Upgrading to PMT's own verdict needs the executor to store the
response body; until then do not call these rows "filled".

The gate sits on the ENTRY only. Normal TP/SL exits never produce a PMT close -- PickMyTrade
holds the bracket server-side -- so requiring a close record would reject nearly every
completed trade. An exit can only ever complete a trade whose entry already passed.

DRY when NOTION_TOKEN / NOTION_JOURNAL_DB are unset (logs what it would write).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import glob
import json
import logging
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from .notion_journal import TradeRecord, NotionTradeJournal
from .journal_sync import FRAMEWORK, _ASSET, _phase, _sym_root

log = logging.getLogger("mex.routed_journal")

# ---- card parsing --------------------------------------------------------------------

_QTY = re.compile(r"(\d+)\s*ct")
_FILL_PX = re.compile(r"@\s*([\d.]+)")
_SL = re.compile(r"\bSL\s*([\d.]+)")
_TP = re.compile(r"\bTP\s*([\d.]+)")
_EXIT_DIR_PX = re.compile(r"\b(long|short)\s+closed\s*@\s*([\d.]+)", re.I)
_EXIT_REASON = re.compile(r"closed\s*@\s*[\d.]+\s*\|\s*([^|]+?)\s*\|", re.I)
_PNL = re.compile(r"PnL\s*([+-])\$([\d.,]+)")
_MFE = re.compile(r"MFE\s*(\d+)\s*t")
_MAE = re.compile(r"MAE\s*(\d+)\s*t")
_ENTRY = re.compile(r"\bEntry\s*([\d.]+)")
_SYM = re.compile(r"([A-Z]{1,4}\d*!)")


def _short(account_id: str) -> str:
    """Full id -> the card's short code: first two letters + last three digits.
    'PAAPEX2700250000015' -> 'PA015'; 'APEX27002500000209' -> 'AP209'."""
    a = (account_id or "").strip()
    return (a[:2] + a[-3:]).upper() if len(a) >= 5 else a.upper()


# The executor writes e.g. "sent 200 (poging 1)". Whitelist, never blacklist: anything we do
# not recognise counts as NOT accepted, so a new failure string can never silently promote a
# signal to an execution.
_PMT_ACCEPTED = re.compile(r"^\s*sent\s+200\b", re.I)

# How long an accepted order may precede its fill. A limit order rests for expiryBars (12 on a
# 1m chart), so this must be minutes, not seconds -- 2026-08-24 shows 12m08s between the PMT
# buy and the FILL card.
PMT_MATCH_WINDOW_S = int(os.environ.get("PMT_MATCH_WINDOW_S", "900"))
# The fill can be logged a hair before the order record; do not reject on clock jitter.
_CLOCK_SKEW_S = 5.0

_DIR_FOR_ACTION = {"buy": "BUY", "sell": "SELL"}


@dataclass
class PmtOrder:
    """One outgoing order to PickMyTrade, as the executor logged it."""
    ts: dt.datetime
    account_short: str
    account_full: str
    symbol: str
    action: str                 # 'buy' | 'sell' | 'close'
    qty: int = 0
    accepted: bool = False
    used: bool = False


def _acct_token(desc: str) -> str:
    """'PA015-0k-260813 | …' -> 'PA015'."""
    return desc.strip().split("-", 1)[0].strip().upper()


def _f(m) -> float | None:
    return float(m.group(1)) if m else None


@dataclass
class RoutedEvent:
    ts: dt.datetime
    typ: str                 # 'fill' | 'exit' | 'limit'
    symbol: str              # 'MGC1!'
    direction: str           # 'BUY' | 'SELL'
    account_short: str = ""
    price: float | None = None
    qty: int = 0
    sl: float | None = None
    tp: float | None = None
    pnl: float | None = None
    mfe: int | None = None
    mae: int | None = None
    reason: str = ""


def _event_from_embed(ts: dt.datetime, embed: dict) -> RoutedEvent | None:
    title = (embed.get("title") or "").strip()
    desc = (embed.get("description") or "").strip()
    sym_m = _SYM.search(title)
    symbol = sym_m.group(1) if sym_m else ""

    if "FILL LONG" in title or "FILL SHORT" in title:
        direction = "BUY" if "FILL LONG" in title else "SELL"
        qty_m = _QTY.search(desc)
        return RoutedEvent(ts, "fill", symbol, direction,
                           account_short=_acct_token(desc),
                           price=_f(_FILL_PX.search(desc)),
                           qty=int(qty_m.group(1)) if qty_m else 0,
                           sl=_f(_SL.search(desc)), tp=_f(_TP.search(desc)))

    if "EXIT" in title:
        dm = _EXIT_DIR_PX.search(desc)
        if not dm:
            return None
        direction = "BUY" if dm.group(1).lower() == "long" else "SELL"
        pnl = None
        pm = _PNL.search(desc)
        if pm:
            pnl = float(pm.group(2).replace(",", "")) * (1 if pm.group(1) == "+" else -1)
        rm = _EXIT_REASON.search(desc)
        mfe_m, mae_m = _MFE.search(desc), _MAE.search(desc)
        return RoutedEvent(ts, "exit", symbol, direction,
                           account_short=_acct_token(desc),
                           price=float(dm.group(2)), pnl=pnl,
                           reason=(rm.group(1).strip() if rm else ""),
                           mfe=int(mfe_m.group(1)) if mfe_m else None,
                           mae=int(mae_m.group(1)) if mae_m else None)

    if "LONG LIMIT" in title or "SHORT LIMIT" in title:
        direction = "BUY" if "LONG LIMIT" in title else "SELL"
        return RoutedEvent(ts, "limit", symbol, direction, price=_f(_ENTRY.search(desc)))

    return None


def _parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_routed_lines(lines) -> tuple[list[RoutedEvent], dict[str, str]]:
    """Return (events, short->full account map). Kept for callers that only need the map."""
    events, amap, _ = parse_routed_lines_full(lines)
    return events, amap


def parse_routed_lines_full(lines) -> tuple[list[RoutedEvent], dict[str, str], list[PmtOrder]]:
    """Return (events, short->full account map, outgoing PMT orders).

    The map resolves short codes and is built from every pmt record, accepted or not -- it is
    a lookup table, not the gate. The gate is the order list, which carries the acceptance."""
    events: list[RoutedEvent] = []
    amap: dict[str, str] = {}
    orders: list[PmtOrder] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        kind = o.get("kind")
        if kind == "pmt":
            aid = (o.get("account") or "").strip()
            if aid:
                amap[_short(aid)] = aid
            try:
                pb = json.loads(o.get("body") or "{}")
            except ValueError:
                pb = {}
            if aid and pb.get("symbol") and o.get("ts"):
                try:
                    _q = int(float(pb.get("quantity") or 0))
                except (TypeError, ValueError):
                    _q = 0
                orders.append(PmtOrder(
                    ts=_parse_ts(o["ts"]), account_short=_short(aid), account_full=aid,
                    symbol=str(pb.get("symbol")), action=str(pb.get("data") or "").lower(),
                    qty=_q, accepted=bool(_PMT_ACCEPTED.match(str(o.get("result") or "")))))
            try:
                b = json.loads(o.get("body") or "{}")
                for a in b.get("multiple_accounts", []) or []:
                    fid = (a.get("account_id") or "").strip()
                    if fid:
                        amap[_short(fid)] = fid
            except ValueError:
                pass
        elif kind == "discord":
            try:
                b = json.loads(o.get("body") or "{}")
            except ValueError:
                continue
            ts = _parse_ts(o["ts"])
            for embed in b.get("embeds", []) or []:
                ev = _event_from_embed(ts, embed)
                if ev and ev.symbol:
                    events.append(ev)
    return events, amap, orders


# ---- pairing -------------------------------------------------------------------------

@dataclass
class RoutedTrade:
    account: str
    symbol: str
    direction: str                 # 'BUY' | 'SELL'
    entry_ts: dt.datetime | None = None
    entry_price: float | None = None
    qty: int = 0
    sl: float | None = None
    tp: float | None = None
    signal_price: float | None = None
    exit_ts: dt.datetime | None = None
    exit_price: float | None = None
    pnl: float | None = None
    mfe: int | None = None
    mae: int | None = None
    reason: str = ""

    @property
    def closed(self) -> bool:
        return self.exit_ts is not None


def _accepted_entry(orders: list[PmtOrder], ev: RoutedEvent,
                    window_s: int) -> PmtOrder | None:
    """The accepted PMT entry order this fill belongs to, or None.

    Match on account + symbol + direction, with the order at or shortly before the fill. The
    most recent candidate wins: on a symbol that is re-entered, the newest resting order is the
    one that just filled. A matched order is consumed so two fills can never claim one order."""
    best: PmtOrder | None = None
    for p in orders:
        if p.used or not p.accepted:
            continue
        if p.account_short != ev.account_short or p.symbol != ev.symbol:
            continue
        if _DIR_FOR_ACTION.get(p.action) != ev.direction:
            continue
        delta = (ev.ts - p.ts).total_seconds()
        if delta < -_CLOCK_SKEW_S or delta > window_s:
            continue
        if best is None or p.ts > best.ts:
            best = p
    return best


def pair_events(events: list[RoutedEvent], amap: dict[str, str],
                orders: list[PmtOrder] | None = None,
                window_s: int | None = None) -> list[RoutedTrade]:
    """FIFO-pair FILL(entry) with EXIT per (account, symbol, direction)."""
    return pair_events_with_report(events, amap, orders, window_s)[0]


def pair_events_with_report(events: list[RoutedEvent], amap: dict[str, str],
                            orders: list[PmtOrder] | None = None,
                            window_s: int | None = None
                            ) -> tuple[list[RoutedTrade], list[RoutedEvent]]:
    """Return (trades, unconfirmed fills).

    A fill becomes a trade only when `_accepted_entry` finds the order that produced it, so the
    account id comes from the very record that authorises the row. Fills carry the intended
    price from the most recent LIMIT card of the same symbol+direction.

    The second list is the whole point of the gate: what it rejects must stay visible. A fill
    without an accepted order means the strategy acted and the order did not reach the broker --
    on 2026-08-24 that was PATRON's entry, whose PMT message never left TradingView. Dropping
    those silently turns a broken execution path into a quiet day.
    """
    orders = orders if orders is not None else []
    window_s = PMT_MATCH_WINDOW_S if window_s is None else window_s
    events = sorted(events, key=lambda e: e.ts)
    last_limit: dict[tuple[str, str], float] = {}
    open_q: dict[tuple[str, str, str], deque] = defaultdict(deque)
    trades: list[RoutedTrade] = []
    unconfirmed: list[RoutedEvent] = []
    for e in events:
        if e.typ == "limit":
            if e.price is not None:
                last_limit[(e.symbol, e.direction)] = e.price
            continue
        if e.typ == "fill":
            order = _accepted_entry(orders, e, window_s)
            if order is None:
                unconfirmed.append(e)
                continue
            order.used = True
            t = RoutedTrade(account=order.account_full, symbol=e.symbol, direction=e.direction,
                            entry_ts=e.ts, entry_price=e.price, qty=e.qty, sl=e.sl, tp=e.tp,
                            signal_price=last_limit.get((e.symbol, e.direction)))
            open_q[(order.account_full, e.symbol, e.direction)].append(t)
            trades.append(t)
        elif e.typ == "exit":
            # No gate on exits: a normal TP/SL exit never produces a PMT close, because
            # PickMyTrade holds the bracket server-side. An exit can only ever complete a trade
            # whose entry already passed, so `open_q` is the gate here.
            full = amap.get(e.account_short)
            if not full:
                continue
            q = open_q.get((full, e.symbol, e.direction))
            if q:
                t = q.popleft()
                t.exit_ts, t.exit_price, t.pnl = e.ts, e.price, e.pnl
                t.mfe, t.mae, t.reason = e.mfe, e.mae, e.reason
            # else: an exit whose entry predates our window (e.g. opened the day before, before
            # the routed log for that day) — skip it. Its full trade comes from the Fills-CSV
            # reconciliation instead, so we don't write an incomplete entry-less row here.
    return trades, unconfirmed


# ---- mapping to the Notion Trade Journal ---------------------------------------------

def to_record(t: RoutedTrade) -> TradeRecord:
    phase = _phase(t.account)
    product = _sym_root(t.symbol)
    framework = FRAMEWORK.get((_ASSET.get(product, ""), phase), "")
    entry_ts = t.entry_ts or t.exit_ts
    exit_ts = t.exit_ts or t.entry_ts
    entry_price = t.entry_price if t.entry_price is not None else (t.exit_price or 0.0)
    exit_price = t.exit_price if t.exit_price is not None else entry_price
    # stable, entry-based idempotency key (unchanged when the trade later closes)
    stamp = (entry_ts or dt.datetime.now(dt.timezone.utc)).strftime("%y%m%d%H%M%S")
    buy_fill_id = f"R{stamp}{product}{'L' if t.direction == 'BUY' else 'S'}"
    status = "Open" if not t.closed else ("Closed (SL)" if t.reason.upper() == "SL" else "Closed")
    rec = TradeRecord(
        account_id=t.account, buy_fill_id=buy_fill_id, sell_fill_id="",
        direction=t.direction, contract=t.symbol, symbol=t.symbol,
        position_size=t.qty, entry_price=entry_price, exit_price=exit_price,
        gross_pnl=t.pnl if t.pnl is not None else 0.0, commissions=0.0,
        open_dt=entry_ts, close_dt=exit_ts,
        framework=framework,
        account_types=f"Apex 50k {'PA' if phase == 'funded' else 'Eval'} (Intraday)",
        status=status,
        signal_price=t.signal_price,
        planned_sl=t.sl, planned_tp=t.tp,
        exit_reason=t.reason or None, mfe_ticks=t.mfe, mae_ticks=t.mae,
    )
    return rec


# ---- runner --------------------------------------------------------------------------

def _recent_routed_files(routed_dir: str, days: int) -> list[str]:
    files = sorted(glob.glob(os.path.join(routed_dir, "routed_*.jsonl")))
    return files[-days:] if days > 0 else files


def _signature(rec: TradeRecord) -> str:
    return f"{rec.status}:{rec.exit_price}:{rec.gross_pnl}"


async def run_once() -> dict:
    routed_dir = os.environ.get("ROUTED_DIR", os.environ.get("INTENT_DIR", "/root/intent-store"))
    days = int(os.environ.get("ROUTED_DAYS", "2"))
    state_file = os.environ.get("ROUTED_STATE_FILE", "routed_journal_state.json")
    journal = NotionTradeJournal(os.environ.get("NOTION_TOKEN", ""),
                                 os.environ.get("NOTION_JOURNAL_DB", ""))
    if journal.enabled:
        try:
            import httpx  # noqa: F401
        except ModuleNotFoundError:
            log.error("httpx not installed in THIS interpreter — run via the venv "
                      "(.venv/bin/python -m app.routed_journal).")
            return {"error": "httpx missing (use the venv python)"}

    lines: list[str] = []
    files = _recent_routed_files(routed_dir, days)
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                lines.extend(f)
        except OSError as exc:
            log.warning("could not read %s: %r", path, exc)

    events, amap, orders = parse_routed_lines_full(lines)
    trades, unconfirmed = pair_events_with_report(events, amap, orders)

    # What the gate rejected must never be silent: a fill without an accepted PMT order means
    # the strategy acted and the order did not reach the broker. Log one line per case, loudly.
    for ev in unconfirmed:
        log.warning("GEEN EXECUTIE: %s %s %s %sct @ %s — geen geaccepteerde PMT-order binnen %ss",
                    ev.ts.isoformat(), ev.account_short, ev.direction, ev.qty, ev.price,
                    PMT_MATCH_WINDOW_S)

    # incremental: skip rows already written in the same state (open->closed re-writes once)
    done: dict[str, str] = {}
    try:
        with open(state_file) as f:
            done = json.load(f)
    except (FileNotFoundError, ValueError):
        pass

    from .notion_journal import trade_key
    throttle = float(os.environ.get("NOTION_THROTTLE_S", "0.34"))
    new = updated = skipped = failed = 0
    for t in trades:
        rec = to_record(t)
        key = trade_key(rec)
        sig = _signature(rec)
        if done.get(key) == sig:
            skipped += 1
            continue
        was_known = key in done
        ok = await journal.upsert(rec)
        if journal.enabled:
            if ok:
                updated += 1 if was_known else 0
                new += 0 if was_known else 1
                done[key] = sig      # only remember rows that were genuinely written
            else:
                failed += 1
            if throttle:
                await asyncio.sleep(throttle)   # stay under Notion's rate limit on a backfill

    if journal.enabled:
        try:
            with open(state_file, "w") as f:
                json.dump(done, f)
        except OSError as exc:
            log.warning("could not write state %s: %r", state_file, exc)

    summary = {"files": len(files), "events": len(events), "accounts": len(amap),
               "orders": len(orders), "orders_accepted": sum(1 for o in orders if o.accepted),
               "trades": len(trades), "unconfirmed": len(unconfirmed),
               "new": new, "updated": updated, "skipped": skipped,
               "failed": failed, "dry": not journal.enabled}
    log.info("routed_journal run: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(asyncio.run(run_once()))
