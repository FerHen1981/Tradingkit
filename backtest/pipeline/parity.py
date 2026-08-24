"""Stage 1 — Pine parity engine (HARD gate).

Gate: Python vs Pine on one fixed baseline — near-equal trade count and
materially comparable win rate / PF. Parameter optimization is INVALID while
baseline parity is unresolved (pipeline v7, ground rule 1).

Two jobs live here:

1. **Properties audit** (ground rule 10). TradingView preserves previously saved
   input values when a script is replaced, so the source-code defaults are NOT
   evidence of what was tested. The exported Properties sheet is the ground
   truth, and this module compares it against the config we believe we are
   validating. A mismatch does not fail parity — it means the export tests a
   different configuration, and the comparison would be meaningless.

2. **Trade-level comparison** against the export's Trades sheet.
"""
from __future__ import annotations

from dataclasses import dataclass

# Properties label -> (config attribute, how to read the exported value)
_PROP_MAP = {
    "Fixed Qty":                        ("contract_size", float),
    "Limit Order Expiry (bars)":        ("expiry_bars", int),
    "Fixed Stop (units, legacy mode)":  ("fixed_stop_ticks", float),
    "R-Multiple (R-multiple mode)":     ("r_multiple", float),
    "Min FVG Size (units)":             ("gap_min_ticks", float),
    "Max FVG Size (units)":             ("gap_max_ticks", float),
    "Count":                            ("cvd_trend_count", int),
    "Distance Unit":                    ("unit_mode", str),
    "Take-Profit Mode":                 ("tp_mode", str),
    "Drawdown Model":                   ("dd_model", str),
}
_ONOFF = {"Use Delta Filter": "use_cvd_filter", "Use FVG Size Range Filter": "use_gap_filter",
          "Enable Break-even": "use_breakeven", "Enable Trailing": "use_trail"}


@dataclass
class Export:
    path: str
    properties: dict
    trades: list      # one dict per CLOSED trade
    performance: dict

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    def stats(self) -> dict:
        nets = [t["net"] for t in self.trades]
        wins = [x for x in nets if x > 0]
        losses = [x for x in nets if x <= 0]
        gl = -sum(losses)
        return {"trades": len(nets), "net": round(sum(nets), 2),
                "win_rate_pct": round(100 * len(wins) / len(nets), 1) if nets else 0.0,
                "profit_factor": round(sum(wins) / gl, 2) if gl > 0 else float("inf"),
                "longs": sum(1 for t in self.trades if t["dir"] > 0),
                "shorts": sum(1 for t in self.trades if t["dir"] < 0)}


