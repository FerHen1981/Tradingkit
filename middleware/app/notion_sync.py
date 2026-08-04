"""LifeOS / Notion fleet dashboard sync.

Pushes the latest per-account P&L snapshot into a Notion database — one row per account,
upserted in place — so LifeOS shows live fleet performance. Runs after each poll.

Setup (once): create a Notion internal integration (https://www.notion.so/my-integrations),
share your "Fleet Performance" database with it, put the token in NOTION_TOKEN and the
database id in NOTION_DB_ID. Expected DB properties (created for you in LifeOS):
  Account (title) · Realized (number) · Open PnL (number) · Total value (number) ·
  Strategy (rich_text) · Updated (date)

DRY: with no token/db the sync logs what it WOULD push and makes no API call.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger("mex.notion")
_API = "https://api.notion.com/v1"
_VER = "2022-06-28"


class NotionSync:
    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.db_id)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Notion-Version": _VER,
                "Content-Type": "application/json"}

    @staticmethod
    def _props(row: dict) -> dict:
        return {
            "Account": {"title": [{"text": {"content": str(row.get("account", ""))}}]},
            "Realized": {"number": row.get("realized")},
            "Open PnL": {"number": row.get("open_pnl")},
            "Total value": {"number": row.get("total_val")},
        }

    async def _find_page(self, client: httpx.AsyncClient, account: str) -> str | None:
        r = await client.post(f"{_API}/databases/{self.db_id}/query",
                              headers=self._headers(),
                              json={"filter": {"property": "Account", "title": {"equals": account}},
                                    "page_size": 1})
        r.raise_for_status()
        res = r.json().get("results", [])
        return res[0]["id"] if res else None

    async def upsert_fleet(self, rows: list[dict]) -> None:
        if not self.enabled:
            log.info("notion sync DRY: would upsert %d accounts", len(rows))
            return
        async with httpx.AsyncClient(timeout=15.0) as client:
            for row in rows:
                try:
                    props = self._props(row)
                    page_id = await self._find_page(client, str(row.get("account", "")))
                    if page_id:
                        await client.patch(f"{_API}/pages/{page_id}", headers=self._headers(),
                                           json={"properties": props})
                    else:
                        await client.post(f"{_API}/pages", headers=self._headers(),
                                          json={"parent": {"database_id": self.db_id}, "properties": props})
                except Exception as exc:  # one account failing must not stall the rest
                    log.warning("notion upsert failed for %s: %r", row.get("account"), exc)


class NotionJournal:
    """Append one row per trade to a Notion Trade Journal database (a visible log in LifeOS).
    Create-only (each trade is its own row). DRY when unconfigured."""

    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.db_id)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Notion-Version": _VER,
                "Content-Type": "application/json"}

    async def append_trade(self, sig, results: list[dict]) -> None:
        ok = sum(1 for r in results if r.get("status") in ("sent", "dry_run"))
        blocked = sum(1 for r in results if r.get("status") == "blocked")
        failed = sum(1 for r in results if r.get("status") == "error")
        result = f"{ok} sent" + (f", {blocked} blocked" if blocked else "") + (f", {failed} FAILED" if failed else "")
        props = {
            "Trade": {"title": [{"text": {"content": f"{sig.strategy} {sig.action} {sig.symbol}"}}]},
            "Strategy": {"rich_text": [{"text": {"content": sig.strategy}}]},
            "Action": {"select": {"name": sig.action}},
            "Symbol": {"rich_text": [{"text": {"content": sig.symbol}}]},
            "Price": {"number": sig.price},
            "Qty": {"number": sig.qty},
            "SL $": {"number": sig.dollar_sl},
            "TP $": {"number": sig.dollar_tp},
            "Accounts": {"number": ok},
            "Result": {"rich_text": [{"text": {"content": result}}]},
        }
        if not self.enabled:
            log.info("notion journal DRY: %s %s %s -> %s", sig.strategy, sig.action, sig.symbol, result)
            return
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(f"{_API}/pages", headers=self._headers(),
                                  json={"parent": {"database_id": self.db_id}, "properties": props})
        except Exception as exc:
            log.warning("notion journal append failed: %r", exc)


class NotionRecon:
    """Append one row per reconciled (trade × venue) to a Notion Reconciliation DB."""

    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.db_id)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Notion-Version": _VER, "Content-Type": "application/json"}

    @staticmethod
    def _num(v):
        return {"number": v if isinstance(v, (int, float)) else None}

    def _props(self, r: dict) -> dict:
        title = f"{r.get('strategy','?')} {r.get('side','')} {r.get('symbol','')} @ {r.get('venue','')}"
        return {
            "Trade": {"title": [{"text": {"content": title}}]},
            "Venue": {"select": {"name": r.get("venue", "?")}},
            "Account": {"rich_text": [{"text": {"content": str(r.get("account", ""))}}]},
            "Matched": {"checkbox": bool(r.get("matched"))},
            "Intended": self._num(r.get("intended_price")),
            "Fill": self._num(r.get("fill_price")),
            "Slippage ticks": self._num(r.get("slippage_ticks")),
            "Slippage $": self._num(r.get("slippage_usd")),
            "Slippage %": self._num(r.get("slippage_pct")),
            "Latency s": self._num(r.get("latency_s")),
            "Qty diff": self._num(r.get("qty_diff")),
        }

    async def append(self, rows: list[dict]) -> None:
        if not self.enabled:
            log.info("notion recon DRY: would append %d rows", len(rows))
            return
        async with httpx.AsyncClient(timeout=15.0) as client:
            for r in rows:
                try:
                    await client.post(f"{_API}/pages", headers=self._headers(),
                                      json={"parent": {"database_id": self.db_id}, "properties": self._props(r)})
                except Exception as exc:
                    log.warning("notion recon append failed: %r", exc)
