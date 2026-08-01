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
"""


class Journal:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute(_SCHEMA)
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
