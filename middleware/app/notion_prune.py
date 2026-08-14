"""Archive Trade Journal rows by Webhook ID (safe cleanup — archived pages are restorable).

Usage (with NOTION_TOKEN / NOTION_JOURNAL_DB in the environment):
  .venv/bin/python -m app.notion_prune <WebhookID> [<WebhookID> ...]

Archives (not hard-deletes) each matching page, so a mistake is reversible from Notion's
trash. Prints one line per id.
"""
from __future__ import annotations

import asyncio
import os
import sys

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"


async def main(ids: list[str]) -> None:
    token = os.environ.get("NOTION_TOKEN", "")
    db = os.environ.get("NOTION_JOURNAL_DB", "")
    if not (token and db):
        print("NOTION_TOKEN / NOTION_JOURNAL_DB not set — load your .env first (set -a; . ./.env; set +a)")
        return
    import httpx
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": _VER, "Content-Type": "application/json"}
    archived = missing = 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        for wid in ids:
            r = await client.post(f"{_API}/databases/{db}/query", headers=headers,
                                  json={"filter": {"property": "Webhook ID", "rich_text": {"equals": wid}},
                                        "page_size": 10})
            r.raise_for_status()
            hits = r.json().get("results", [])
            if not hits:
                print(f"not found : {wid}")
                missing += 1
                continue
            for page in hits:
                pr = await client.patch(f"{_API}/pages/{page['id']}", headers=headers,
                                        json={"archived": True})
                pr.raise_for_status()
                print(f"archived  : {wid}")
                archived += 1
    print(f"\ndone: {archived} archived, {missing} not found")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
