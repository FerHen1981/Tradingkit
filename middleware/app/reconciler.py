"""Reconciler — ties it together: read the intended trades (journalled signals) and the
actual fills (Tradovate futures + MetaAPI MT5), match them, compute discrepancies, and
write the result to the persistent store + the LifeOS Reconciliation dashboard.

Run on demand via POST /reconcile, or on an interval.
"""
from __future__ import annotations

import logging
import time

from .reconcile import match_fills

log = logging.getLogger("mex.reconciler")


class Reconciler:
    def __init__(self, journal, tv_client=None, meta_client=None, notion_recon=None):
        self.journal = journal
        self.tv = tv_client
        self.meta = meta_client
        self.notion = notion_recon

    async def run(self, lookback_s: float = 900.0) -> dict:
        now = time.time()
        since = now - lookback_s
        intended = [s for s in self.journal.signals_since(since) if s.get("side") in ("buy", "sell")]

        fills = []
        if self.tv is not None:
            try:
                fills += await self.tv.fills(since)
            except Exception as exc:
                log.warning("tradovate fills error: %r", exc)
        if self.meta is not None and self.meta.enabled:
            try:
                fills += await self.meta.fills(since, now)
            except Exception as exc:
                log.warning("metaapi fills error: %r", exc)

        rows = match_fills(intended, fills)
        if rows:
            self.journal.write_recon(rows)
            if self.notion is not None:
                await self.notion.append(rows)

        matched = [r for r in rows if r.get("matched")]
        return {
            "intended": len(intended), "fills": len(fills),
            "matched": len(matched), "unmatched": len(rows) - len(matched),
            "avg_slippage_ticks": round(
                sum(r["slippage_ticks"] for r in matched if r.get("slippage_ticks") is not None)
                / max(1, sum(1 for r in matched if r.get("slippage_ticks") is not None)), 2) if matched else None,
            "avg_latency_s": round(
                sum(r["latency_s"] for r in matched if r.get("latency_s") is not None)
                / max(1, sum(1 for r in matched if r.get("latency_s") is not None)), 2) if matched else None,
        }
