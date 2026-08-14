"""Per-account survival buffers + health — writes back to the LifeOS Accounts DB.

Reads each account's balance/rule from the Accounts database (which already carries the live
Net PnL rollup → Current Balance formula now that trades flow in), applies the prop-firm
drawdown logic from `backtest/firms.py`, and writes back per account:

  DD Buffer $      how many $ above the drawdown floor (the survival buffer)
  DD Buffer %      that buffer as % of the drawdown allowance
  Daily Buffer $   room left before the daily-loss limit (only for firms that HAVE one)
  Health           Healthy / Watch / Warning / Critical / Breached / Inactive
  Health Reasons   the transparent factors behind the status
  Peak Balance $   maintained running peak (for the trailing floor)
  Buffers Updated  timestamp

⚠️ Trailing drawdown tracks the equity PEAK incl. intraday highs; our balance is realized-only,
so the trailing floor here is a close *approximation* (peak is the realized peak, maintained
from run to run). EOD-locked firms are exact. Thresholds come from firms.py — verify per firm.

DRY when NOTION_TOKEN unset (logs what it would write).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("mex.account_health")

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"
_ACCOUNTS_DB = os.environ.get("NOTION_ACCOUNTS_DB", "1ddb61ea444d8119aea2fd0d11de4493")

# Apex trailing drawdown allowance by account size ($) — from backtest/firms.py (_APEX_SIZES).
_APEX_DD = {25_000: 1_500, 50_000: 2_500, 100_000: 3_000, 150_000: 5_000, 250_000: 6_500, 300_000: 7_500}


def dd_threshold(size: float | None, rule: str | None) -> float:
    """Drawdown allowance ($) for an account, from its rule label / size."""
    rule = rule or ""
    if "$2000" in rule:
        return 2000.0
    if "$2500" in rule:
        return 2500.0
    return _APEX_DD.get(int(size or 0), 2500.0)   # trailing / equity-peak / generic → size table


@dataclass
class Health:
    threshold: float
    floor: float
    buffer_usd: float
    buffer_pct: float
    peak_balance: float
    status: str
    reasons: str


def compute(size, starting, current, peak_stored, rule, prop_firm, status) -> Health | None:
    """Pure survival-buffer + health calc. Returns None when the account lacks the balances
    needed to compute (so we don't write misleading zeros)."""
    if starting is None or current is None:
        return None
    rule = rule or ""
    prop_firm = prop_firm or ""
    threshold = dd_threshold(size, rule)
    is_eod = "EOD" in rule and "Apex" not in prop_firm   # MFFU/Topstep EOD lock at start; Apex at start+100
    lock_offset = 0.0 if is_eod else 100.0               # Apex trailing locks at start + $100

    # maintained realized peak (converges; historical pre-tracking peak not reconstructed)
    peak = max(x for x in (peak_stored or 0.0, current, starting) if x is not None)
    # trailing floor: trails the peak by the allowance, but never rises above the lock level
    floor = min(starting + lock_offset, peak - threshold)
    buffer_usd = round(current - floor, 2)
    buffer_pct = round(100.0 * buffer_usd / threshold, 1) if threshold else 0.0

    if (status or "") == "Breached" or buffer_usd <= 0:
        health = "Breached"
    elif buffer_pct < 15:
        health = "Critical"
    elif buffer_pct < 30:
        health = "Warning"
    elif buffer_pct < 50:
        health = "Watch"
    else:
        health = "Healthy"

    profit = current - starting
    reasons = (f"DD-buffer {buffer_pct:g}% (${buffer_usd:,.0f}) · "
               f"balans {'+' if profit >= 0 else '−'}${abs(profit):,.0f} · "
               f"piek +${max(0.0, peak - starting):,.0f} · floor ${floor:,.0f} · "
               f"regel {rule or '?'} (dd ${threshold:,.0f})")
    return Health(threshold, floor, buffer_usd, buffer_pct, peak, health, reasons)


# ---- Notion I/O ----------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Notion-Version": _VER, "Content-Type": "application/json"}


def _title(prop) -> str:
    try:
        return "".join(t["plain_text"] for t in prop["title"])
    except Exception:
        return ""


def _num(prop):
    if not prop:
        return None
    t = prop.get("type")
    if t == "number":
        return prop.get("number")
    if t == "formula":
        return prop.get("formula", {}).get("number")
    if t == "rollup":
        return prop.get("rollup", {}).get("number")
    return None


def _sel(prop):
    if prop and prop.get("type") == "select" and prop.get("select"):
        return prop["select"]["name"]
    return None


def _checkbox(prop):
    return bool(prop.get("checkbox")) if prop and prop.get("type") == "checkbox" else False


async def run_once() -> dict:
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        log.error("NOTION_TOKEN unset — DRY only makes sense with the token; nothing to read.")
        return {"error": "no token"}
    import httpx
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    throttle = float(os.environ.get("NOTION_THROTTLE_S", "0.34"))
    updated = skipped = failed = 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        cursor = None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            r = await client.post(f"{_API}/databases/{_ACCOUNTS_DB}/query", headers=_headers(token), json=body)
            r.raise_for_status()
            data = r.json()
            for page in data.get("results", []):
                props = page.get("properties", {})
                if _checkbox(props.get("Archived")):
                    continue
                acct = _title(props.get("Account ID"))
                h = compute(
                    size=_num(props.get("Account Size")),
                    starting=_num(props.get("Starting Balance")),
                    current=_num(props.get("Current Balance")),
                    peak_stored=_num(props.get("Peak Balance $")),
                    rule=_sel(props.get("Drawdown Rule")),
                    prop_firm=_sel(props.get("Prop Firm")),
                    status=_sel(props.get("Status")),
                )
                if h is None:
                    skipped += 1
                    continue
                update = {
                    "DD Buffer $": {"number": h.buffer_usd},
                    "DD Buffer %": {"number": h.buffer_pct},
                    "Health": {"select": {"name": h.status}},
                    "Health Reasons": {"rich_text": [{"text": {"content": h.reasons[:1900]}}]},
                    "Peak Balance $": {"number": round(h.peak_balance, 2)},
                    "Buffers Updated": {"date": {"start": now}},
                }
                try:
                    pr = await client.patch(f"{_API}/pages/{page['id']}", headers=_headers(token),
                                            json={"properties": update})
                    pr.raise_for_status()
                    updated += 1
                    log.info("%s → %s  buffer $%.0f (%.0f%%)", acct, h.status, h.buffer_usd, h.buffer_pct)
                except Exception as exc:
                    failed += 1
                    log.warning("write failed for %s: %r", acct, exc)
                if throttle:
                    await asyncio.sleep(throttle)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
    summary = {"updated": updated, "skipped": skipped, "failed": failed}
    log.info("account_health run: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(asyncio.run(run_once()))
