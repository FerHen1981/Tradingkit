"""Canonical, broker-agnostic trade signal.

TradingView / the Pine strategy sends THIS (lean) shape to the middleware — it knows
nothing about accounts or brokers. The middleware maps `strategy` -> subscribed
accounts and builds each broker's real payload. That is what lets you keep ONE alert
per strategy instead of one alert per account per strategy.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class Signal(BaseModel):
    secret: str = Field(..., description="Shared secret; must match MIDDLEWARE_SECRET.")
    strategy: str = Field(..., description="Strategy key, e.g. 'GC' or 'ES'. Maps to accounts.yaml.")
    event: Literal["ENTRY", "EXIT"] = "ENTRY"
    action: Literal["buy", "sell", "close"] = Field(..., description="buy/sell to open, close to flatten.")
    symbol: str = Field(..., description="Chart symbol, e.g. 'GC1!'. Per-account override lives in yaml.")
    price: float = 0.0
    order_type: Literal["LMT", "MKT"] = "MKT"
    dollar_sl: float = Field(0.0, description="Stop distance in $ per contract (PMT dollar_sl).")
    dollar_tp: float = Field(0.0, description="Target distance in $ per contract (PMT dollar_tp).")
    qty: int = Field(1, ge=0, description="Base contracts; each account scales by its quantity_multiplier.")
    # Stop management — carried through to PMT so the trailing / break-even bracket is placed
    # exactly as the Pine f_pmtJSON did (PMT trails the Tradovate stop server-side from these).
    trail: int = Field(0, description="1 = PMT trails the stop, 0 = fixed stop.")
    trail_stop: float = Field(0.0, description="Trail distance kept from the extreme (price units).")
    trail_trigger: float = Field(0.0, description="Profit (price units) at which the trail starts.")
    trail_freq: float = Field(0.0, description="Trail update step (price units).")
    breakeven: float = Field(0.0, description="MFE (price units) at which the stop moves to break-even; 0 = off.")

    def redacted(self) -> dict:
        d = self.model_dump()
        d["secret"] = "***"
        return d
