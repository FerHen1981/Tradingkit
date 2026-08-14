"""Fill-driven Notion Trade Journal writer.

One row per COMPLETED trade (a paired buy-fill + sell-fill from Tradovate), mapped onto
the real LifeOS Trade Journal schema and upserted idempotently by `Webhook ID`.

This replaces the old signal-time `NotionJournal` (which wrote a different, simplistic
set of columns and would have failed silently against the real DB). The journal is
populated when a trade CLOSES, from actual fills — not at signal time.

Field mapping was derived from the user's own exported Trade Journal data:
  - Trade ID / Webhook ID  = "{last3ofAccount}_{buyFillId}_{sellFillId}"
  - Strategy (select)      = engine version, e.g. "MEX PROP TRADER v6.4.4j"
  - Framework (relation)   = the specific "El ___" script (the Pine alert sends its name)
  - Source (select)        = "Custom Executor"  (distinguishes middleware rows from CSV import)
  - Signal Price + Slippage= computed from intended signal vs actual fill (the middleware's
                             edge over a plain CSV import)

Relations (Account, Assets, Framework, Account Types, Provider Account) are resolved by
title against their target databases and CREATED if missing. Target database ids and each
target's title-property name are discovered at runtime from the Trade Journal schema, so
nothing is hard-coded.

DRY: with no token/db configured, `upsert()` logs what it WOULD write and makes no API call.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

log = logging.getLogger("mex.journal")

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"
_ET = ZoneInfo("America/New_York")
_CT = ZoneInfo("America/Chicago")

ENGINE_STRATEGY = "MEX PROP TRADER v6.4.4j"   # the `Strategy` select value
SOURCE_CUSTOM = "Custom Executor"             # the `Source` select value for middleware rows

# Minimum price increment per instrument root — used for tick math (slippage, result ticks).
# Extend as needed; falls back to 0.25 (index-future default) with a warning.
_TICK_SIZE = {
    "ES": 0.25, "MES": 0.25, "NQ": 0.25, "MNQ": 0.25,
    "GC": 0.10, "MGC": 0.10, "YM": 1.0, "MYM": 1.0,
    "CL": 0.01, "MCL": 0.01, "RTY": 0.10, "M2K": 0.10,
}


def tick_size_for(contract_or_symbol: str) -> float:
    """Best-effort tick size from a contract ('MGCZ6') or symbol ('MGC1!')."""
    s = (contract_or_symbol or "").upper().lstrip("$")
    for root in sorted(_TICK_SIZE, key=len, reverse=True):
        if s.startswith(root):
            return _TICK_SIZE[root]
    log.warning("no tick size for %r; defaulting to 0.25", contract_or_symbol)
    return 0.25


@dataclass
class TradeRecord:
    """A completed trade, assembled by the fill feed from a paired entry+exit fill."""
    account_id: str                 # e.g. "PAAPEX2700250000018"
    buy_fill_id: str                # Tradovate buyFillId
    sell_fill_id: str               # Tradovate sellFillId
    direction: str                  # "BUY" | "SELL"
    contract: str                   # exact contract, e.g. "MGCZ6"
    symbol: str                     # chart symbol / asset, e.g. "MGC1!"
    position_size: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    commissions: float
    open_dt: dt.datetime            # tz-aware entry time
    close_dt: dt.datetime           # tz-aware exit time
    framework: str                  # the "El ___" script name (from the Pine alert)
    provider_account: str = "Apex Trader Funding"
    account_types: str | None = None       # e.g. "Apex 50k PA (Intraday)"
    status: str = "Closed Manually"        # a Trade Journal `Status` option
    # --- from the originating TradingView signal (the middleware's edge) ---
    signal_price: float | None = None      # intended entry price
    planned_sl: float | None = None        # planned stop PRICE
    planned_tp: float | None = None        # planned target PRICE
    tick_size: float | None = None         # override; else derived from contract
    # --- extras carried by the executor's routed cards (live layer) ---
    exit_reason: str | None = None         # e.g. "TRAIL", "SL", "TP"
    mfe_ticks: int | None = None           # max favourable excursion (ticks)
    mae_ticks: int | None = None           # max adverse excursion (ticks)

    def tick(self) -> float:
        return self.tick_size if self.tick_size else tick_size_for(self.contract or self.symbol)


# --------------------------------------------------------------------------- helpers

def trade_key(t: TradeRecord) -> str:
    """The idempotency key = Trade ID + Webhook ID. Matches the exported data exactly."""
    return f"{t.account_id[-3:]}_{t.buy_fill_id}_{t.sell_fill_id}"


def result_ticks(t: TradeRecord) -> float:
    sign = 1 if t.direction.upper() == "BUY" else -1
    return round(sign * (t.exit_price - t.entry_price) / t.tick(), 2)


def slippage_entry_ticks(t: TradeRecord) -> float | None:
    """Actual entry vs intended signal price, in ticks (positive = worse fill)."""
    if t.signal_price is None:
        return None
    sign = 1 if t.direction.upper() == "BUY" else -1
    return round(sign * (t.entry_price - t.signal_price) / t.tick(), 2)


def duration_min(t: TradeRecord) -> float:
    return round((t.close_dt - t.open_dt).total_seconds() / 60.0, 1)


def hour_et(t: TradeRecord) -> int:
    return t.open_dt.astimezone(_ET).hour


def day_name(t: TradeRecord) -> str:
    return t.open_dt.astimezone(_ET).strftime("%A")


def apex_trade_date(t: TradeRecord) -> str:
    """CME/Apex trading day (17:00 CT rollover): a session belongs to the next date once
    it crosses 17:00 Central. Best-effort; matches Apex's consistency dating."""
    ct = t.open_dt.astimezone(_CT)
    d = ct.date()
    if ct.hour >= 17:
        d = d + dt.timedelta(days=1)
    return d.isoformat()


