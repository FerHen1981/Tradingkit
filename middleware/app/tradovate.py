"""Tradovate read-side client — pulls live account P&L for fleet tracking.

This is separate from the order-routing brokers/: here the middleware READS each
account's realized/open PnL from Tradovate and stores snapshots, so LifeOS can show live
fleet performance. A background poller refreshes on an interval.

Endpoints (confirmed):
  POST /v1/auth/accessTokenRequest   {name,password,appId,appVersion,cid,sec} -> {accessToken, expirationTime}
  GET  /v1/account/list              -> [{id, name, ...}]
  POST /v1/cashBalance/getcashbalancesnapshot  {accountId} -> {realizedPnL, openPnL, totalCashValue, ...}

Base: https://live.tradovateapi.com/v1 (live) or https://demo.tradovateapi.com/v1 (demo).
Set TRADOVATE_MOCK=true to run the whole pipeline with fake data (no credentials).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

from .reconcile import Fill

log = logging.getLogger("mex.tradovate")


def _num(d: dict, *keys) -> float:
    """First present numeric field among keys (Tradovate field names vary slightly)."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


class TradovateClient:
    def __init__(self, base: str, creds: dict, mock: bool = False):
        self.base = base.rstrip("/")
        self.creds = creds
        self.mock = mock
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    async def _auth(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        body = {k: self.creds.get(k, "") for k in ("name", "password", "appId", "appVersion", "cid", "sec", "deviceId")}
        r = await client.post(f"{self.base}/auth/accessTokenRequest", json=body)
        r.raise_for_status()
        j = r.json()
        if not j.get("accessToken"):
            raise RuntimeError(f"Tradovate auth failed: {j.get('errorText') or j}")
        self._token = j["accessToken"]
        # expirationTime is ISO; fall back to 50 min if unparseable
        self._token_exp = time.time() + 50 * 60
        return self._token

    async def fleet_pnl(self) -> list[dict]:
        """Return a snapshot row per account: {ts, account, account_id, realized, open_pnl, total_val, raw}."""
        now = time.time()
        if self.mock:
            return [
                {"ts": now, "account": f"MOCK-{i}", "account_id": 1000 + i,
                 "realized": v[0], "open_pnl": v[1], "total_val": 50000 + v[0] + v[1], "raw": {"mock": True}}
                for i, v in enumerate([(3382.85, 0.0), (10148.55, -120.0), (0.0, 45.0)], start=1)
            ]
        rows: list[dict] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._auth(client)
            headers = {"Authorization": f"Bearer {token}"}
            accts = (await client.get(f"{self.base}/account/list", headers=headers)).json()
            for a in accts:
                aid, name = a.get("id"), a.get("name", str(a.get("id")))
                try:
                    snap = (await client.post(f"{self.base}/cashBalance/getcashbalancesnapshot",
                                              json={"accountId": aid}, headers=headers)).json()
                except Exception as exc:
                    log.warning("snapshot failed for %s: %r", name, exc)
                    continue
                rows.append({
                    "ts": now, "account": name, "account_id": aid,
                    "realized": _num(snap, "realizedPnL", "realizedPnl", "weekRealizedPnL"),
                    "open_pnl": _num(snap, "openPnL", "openPnl"),
                    "total_val": _num(snap, "totalCashValue", "totalCashValueSnapshot", "amount"),
                    "raw": snap,
                })
        return rows


    async def fills(self, since_ts: float) -> list["Fill"]:
        """Actual futures fills for reconciliation. Real path: GET /fill/list (defensive
        parse — confirm price/qty/action/symbol fields against your first live fills)."""
        if self.mock:
            return [Fill("tradovate", "APEX-1", "GC1!", "buy", 2650.8, 1.0, since_ts + 1.2, "tv-mock-1")]
        out: list[Fill] = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                token = await self._auth(client)
                headers = {"Authorization": f"Bearer {token}"}
                data = (await client.get(f"{self.base}/fill/list", headers=headers)).json()
                for f in data:
                    ts = f.get("timestamp")
                    try:
                        import datetime as _dt
                        fts = _dt.datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
                    except Exception:
                        fts = since_ts
                    if fts < since_ts:
                        continue
                    side = "buy" if str(f.get("action", "")).lower().startswith("b") else "sell"
                    out.append(Fill("tradovate", str(f.get("accountId", "")), str(f.get("symbol", "")),
                                    side, float(f.get("price", 0) or 0), float(f.get("qty", 0) or 0),
                                    fts, str(f.get("id", ""))))
        except Exception as exc:
            log.warning("tradovate fills failed: %r", exc)
        return out


async def poll_loop(client: TradovateClient, journal, interval: float, on_snapshot=None) -> None:
    """Background task: refresh fleet P&L on an interval, store each snapshot, and hand the
    rows to an optional async `on_snapshot(rows)` callback (e.g. the Notion sync)."""
    log.info("Tradovate poller started (interval=%ss, mock=%s)", interval, client.mock)
    while True:
        try:
            rows = await client.fleet_pnl()
            if rows:
                journal.write_perf(rows)
                log.info("perf snapshot: %d accounts", len(rows))
                if on_snapshot is not None:
                    await on_snapshot(rows)
        except Exception as exc:  # keep the loop alive across transient failures
            log.warning("poll failed: %r", exc)
        await asyncio.sleep(interval)
