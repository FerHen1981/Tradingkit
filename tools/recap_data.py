#!/usr/bin/env python3
"""Zet de audit-log van de middleware om in de feiten voor de dagrecap.

De trechter schrijft elk binnengekomen bericht weg in
`routed_<YYYYMMDD>.jsonl`. Daar staat de hele handelsdag in — entries, exits,
guards, halts — inclusief de Discord-omschrijvingen waar de bedragen in staan.
Dit script leest die en levert de cijfers waar de recap op leunt, zodat die
niet met de hand uit Discord geplukt hoeven worden.

    tools/recap_data.py routed_20260811.jsonl
    tools/recap_data.py routed_20260811.jsonl --json   # machineleesbaar

Bewust géén oordeel: dit telt alleen wat er gebeurd is. De duiding hoort in de
recap zelf, en die schrijf je pas als de cijfers kloppen.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

ET = timezone(timedelta(hours=-4))          # EDT; in de winter -5

EVENTS = [("CONFIG", "config"), ("ACCOUNT STARTED", "start"), ("ACCOUNT HALT", "acct_halt"),
          ("DAY HALT", "day_halt"), ("LIMIT EXPIRED", "expired"), ("SIGNAL BLOCKED", "blocked"),
          ("AUTO FLAT", "auto_flat"), ("FILL", "fill"), ("EXIT", "exit"),
          ("RISK OFF", "risk_off"), ("TRAIL", "trail"), ("DERISK", "derisk"),
          ("PAYOUT", "payout"), ("PASSED", "passed"), ("FAILED", "failed"),
          ("LIMIT", "limit"), ("MARKET", "market")]


def classify(title: str) -> str:
    t = title.upper()
    for needle, tag in EVENTS:
        if needle in t:
            return tag
    return "overig"


def money(s: str):
    m = re.search(r"PnL\s*([+-])\$([\d.,]+)", s)
    if not m:
        return None
    v = float(m.group(2).replace(",", ""))
    return -v if m.group(1) == "-" else v


def parse(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") not in ("discord", "discord-card"):
                rows.append({"kind": r.get("kind"), "ts": r.get("ts"), "raw": r})
                continue
            if r.get("kind") == "discord-card":
                continue                     # uitgaande kaart; het inkomende bericht telt
            try:
                em = json.loads(r["body"])["embeds"][0]
            except Exception:
                continue
            desc = str(em.get("description", "")).replace("\\n", "\n")
            title = str(em.get("title", ""))
            acct = re.search(r"\b([A-Z]{2}\d{3}-\d+k-\d+)\b", desc)
            rows.append({
                "kind": "event", "ts": r.get("ts"), "event": classify(title),
                "asset": (em.get("footer", {}) or {}).get("text", ""),
                "account": acct.group(1) if acct else "",
                "pnl": money(desc), "title": title, "desc": desc,
            })
    return rows


def et(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET).strftime("%H:%M:%S")
    except Exception:
        return "??:??:??"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = parse(a.logfile)
    ev = [r for r in rows if r["kind"] == "event"]
    if not ev:
        print("Geen events in dit logbestand — draaide de trechter wel?", file=sys.stderr)
        return 1

    counts = defaultdict(int)
    for r in ev:
        counts[r["event"]] += 1

    exits = [r for r in ev if r["event"] == "exit" and r["pnl"] is not None]
    per_acct = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
    for r in exits:
        k = r["account"] or r["asset"] or "onbekend"
        per_acct[k]["n"] += 1
        per_acct[k]["pnl"] += r["pnl"]
        per_acct[k]["wins"] += 1 if r["pnl"] > 0 else 0

    total = sum(v["pnl"] for v in per_acct.values())
    wins = sum(v["wins"] for v in per_acct.values())
    n = sum(v["n"] for v in per_acct.values())
    gross_w = sum(r["pnl"] for r in exits if r["pnl"] > 0)
    gross_l = -sum(r["pnl"] for r in exits if r["pnl"] < 0)

    summary = {
        "bestand": a.logfile,
        "events_totaal": len(ev),
        "per_event": dict(sorted(counts.items(), key=lambda x: -x[1])),
        "afgesloten_trades": n,
        "netto": round(total, 2),
        "winrate_pct": round(100 * wins / n, 1) if n else None,
        "profit_factor": round(gross_w / gross_l, 2) if gross_l else None,
        "per_account": {k: {"trades": v["n"], "netto": round(v["pnl"], 2),
                            "winrate_pct": round(100 * v["wins"] / v["n"], 1)}
                        for k, v in sorted(per_acct.items())},
        "guards": {k: counts[k] for k in ("day_halt", "acct_halt", "blocked", "derisk", "auto_flat")
                   if counts.get(k)},
    }

    if a.json:
        print(json.dumps(summary, indent=1, ensure_ascii=False))
        return 0

    print(f"\n=== RECAP-DATA  {a.logfile} ===\n")
    print(f"Events: {len(ev)}   ", " · ".join(f"{k} {v}" for k, v in summary["per_event"].items()))
    print(f"\nAfgesloten trades: {n}   netto ${total:,.2f}   "
          f"winrate {summary['winrate_pct']}%   PF {summary['profit_factor']}")
    if summary["guards"]:
        print("Guards:", " · ".join(f"{k}={v}" for k, v in summary["guards"].items()))

    print("\nPer account:")
    for k, v in summary["per_account"].items():
        print(f"  {k:<22} {v['trades']:>3} trades   ${v['netto']:>10,.2f}   {v['winrate_pct']:>5}% wr")

    print("\nTijdlijn (ET):")
    for r in ev:
        tag = f"{r['pnl']:+.2f}" if r["pnl"] is not None else ""
        print(f"  {et(r['ts'])}  {r['event']:<10} {r['asset']:<8} {r['account']:<20} {tag}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
