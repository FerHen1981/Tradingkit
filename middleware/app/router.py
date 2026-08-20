# =============================================================================
# DEAD PATH — do not add features here.
# The live fan-out runs in the .NET receiver (`Mex.Journal.Receiver`) on the VPS;
# this router is not wired to any HTTP entry point that runs in production.
# See docs/SPRINT.md D-05 — removal scheduled after D-02.
# =============================================================================
"""Fan-out: one strategy signal -> every subscribed account, via that account's broker.

Phase 1 wires the PMT (Tradovate) route. Adding PineConnector later is a new branch
here plus a brokers/pineconnector.py — the router stays the switchboard.
"""
from __future__ import annotations

import httpx

from .brokers import pineconnector, pmt
from .config import AccountMap, Settings
from .models import Signal
from .risk import RiskState


async def dispatch(sig: Signal, accounts: AccountMap, settings: Settings,
                   risk: RiskState | None = None) -> list[dict]:
    targets = accounts.accounts_for(sig.strategy)
    if not targets:
        return [{"status": "no_accounts", "strategy": sig.strategy}]

    is_entry = sig.event == "ENTRY" and sig.action in ("buy", "sell")
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for acct in targets:
            aid = acct["id"]
            if risk is not None:
                ok, why = risk.allow(aid, acct, is_entry)
                if not ok:
                    results.append({"status": "blocked", "reason": why, "account": aid})
                    continue
            broker = acct.get("broker", "")
            if broker == "pmt_tradovate":
                res = await pmt.send(sig, acct, pmt_url=settings.pmt_url,
                                     dry_run=settings.dry_run, retry_max=settings.retry_max,
                                     retry_backoff=settings.retry_backoff, client=client)
            elif broker == "pineconnector":
                res = await pineconnector.send(sig, acct, pc_url=settings.pc_url,
                                               dry_run=settings.dry_run, retry_max=settings.retry_max,
                                               retry_backoff=settings.retry_backoff, client=client)
            else:
                res = {"status": "error", "reason": f"unknown broker '{broker}'"}
            res["account"] = aid
            if risk is not None and is_entry and res.get("status") in ("sent", "dry_run"):
                risk.record_entry(aid)
            results.append(res)
    return results
