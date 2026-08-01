"""Per-account risk overlay.

What it enforces NOW (no PnL feed required):
  - a per-account daily ENTRY cap (max new positions per trading day)
  - a per-account HALT flag (set manually or by an external monitor when an account
    hits its daily-loss limit) — blocks new entries until resumed / day rollover

What it never does:
  - block a `close`/exit — you must always be able to flatten a position

Full daily-loss ($) and 50%-consistency enforcement need realized PnL, which the
middleware does not see today. `record_fill()` is the hook: wire a broker/PnL feed to
it later and this class can auto-halt on DLL or consistency breach (Phase 5b). Until
then those checks are dormant and the entry-cap + halt flag are the live guards.

Trading day = America/New_York calendar date (close enough to the 18:00 ET futures roll
for a per-day cap; refine to session-anchored later if needed).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def trading_day() -> str:
    return dt.datetime.now(_ET).strftime("%Y-%m-%d")


class RiskState:
    def __init__(self, default_cap: int = 0):
        self.default_cap = default_cap
        self._day: str | None = None
        self._entries: dict[str, int] = {}
        self._halted: set[str] = set()

    def _roll(self, day: str) -> None:
        if self._day != day:
            self._day = day
            self._entries = {}
            self._halted = set()  # halts are per-day; a new day clears them

    def allow(self, account_id: str, acct: dict, is_entry: bool, day: str | None = None) -> tuple[bool, str]:
        self._roll(day or trading_day())
        if not is_entry:
            return True, ""  # never block an exit
        if account_id in self._halted:
            return False, "account halted (risk)"
        cap = int(acct.get("max_entries_per_day", self.default_cap) or 0)
        if cap and self._entries.get(account_id, 0) >= cap:
            return False, f"daily entry cap {cap} reached"
        return True, ""

    def record_entry(self, account_id: str) -> None:
        self._entries[account_id] = self._entries.get(account_id, 0) + 1

    def halt(self, account_id: str) -> None:
        self._roll(trading_day())
        self._halted.add(account_id)

    def resume(self, account_id: str) -> None:
        self._halted.discard(account_id)

    # Hook for a future PnL feed (Phase 5b) — dormant until fills are wired in.
    def record_fill(self, account_id: str, pnl: float) -> None:  # pragma: no cover
        pass

    def snapshot(self) -> dict:
        return {"trading_day": self._day, "entries_today": dict(self._entries),
                "halted": sorted(self._halted), "default_cap": self.default_cap}
