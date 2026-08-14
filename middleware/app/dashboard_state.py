"""Command-center state — the reconciled fleet view behind app.mex-traders.com.

Two robust, server-side sources (no browser, no Notion paging of 700 trades):

  ACCOUNTS  → the LifeOS Accounts DB (small, ~20 rows). account_health already materialises
              Current Balance / DD Floor / DD Buffer / Health there every 5 min, so we just
              read that one query. NOTION_TOKEN unset → accounts omitted (assets still work).
  ASSETS    → the local Tradovate Fills export, paired with the SAME fills_pairing the journal
              uses (real commissions). Deduped on trade key so overlapping exports never double
              count. Rolled up per asset (GC/ES/NQ/YM) → net, ticks, win-rate, count.

Fleet / firm / strategy cuts derive from those. Result is cached (DASH_TTL_S, default 60s) so
the 10-second dashboard poll stays cheap. Shape matches the front-end in viewer.py 1:1.
"""
from __future__ import annotations

import datetime as dt
import glob
import logging
import os
import time
from collections import defaultdict

from .fills_pairing import parse_fills_csv, pair_fills

log = logging.getLogger("mex.dashboard")

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"
_ACCOUNTS_DB = os.environ.get("NOTION_ACCOUNTS_DB", "1ddb61ea444d8119aea2fd0d11de4493")

# product root -> display asset · engine family · funded-edge flag
_ROOT2ASSET = {"GC": "GC", "MGC": "GC", "ES": "ES", "MES": "ES",
               "NQ": "NQ", "MNQ": "NQ", "YM": "YM", "MYM": "YM",
               "RTY": "RTY", "M2K": "RTY", "CL": "CL", "MCL": "CL"}
_ENGINE = {"GC": "El Tesoro / El Minero", "ES": "El Rey / El León",
           "NQ": "El Toro / Matador / Dorado / Patrón", "YM": "El Yankee"}
_FUNDED_EDGE = {"GC", "ES"}          # validated funded edges; NQ/YM = eval-only variance
_EDGE_LABEL = {"GC": "Funded workhorse", "ES": "Cleanest OOS",
               "NQ": "Variance-lottery (eval)", "YM": "Variance-lottery (eval)"}

_HEALTH_RANK = {"Healthy": 5, "Watch": 4, "Warning": 3, "Critical": 2, "Breached": 1}


# ---- Notion accounts -----------------------------------------------------------------

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


def _phase(account: str) -> str:
    return "Funded" if account.upper().startswith(("PA", "PAAPEX")) else "Eval"


def _load_accounts(token: str) -> list[dict]:
    import httpx
    out: list[dict] = []
    with httpx.Client(timeout=15.0) as client:
        cursor = None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            r = client.post(f"{_API}/databases/{_ACCOUNTS_DB}/query", headers=_headers(token), json=body)
            r.raise_for_status()
            data = r.json()
            for page in data.get("results", []):
                p = page.get("properties", {})
                if _checkbox(p.get("Archived")):
                    continue
                full = _title(p.get("Account ID"))
                current = _num(p.get("Current Balance"))
                if current is None:
                    continue                      # bare row — nothing to show yet
                buffer = _num(p.get("DD Buffer $"))
                seed = _num(p.get("DD Floor $"))
                health = _sel(p.get("Health")) or "—"
                out.append({
                    "id": full[-3:] or full, "full": full,
                    "firm": (_sel(p.get("Prop Firm")) or "—"),
                    "stage": _phase(full),
                    "current": round(current, 2),
                    "buffer": None if buffer is None else round(buffer, 2),
                    "floor": None if buffer is None else round(current - buffer, 2),
                    "bufpct": _num(p.get("DD Buffer %")),
                    "net": _num(p.get("Net PnL")),
                    "health": health, "seed": seed is not None,
                    "hrank": _HEALTH_RANK.get(health, 0) * 1000 + (_num(p.get("DD Buffer %")) or -999),
                })
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
    out.sort(key=lambda a: a["hrank"])            # worst first (attention up top)
    return out


# ---- local fills -> asset rollup -----------------------------------------------------

