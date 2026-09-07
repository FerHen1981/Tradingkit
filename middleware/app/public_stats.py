"""Publieke statistieken schrijven — de brug tussen de trade-log en `public-stats.json`.

Dit is de bezorgster: geen data-toegang van eigen, geen aggregatie van eigen,
geen role-logica van eigen. Zij haalt bestaande trades op uit `dashboard_state`
(één source of truth), zet ze in het formaat dat `mex_units.roles` verwacht,
laat die de `for_public()`-payload bouwen en schrijft het resultaat naar disk.

De publicatiepoort (`assert_no_currency`) wordt gedraaid vóór het bestand
geschreven wordt — één ValueError en er verlaat niets het pand. Dat is een
tweede slot bovenop de builder, precies zoals `mex_units/README.md` bedoelt.

Runner:
    python -m app.public_stats

Env:
    PUBLIC_STATS_PATH   waar het bestand landt (default /root/public-stats.json).
                        De viewer serveert deze file op /public-stats.json.
    PUBLIC_STATS_DELAY  het "delay" label in de payload (default "T+1").
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path

from .dashboard_state import _sources
from .mex_units import roles

log = logging.getLogger("mex.public_stats")

_DEFAULT_PATH = "/root/public-stats.json"


def _to_mex_units_trade(t: dict) -> dict:
    """dashboard_state trade → mex_units.roles trade.

    `_sources()` geeft `{acct, sym, strat, net, ticks, close, hour, dow, comm, mfe, mae}`;
    `roles.build()` wil ten minste `{ts, symbol, realized_usd}` en gebruikt
    optioneel `realized_r`, `fill_qty`, `slippage_ticks`, `hold_s`.

    We hebben (nog) geen R-berekening op deze laag — dat zou de intended
    stop-afstand uit de routed-log vereisen. Zonder R blijven R-metrics
    (profit_factor, expectancy_r) `None`, wat correcter is dan een geraden
    waarde. Verrijking komt via de reconcile-runner (D-03) als die volwassen is.
    """
    close = t.get("close")
    if isinstance(close, dt.date):
        # Sessiedag → epoch (middag als anker; de UTC-datum is wat telt voor _month()).
        ts = dt.datetime(close.year, close.month, close.day, 12, tzinfo=dt.timezone.utc).timestamp()
    else:
        ts = 0.0
    return {
        "ts": ts,
        "symbol": t.get("sym") or "",
        "realized_usd": float(t.get("net") or 0.0),
        # kwaliteitsvelden die we wél al hebben:
        "slippage_ticks": None,   # niet betrouwbaar op deze laag; komt uit reconcile
        "hold_s": None,           # zelfde
    }


def build_public_payload(delay: str = "T+1") -> dict:
    """Bouw de publieke payload uit de gezaghebbende trade-bron."""
    trades, _accounts = _sources()   # accounts publiceren we niet, dus negeren
    payload_trades = [_to_mex_units_trade(t) for t in trades]
    fleet = roles.build(payload_trades, accounts=None)
    payload = roles.for_public(fleet, delay=delay)
    # Tweede slot: publicatie mag geen geldveld bevatten.
    roles.assert_no_currency(payload)
    return payload


def write(path: str | Path | None = None, delay: str | None = None) -> dict:
    """Schrijf `public-stats.json` en geef een korte samenvatting terug."""
    path = Path(path or os.environ.get("PUBLIC_STATS_PATH") or _DEFAULT_PATH)
    delay = delay or os.environ.get("PUBLIC_STATS_DELAY") or "T+1"
    started = time.monotonic()
    payload = build_public_payload(delay=delay)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)     # atomic swap zodat de viewer nooit een halve file leest
    summary = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "trades": payload["headline"]["trades"],
        "markets": len(payload["markets"]),
        "period": payload["period"],
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    log.info("public-stats written: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        print(json.dumps(write(), indent=2, default=str))
    except Exception as exc:
        log.error("public-stats build failed: %r", exc)
        sys.exit(1)
