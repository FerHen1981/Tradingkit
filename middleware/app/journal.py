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
    kind      TEXT NOT NULL,          -- 'signal' | 'dispatch' | 'dedupe' | 'alert' | 'error'
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
CREATE TABLE IF NOT EXISTS recon (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    strategy   TEXT, venue TEXT, account TEXT, symbol TEXT, side TEXT,
    intended_price REAL, fill_price REAL,
    slippage_price REAL, slippage_ticks REAL, slippage_usd REAL, slippage_pct REAL,
    latency_s REAL, intended_qty REAL, fill_qty REAL, qty_diff REAL,
    realized_usd REAL, realized_r REAL, expected_r REAL, hold_s REAL,
    matched INTEGER
);
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

    def recent(self, limit: int = 50, kind: str = "", strategy: str = "",
               contains: str = "") -> list[dict]:
        """Newest events first. `kind`/`strategy` filter exactly (comma-separated for
        several kinds); `contains` is a substring match on the JSON detail — the quickest
        way to answer "did that alert reach me, and what did I make of it?".
        """
        where, args = [], []
        kinds = [k.strip() for k in kind.split(",") if k.strip()]
        if kinds:
            where.append(f"kind IN ({','.join('?' * len(kinds))})")
            args += kinds
        if strategy:
            where.append("strategy = ?")
            args.append(strategy)
        if contains:
            where.append("detail LIKE ?")
            args.append(f"%{contains}%")
        sql = "SELECT ts, kind, strategy, account, detail FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        cur = self._db.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit))
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

    def signals_since(self, since_ts: float) -> list[dict]:
        """Intended trades: signal events since `since_ts`, flattened with their timestamp."""
        cur = self._db.execute(
            "SELECT ts, detail FROM events WHERE kind='signal' AND ts>=? ORDER BY ts", (since_ts,))
        out = []
        for ts, detail in cur.fetchall():
            d = json.loads(detail)
            out.append({"ts": ts, "strategy": d.get("strategy"), "symbol": d.get("symbol"),
                        "side": d.get("action"), "price": d.get("price"), "qty": d.get("qty"),
                        "dollar_sl": d.get("dollar_sl"), "dollar_tp": d.get("dollar_tp")})
        return out

    def write_recon(self, rows: list[dict]) -> None:
        cols = ("ts", "strategy", "venue", "account", "symbol", "side", "intended_price",
                "fill_price", "slippage_price", "slippage_ticks", "slippage_usd", "slippage_pct",
                "latency_s", "intended_qty", "fill_qty", "qty_diff",
                "realized_usd", "realized_r", "expected_r", "hold_s", "matched")
        import time as _t
        payload = [{**{c: r.get(c) for c in cols if c != "ts"},
                    "ts": r.get("fill_ts") or _t.time(),
                    "matched": 1 if r.get("matched") else 0} for r in rows]
        self._db.executemany(
            f"INSERT INTO recon ({','.join(cols)}) VALUES ({','.join(':' + c for c in cols)})", payload)
        self._db.commit()

    def day_pnl(self, since_ts: float) -> dict:
        """Fleet P&L moved since `since_ts`, from the Tradovate perf snapshots.

        `perf.realized` is cumulative per account, so the day's realized = latest minus
        the first snapshot at/after the day boundary. That means the tally only covers
        what the poller actually saw: with no poller running (TRADOVATE_* unset) this
        returns realized=None and the notify message simply omits the P&L field.
        """
        cur = self._db.execute(
            "SELECT account, ts, realized, open_pnl FROM perf WHERE ts>=? ORDER BY ts", (since_ts,))
        first: dict[str, float] = {}
        last: dict[str, tuple[float, float]] = {}
        for account, _ts, realized, open_pnl in cur.fetchall():
            if account not in first:
                first[account] = realized or 0.0
            last[account] = (realized or 0.0, open_pnl or 0.0)
        if not last:
            return {"realized": None, "open_pnl": None, "accounts": 0, "since_ts": since_ts}
        return {
            "realized": round(sum(r - first[a] for a, (r, _o) in last.items()), 2),
            "open_pnl": round(sum(o for _r, o in last.values()), 2),
            "accounts": len(last),
            "since_ts": since_ts,
        }

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
