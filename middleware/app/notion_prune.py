"""Archive Trade Journal rows — safe cleanup (archived pages are restorable from Notion trash).

Two modes (NOTION_TOKEN / NOTION_JOURNAL_DB must be in the environment):

  # archive every row whose Open Date is on/after a date (e.g. wipe a botched backfill)
  .venv/bin/python -m app.notion_prune --after 2026-08-10

  # archive specific rows by Webhook ID
  .venv/bin/python -m app.notion_prune <WebhookID> [<WebhookID> ...]

Archives (not hard-deletes), so mistakes are reversible from Notion's trash.
"""
from __future__ import annotations

import asyncio
import os
import sys

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Notion-Version": _VER, "Content-Type": "application/json"}


async def _archive_page(client, token, page_id) -> None:
    r = await client.patch(f"{_API}/pages/{page_id}", headers=_headers(token), json={"archived": True})
    r.raise_for_status()


async def _by_after(client, token, db, date: str) -> int:
    """Archive all rows with Open Date on/after `date` (paginated)."""
    n = 0
    cursor = None
    while True:
        body = {"filter": {"property": "Open Date", "date": {"on_or_after": date}}, "page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = await client.post(f"{_API}/databases/{db}/query", headers=_headers(token), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data.get("results", []):
            await _archive_page(client, token, page["id"])
            n += 1
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return n


async def _by_ids(client, token, db, ids: list[str]) -> tuple[int, int]:
    archived = missing = 0
    for wid in ids:
        r = await client.post(f"{_API}/databases/{db}/query", headers=_headers(token),
                              json={"filter": {"property": "Webhook ID", "rich_text": {"equals": wid}},
                                    "page_size": 10})
        r.raise_for_status()
        hits = r.json().get("results", [])
        if not hits:
            print(f"not found : {wid}")
            missing += 1
            continue
        for page in hits:
            await _archive_page(client, token, page["id"])
            print(f"archived  : {wid}")
            archived += 1
    return archived, missing


async def main(argv: list[str]) -> None:
    token = os.environ.get("NOTION_TOKEN", "")
    db = os.environ.get("NOTION_JOURNAL_DB", "")
    if not (token and db):
        print("NOTION_TOKEN / NOTION_JOURNAL_DB not set — load your .env first (set -a; . ./.env; set +a)")
        return
    if not argv:
        print(__doc__)
        return
    import httpx
    async with httpx.AsyncClient(timeout=20.0) as client:
        if argv[0] == "--after":
            if len(argv) < 2:
                print("usage: --after YYYY-MM-DD")
                return
            n = await _by_after(client, token, db, argv[1])
            print(f"\ndone: {n} rows archived (Open Date on/after {argv[1]})")
        else:
            archived, missing = await _by_ids(client, token, db, argv)
            print(f"\ndone: {archived} archived, {missing} not found")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
