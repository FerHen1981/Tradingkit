"""Command-center state — the reconciled fleet view behind app.mex-traders.com.

Two robust, server-side sources (no browser, no Notion paging of 700 trades):

  ACCOUNTS  → the LifeOS Accounts DB (small, ~20 rows). account_health already materialises
              Current Balance / DD Floor / DD Buffer / Health there every 5 min, so we just
              read that one query. NOTION_TOKEN unset → accounts omitted (assets still work).
  TRADES    → the local Tradovate Fills export, paired with the SAME fills_pairing the journal
              uses (real commissions). Deduped on trade key so overlapping exports never double
              count. Each carries its ET close-date so P&L can be sliced by timeframe.

The P&L cuts (fleet / firm / strategy / asset, and each account's Net P&L) are filtered to a
timeframe window — day / week / month / quarter / rolling / all. The survival buffers are
point-in-time state and never window (an account's cushion is whatever it is *now*).

Trades and accounts are cached (DASH_TTL_S, default 60s); windows re-aggregate the cached
trades cheaply. Shape matches the front-end in viewer.py 1:1.
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

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:                                    # pragma: no cover - tzdata missing
    _ET = dt.timezone(dt.timedelta(hours=-4))

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

# tick size per product root — to score ticks on routed-log trades (which carry only prices)
_TICK = {"GC": 0.1, "MGC": 0.1, "ES": 0.25, "MES": 0.25, "NQ": 0.25, "MNQ": 0.25,
         "YM": 1.0, "MYM": 1.0, "RTY": 0.1, "M2K": 0.1, "CL": 0.01, "MCL": 0.01}

WINDOWS = ("day", "week", "month", "quarter", "rolling", "all")
_WINDOW_LABEL = {"day": "Today", "week": "This week", "month": "This month",
                 "quarter": "This quarter", "rolling": "Rolling 30d", "all": "All time"}


# ---- timeframe -----------------------------------------------------------------------

def _window_start(window: str, today: dt.date) -> dt.date | None:
    """Inclusive start date (ET) for the window, or None for 'all'."""
    if window == "day":
        return today
    if window == "week":
        return today - dt.timedelta(days=today.weekday())      # Monday
    if window == "month":
        return today.replace(day=1)
    if window == "quarter":
        qm = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=qm, day=1)
    if window == "rolling":
        return today - dt.timedelta(days=30)
    return None                                                # all


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
                starting = _num(p.get("Starting Balance"))
                current = _num(p.get("Current Balance"))
                if starting is None or current is None:
                    continue                      # bare / unconfigured row — hide it
                buffer = _num(p.get("DD Buffer $"))
                seed = _num(p.get("DD Floor $"))
                health = _sel(p.get("Health")) or "—"
                out.append({
                    "id": full[-3:] or full, "full": full,
                    "firm": (_sel(p.get("Prop Firm")) or "—"),
                    "stage": _phase(full),
                    "current": round(current, 2),
                    "starting": round(starting, 2),
                    "size": _num(p.get("Account Size")),
                    "buffer": None if buffer is None else round(buffer, 2),
                    "floor": None if buffer is None else round(current - buffer, 2),
                    "bufpct": _num(p.get("DD Buffer %")),
                    "net": _num(p.get("Net PnL")),   # ledger truth (rollup), matches Current
                    "health": health, "seed": seed is not None,
                    "hrank": _HEALTH_RANK.get(health, 0) * 1000 + (_num(p.get("DD Buffer %")) or -999),
                })
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
    out.sort(key=lambda a: a["hrank"])            # worst first (attention up top)
    return out


# ---- local fills -> closed trades ----------------------------------------------------

def _load_trades(exports: str, skip: list[str]) -> list[dict]:
    # Gather EVERY fill across all export snapshots and dedup by fill id (overlapping snapshots
    # share the same fills), THEN FIFO-pair once — globally, not per file. Pairing per file
    # mis-attributes any position that opens in one snapshot and closes in another.
    fills_by_id: dict = {}
    for path in sorted(glob.glob(os.path.join(exports, "*Fills*.csv"))):
        try:
            for f in parse_fills_csv(path):
                if any(s in f.account for s in skip):
                    continue
                fills_by_id[f.fill_id] = f
        except Exception as exc:
            log.warning("dashboard: failed to parse %s: %r", path, exc)
    fills = sorted(fills_by_id.values(), key=lambda x: (x.ts, x.fill_id))

    trades: list[dict] = []
    for t in pair_fills(fills):
        sym = _ROOT2ASSET.get(t.product.upper(), t.product.upper())
        net = round(t.gross_pnl - t.commissions, 2)
        move = (t.exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - t.exit_price)
        ticks = round(move / t.tick_size) if t.tick_size else 0
        et = t.exit_ts.astimezone(_ET)
        trades.append({"acct": t.account, "sym": sym, "net": net, "ticks": ticks,
                       "close": et.date(), "hour": et.hour, "dow": et.weekday(),
                       "comm": round(t.commissions, 2), "mfe": None, "mae": None})
    return trades


def _load_routed_trades(routed_dir: str, skip: list[str], after: "dt.date | None") -> list[dict]:
    """Recent closed trades from the executor's routed-log — used only for dates AFTER the
    last reconciled Fills date, so 'today/this week' populate live while history stays exact."""
    from .routed_journal import parse_routed_lines, pair_events, _recent_routed_files
    from .journal_sync import _sym_root
    days = int(os.environ.get("DASH_ROUTED_DAYS", "14"))
    lines: list[str] = []
    for path in _recent_routed_files(routed_dir, days):
        try:
            with open(path, encoding="utf-8") as f:
                lines.extend(f)
        except OSError:
            pass
    if not lines:
        return []
    events, amap = parse_routed_lines(lines)
    out: list[dict] = []
    for t in pair_events(events, amap):
        if not t.closed or t.pnl is None or t.exit_ts is None:
            continue
        if any(s in t.account for s in skip):
            continue
        et = t.exit_ts.astimezone(_ET)
        close = et.date()
        if after is not None and close <= after:
            continue                                 # already covered by the Fills export
        product = _sym_root(t.symbol)
        sym = _ROOT2ASSET.get(product.upper(), product.upper())
        tick = _TICK.get(product.upper()) or _TICK.get(sym, 0)
        if tick and t.entry_price is not None and t.exit_price is not None:
            move = (t.exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - t.exit_price)
            ticks = round(move / tick)
        else:
            ticks = 0
        out.append({"acct": t.account, "sym": sym, "net": round(t.pnl, 2), "ticks": ticks,
                    "close": close, "hour": et.hour, "dow": et.weekday(),
                    "comm": 0.0, "mfe": t.mfe, "mae": t.mae})
    return out


def _aggregate(trades: list[dict], window: str, stage: str = "all") -> dict:
    today = dt.datetime.now(_ET).date()
    start = _window_start(window, today)
    if window == "day":
        rows = [t for t in trades if t["close"] == today]
    elif start is not None:
        rows = [t for t in trades if t["close"] >= start]
    else:
        rows = trades
    if stage in ("funded", "eval"):
        rows = [t for t in rows if _phase(t["acct"]).lower() == stage]

    agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "net": 0.0, "ticks": 0,
                                                "comm": 0.0, "mfe": [], "mae": []})
    acct_net: dict[str, float] = defaultdict(float)
    for t in rows:
        a = agg[t["sym"]]
        a["n"] += 1
        a["wins"] += 1 if t["net"] > 0 else 0
        a["net"] = round(a["net"] + t["net"], 2)
        a["ticks"] += t["ticks"]
        a["comm"] = round(a["comm"] + t.get("comm", 0.0), 2)
        if t.get("mfe") is not None:
            a["mfe"].append(t["mfe"])
        if t.get("mae") is not None:
            a["mae"].append(t["mae"])
        acct_net[t["acct"]] = round(acct_net[t["acct"]] + t["net"], 2)   # full id — 013 collision-safe

    def _avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    assets = []
    for sym, a in agg.items():
        gross = round(a["net"] + a["comm"], 2)
        assets.append({
            "sym": sym, "engine": _ENGINE.get(sym, "—"),
            "n": a["n"], "wins": a["wins"],
            "win": round(100 * a["wins"] / a["n"], 1) if a["n"] else 0.0,
            "ticks": int(a["ticks"]), "net": a["net"],
            "comm": a["comm"], "fees_pct": round(100 * a["comm"] / gross, 1) if gross > 0 else None,
            "mfe": _avg(a["mfe"]), "mae": _avg(a["mae"]),
            "robust": sym in _FUNDED_EDGE, "edge": _EDGE_LABEL.get(sym, "—"),
            "cls": {"GC": "gc", "ES": "es"}.get(sym, "nq"),
        })
    assets.sort(key=lambda x: -x["net"])
    totals = {"net": round(sum(x["net"] for x in assets), 2),
              "n": sum(x["n"] for x in assets),
              "wins": sum(x["wins"] for x in assets),
              "comm": round(sum(x["comm"] for x in assets), 2)}

    # heatmap: net + count per (weekday 0=Mon, hour ET) over the same filtered rows
    hm: dict = defaultdict(lambda: {"net": 0.0, "n": 0})
    for t in rows:
        if t.get("hour") is None or t.get("dow") is None:
            continue
        c = hm[(t["dow"], t["hour"])]
        c["net"] = round(c["net"] + t["net"], 2)
        c["n"] += 1
    heatmap = [{"dow": d, "hour": h, "net": v["net"], "n": v["n"]} for (d, h), v in hm.items()]

    return {"assets": assets, "totals": totals, "acct_net": dict(acct_net), "heatmap": heatmap}


# ---- caches --------------------------------------------------------------------------

_cache: dict = {"t": 0.0, "trades": None, "accounts": None}


def _sources() -> tuple[list[dict], list[dict]]:
    ttl = float(os.environ.get("DASH_TTL_S", "60"))
    now = time.monotonic()
    if _cache["trades"] is not None and (now - _cache["t"]) < ttl:
        return _cache["trades"], _cache["accounts"]

    exports = os.environ.get("EXPORTS_DIR", "/root/exports")
    routed_dir = os.environ.get("ROUTED_DIR", os.environ.get("INTENT_DIR", "/root/intent-store"))
    skip = [s.strip() for s in os.environ.get("DASH_SKIP", "").split(",") if s.strip()]
    trades = _load_trades(exports, skip)
    max_fills = max((t["close"] for t in trades), default=None)     # hand recent days to the live log
    trades = trades + _load_routed_trades(routed_dir, skip, max_fills)

    accounts: list[dict] = []
    token = os.environ.get("NOTION_TOKEN", "")
    if token:
        try:
            accounts = _load_accounts(token)
        except Exception as exc:
            log.warning("dashboard: accounts load failed: %r", exc)

    _cache.update(t=now, trades=trades, accounts=accounts)
    return trades, accounts


# ---- assemble ------------------------------------------------------------------------

def command_state(window: str = "all", stage: str = "all") -> dict:
    window = window if window in WINDOWS else "all"
    stage = stage if stage in ("funded", "eval") else "all"
    trades, accounts_src = _sources()
    ag = _aggregate(trades, window, stage)
    assets, atot = ag["assets"], ag["totals"]

    # accounts: live buffers + ledger Net P&L (from Notion — always matches Current/Tradovate).
    # acct_net (from the trade log) drives the window-scoped performance cards, not this column.
    accounts = [dict(a) for a in accounts_src
                if stage == "all" or a["stage"].lower() == stage]
    funded_net = round(sum((a["net"] or 0.0) for a in accounts if a["stage"] == "Funded"), 2)

    # payout & rules: from each account's ALL-TIME daily realized P&L (window-independent)
    import dataclasses
    from .payout_rules import evaluate as _eval_payout
    daily: dict = defaultdict(lambda: defaultdict(float))
    for t in trades:
        daily[t["acct"]][t["close"]] = round(daily[t["acct"]][t["close"]] + t["net"], 2)
    for a in accounts:
        p = _eval_payout(a.get("size"), a.get("starting"), a.get("current"),
                         a["stage"], dict(daily.get(a["full"], {})))
        a["payout"] = dataclasses.asdict(p) if p else None
    _funded_p = [a["payout"] for a in accounts if a.get("payout") and a["payout"]["stage"] == "Funded"]
    total_withdrawable = round(sum(p["withdrawable"] for p in _funded_p), 2)
    payout_eligible = sum(1 for p in _funded_p if p["eligible"])
    fleet_buffer = round(sum(a["buffer"] for a in accounts if a["buffer"] and a["buffer"] > 0), 2)
    breached = sum(1 for a in accounts if a["health"] == "Breached")
    best = assets[0] if assets else None

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

    # headline = ledger truth (sum of account Net PnL) → reconciles with the accounts table,
    # the firm rollup and Tradovate. The trade-log total (window_net) can include the live
    # routed-log tail (recent days, no commissions) so it only drives the breakdown cards.
    realized_ledger = round(sum((a["net"] or 0.0) for a in accounts), 2)

    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window": window,
        "window_label": _WINDOW_LABEL.get(window, window),
        "windows": list(WINDOWS),
        "stage": stage,
        "fleet": {
            "realized_net": realized_ledger,        # ledger truth — reconciles with firms/Tradovate
            "window_net": atot["net"],              # trade-log over the window (recent days = live est.)
            "funded_net": funded_net,
            "survival_buffer": fleet_buffer,
            "accounts": len(accounts),
            "breached": breached,
            "trades": atot["n"],
            "win_rate": round(100 * atot["wins"] / atot["n"], 1) if atot["n"] else None,
            "best_asset": best["sym"] if best else None,
            "best_asset_net": best["net"] if best else None,
            "fees": atot.get("comm", 0.0),
            "withdrawable": total_withdrawable,
            "payout_eligible": payout_eligible,
        },
        "accounts": accounts,
        "assets": assets,
        "firms": firm_rows,
        "heatmap": ag["heatmap"],
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(command_state(os.environ.get("WINDOW", "all")), indent=2))
