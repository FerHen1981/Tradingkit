"""Failure alerts: ping a Discord/Telegram webhook when a dispatch fails, so a broken
order does not sit silently in the journal. Best-effort — never raises into the request.
"""
from __future__ import annotations

import httpx


async def alert_failure(webhook: str, text: str, client: httpx.AsyncClient | None = None) -> None:
    if not webhook:
        return
    own = client is None
    client = client or httpx.AsyncClient(timeout=8.0)
    try:
        # Discord expects {"content": ...}; Telegram sendMessage expects {"text": ...}.
        # Sending both keys is harmless — each service reads the one it knows.
        await client.post(webhook, json={"content": text, "text": text})
    except Exception:
        pass  # alerting must never break the request path
    finally:
        if own:
            await client.aclose()