def read_export(path: str) -> Export:
    """Parse a TradingView strategy export (.xlsx): Properties, Trades, Performance."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    props = {}
    if "Properties" in wb.sheetnames:
        for row in wb["Properties"].iter_rows(values_only=True):
            if row and row[0] is not None:
                props[str(row[0]).strip()] = row[1]

    trades = []
    if "Trades" in wb.sheetnames:
        ws = wb["Trades"]
        rows = list(ws.iter_rows(values_only=True))
        hdr = [str(c).strip() if c is not None else "" for c in rows[0]]
        ix = {name: hdr.index(name) for name in hdr}
        get = lambda r, k: (r[ix[k]] if k in ix and ix[k] < len(r) else None)
        # TradingView writes one row per LEG; pair them on trade number.
        legs: dict = {}
        for r in rows[1:]:
            num = get(r, "Trade number")
            if num is None:
                continue
            legs.setdefault(str(num), []).append(r)
        for num, rs in legs.items():
            entry = next((r for r in rs if str(get(r, "Type") or "").lower().startswith("entry")), None)
            exit_ = next((r for r in rs if str(get(r, "Type") or "").lower().startswith("exit")), None)
            if entry is None or exit_ is None:
                continue                       # still-open trade
            typ = str(get(entry, "Type") or "").lower()
            try:
                net = float(get(exit_, "Net PnL USD") or 0.0)
            except (TypeError, ValueError):
                net = 0.0
            trades.append({
                "n": int(float(num)), "dir": 1 if "long" in typ else -1,
                "entry_time": str(get(entry, "Date and time") or ""),
                "exit_time": str(get(exit_, "Date and time") or ""),
                "entry_px": _f(get(entry, "Price USD")), "exit_px": _f(get(exit_, "Price USD")),
                "qty": _f(get(entry, "Size (qty)")), "net": net,
                "signal": str(get(entry, "Signal") or ""),
                "exit_reason": str(get(exit_, "Signal") or ""),
            })
        trades.sort(key=lambda t: t["n"])

    perf = {}
    if "Performance" in wb.sheetnames:
        for row in wb["Performance"].iter_rows(values_only=True):
            if row and row[0] is not None:
                perf[str(row[0]).strip()] = row[1]
    wb.close()
    return Export(path=path, properties=props, trades=trades, performance=perf)


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def audit_properties(export: Export, cfg) -> dict:
    """Ground rule 10 — does the export actually test the config we think it does?"""
    rows, mismatches = [], 0
    for label, (attr, cast) in _PROP_MAP.items():
        if label not in export.properties:
            continue
        raw = export.properties[label]
        have = getattr(cfg, attr, None)
        try:
            want, got = (cast(have), cast(raw)) if cast is not str else (str(have), str(raw))
        except (TypeError, ValueError):
            want, got = str(have), str(raw)
        ok = (want == got)
        mismatches += 0 if ok else 1
        rows.append({"label": label, "attr": attr, "export": got, "config": want, "ok": ok})
    for label, attr in _ONOFF.items():
        if label not in export.properties:
            continue
        got = str(export.properties[label]).strip().lower() in ("on", "true", "1")
        want = bool(getattr(cfg, attr, False))
        ok = got == want
        mismatches += 0 if ok else 1
        rows.append({"label": label, "attr": attr, "export": got, "config": want, "ok": ok})
    return {"rows": rows, "mismatches": mismatches,
            "symbol": export.properties.get("Symbol"),
            "commission": export.properties.get("Commission"),
            "slippage": export.properties.get("Slippage"),
            "start": export.properties.get("Start date/time (measure from)"),
            "end": export.properties.get("End date/time (measure through)"),
            "ok": mismatches == 0}


def compare(sim_kpis: dict, export: Export,
            trade_tol: float = 0.10, pf_tol: float = 0.20, wr_tol: float = 10.0) -> dict:
    """Stage-1 verdict. 'Near-equal trade count and materially comparable WR/PF'
    is made explicit: trade count within `trade_tol`, PF within `pf_tol`
    (relative), win rate within `wr_tol` percentage points."""
    tv = export.stats()
    sim_n = int(sim_kpis.get("trades") or 0)
    tv_n = tv["trades"]
    checks = []

    def chk(name, sim, ref, ok, detail):
        checks.append({"name": name, "sim": sim, "pine": ref, "ok": bool(ok), "detail": detail})

    dn = abs(sim_n - tv_n) / tv_n if tv_n else 1.0
    chk("trade count", sim_n, tv_n, dn <= trade_tol, f"{dn*100:.1f}% apart (limit {trade_tol*100:.0f}%)")

    s_pf, t_pf = float(sim_kpis.get("profit_factor") or 0), tv["profit_factor"]
    dpf = abs(s_pf - t_pf) / t_pf if t_pf not in (0, float("inf")) else 1.0
    chk("profit factor", round(s_pf, 2), t_pf, dpf <= pf_tol, f"{dpf*100:.1f}% apart (limit {pf_tol*100:.0f}%)")

    s_wr, t_wr = float(sim_kpis.get("win_rate_pct") or 0), tv["win_rate_pct"]
    chk("win rate", s_wr, t_wr, abs(s_wr - t_wr) <= wr_tol, f"{abs(s_wr-t_wr):.1f}pp apart (limit {wr_tol:.0f}pp)")

    s_l, s_s = int(sim_kpis.get("longs") or 0), int(sim_kpis.get("shorts") or 0)
    side_ok = (tv["longs"] == 0 or abs(s_l - tv["longs"]) / max(tv["longs"], 1) <= 0.25) and \
              (tv["shorts"] == 0 or abs(s_s - tv["shorts"]) / max(tv["shorts"], 1) <= 0.25)
    chk("long/short split", f"{s_l}/{s_s}", f"{tv['longs']}/{tv['shorts']}", side_ok, "within 25% per side")

    passed = all(c["ok"] for c in checks)
    return {"pass": passed, "checks": checks, "pine": tv, "sim": {
        "trades": sim_n, "profit_factor": round(s_pf, 2), "win_rate_pct": s_wr,
        "net": sim_kpis.get("net_profit")},
        "verdict": ("parity established on this baseline" if passed else
                    "NOT at parity — fix engine semantics before any parameter search "
                    "(ground rule 1); investigate the first divergent trades, do not re-optimize")}
