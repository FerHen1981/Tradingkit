"""Dagelijkse Fleet Performance writer — Cash History → Notion (D-163).

Doel. Fleet Performance (`ae5105393828447e84a1a87d31562d7d`) en Trade Journal
(`c3e9d05525404849ad484b648c82fd59`) hebben **nul rijen** sinds ze bestaan (D-20)
omdat de poller en de journal-writer in `middleware/app/` nooit als dagelijkse
timer op de VPS gezet zijn. Besluit Ferry 04-11 (D-164): één MEX-dagstand onder
Claude-beheer met trading-P&L **per account per handelsdag uit Notion**. Deze
module is de schrijfkant die die rijen maakt.

Bron is de **Cash History** (Tradovate-export in `EXPORTS_DIR/*Cash_History*.csv`).
Dat is de enige bron met de **echte** commissies — de PA rekent met $0 en het
Pine-tarief is een schatting. Per account per handelsdag schrijven we:

  bruto P&L   = Σ Trade Paired  (gross, voor commissie)
  commissies  = −Σ Commission   (positieve kostenpost)
  netto       = bruto − commissies + eventuele trading-fees
  aantal trades = aantal Trade Paired-events
  contracten  = Σ qty uit de Fills-CSV, per account per dag (optioneel)

Niet-trading-mutaties (payout, reset/activatie via Fund Transaction, Data Fee,
…) komen als aparte rijen met `kind="mutation"` zodat de Dagstand-taak er een
boekingsvoorstel van maakt — zonder ze in de Fleet-P&L te mengen.

LEESKANT ONLY. Geen raakpunt met `mex-receiver`, orders of PMT. De Notion-token
blijft in `.env`. DRY-mode zonder token/db: log wat hij zou schrijven.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import glob
import logging
import os
from collections import defaultdict

from .cash_ledger import AccountLedger, parse_cash_history

log = logging.getLogger("mex.fleet_daily")

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"


# -- aggregatie --------------------------------------------------------------


def load_ledgers(cash_dir: str, skip: list[str] | None = None) -> dict[str, AccountLedger]:
    """Alle Cash_History-exports in `cash_dir` lezen. Elke export is cumulatief
    vanaf account-open; de meest complete (meeste events) wint per account, zodat
    overlappende exports nooit dubbeltellen. Lege map → lege dict, nooit een fout."""
    skip = skip or []
    best: dict[str, AccountLedger] = {}
    for path in sorted(glob.glob(os.path.join(cash_dir, "*Cash_History*.csv"))):
        try:
            for acct, led in parse_cash_history(path).items():
                if any(s in acct for s in skip):
                    continue
                cur = best.get(acct)
                if cur is None or led.n_events > cur.n_events:
                    best[acct] = led
        except Exception as exc:
            log.warning("cash ledger parse failed %s: %r", path, exc)
    return best


def contracts_per_day(fills_dir: str) -> dict[str, dict[str, int]]:
    """Per account per handelsdag: Σ qty uit de Fills-CSV's. Fills-CSV's komen uit
    `fills_pairing.parse_fills_csv`; die hergebruiken we niet omdat we alleen qty
    en een datumstempel nodig hebben, geen FIFO-pairing. Fallback: lege map, dan
    toont de daily-rij `contracts=null` i.p.v. een geraden getal."""
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in sorted(glob.glob(os.path.join(fills_dir, "*_Fills.csv"))):
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    acct = (row.get("Account") or row.get("accountName") or "").strip()
                    if not acct:
                        continue
                    ts = (row.get("Timestamp") or row.get("timestamp") or "").strip()
                    date = _iso_date(ts)
                    qty = _int(row.get("qty") or row.get("Qty") or row.get("Quantity"))
                    if date and qty:
                        out[acct][date] += qty
        except Exception as exc:
            log.warning("fills parse failed %s: %r", path, exc)
    return {k: dict(v) for k, v in out.items()}


def _iso_date(s: str) -> str:
    s = (s or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _int(s) -> int:
    try:
        return int(float(str(s).strip() or 0))
    except (ValueError, TypeError):
        return 0


def build_rows(ledgers: dict[str, AccountLedger],
               contracts: dict[str, dict[str, int]] | None = None,
               today: dt.date | None = None) -> list[dict]:
    """Eén trade-day-row per account per dag waarop er trades waren. Rijen t/m
    `today` (default = nu in UTC) worden teruggegeven; latere dates (datafout)
    worden stil overgeslagen, zodat een fout in een export de rijen niet vervuilt."""
    today = today or dt.datetime.utcnow().date()
    out: list[dict] = []
    for acct, led in ledgers.items():
        for row in led.daily_rows():
            d = _parse_date(row["date"])
            if d is None or d > today:
                continue
            row["contracts"] = (contracts or {}).get(acct, {}).get(row["date"])
            row["kind"] = "trade_day"
            out.append(row)
    return sorted(out, key=lambda r: (r["date"], r["account"]))


def build_mutation_rows(ledgers: dict[str, AccountLedger],
                        today: dt.date | None = None) -> list[dict]:
    """Payouts / Fund Transactions / fees als aparte rijen. De Dagstand-taak
    (D-164) maakt er een boekingsvoorstel van; wij raden niets."""
    today = today or dt.datetime.utcnow().date()
    out: list[dict] = []
    for led in ledgers.values():
        for m in led.mutations:
            d = _parse_date(m.get("date", ""))
            if d is None or d > today:
                continue
            out.append({**m, "kind": "mutation"})
    return sorted(out, key=lambda r: (r.get("date", ""), r.get("account", "")))


def _parse_date(s: str) -> dt.date | None:
    s = (s or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# -- Notion writer -----------------------------------------------------------


class FleetDailyWriter:
    """Fleet Performance upsert. Keyed op `Account + Date`; één rij per account
    per handelsdag. Herrunnen is veilig: dezelfde (account, date) → patch, niet
    nieuwe rij. Non-trading-mutaties krijgen `Kind = mutation` (eigen select)
    naast de trade-day-rijen, in dezelfde database."""

    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id
        self._title_prop = ""                # "Name" or whatever the DB's title is called
        self._discovered = False

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.db_id)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Notion-Version": _VER,
                "Content-Type": "application/json"}

    async def _discover(self, client) -> None:
        if self._discovered:
            return
        r = await client.get(f"{_API}/databases/{self.db_id}", headers=self._headers())
        r.raise_for_status()
        for name, meta in r.json().get("properties", {}).items():
            if meta.get("type") == "title":
                self._title_prop = name
                break
        if not self._title_prop:
            self._title_prop = "Name"
        self._discovered = True

    @staticmethod
    def _row_title(row: dict) -> str:
        if row.get("kind") == "mutation":
            return f"{row.get('account','?')} {row.get('date','?')} {row.get('type','mutation')}"
        return f"{row.get('account','?')} {row.get('date','?')}"

    def _trade_props(self, row: dict) -> dict:
        return {
            self._title_prop: {"title": [{"text": {"content": self._row_title(row)}}]},
            "Account": {"rich_text": [{"text": {"content": str(row.get("account", ""))}}]},
            "Date": {"date": {"start": row["date"]}},
            "Kind": {"select": {"name": "trade_day"}},
            "Gross PnL": {"number": row.get("gross_pnl")},
            "Commissions": {"number": row.get("commissions")},
            "Net PnL": {"number": row.get("net_pnl")},
            "Trades": {"number": row.get("trade_count")},
            "Contracts": {"number": row.get("contracts")},
        }

    def _mutation_props(self, row: dict) -> dict:
        return {
            self._title_prop: {"title": [{"text": {"content": self._row_title(row)}}]},
            "Account": {"rich_text": [{"text": {"content": str(row.get("account", ""))}}]},
            "Date": {"date": {"start": row.get("date") or dt.date.today().isoformat()}},
            "Kind": {"select": {"name": "mutation"}},
            "Mutation Type": {"rich_text": [{"text": {"content": str(row.get("type", ""))}}]},
            "Delta": {"number": row.get("delta")},
            "Transaction ID": {"rich_text": [{"text": {"content": str(row.get("txid", ""))}}]},
        }

    async def _existing_page(self, client, title_text: str) -> str | None:
        r = await client.post(f"{_API}/databases/{self.db_id}/query", headers=self._headers(),
                              json={"filter": {"property": self._title_prop,
                                               "title": {"equals": title_text}},
                                    "page_size": 1})
        r.raise_for_status()
        res = r.json().get("results", [])
        return res[0]["id"] if res else None

    async def upsert(self, rows: list[dict], mutations: list[dict] | None = None) -> dict:
        mutations = mutations or []
        if not self.enabled:
            log.info("fleet_daily DRY: would write %d trade-days + %d mutations",
                     len(rows), len(mutations))
            return {"trade_days": len(rows), "mutations": len(mutations), "dry": True}
        import httpx       # lokaal: pure aggregatie + DRY-pad werken zonder httpx
        wrote = patched = failed = 0
        async with httpx.AsyncClient(timeout=20.0) as client:
            await self._discover(client)
            for row in rows:
                title = self._row_title(row)
                try:
                    props = self._trade_props(row)
                    existing = await self._existing_page(client, title)
                    if existing:
                        r = await client.patch(f"{_API}/pages/{existing}",
                                               headers=self._headers(),
                                               json={"properties": props})
                        patched += 1
                    else:
                        r = await client.post(f"{_API}/pages", headers=self._headers(),
                                              json={"parent": {"database_id": self.db_id},
                                                    "properties": props})
                        wrote += 1
                    r.raise_for_status()
                except Exception as exc:
                    log.warning("fleet_daily row failed for %s: %r", title, exc)
                    failed += 1
            for row in mutations:
                title = self._row_title(row)
                try:
                    props = self._mutation_props(row)
                    existing = await self._existing_page(client, title)
                    if existing:
                        r = await client.patch(f"{_API}/pages/{existing}",
                                               headers=self._headers(),
                                               json={"properties": props})
                        patched += 1
                    else:
                        r = await client.post(f"{_API}/pages", headers=self._headers(),
                                              json={"parent": {"database_id": self.db_id},
                                                    "properties": props})
                        wrote += 1
                    r.raise_for_status()
                except Exception as exc:
                    log.warning("fleet_daily mutation failed for %s: %r", title, exc)
                    failed += 1
        return {"trade_days": len(rows), "mutations": len(mutations),
                "wrote": wrote, "patched": patched, "failed": failed, "dry": False}


# -- runner ------------------------------------------------------------------


async def run_once() -> dict:
    """Eén dagelijkse ronde. Leest `EXPORTS_DIR` voor Cash_History én Fills,
    bouwt de rijen op en upsert naar `NOTION_FLEET_DB`. DRY-vrij als token/db
    beide gezet zijn; anders logt hij wat hij zou schrijven en keert terug."""
    exports = os.environ.get("EXPORTS_DIR", "/root/exports")
    skip_raw = (os.environ.get("SKIP_ACCOUNTS") or "").strip()
    skip = [s.strip() for s in skip_raw.split(",") if s.strip()]
    ledgers = load_ledgers(exports, skip=skip)
    cpd = contracts_per_day(exports)
    trade_rows = build_rows(ledgers, contracts=cpd)
    mut_rows = build_mutation_rows(ledgers)
    writer = FleetDailyWriter(os.environ.get("NOTION_TOKEN", ""),
                              os.environ.get("NOTION_FLEET_DB", ""))
    if writer.enabled:
        try:
            import httpx  # noqa: F401
        except ModuleNotFoundError:
            log.error("httpx not installed in THIS interpreter. Run via the venv: "
                      "`.venv/bin/pip install -r requirements.txt` then "
                      "`.venv/bin/python -m app.fleet_daily`.")
            return {"error": "httpx missing (use the venv python)",
                    "trade_days": len(trade_rows), "mutations": len(mut_rows)}
    summary = await writer.upsert(trade_rows, mut_rows)
    log.info("fleet_daily run: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(asyncio.run(run_once()))
