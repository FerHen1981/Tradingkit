"""Fan-out: one strategy signal -> every subscribed account, via that account's broker.

Phase 1 wires the PMT (Tradovate) route. Adding PineConnector later is a new branch
here plus a brokers/pineconnector.py — the router stays the switchboard.
"""
from __future__ import annotations

import httpx

from .brokers import pmt
from .config import AccountMap, Settings
from .models import Signal


async def dispatch(sig: Signal, accounts: AccountMap, settings: Settings) -> list[dict]:
    targets = accounts.accounts_for(sig.strategy)
    if not targets:
        return [{"status": "no_accounts", "strategy": sig.strategy}]

    results: list[dict] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for acct in targets:
            broker = acct.get("broker", "")
            if broker == "pmt_tradovate":
                res = await pmt.send(sig, acct, pmt_url=settings.pmt_url,
                                     dry_run=settings.dry_run, retry_max=settings.retry_max,
                                     retry_backoff=settings.retry_backoff, client=client)
            else:
                res = {"status": "error", "reason": f"unknown broker '{broker}'"}
            res["account"] = acct["id"]
            results.append(res)
    return results