def _load_asset_rollup(exports: str, skip: list[str]) -> tuple[list[dict], dict]:
    seen: set[tuple] = set()
    agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "net": 0.0, "ticks": 0.0})
    for path in sorted(glob.glob(os.path.join(exports, "*Fills*.csv"))):
        try:
            fills = parse_fills_csv(path)
        except Exception as exc:
            log.warning("dashboard: failed to parse %s: %r", path, exc)
            continue
        for t in pair_fills(fills):
            if any(s in t.account for s in skip):
                continue
            key = (t.account, t.buy_fill_id, t.sell_fill_id)
            if key in seen:
                continue                          # overlapping exports → count once
            seen.add(key)
            sym = _ROOT2ASSET.get(t.product.upper(), t.product.upper())
            net = round(t.gross_pnl - t.commissions, 2)
            move = (t.exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - t.exit_price)
            ticks = round(move / t.tick_size) if t.tick_size else 0
            a = agg[sym]
            a["n"] += 1
            a["wins"] += 1 if net > 0 else 0
            a["net"] = round(a["net"] + net, 2)
            a["ticks"] += ticks

    assets = []
    for sym, a in agg.items():
        assets.append({
            "sym": sym, "engine": _ENGINE.get(sym, "—"),
            "n": a["n"], "wins": a["wins"],
            "win": round(100 * a["wins"] / a["n"], 1) if a["n"] else 0.0,
            "ticks": int(a["ticks"]), "net": a["net"],
            "robust": sym in _FUNDED_EDGE, "edge": _EDGE_LABEL.get(sym, "—"),
            "cls": {"GC": "gc", "ES": "es"}.get(sym, "nq"),
        })
    assets.sort(key=lambda x: -x["net"])
    totals = {
        "net": round(sum(x["net"] for x in assets), 2),
        "n": sum(x["n"] for x in assets),
        "wins": sum(x["wins"] for x in assets),
    }
    return assets, totals


# ---- assemble ------------------------------------------------------------------------

def _build() -> dict:
    token = os.environ.get("NOTION_TOKEN", "")
    exports = os.environ.get("EXPORTS_DIR", "/root/exports")
    skip = [s.strip() for s in os.environ.get("DASH_SKIP", "").split(",") if s.strip()]

    accounts: list[dict] = []
    if token:
        try:
            accounts = _load_accounts(token)
        except Exception as exc:
            log.warning("dashboard: accounts load failed: %r", exc)

    assets, atot = _load_asset_rollup(exports, skip)

    funded_net = round(sum(a["net"] or 0 for a in accounts if a["stage"] == "Funded"), 2)
    fleet_buffer = round(sum(a["buffer"] for a in accounts if a["buffer"] and a["buffer"] > 0), 2)
    breached = sum(1 for a in accounts if a["health"] == "Breached")
    best = assets[0] if assets else None

    # firm rollup
    firms: dict[str, dict] = defaultdict(lambda: {"accts": 0, "net": 0.0, "buffer": 0.0})
    for a in accounts:
        f = firms[a["firm"]]
        f["accts"] += 1
        f["net"] = round(f["net"] + (a["net"] or 0), 2)
        if a["buffer"] and a["buffer"] > 0:
            f["buffer"] = round(f["buffer"] + a["buffer"], 2)
    firm_rows = [{"name": k, "accts": v["accts"], "net": v["net"],
                  "buffer": v["buffer"] or None} for k, v in firms.items()]
    firm_rows.sort(key=lambda x: -x["net"])

    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fleet": {
            "realized_net": atot["net"],
            "funded_net": funded_net,
            "survival_buffer": fleet_buffer,
            "accounts": len(accounts),
            "breached": breached,
            "trades": atot["n"],
            "win_rate": round(100 * atot["wins"] / atot["n"], 1) if atot["n"] else None,
            "best_asset": best["sym"] if best else None,
            "best_asset_net": best["net"] if best else None,
        },
        "accounts": accounts,
        "assets": assets,
        "firms": firm_rows,
    }


_cache: dict = {"t": 0.0, "data": None}


def command_state() -> dict:
    ttl = float(os.environ.get("DASH_TTL_S", "60"))
    now = time.monotonic()
    if _cache["data"] is not None and (now - _cache["t"]) < ttl:
        return _cache["data"]
    data = _build()
    _cache.update(t=now, data=data)
    return data


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(command_state(), indent=2))
