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

# product root -> (label, market, is_micro, engine, funded_edge, edge_label, cls). Kept at the
# ACTUAL traded product so micro (MGC/MES = funded) and full-size (GC/ES = eval) stay distinct.
# Extend this one table to add a market/contract; nothing else needs to change.
_PRODUCT = {
    "MGC": ("MGC", "Gold", True,  "El Tesoro — MGC",  True,  "Funded workhorse",  "gc"),
    "GC":  ("GC",  "Gold", False, "El Minero — GC",   False, "Eval (full-size)",  "gc"),
    "MES": ("MES", "ES",   True,  "El Rey — MES",     True,  "Cleanest OOS",      "es"),
    "ES":  ("ES",  "ES",   False, "El León — ES",     False, "Eval (full-size)",  "es"),
    "MNQ": ("MNQ", "NQ",   True,  "El Toro / Matador / Dorado / Patrón", False, "Variance (eval)", "nq"),
    "NQ":  ("NQ",  "NQ",   False, "El Toro / Matador / Dorado / Patrón", False, "Variance (eval)", "nq"),
    "MYM": ("MYM", "YM",   True,  "El Yankee — YM",   False, "Variance (eval)",   "nq"),
    "YM":  ("YM",  "YM",   False, "El Yankee — YM",   False, "Variance (eval)",   "nq"),
    "RTY": ("RTY", "RTY",  False, "—", False, "—", "nq"), "M2K": ("M2K", "RTY", True, "—", False, "—", "nq"),
    "CL":  ("CL",  "CL",   False, "—", False, "—", "nq"), "MCL": ("MCL", "CL",  True, "—", False, "—", "nq"),
}


def _prod(root: str) -> tuple:
    r = (root or "").upper()
    return _PRODUCT.get(r, (r, r, False, "—", False, "—", "nq"))

_HEALTH_RANK = {"Healthy": 5, "Watch": 4, "Warning": 3, "Critical": 2, "Breached": 1}

# tick size per product root — to score ticks on routed-log trades (which carry only prices)
_TICK = {"GC": 0.1, "MGC": 0.1, "ES": 0.25, "MES": 0.25, "NQ": 0.25, "MNQ": 0.25,
         "YM": 1.0, "MYM": 1.0, "RTY": 0.1, "M2K": 0.1, "CL": 0.01, "MCL": 0.01}

