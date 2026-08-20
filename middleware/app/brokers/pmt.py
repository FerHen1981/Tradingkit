# =============================================================================
# DEAD PATH — do not add features here.
# The live PMT → Tradovate call is made by the .NET receiver
# (`Mex.Journal.Receiver`). This module is only imported by router.py, which
# never runs in production. See docs/SPRINT.md D-05.
# =============================================================================
"""PickMyTrade (PMT) → Tradovate route.

Builds the exact PMT JSON payload the Pine strategy proved out (dollar SL/TP, the
`multiple_accounts` block), but with the account's own token / id / size injected by
the middleware instead of baked into each TradingView alert.

Sending is guarded by DRY_RUN: with DRY_RUN=true (the default) we build and journal
the payload but do NOT POST it, so you can wire everything end-to-end without risking
a live order. Flip DRY_RUN=false when you're ready.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Optional

import httpx

from ..models import Signal


def build_payload(sig: Signal, account: dict) -> dict:
    """One PMT order for one account. `account` = an entry from accounts.yaml."""
    token = account.get("token", "")
    account_id = account.get("account_id", "")
    mult = account.get("quantity_multiplier", 1)
    symbol = account.get("symbol_override") or sig.symbol
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "symbol": symbol,
        "date": now,
        "data": sig.action,                 # buy | sell | close
        "quantity": str(sig.qty),           # PMT expects quantity/price as strings (matches f_pmtJSON)
        "risk_percentage": 0,
        "price": str(sig.price),
        "tp": 0,
        "percentage_tp": 0,
        "dollar_tp": sig.dollar_tp,
        "sl": 0,
        "dollar_sl": sig.dollar_sl,
        "percentage_sl": 0,
        # trailing / break-even — mirror the Pine f_pmtJSON so PMT trails the Tradovate stop
        # server-side exactly as it did before the fan-out moved through the middleware.
        "trail": sig.trail,
        "trail_stop": sig.trail_stop,
        "trail_trigger": sig.trail_trigger,
        "trail_freq": sig.trail_freq,
        "breakeven": sig.breakeven,
        "update_tp": False,
        "update_sl": False,
        "token": token,
        "pyramid": False,
        "reverse_order_close": True,
        "order_type": sig.order_type,
        "multiple_accounts": [
            {"token": token, "account_id": account_id, "risk_percentage": 0, "quantity_multiplier": mult}
        ],
    }


async def send(sig: Signal, account: dict, *, pmt_url: str, dry_run: bool,
               retry_max: int = 3, retry_backoff: float = 0.5,
               client: Optional[httpx.AsyncClient] = None) -> dict:
    """POST the PMT order, retrying on network errors and 5xx (not 4xx — a client error
    won't fix by retrying). Returns a result dict for the journal; never raises."""
    payload = build_payload(sig, account)
    if dry_run:
        return {"status": "dry_run", "would_post_to": pmt_url or "(PMT_URL unset)", "payload": payload}
    if not pmt_url:
        return {"status": "error", "reason": "PMT_URL not configured", "payload": payload}

    own = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    last = {}
    try:
        for attempt in range(1, max(1, retry_max) + 1):
            try:
                resp = await client.post(pmt_url, json=payload)
                if resp.status_code < 400:
                    return {"status": "sent", "http_status": resp.status_code,
                            "response": resp.text[:500], "attempts": attempt, "payload": payload}
                last = {"status": "error", "http_status": resp.status_code,
                        "response": resp.text[:500], "attempts": attempt, "payload": payload}
                if resp.status_code < 500:
                    return last  # 4xx: don't retry
            except Exception as exc:  # network / timeout
                last = {"status": "error", "reason": repr(exc), "attempts": attempt, "payload": payload}
            if attempt < retry_max:
                await asyncio.sleep(retry_backoff * (2 ** (attempt - 1)))
        return last
    finally:
        if own:
            await client.aclose()
