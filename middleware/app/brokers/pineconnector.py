# =============================================================================
# DEAD PATH — do not add features here.
# No FTMO / MT5 accounts are wired in the live executor. This module is not
# imported by anything that runs. See docs/SPRINT.md D-05.
# =============================================================================
"""PineConnector (MT4/5) route — for FTMO / MetaTrader accounts.

PineConnector consumes a comma command as the alert body and its licensed EA on MT4/5
executes it. The middleware rebuilds the exact command the Pine proved out:
    entry:  {license},{buy|sell},{symbol},sl={price},tp={price},risk={risk}
    close:  {license},exit,{symbol}

The signal carries dollar_sl/dollar_tp as PRICE DISTANCES (same as the Pine _slD/_tpD),
so absolute SL/TP prices are reconstructed here from the entry price and direction.
Sending posts the command as text/plain to your PineConnector webhook (PC_URL).
Guarded by DRY_RUN, with the same retry policy as the PMT route.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from ..models import Signal


def build_command(sig: Signal, account: dict) -> str:
    license_id = account.get("license", "")
    symbol = account.get("symbol_override") or sig.symbol
    if sig.action == "close":
        return f"{license_id},exit,{symbol}"
    risk = account.get("risk", 1.0)
    if sig.action == "buy":
        sl_px = sig.price - sig.dollar_sl
        tp_px = sig.price + sig.dollar_tp
    else:  # sell
        sl_px = sig.price + sig.dollar_sl
        tp_px = sig.price - sig.dollar_tp
    return f"{license_id},{sig.action},{symbol},sl={sl_px},tp={tp_px},risk={risk}"


async def send(sig: Signal, account: dict, *, pc_url: str, dry_run: bool,
               retry_max: int = 3, retry_backoff: float = 0.5,
               client: Optional[httpx.AsyncClient] = None) -> dict:
    cmd = build_command(sig, account)
    if dry_run:
        return {"status": "dry_run", "would_post_to": pc_url or "(PC_URL unset)", "command": cmd}
    if not pc_url:
        return {"status": "error", "reason": "PC_URL not configured", "command": cmd}

    own = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    last: dict = {}
    try:
        for attempt in range(1, max(1, retry_max) + 1):
            try:
                resp = await client.post(pc_url, content=cmd, headers={"content-type": "text/plain"})
                if resp.status_code < 400:
                    return {"status": "sent", "http_status": resp.status_code,
                            "response": resp.text[:500], "attempts": attempt, "command": cmd}
                last = {"status": "error", "http_status": resp.status_code,
                        "response": resp.text[:500], "attempts": attempt, "command": cmd}
                if resp.status_code < 500:
                    return last
            except Exception as exc:
                last = {"status": "error", "reason": repr(exc), "attempts": attempt, "command": cmd}
            if attempt < retry_max:
                await asyncio.sleep(retry_backoff * (2 ** (attempt - 1)))
        return last
    finally:
        if own:
            await client.aclose()