WINDOWS = ("day", "week", "month", "quarter", "rolling", "all")
_WINDOW_LABEL = {"day": "Last trading day", "week": "This week", "month": "This month",
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
                    # --- payout-playbook inputs (all owner-maintained in the Accounts DB) ---
                    "payouts_taken": _num(p.get("Payouts (0-6)")),   # ladder rung already taken (0-6)
                    "fase_config": _sel(p.get("Fase Config")),       # e.g. "Milking (2c/day-trail $150)"
                    "pos_band": _sel(p.get("Position Size")),        # e.g. "2-4 contracts"
                    "dd_rule": _sel(p.get("Drawdown Rule")),         # Trailing / EOD ($2500) / ...
                    "daily_buffer": _num(p.get("Daily Buffer $")),
                    "dd_amount": _num(p.get("DD Amount $")),
                    "status": _sel(p.get("Status")),                 # Active Eval / Funded / Milking / ...
                    "payout_total": _num(p.get("Payout Total ($)")),
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
        p = _prod(t.product)
        net = round(t.gross_pnl - t.commissions, 2)
        move = (t.exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - t.exit_price)
        ticks = round(move / t.tick_size) if t.tick_size else 0
        et = t.exit_ts.astimezone(_ET)
        trades.append({"acct": t.account, "sym": p[0], "strat": p[3], "net": net, "ticks": ticks,
                       "close": et.date(), "hour": et.hour, "dow": et.weekday(),
                       "comm": round(t.commissions, 2), "mfe": None, "mae": None})
    return trades


def _pearson(x: list[float], y: list[float]) -> "float | None":
    """Pearson correlation, or None when it's undefined (n<2 or a flat series)."""
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    if vx <= 0 or vy <= 0:
        return None
    return round(cov / ((vx * vy) ** 0.5), 2)


def _hm_cells(rows: list[dict]) -> list[dict]:
    """weekday × hour net+count cells for a slice of trades."""
    hm: dict = defaultdict(lambda: {"net": 0.0, "n": 0})
    for t in rows:
        if t.get("hour") is None or t.get("dow") is None:
            continue
        c = hm[(t["dow"], t["hour"])]
        c["net"] = round(c["net"] + t["net"], 2)
        c["n"] += 1
    return [{"dow": d, "hour": h, "net": v["net"], "n": v["n"]} for (d, h), v in hm.items()]


def _day_cells(rows: list[dict]) -> dict:
    """{date-iso: {net, n}} for a slice of trades."""
    d: dict = defaultdict(lambda: {"net": 0.0, "n": 0})
    for t in rows:
        c = d[t["close"].isoformat()]
        c["net"] = round(c["net"] + t["net"], 2)
        c["n"] += 1
    return {k: dict(v) for k, v in d.items()}


def _stats(rows: list[dict]) -> dict:
    """The CIO metric set for any slice of trades: PF, win%, expectancy, avg win/loss, heat."""
    n = len(rows)
    gw = round(sum(t["net"] for t in rows if t["net"] > 0), 2)
    gl = round(-sum(t["net"] for t in rows if t["net"] < 0), 2)
    wins = sum(1 for t in rows if t["net"] > 0)
    losers = sum(1 for t in rows if t["net"] < 0)
    net = round(sum(t["net"] for t in rows), 2)
    maes = [t["mae"] for t in rows if t.get("mae") is not None]
    return {
        "n": n, "wins": wins,
        "win_pct": round(100 * wins / n, 1) if n else 0.0,
        "net": net, "gross_win": gw, "gross_loss": gl,
        "pf": round(gw / gl, 2) if gl > 0 else (None if gw == 0 else 99.99),
        "expectancy": round(net / n, 2) if n else 0.0,
        "avg_win": round(gw / wins, 2) if wins else 0.0,
        "avg_loss": round(gl / losers, 2) if losers else 0.0,
        "heat": round(sum(maes) / len(maes), 1) if maes else None,   # avg MAE ticks
    }


_SEV = {"critical": 0, "warning": 1, "info": 2}


def _attention(accounts: list[dict]) -> tuple:
    """Ranked 'needs attention now' signals: breach risk, thin buffers, consistency, payout-ready."""
    items: list = []

    def flag(a, sev, title, detail):
        items.append({"sev": sev, "account": a["id"], "firm": a["firm"], "title": title, "detail": detail})

    for a in accounts:
        bp, health, pay = a.get("bufpct"), a.get("health"), (a.get("payout") or {})
        if health == "Breached":
            flag(a, "critical", "Breached", f"buffer {bp:.0f}%" if bp is not None else "below floor")
        elif bp is not None and bp < 15:
            flag(a, "critical", "Near breach", f"buffer {bp:.0f}% (${a.get('buffer') or 0:,.0f})")
        elif bp is not None and bp < 30:
            flag(a, "warning", "Thin buffer", f"buffer {bp:.0f}% (${a.get('buffer') or 0:,.0f})")
        elif bp is not None and bp < 50:
            flag(a, "info", "Watch buffer", f"buffer {bp:.0f}%")
        if pay.get("stage") == "Funded":
            cp = pay.get("consistency_pct")
            if cp is not None and cp >= 25:
                flag(a, "warning" if cp > 30 else "info", "Consistency risk", f"best day {cp:.0f}% (limit 30%)")
            if pay.get("eligible"):
                flag(a, "info", "Payout ready", f"withdrawable ${pay.get('withdrawable') or 0:,.0f}")
        elif pay.get("stage") == "Eval":
            tgt, prof = pay.get("target"), pay.get("profit")
            if tgt and prof is not None and 0 < prof < tgt and prof >= 0.8 * tgt:
                flag(a, "info", "Near eval target", f"${prof:,.0f} / ${tgt:,.0f}")
    items.sort(key=lambda x: _SEV.get(x["sev"], 3))
    counts = {s: sum(1 for x in items if x["sev"] == s) for s in ("critical", "warning", "info")}
    return items, counts


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
        p = _prod(product)
        sym = p[0]
        tick = _TICK.get(product.upper()) or _TICK.get(sym, 0)
        if tick and t.entry_price is not None and t.exit_price is not None:
            move = (t.exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - t.exit_price)
            ticks = round(move / tick)
        else:
            ticks = 0
        out.append({"acct": t.account, "sym": sym, "strat": p[3], "net": round(t.pnl, 2), "ticks": ticks,
                    "close": close, "hour": et.hour, "dow": et.weekday(),
                    "comm": 0.0, "mfe": t.mfe, "mae": t.mae})
    return out


def _aggregate(trades: list[dict], window: str, stage: str = "all") -> dict:
    today = dt.datetime.now(_ET).date()
    start = _window_start(window, today)
    if window == "day":
        # the LAST trading day that actually has trades (not necessarily today)
        last = max((t["close"] for t in trades), default=today)
        rows = [t for t in trades if t["close"] == last]
    elif start is not None:
        rows = [t for t in trades if t["close"] >= start]
    else:
        rows = trades
    if stage in ("funded", "eval"):
        rows = [t for t in rows if _phase(t["acct"]).lower() == stage]

    agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "losers": 0, "net": 0.0,
                                                "ticks": 0, "comm": 0.0, "gw": 0.0, "gl": 0.0,
                                                "mfe": [], "mae": []})
    acct_net: dict[str, float] = defaultdict(float)
    acct_rows: dict[str, list] = defaultdict(list)
    for t in rows:
        a = agg[t["sym"]]
        a["n"] += 1
        if t["net"] > 0:
            a["wins"] += 1
            a["gw"] = round(a["gw"] + t["net"], 2)
        elif t["net"] < 0:
            a["losers"] += 1
            a["gl"] = round(a["gl"] - t["net"], 2)
        a["net"] = round(a["net"] + t["net"], 2)
        a["ticks"] += t["ticks"]
        a["comm"] = round(a["comm"] + t.get("comm", 0.0), 2)
        if t.get("mfe") is not None:
            a["mfe"].append(t["mfe"])
        if t.get("mae") is not None:
            a["mae"].append(t["mae"])
        acct_net[t["acct"]] = round(acct_net[t["acct"]] + t["net"], 2)   # full id — 013 collision-safe
        acct_rows[t["acct"][-3:]].append(t)

    def _avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    assets = []
    for sym, a in agg.items():
        gross = round(a["net"] + a["comm"], 2)
        label, market, micro, engine, robust, edge, cls = _prod(sym)
        assets.append({
            "sym": sym, "market": market, "micro": micro, "engine": engine,
            "n": a["n"], "wins": a["wins"],
            "win": round(100 * a["wins"] / a["n"], 1) if a["n"] else 0.0,
            "ticks": int(a["ticks"]), "net": a["net"],
            "pf": round(a["gw"] / a["gl"], 2) if a["gl"] > 0 else (None if a["gw"] == 0 else 99.99),
            "expectancy": round(a["net"] / a["n"], 2) if a["n"] else 0.0,
            "avg_win": round(a["gw"] / a["wins"], 2) if a["wins"] else 0.0,
            "avg_loss": round(a["gl"] / a["losers"], 2) if a["losers"] else 0.0,
            "comm": a["comm"], "fees_pct": round(100 * a["comm"] / gross, 1) if gross > 0 else None,
            "mfe": _avg(a["mfe"]), "mae": _avg(a["mae"]),
            "robust": robust, "edge": edge, "cls": cls,
        })
    assets.sort(key=lambda x: -x["net"])
    totals = {"net": round(sum(x["net"] for x in assets), 2),
              "n": sum(x["n"] for x in assets),
              "wins": sum(x["wins"] for x in assets),
              "comm": round(sum(x["comm"] for x in assets), 2)}

    # group the filtered rows once, then build heatmap + calendar per dimension (all / asset /
    # strategy / account) so both grids share the same drill-down filter.
    by_asset: dict = defaultdict(list)
    by_strat: dict = defaultdict(list)
    by_acct: dict = defaultdict(list)
    for t in rows:
        by_asset[t["sym"]].append(t)
        by_strat[t.get("strat") or "—"].append(t)
        by_acct[t["acct"][-3:]].append(t)

    heatmap = {
        "all": _hm_cells(rows),
        "asset": {k: _hm_cells(v) for k, v in by_asset.items()},
        "strat": {k: _hm_cells(v) for k, v in by_strat.items()},
        "acct": {k: _hm_cells(v) for k, v in by_acct.items()},
    }

    # correlation of daily net between assets (0-filled on non-trading days = flat that day)
    by_ad: dict = defaultdict(lambda: defaultdict(float))
    days: set = set()
    for t in rows:
        by_ad[t["sym"]][t["close"]] = round(by_ad[t["sym"]][t["close"]] + t["net"], 2)
        days.add(t["close"])
    labels = [a["sym"] for a in assets]
    day_list = sorted(days)
    series = {sym: [by_ad[sym].get(d, 0.0) for d in day_list] for sym in labels}
    matrix = [[1.0 if s1 == s2 else _pearson(series[s1], series[s2]) for s2 in labels] for s1 in labels]
    correlation = {"labels": labels, "matrix": matrix, "days": len(day_list)}

    # calendar: daily net for the whole fleet, and per asset / strategy / account
    day_all = _day_cells(rows)
    calendar = {
        "by_day": [{"d": k, "net": v["net"], "n": v["n"]} for k, v in sorted(day_all.items())],
        "asset_day": {k: _day_cells(v) for k, v in by_asset.items()},
        "strat_day": {k: _day_cells(v) for k, v in by_strat.items()},
        "acct_day": {k: _day_cells(v) for k, v in by_acct.items()},
    }

    # equity curve (cumulative net + drawdown from peak) + a forward risk/expectancy band:
    # project H trading days from daily expectancy ± volatility (√-time widening cone).
    eq_days = sorted(day_all.items())
    cum = peak = 0.0
    curve = []
    for iso, v in eq_days:
        cum = round(cum + v["net"], 2)
        peak = max(peak, cum)
        curve.append({"d": iso, "cum": cum, "dd": round(cum - peak, 2)})
    dn = [v["net"] for _, v in eq_days]
    m = len(dn)
    mean = sum(dn) / m if m else 0.0
    std = (sum((x - mean) ** 2 for x in dn) / m) ** 0.5 if m else 0.0
    proj = [{"k": k, "mid": round(cum + mean * k, 2),
             "lo": round(cum + mean * k - std * k ** 0.5, 2),
             "hi": round(cum + mean * k + std * k ** 0.5, 2)} for k in range(1, 16)]
    equity = {"curve": curve, "proj": proj, "exp_day": round(mean, 2), "std_day": round(std, 2),
              "max_dd": round(min((c["dd"] for c in curve), default=0.0), 2)}

    # per-account, per-strategy + fleet CIO stats (PF, win%, expectancy, heat)
    acct_stats = {k: _stats(v) for k, v in acct_rows.items()}
    strat_stats = {k: _stats(v) for k, v in by_strat.items()}
    day_nets = [v["net"] for v in day_all.values()]
    stats = _stats(rows)
    stats.update(best_day=max(day_nets) if day_nets else 0.0,
                 worst_day=min(day_nets) if day_nets else 0.0,
                 up_days=sum(1 for x in day_nets if x > 0),
                 down_days=sum(1 for x in day_nets if x < 0),
                 trading_days=len(day_nets))

    return {"assets": assets, "totals": totals, "acct_net": dict(acct_net),
            "heatmap": heatmap, "correlation": correlation, "calendar": calendar,
            "equity": equity, "acct_stats": acct_stats, "strat_stats": strat_stats, "stats": stats}


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

    # attach CIO stats (PF, win%, expectancy, trade count) per account from the trade log
    _ast = ag["acct_stats"]
    for a in accounts:
        s = _ast.get(a["id"]) or {}
        a["pf"] = s.get("pf")
        a["win_pct"] = s.get("win_pct")
        a["expectancy"] = s.get("expectancy")
        a["avg_win"] = s.get("avg_win")
        a["avg_loss"] = s.get("avg_loss")
        a["heat"] = s.get("heat")
        a["trades"] = s.get("n", 0)

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

    # payout playbook: per-account doctrine preset (track/phase → asset·strategy + contracts +
    # day-trail) plus live payout progress. Follows the Operating Schema, not an optimizer.
    from .playbook import PlaybookParams, build_playbook
    dom_asset: dict = defaultdict(lambda: defaultdict(int))
    for t in trades:
        dom_asset[t["acct"]][t["sym"]] += 1
    _pp = PlaybookParams()
    for a in accounts:
        da = dom_asset.get(a["full"]) or {}
        instrument = max(da, key=da.get) if da else None      # the real instrument (MGC/MES…)
        try:
            a["playbook"] = build_playbook(a, dict(daily.get(a["full"], {})), instrument, _pp)
        except Exception as exc:                       # never let the playbook break the dashboard
            log.warning("playbook failed for %s: %r", a.get("full"), exc)
            a["playbook"] = None
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

    # portfolio: how allocated capital + P&L are distributed, plus asset correlation
    cap_firm: dict = defaultdict(float)
    cap_stage: dict = defaultdict(float)
    for a in accounts:
        sz = a.get("size") or 0.0
        cap_firm[a["firm"]] += sz
        cap_stage[a["stage"]] += sz
    total_cap = sum(cap_firm.values()) or 1.0
    alloc_firm = sorted(({"name": k, "capital": round(v, 0), "pct": round(100 * v / total_cap, 1)}
                         for k, v in cap_firm.items()), key=lambda z: -z["capital"])
    alloc_stage = [{"name": k, "capital": round(v, 0), "pct": round(100 * v / total_cap, 1)}
                   for k, v in cap_stage.items()]
    pos_net = sum(x["net"] for x in assets if x["net"] > 0) or 1.0
    alloc_asset = [{"sym": x["sym"], "net": x["net"], "cls": x["cls"],
                    "pct": round(100 * x["net"] / pos_net, 1)} for x in assets]
    portfolio = {"total_capital": round(total_cap, 0), "alloc_firm": alloc_firm,
                 "alloc_stage": alloc_stage, "alloc_asset": alloc_asset,
                 "correlation": ag["correlation"]}

    attention, attn_counts = _attention(accounts)

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
            "trades": ag["stats"]["n"],
            "win_rate": ag["stats"]["win_pct"],
            "pf": ag["stats"]["pf"],
            "expectancy": ag["stats"]["expectancy"],
            "avg_win": ag["stats"]["avg_win"],
            "avg_loss": ag["stats"]["avg_loss"],
            "heat": ag["stats"]["heat"],
            "best_day": ag["stats"]["best_day"],
            "worst_day": ag["stats"]["worst_day"],
            "up_days": ag["stats"]["up_days"],
            "down_days": ag["stats"]["down_days"],
            "trading_days": ag["stats"]["trading_days"],
            "best_asset": best["sym"] if best else None,
            "best_asset_net": best["net"] if best else None,
            "fees": atot.get("comm", 0.0),
            "withdrawable": total_withdrawable,
            "payout_eligible": payout_eligible,
            "attention": attn_counts,
        },
        "accounts": accounts,
        "assets": assets,
        "firms": firm_rows,
        "heatmap": ag["heatmap"],
        "portfolio": portfolio,
        "calendar": ag["calendar"],
        "equity": ag["equity"],
        "strat_stats": ag["strat_stats"],
        "attention": attention,
        "status": {
            "data_through": max((t["close"] for t in trades), default=None) and
                            max(t["close"] for t in trades).isoformat(),
            "trades_total": len(trades),
            "accounts": len(accounts_src),
            "notion_ok": bool(os.environ.get("NOTION_TOKEN")) and len(accounts_src) > 0,
        },
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(command_state(os.environ.get("WINDOW", "all")), indent=2))