def build_notes(t: TradeRecord) -> str:
    parts = [f"acct={t.account_id}"]
    if t.planned_sl is not None:
        parts.append(f"plannedSL={t.planned_sl:g}")
    if t.planned_tp is not None:
        parts.append(f"plannedTP={t.planned_tp:g}")
    if t.exit_reason:
        parts.append(f"exit={t.exit_reason}")
    if t.mfe_ticks is not None:
        parts.append(f"MFE={t.mfe_ticks}t")
    if t.mae_ticks is not None:
        parts.append(f"MAE={t.mae_ticks}t")
    return "; ".join(parts)


def _num(v):
    return {"number": v}


def _text(v: str):
    return {"rich_text": [{"text": {"content": v}}]} if v else {"rich_text": []}


def _select(v: str | None):
    return {"select": {"name": v}} if v else {"select": None}


def _date(d: dt.datetime | str):
    iso = d.isoformat() if isinstance(d, dt.datetime) else d
    return {"date": {"start": iso}}


def scalar_properties(t: TradeRecord) -> dict:
    """All non-relation properties. Pure + deterministic → unit-testable against the CSV."""
    key = trade_key(t)
    props = {
        "Trade ID": {"title": [{"text": {"content": key}}]},
        "Webhook ID": _text(key),
        "Direction": _select(t.direction.upper()),
        "Contract": _text(t.contract),
        "PositionSize": _num(t.position_size),
        "Entry Price ($)": _num(t.entry_price),
        "Exit Price ($)": _num(t.exit_price),
        "Gross PnL": _num(t.gross_pnl),
        "Commissions": _num(t.commissions),
        "Buy Fill ID": _text(t.buy_fill_id),
        "Sell Fill ID": _text(t.sell_fill_id),
        "Open Date": _date(t.open_dt),
        "Close Date": _date(t.close_dt),
        "Apex Trade Date": _date(apex_trade_date(t)),
        "Duration (min)": _num(duration_min(t)),
        "Result (Ticks)": _num(result_ticks(t)),
        "Hour (ET)": _num(hour_et(t)),
        "Day": _select(day_name(t)),
        "Notes": _text(build_notes(t)),
        "Strategy": _select(ENGINE_STRATEGY),
        "Source": _select(SOURCE_CUSTOM),
        "Status": _select(t.status),
        "Sync Status": _select("Auto"),
    }
    if t.signal_price is not None:
        props["Signal Price ($)"] = _num(t.signal_price)
        se = slippage_entry_ticks(t)
        if se is not None:
            props["Slippage Entry (ticks)"] = _num(se)
    return props


# --------------------------------------------------------------------------- writer

