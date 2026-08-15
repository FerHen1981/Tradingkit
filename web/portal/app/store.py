"""Read-only access to the trading journal.

The portal never touches the live `journal.db`. The middleware writes to that
file continuously and it is the record of what the fleet actually did; a web
process holding locks on it — or worse, writing to it — is a trading incident
waiting to happen. Instead a consistent copy is taken with `VACUUM INTO` and
every query runs against the copy, opened read-only at the driver level so a
coding mistake cannot write even if it tries.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("mex.portal.store")


def take_snapshot(source: str, dest: str) -> str:
    """Copy the live journal to `dest` without blocking the writer.

    `VACUUM INTO` produces a transactionally consistent copy while the source
    stays writable. It refuses to overwrite, so the copy is written to a
    temporary name and moved into place — which also makes the swap atomic for
    readers of `dest`.
    """
    src = Path(source)
    if not src.exists():
        raise FileNotFoundError(f"journal not found: {source}")

    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=dest_path.parent, suffix=".tmp")
    os.close(fd)
    os.unlink(tmp)  # VACUUM INTO requires the target not to exist

    conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        conn.execute("VACUUM INTO ?", (tmp,))
    finally:
        conn.close()

    shutil.move(tmp, dest_path)
    log.info("journal snapshot written to %s (%d bytes)", dest_path, dest_path.stat().st_size)
    return str(dest_path)


class Store:
    """Read-only queries over a journal snapshot."""

    def __init__(self, path: str):
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._mtime: float = 0.0

    def _connect(self) -> sqlite3.Connection:
        # Reconnect when the snapshot has been replaced underneath us, so a
        # long-lived process picks up each new refresh without a restart.
        mtime = Path(self.path).stat().st_mtime if Path(self.path).exists() else 0.0
        if self._conn is None or mtime != self._mtime:
            if self._conn is not None:
                self._conn.close()
            self._conn = sqlite3.connect(
                f"file:{self.path}?mode=ro", uri=True, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._mtime = mtime
        return self._conn

    @property
    def available(self) -> bool:
        return Path(self.path).exists()

    @property
    def generated_at(self) -> float:
        return self._mtime or (Path(self.path).stat().st_mtime if self.available else 0.0)

    def _rows(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        if not self.available:
            return []
        try:
            cur = self._connect().execute(sql, params)
        except sqlite3.OperationalError as exc:
            # A snapshot taken before a migration may lack a table. Degrade to
            # empty rather than 500 the whole dashboard.
            log.warning("query failed (%s); returning no rows", exc)
            return []
        return [dict(r) for r in cur.fetchall()]

    def trades(self, since_ts: float = 0.0) -> list[dict[str, Any]]:
        """Reconciled trades — the per-trade truth, with units already on it."""
        return self._rows(
            """
            SELECT ts, strategy, venue, account, symbol, side,
                   intended_price, fill_price, slippage_ticks, slippage_usd,
                   latency_s, intended_qty, fill_qty,
                   realized_usd, realized_r, expected_r, hold_s, matched
            FROM recon
            WHERE ts >= ? AND matched = 1
            ORDER BY ts
            """,
            (since_ts,),
        )

    def accounts(self) -> list[dict[str, Any]]:
        """Most recent balance snapshot per account (currency — owner only)."""
        return self._rows(
            """
            SELECT p.ts, p.account, p.account_id, p.realized, p.open_pnl, p.total_val
            FROM perf p
            JOIN (SELECT account, MAX(ts) mt FROM perf GROUP BY account) x
              ON p.account = x.account AND p.ts = x.mt
            ORDER BY p.account
            """
        )

    def equity_points(self, account: str | None = None) -> list[dict[str, Any]]:
        """Daily total account value, for the equity curve."""
        if account:
            return self._rows(
                "SELECT ts, account, total_val FROM perf WHERE account = ? ORDER BY ts",
                (account,),
            )
        return self._rows("SELECT ts, account, total_val FROM perf ORDER BY ts")

    def last_activity(self) -> float:
        rows = self._rows("SELECT MAX(ts) AS t FROM recon")
        return (rows[0]["t"] if rows and rows[0]["t"] else 0.0) or 0.0

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def humanise_age(ts: float) -> str:
    if not ts:
        return "onbekend"
    delta = max(0, time.time() - ts)
    if delta < 90:
        return "zojuist"
    if delta < 3600:
        return f"{int(delta // 60)} min geleden"
    if delta < 86400:
        return f"{int(delta // 3600)} uur geleden"
    return f"{int(delta // 86400)} dagen geleden"
