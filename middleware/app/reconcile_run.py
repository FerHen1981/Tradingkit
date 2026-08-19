"""Runner: reconcile INTENDED vs ACTUAL on the sources that actually exist (D-03).

The reconciliation engine (`reconcile.py` + `reconciler.py`) was complete but never wrote a
row, because both of its inputs hang off parts of the stack that do not run:

  intended  <- journal.signals_since()  -> the sqlite `events` table, only ever filled by
                                           main.py:/webhook, and main.py is not the live path
  actual    <- tv.fills()               -> the Tradovate read-API, which these prop sub-accounts
                                           do not have (and TRADOVATE_NAME is unset)

and nothing triggered it either — there is no reconcile timer, only `POST /reconcile` on that
same dead app. Hence: complete schema, zero rows.

Both inputs DO exist elsewhere, so this runner re-points the same pure functions at them:

  intended  <- /root/intent-store/routed_*.jsonl   the .NET receiver logs every PMT payload it
                                                   forwards (symbol, side, qty, price, account)
  actual    <- /root/exports/*Fills*.csv           the broker's own fills, already proven to
                                                   reconcile to the cent (fills_pairing)

Nothing is re-implemented: matching, slippage and round-trip P&L stay in `reconcile.py`, the
Notion writer stays `notion_sync.NotionRecon`. This module only adapts the two sources and
provides the entry point a timer can call.

DRY by default — prints what it would write. Set RECONCILE_APPLY=1 to write to Notion.

  EXPORTS_DIR   (default /root/exports)        Fills CSVs (actual)
  ROUTED_DIR    (default /root/intent-store)   routed_*.jsonl (intended)
  RECON_DAYS    (default 3)                    how far back to reconcile
"""
from __future__ import annotations

import glob
import json
import logging
import os
import time

from .fills_pairing import parse_fills_csv
from .reconcile import Fill, match_fills, pair_roundtrips, roundtrip_pnl

log = logging.getLogger("mex.reconcile_run")

# PMT action -> the side reconcile.py matches on. "close" is an exit, not an intended entry.
_SIDES = {"buy": "buy", "sell": "sell"}


def intents_from_routed(routed_dir: str, since_ts: float, days: int = 3) -> list[dict]:
    """Intended trades from the receiver's routed-log: one per forwarded PMT entry payload.

    Each line is {kind, account, body, result, ts}; `body` is the PMT JSON the strategy built.
    Only entries (buy/sell) are intents — a `close` is the exit of an earlier one.
    """
    out: list[dict] = []
    for path in sorted(glob.glob(os.path.join(routed_dir, "routed_*.jsonl")))[-max(1, days):]:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in lines:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("kind") != "pmt":
                continue
            try:
                body = json.loads(o.get("body") or "{}")
            except ValueError:
                continue
            side = _SIDES.get(str(body.get("data", "")).lower())
            if not side:
                continue
            ts = _ts_of(o)
            if ts < since_ts:
                continue
            accts = [a.get("account_id") for a in (body.get("multiple_accounts") or []) if a.get("account_id")]
            out.append({
                "strategy": body.get("strategy_name") or "",
                "symbol": body.get("symbol") or "",
                "side": side,
                "price": _f(body.get("price")),
                "qty": _f(body.get("quantity")),
                "ts": ts,
                "account": (o.get("account") or (accts[0] if accts else "")).strip(),
                "dollar_sl": _f(body.get("dollar_sl")),
                "dollar_tp": _f(body.get("dollar_tp")),
                "forward_result": o.get("result") or "",
            })
    out.sort(key=lambda x: x["ts"])
    return out


def fills_from_exports(exports_dir: str, since_ts: float, skip: list[str] | None = None) -> list[Fill]:
    """Actual fills from the broker's own export, deduped on fill id across snapshots."""
    skip = skip or []
    by_id: dict[str, Fill] = {}
    for path in sorted(glob.glob(os.path.join(exports_dir, "*Fills*.csv"))):
        try:
            rows = parse_fills_csv(path)
        except Exception as exc:
            log.warning("fills parse failed %s: %r", path, exc)
            continue
        for f in rows:
            if any(s in f.account for s in skip):
                continue
            ts = f.ts.timestamp()
            if ts < since_ts:
                continue
            by_id[f.fill_id] = Fill(
                venue="tradovate", account=f.account, symbol=f.product or f.contract,
                side="buy" if f.is_buy else "sell", price=f.price, qty=float(f.qty),
                ts=ts, order_ref=f.order_id,
            )
    return sorted(by_id.values(), key=lambda x: x.ts)


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _ts_of(o: dict) -> float:
    """Epoch seconds for a routed-log line (accepts ts/epoch or an ISO timestamp)."""
    for key in ("ts", "epoch", "time", "timestamp"):
        v = o.get(key)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str) and v:
            import datetime as dt
            try:
                return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
    return 0.0


async def run_once() -> dict:
    exports = os.environ.get("EXPORTS_DIR", "/root/exports")
    routed = os.environ.get("ROUTED_DIR", os.environ.get("INTENT_DIR", "/root/intent-store"))
    days = int(os.environ.get("RECON_DAYS", "3"))
    skip = [s.strip() for s in os.environ.get("DASH_SKIP", "").split(",") if s.strip()]
    apply = os.environ.get("RECONCILE_APPLY", "").strip().lower() in ("1", "true", "yes")
    since = time.time() - days * 86400

    intended = intents_from_routed(routed, since, days)
    fills = fills_from_exports(exports, since, skip)

    slip_rows = match_fills(intended, fills)
    pnl_rows = [roundtrip_pnl(rt, _closest(rt["entry"], intended)) for rt in pair_roundtrips(fills)]
    rows = slip_rows + pnl_rows
    matched = [r for r in slip_rows if r.get("matched")]

    summary = {
        "intended": len(intended), "fills": len(fills), "rows": len(rows),
        "matched": len(matched), "unmatched": len(slip_rows) - len(matched),
        "roundtrips": len(pnl_rows), "applied": False,
    }
    if not rows:
        log.info("reconcile: nothing to do %s", summary)
        return summary

    if not apply:
        log.info("reconcile DRY (set RECONCILE_APPLY=1 to write): %s", summary)
        return summary

    from .config import Settings
    from .notion_sync import NotionRecon
    s = Settings()
    recon = NotionRecon(s.notion_token, s.notion_recon_db)
    if not recon.enabled:
        log.error("NOTION_TOKEN / NOTION_RECON_DB unset — cannot write the reconciliation rows")
        return {**summary, "error": "notion not configured"}
    await recon.append(rows)
    summary["applied"] = True
    log.info("reconcile applied: %s", summary)
    return summary


def _closest(fill: Fill, intended: list[dict], window_s: float = 900.0) -> dict | None:
    """The intent that best matches an entry fill. Wider than the slippage window on purpose:
    a limit order can rest for minutes before it fills, and this is only used to read back the
    SL/TP distances for the expected-R comparison."""
    from .reconcile import find_intended
    return find_intended(fill, intended, window_s=window_s)


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(asyncio.run(run_once()), indent=2, default=str))
