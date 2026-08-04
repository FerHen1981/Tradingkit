"""Failure alerts: ping a Discord/Telegram webhook when a dispatch fails, so a broken
order does not sit silently in the journal. Best-effort — never raises into the request.
"""
from __future__ import annotations

import httpx


async def _post(webhook: str, text: str, client: httpx.AsyncClient | None = None) -> None:
    if not webhook:
        return
    own = client is None
    client = client or httpx.AsyncClient(timeout=8.0)
    try:
        # Discord expects {"content": ...}; Telegram sendMessage expects {"text": ...}.
        # Sending both keys is harmless — each service reads the one it knows.
        await client.post(webhook, json={"content": text, "text": text})
    except Exception:
        pass  # notifications must never break the request path
    finally:
        if own:
            await client.aclose()


async def alert_failure(webhook: str, text: str, client: httpx.AsyncClient | None = None) -> None:
    await _post(webhook, text, client)


def format_trade(sig, results: list[dict]) -> str:
    """Human-readable one-liner for the live Discord notify channel."""
    ok = [r for r in results if r.get("status") in ("sent", "dry_run")]
    blocked = [r for r in results if r.get("status") == "blocked"]
    failed = [r for r in results if r.get("status") == "error"]
    arrow = "🟢" if sig.action in ("buy", "sell") else "⚪"
    head = f"{arrow} **{sig.strategy} {sig.action.upper()}** {sig.symbol} @ {sig.price} · {sig.qty}ct · SL {sig.dollar_sl}/TP {sig.dollar_tp}"
    tail = f"→ {len(ok)} account(s)"
    if blocked:
        tail += f", {len(blocked)} blocked"
    if failed:
        tail += f", ⚠️ {len(failed)} failed"
    return f"{head}  {tail}"


async def notify_trade(webhook: str, sig, results: list[dict], client: httpx.AsyncClient | None = None) -> None:
    """Live per-trade notification (distinct from failure alerts)."""
    if not webhook:
        return
    await _post(webhook, format_trade(sig, results), client)
