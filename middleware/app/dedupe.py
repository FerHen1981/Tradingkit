"""Idempotency: drop duplicate signals that arrive within a short TTL window.

TradingView (or a network retry) can deliver the same alert more than once. We key on
the signal's content and refuse to dispatch the same order twice inside `ttl` seconds.
In-memory is enough — duplicates arrive seconds apart, and a restart is a safe reset.
"""
from __future__ import annotations

import hashlib
import time

from .models import Signal


class Deduper:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._seen: dict[str, float] = {}

    @staticmethod
    def key(sig: Signal) -> str:
        raw = f"{sig.strategy}|{sig.event}|{sig.action}|{sig.symbol}|{sig.price}|{sig.qty}|{sig.dollar_sl}|{sig.dollar_tp}"
        return hashlib.sha1(raw.encode()).hexdigest()

    def seen_recently(self, sig: Signal, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        # prune expired
        self._seen = {k: t for k, t in self._seen.items() if now - t < self.ttl}
        k = self.key(sig)
        if k in self._seen:
            return True
        self._seen[k] = now
        return False
