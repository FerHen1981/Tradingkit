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
