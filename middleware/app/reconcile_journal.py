"""Reconcile the Notion Trade Journal from the authoritative Tradovate Fills export.

The Fills CSV carries the real per-fill `commission`, so pairing it reproduces each trade's
exact net P&L (validated: account 013 → net $5,470.08, matching Tradovate to the cent). This
rebuilds the journal from that truth, per account, and supersedes the live/duplicate rows:

  for each account present in the Fills dir:
    - pair fills → authoritative trades (real commissions), Source="Tradovate CSV Import",
      Sync Status="Reconciled"
    - upsert them (idempotent on Webhook ID = {acct3}_{buyFill}_{sellFill})
    - ARCHIVE that account's existing rows whose key is NOT in the authoritative set
      (the routed "R…" live rows and any old-import duplicates) — recoverable from Notion trash

Net PnL then rolls up to the exact Current Balance / Recap / health — no account-level
hard-overwrite. Accounts absent from the Fills dir are left untouched.

DRY by default: prints the per-account plan. Set RECONCILE_APPLY=1 to execute.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import os
from collections import defaultdict

from .fills_pairing import parse_fills_csv, pair_fills
from .journal_sync import to_record, IntentIndex
from .notion_journal import NotionTradeJournal, trade_key

log = logging.getLogger("mex.reconcile")

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"
SOURCE_RECON = "Tradovate CSV Import"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Notion-Version": _VER, "Content-Type": "application/json"}


def _title(props) -> str:
    p = props.get("Webhook ID") or {}
    try:
        return "".join(t["plain_text"] for t in p.get("rich_text", []))
    except Exception:
        return ""


async def _existing_rows(client, token, db, prefix):
    """(webhook_id, page_id) for all Trade Journal rows whose Webhook ID starts with prefix."""
    out, cursor = [], None
    while True:
        body = {"filter": {"property": "Webhook ID", "rich_text": {"starts_with": prefix}},
                "page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = await client.post(f"{_API}/databases/{db}/query", headers=_headers(token), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data.get("results", []):
            out.append((_title(page.get("properties", {})), page["id"]))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return out


async def run() -> dict:
    apply = os.environ.get("RECONCILE_APPLY") == "1"
    exports = os.environ.get("EXPORTS_DIR", "/root/exports")
    intent_dir = os.environ.get("INTENT_DIR", "/root/intent-store")
    window_s = float(os.environ.get("INTENT_WINDOW_S", "900"))
    token = os.environ.get("NOTION_TOKEN", "")
    db = os.environ.get("NOTION_JOURNAL_DB", "")
    throttle = float(os.environ.get("NOTION_THROTTLE_S", "0.34"))
    journal = NotionTradeJournal(token, db)
    intents = IntentIndex(intent_dir)

    # pair every fills CSV, grouped by account
    skip = [s.strip() for s in os.environ.get("RECONCILE_SKIP", "").split(",") if s.strip()]
    trades_by_acct = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(exports, "*Fills*.csv"))):   # matches "Fills (11).csv" too
        try:
            for t in pair_fills(parse_fills_csv(path)):
                if any(s in t.account for s in skip):
                    continue
                trades_by_acct[t.account].append(t)
        except Exception as exc:
            log.warning("failed to pair %s: %r", path, exc)

    if not journal.enabled:
        for acct, trades in sorted(trades_by_acct.items()):
            recs = [to_record(t, intents, window_s) for t in trades]
            print(f"DRY {acct}: {len(recs)} authoritative trades "
                  f"(net ${sum(r.gross_pnl - r.commissions for r in recs):,.2f})  — no token, cannot inspect existing")
        return {"accounts": len(trades_by_acct), "dry": True, "reason": "no token"}

    import httpx
    summary = {"accounts": 0, "written": 0, "archived": 0, "apply": apply}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for acct, trades in sorted(trades_by_acct.items()):
            recs = []
            for t in trades:
                rec = to_record(t, intents, window_s)
                rec.source = SOURCE_RECON
                rec.sync_status = "Reconciled"
                recs.append(rec)
            auth_keys = {trade_key(r) for r in recs}
            prefix = f"{acct[-3:]}_"
            existing = await _existing_rows(client, token, db, prefix)
            supersede = [pid for (k, pid) in existing if k not in auth_keys]
            net = sum(r.gross_pnl - r.commissions for r in recs)
            log.info("%s: %d authoritative (net $%.2f) · %d existing · archive %d superseded%s",
                     acct, len(recs), net, len(existing), len(supersede), "" if apply else "  [DRY]")
            summary["accounts"] += 1
            if not apply:
                continue
            for rec in recs:
                if await journal.upsert(rec):
                    summary["written"] += 1
                if throttle:
                    await asyncio.sleep(throttle)
            for pid in supersede:
                try:
                    pr = await client.patch(f"{_API}/pages/{pid}", headers=_headers(token),
                                            json={"archived": True})
                    pr.raise_for_status()
                    summary["archived"] += 1
                except Exception as exc:
                    log.warning("archive failed for %s: %r", pid, exc)
                if throttle:
                    await asyncio.sleep(throttle)
    log.info("reconcile run: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(asyncio.run(run()))
