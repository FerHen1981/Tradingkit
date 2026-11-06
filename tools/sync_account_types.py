#!/usr/bin/env python3
"""Enrich the LifeOS **Account Types** database from data/propfirms.json.

One rule set per account TYPE — that is the whole point. The Accounts DB already relates each
account to an Account Type; this script fills that type's row with the rules that belong to the
account and that the owner cannot influence (target, drawdown, consistency, day counters, max
contracts, payout ladder). Everything the owner DOES choose — contracts traded, day cap, daily
loss limit — stays out of here; the Playbook derives those from the actuals.

The link between a row and the registry is the row's ``Firm Program`` select: it holds a program
key from data/propfirms.json. Rows without one are skipped and reported.

Usage:
    NOTION_TOKEN=secret_... python3 tools/sync_account_types.py [--dry-run]

Re-runnable: it writes the same values every time, so running it after a registry change is how
the rules get refreshed. It never touches Name, the Accounts relation, or any rollup.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "data", "propfirms.json")
ACCOUNT_TYPES_DS = "1ddb61ea-444d-8161-aa49-000b1430ae2d"
API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


# --- registry ----------------------------------------------------------------------------------
# No second reader: middleware/app/firm_rules.py already resolves a Notion "Firm Program" family
# plus an account size onto a concrete key in data/propfirms.json, and flattens it. Importing it
# keeps one implementation of that mapping instead of two that can drift.
sys.path.insert(0, os.path.join(ROOT, "middleware"))
from app import firm_rules                                             # noqa: E402


def rules_for(family: str, size) -> tuple:
    """(concrete registry key, the rule columns for one Account Type row)."""
    key = firm_rules.resolve_key(family, size)
    r = firm_rules.rules(key)
    if not r:
        return key, None
    ladder = r.get("payout_ladder") or []
    return key, {
        "Firm": r.get("firm"),
        "Stage": r.get("stage"),
        "Rule Size $": r.get("size"),
        "Profit Target $": r.get("profit_target"),
        "Max Overall Loss $": r.get("drawdown"),
        "Max Daily Loss $": r.get("max_daily_loss"),
        "Drawdown Type": r.get("drawdown_type"),
        "Consistency %": (None if r.get("consistency") is None else round(100 * r["consistency"])),
        "Min Trading Days": r.get("min_days"),
        "Profitable Days": r.get("profit_days") or None,
        "Qualifying Day $": r.get("profit_day_min"),
        "Max Contracts": r.get("max_position"),
        "Min Payout $": r.get("min_payout"),
        "Safety Net Payouts": r.get("safety_net_payouts"),
        "Payout Ladder": " · ".join(f"${x:,.0f}" for x in ladder) if ladder else None,
        "Converts To": r.get("converts_to"),
        "Rules As Of": r.get("notes") or "",
        "Rules Verified": bool(r.get("verified")),
    }


# --- Notion ------------------------------------------------------------------------------------

def call(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Notion-Version": VERSION,
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:                       # surface Notion's own message
        raise SystemExit(f"Notion {method} {path} → {e.code}: {e.read().decode()[:400]}")


def rows(token: str) -> list:
    out, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        page = call(token, "POST", f"/databases/{ACCOUNT_TYPES_DS}/query", body)
        out += page.get("results", [])
        if not page.get("has_more"):
            return out
        cursor = page.get("next_cursor")


def prop_value(props: dict, name: str):
    p = props.get(name) or {}
    kind = p.get("type")
    if kind == "select":
        return (p.get("select") or {}).get("name")
    if kind == "number":
        return p.get("number")
    if kind == "title":
        return "".join(x.get("plain_text", "") for x in p.get("title") or [])
    return None


def payload(values: dict) -> dict:
    """Rule columns → Notion property payload. None clears the field, so a rule the registry
    does not have shows as empty rather than as a stale number."""
    out = {}
    for name, v in values.items():
        if name in ("Firm", "Drawdown Type", "Payout Ladder", "Rules As Of", "Converts To"):
            out[name] = {"rich_text": [{"text": {"content": str(v)}}] if v else []}
        elif name == "Stage":
            out[name] = {"select": {"name": v} if v else None}
        elif name == "Rules Verified":
            out[name] = {"checkbox": bool(v)}
        else:
            out[name] = {"number": None if v is None else float(v)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print what would change, write nothing")
    args = ap.parse_args()
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("NOTION_TOKEN is not set", file=sys.stderr)
        return 2

    synced = skipped = unknown = 0
    for page in rows(token):
        props = page.get("properties", {})
        name = prop_value(props, "Name") or page["id"]
        family = prop_value(props, "Firm Program")
        if not family:
            print(f"skip    {name}: no Firm Program set")
            skipped += 1
            continue
        key, values = rules_for(family, prop_value(props, "Rule Size $"))
        if not values:
            print(f"UNKNOWN {name}: '{family}' (size {prop_value(props, 'Rule Size $')}) "
                  f"resolves to {key!r}, which is not in data/propfirms.json")
            unknown += 1
            continue
        print(f"sync    {name} ← {key} "
              f"(target ${values['Profit Target $'] or 0:,.0f} · dd ${values['Max Overall Loss $'] or 0:,.0f}"
              f" · cons {values['Consistency %'] or '—'}%"
              f" · days {values['Min Trading Days'] or 0}/{values['Profitable Days'] or 0})")
        if not args.dry_run:
            call(token, "PATCH", f"/pages/{page['id']}", {"properties": payload(values)})
        synced += 1
    print(f"\n{synced} synced · {skipped} without a Firm Program · {unknown} unknown key(s)")
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
