"""One-shot seeder for the LifeOS Accounts DB — exact DD-floor seeds + prefilling bare rows.

account_health *reads* the DD Floor / DD Amount seeds and the account metadata; this writes
them. It runs on the VPS with the same NOTION_TOKEN account_health already uses, so it needs
no interactive approval and is versioned + repeatable.

  - Floor seeds (funded): the exact Tradovate risk-grid floor, so the survival buffer matches
    to the cent (captures intraday peaks our realized fills miss).
  - Prefills (bare rows): Prop Firm / size / starting / rule / status so the account computes
    at all (Current Balance = Starting + Net PnL rollup) instead of showing a bare net.

DRY by default (prints the plan). Set SEED_APPLY=1 to write. After applying, run account_health
(or wait for its timer) so the buffers recompute from the fresh seeds.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("mex.seed")

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"
_ACCOUNTS_DB = os.environ.get("NOTION_ACCOUNTS_DB", "1ddb61ea444d8119aea2fd0d11de4493")

_SELECT = {"Prop Firm", "Drawdown Rule", "Status"}     # everything else is a number

# account title -> properties to set. Floors are the exact Tradovate DRAWDOWN AUTO values.
SEEDS: dict[str, dict] = {
    # funded floor seeds (metadata already present)
    "PAAPEX2700250000013": {"DD Floor $": 50100.00, "DD Amount $": 2500},
    "PAAPEX2700250000015": {"DD Floor $": 49897.60, "DD Amount $": 2500},
    "PAAPEX2700250000016": {"DD Floor $": 50100.00, "DD Amount $": 2500},
    "PAAPEX2700250000017": {"DD Floor $": 48553.15, "DD Amount $": 2500},
    "PAAPEX2700250000018": {"DD Floor $": 50100.00, "DD Amount $": 2500},
    # prefill bare rows (+ floor where known exactly)
    "PAAPEX2700250000021": {"Prop Firm": "Apex Trader Funding", "Account Size": 50000,
                            "Starting Balance": 50000, "Drawdown Rule": "Trailing Equity Peak",
                            "Status": "Funded Account", "DD Amount $": 2500, "DD Floor $": 47939.98},
    "APEX27002500000214": {"Prop Firm": "Apex Trader Funding", "Account Size": 50000,
                           "Starting Balance": 50000, "Drawdown Rule": "Trailing Equity Peak",
                           "Status": "Active Eval", "DD Amount $": 2500, "DD Floor $": 50534.50},
    "APEX27002500000213": {"Prop Firm": "Apex Trader Funding", "Account Size": 50000,
                           "Starting Balance": 50000, "Drawdown Rule": "Trailing Equity Peak",
                           "Status": "Active Eval", "DD Amount $": 2500},
    # 209 deliberately omitted — incomplete Fills export; seed after a full re-export.
}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Notion-Version": _VER, "Content-Type": "application/json"}


def _title(prop) -> str:
    try:
        return "".join(t["plain_text"] for t in prop["title"])
    except Exception:
        return ""


def to_property(key: str, value):
    """Map a plain value to the Notion property payload for its type."""
    if key in _SELECT:
        return {"select": {"name": value}}
    return {"number": value}


async def run() -> dict:
    apply = os.environ.get("SEED_APPLY") == "1"
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        log.error("NOTION_TOKEN unset — nothing to do.")
        return {"error": "no token"}
    import httpx
    throttle = float(os.environ.get("NOTION_THROTTLE_S", "0.34"))

    # title -> page id
    pages: dict[str, str] = {}
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
                pages[_title(page.get("properties", {}).get("Account ID"))] = page["id"]
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        summary = {"written": 0, "missing": 0, "apply": apply}
        for acct, fields in SEEDS.items():
            pid = pages.get(acct)
            if not pid:
                summary["missing"] += 1
                log.warning("account not found in DB: %s", acct)
                continue
            props = {k: to_property(k, v) for k, v in fields.items()}
            plan = ", ".join(f"{k}={v}" for k, v in fields.items())
            log.info("%s ← %s%s", acct, plan, "" if apply else "  [DRY]")
            if not apply:
                continue
            pr = await client.patch(f"{_API}/pages/{pid}", headers=_headers(token),
                                    json={"properties": props})
            pr.raise_for_status()
            summary["written"] += 1
            if throttle:
                await asyncio.sleep(throttle)
    log.info("seed run: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(asyncio.run(run()))
