"""MetaAPI (metaapi.cloud) read client — pulls MT5 deals (fills) for FTMO/MT5 accounts,
so the reconciliation engine can compare intended vs actual on the FX side.

Real path uses the MetaApi client REST API:
  GET {base}/users/current/accounts/{accountId}/history-deals/time/{start}/{end}
  header: auth-token: <METAAPI_TOKEN>
Field mapping (symbol/price/volume/time/type) is parsed defensively and must be
confirmed against your account's first real deals. Set METAAPI_MOCK=true to run the
pipeline with fake MT5 fills (no token needed).
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx

from .reconcile import Fill

log = logging.getLogger("mex.metaapi")


class MetaApiClient:
    def __init__(self, base: str, token: str, account_id: str, mock: bool = False):
        self.base = base.rstrip("/")
        self.token = token
        self.account_id = account_id
        self.mock = mock

    @property
    def enabled(self) -> bool:
        return self.mock or bool(self.token and self.account_id)

    async def fills(self, since_ts: float, now_ts: float) -> list[Fill]:
        if self.mock:
            return [Fill("mt5", "FTMO-1", "US500", "sell", 5300.5, 2.0, since_ts + 6.0, "mt5-mock-1")]
        start = dt.datetime.utcfromtimestamp(since_ts).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end = dt.datetime.utcfromtimestamp(now_ts).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        url = f"{self.base}/users/current/accounts/{self.account_id}/history-deals/time/{start}/{end}"
        out: list[Fill] = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url, headers={"auth-token": self.token})
                r.raise_for_status()
                for d in r.json():
                    dtype = str(d.get("type", "")).upper()          # DEAL_TYPE_BUY / DEAL_TYPE_SELL
                    if "BUY" not in dtype and "SELL" not in dtype:
                        continue
                    side = "buy" if "BUY" in dtype else "sell"
                    t = d.get("time") or d.get("brokerTime")
                    try:
                        ts = dt.datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
                    except Exception:
                        ts = now_ts
                    out.append(Fill("mt5", str(d.get("accountId", self.account_id)),
                                    d.get("symbol", ""), side,
                                    float(d.get("price", 0) or 0), float(d.get("volume", 0) or 0),
                                    ts, str(d.get("id", ""))))
        except Exception as exc:
            log.warning("metaapi fills failed: %r", exc)
        return out