class NotionTradeJournal:
    """Resolves relations (create-if-missing) and upserts one row per completed trade."""

    # Trade Journal property name -> the trade field that supplies the relation's title.
    _RELATION_FIELDS = {
        "Account": "account_id",
        "Assets": "symbol",
        "Framework": "framework",
        "Account Types": "account_types",
        "Provider Account": "provider_account",
    }

    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id
        self._rel_db: dict[str, str] = {}      # prop name -> target database_id
        self._title_prop: dict[str, str] = {}  # database_id -> its title property name
        self._rel_cache: dict[tuple[str, str], str] = {}  # (db_id, name) -> page id
        self._discovered = False

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.db_id)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Notion-Version": _VER,
                "Content-Type": "application/json"}

    async def _discover(self, client: httpx.AsyncClient) -> None:
        """Read the Trade Journal schema once: map each relation prop to its target DB,
        and find each target DB's title property. No hard-coded ids."""
        if self._discovered:
            return
        r = await client.get(f"{_API}/databases/{self.db_id}", headers=self._headers())
        r.raise_for_status()
        schema = r.json().get("properties", {})
        for prop in self._RELATION_FIELDS:
            meta = schema.get(prop)
            if meta and meta.get("type") == "relation":
                self._rel_db[prop] = meta["relation"]["database_id"]
        for db_id in set(self._rel_db.values()):
            self._title_prop[db_id] = await self._find_title_prop(client, db_id)
        self._discovered = True

    async def _find_title_prop(self, client: httpx.AsyncClient, db_id: str) -> str:
        r = await client.get(f"{_API}/databases/{db_id}", headers=self._headers())
        r.raise_for_status()
        for name, meta in r.json().get("properties", {}).items():
            if meta.get("type") == "title":
                return name
        return "Name"

    async def _resolve_relation(self, client: httpx.AsyncClient, prop: str, name: str) -> str | None:
        """Return the page id for `name` in the relation's target DB, creating it if absent."""
        db_id = self._rel_db.get(prop)
        if not db_id or not name:
            return None
        ck = (db_id, name)
        if ck in self._rel_cache:            # resolve each account/framework/asset once
            return self._rel_cache[ck]
        title = self._title_prop.get(db_id, "Name")
        q = await client.post(f"{_API}/databases/{db_id}/query", headers=self._headers(),
                              json={"filter": {"property": title, "title": {"equals": name}},
                                    "page_size": 1})
        q.raise_for_status()
        hits = q.json().get("results", [])
        if hits:
            page_id = hits[0]["id"]
        else:
            created = await client.post(f"{_API}/pages", headers=self._headers(),
                                        json={"parent": {"database_id": db_id},
                                              "properties": {title: {"title": [{"text": {"content": name}}]}}})
            created.raise_for_status()
            page_id = created.json()["id"]
            log.info("created missing %s relation: %s", prop, name)
        self._rel_cache[ck] = page_id
        return page_id

    async def _existing_page(self, client: httpx.AsyncClient, key: str) -> str | None:
        r = await client.post(f"{_API}/databases/{self.db_id}/query", headers=self._headers(),
                              json={"filter": {"property": "Webhook ID", "rich_text": {"equals": key}},
                                    "page_size": 1})
        r.raise_for_status()
        res = r.json().get("results", [])
        return res[0]["id"] if res else None

    async def upsert(self, t: TradeRecord) -> None:
        key = trade_key(t)
        if not self.enabled:
            log.info("journal DRY: would upsert %s (%s %s %s @ %.2f→%.2f, pnl %.2f)",
                     key, t.framework, t.direction, t.contract, t.entry_price, t.exit_price, t.gross_pnl)
            return
        import httpx  # local import: pure mapping + DRY mode stay usable without httpx
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                await self._discover(client)
                props = scalar_properties(t)
                for prop, field_name in self._RELATION_FIELDS.items():
                    name = getattr(t, field_name, None)
                    page_id = await self._resolve_relation(client, prop, name) if name else None
                    if page_id:
                        props[prop] = {"relation": [{"id": page_id}]}
                existing = await self._existing_page(client, key)
                if existing:
                    await client.patch(f"{_API}/pages/{existing}", headers=self._headers(),
                                       json={"properties": props})
                else:
                    await client.post(f"{_API}/pages", headers=self._headers(),
                                      json={"parent": {"database_id": self.db_id}, "properties": props})
        except Exception as exc:  # never let journaling stall execution
            log.warning("journal upsert failed for %s: %r", key, exc)
