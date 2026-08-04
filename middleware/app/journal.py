"""Append-only SQLite journal. Every inbound signal and every outbound attempt is
recorded, so you can always answer "did that order actually go out, and what came back".
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    kind      TEXT NOT NULL,          -- 'signal' | 'dispatch' | 'error'
    strategy  TEXT,
    account   TEXT,
    detail    TEXT                    -- JSON blob
);
CREATE TABLE IF NOT EXISTS perf (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    account    TEXT NOT NULL,         -- Tradovate account name
    account_id INTEGER,               -- Tradovate numeric id
    realized   REAL,                  -- realized PnL
    open_pnl   REAL,                  -- open (unrealized) PnL
    total_val  REAL,                  -- total cash value
    raw        TEXT                   -- full snapshot JSON
);
CREATE INDEX IF NOT EXISTS perf_ts ON perf(ts);
"""


class Journal:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def write(self, kind: str, detail: dict, strategy: str = "", account: str = "") -> None:
        self._db.execute(
            "INSERT INTO events (ts, kind, strategy, account, detail) VALUES (?,?,?,?,?)",
            (time.time(), kind, strategy, account, json.dumps(detail, default=str)),
        )
        self._db.commit()

    def recent(self, limit: int = 50) -> list[dict]:
        cur = self._db.execute(
            "SELECT ts, kind, strategy, account, detail FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [
            {"ts": r[0], "kind": r[1], "strategy": r[2], "account": r[3], "detail": json.loads(r[4])}
            for r in cur.fetchall()
        ]

    def write_perf(self, rows: list[dict]) -> None:
        """rows: [{ts, account, account_id, realized, open_pnl, total_val, raw}]"""
        self._db.executemany(
            "INSERT INTO perf (ts, account, account_id, realized, open_pnl, total_val, raw) "
            "VALUES (:ts, :account, :account_id, :realized, :open_pnl, :total_val, :raw)",
            [{**r, "raw": json.dumps(r.get("raw", {}), default=str)} for r in rows],
        )
        self._db.commit()

    def latest_perf(self) -> list[dict]:
        """Most recent snapshot per account."""
        cur = self._db.execute(
            "SELECT p.ts, p.account, p.account_id, p.realized, p.open_pnl, p.total_val "
            "FROM perf p JOIN (SELECT account, MAX(ts) mt FROM perf GROUP BY account) x "
            "ON p.account = x.account AND p.ts = x.mt ORDER BY p.account"
        )
        return [
            {"ts": r[0], "account": r[1], "account_id": r[2],
             "realized": r[3], "open_pnl": r[4], "total_val": r[5]}
            for r in cur.fetchall()
        ]
