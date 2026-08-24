"""Trade-level diff between the simulator and a TradingView export.

Stage 1's verdict says "investigate the first divergent trades, do not
re-optimize" — this is the tool that makes that instruction actionable. Aggregate
KPIs tell you THAT the engines disagree; only a trade-level alignment tells you
WHERE, and the shape of the disagreement usually names the cause:

  * pine-only trades clustered on one weekday  -> a session/day filter differs
  * every trade present but exits differ       -> stop/target/exit semantics
  * entries offset by exactly one bar          -> fill timing (bar close vs fill)
  * matched entries, smaller wins              -> the target is being cut short

Alignment is on entry time with a tolerance, because a one-bar timing difference
is itself a finding — not a reason to call a trade missing.
"""
from __future__ import annotations

from collections import Counter


def _minutes(ts) -> int | None:
    """Timestamp -> minutes since epoch, tz-naive, for cheap comparison."""
    import pandas as pd
    if ts is None:
        return None
    t = pd.Timestamp(ts)
    if t.tz is not None:
        t = t.tz_localize(None)
    return int(t.value // 60_000_000_000)


def _pine_rows(export) -> list[dict]:
    import pandas as pd
    out = []
    for t in export.trades:
        try:
            entry = pd.Timestamp(t["entry_time"])
        except Exception:
            continue
        out.append({"t": _minutes(entry), "dir": t["dir"], "net": t["net"],
                    "entry_px": t["entry_px"], "exit_px": t["exit_px"],
                    "reason": (t.get("exit_reason") or "").strip(),
                    "entry_time": str(entry)})
    return [r for r in out if r["t"] is not None]


def _sim_rows(trades) -> list[dict]:
    out = []
    for t in trades:
        if getattr(t, "exit_time", None) is None:
            continue
        out.append({"t": _minutes(t.entry_time), "dir": int(t.dir),
                    "net": float(t.net), "entry_px": float(t.entry_px),
                    "exit_px": float(t.exit_px),
                    "reason": (t.reason or "").strip(),
                    "entry_time": str(t.entry_time)})
    return [r for r in out if r["t"] is not None]


def diff(sim_trades, export, tol_minutes: int = 2, examples: int = 12,
         net_tol: float = 25.0) -> dict:
    """Align the two trade lists on entry time and describe the disagreement."""
    sim, pine = _sim_rows(sim_trades), _pine_rows(export)
    sim.sort(key=lambda r: r["t"])
    pine.sort(key=lambda r: r["t"])

    used, matched = set(), []
    for s in sim:
        best, best_gap = None, None
        for j, p in enumerate(pine):
            if j in used or p["dir"] != s["dir"]:
                continue
            gap = abs(p["t"] - s["t"])
            if gap <= tol_minutes and (best_gap is None or gap < best_gap):
                best, best_gap = j, gap
        if best is not None:
            used.add(best)
            matched.append((s, pine[best], best_gap))

    sim_only = [s for s in sim if not any(m[0] is s for m in matched)]
    pine_only = [p for j, p in enumerate(pine) if j not in used]

    def _weekday(rows):
        import pandas as pd
        c = Counter()
        for r in rows:
            c[pd.Timestamp(r["entry_time"]).day_name()] += 1
        return dict(c.most_common())

    def _hours(rows):
        import pandas as pd
        return dict(Counter(pd.Timestamp(r["entry_time"]).hour for r in rows).most_common())

    # Only MATERIAL result differences. A few dollars per trade is a cost or
    # half-tick fill artefact, and flagging those marks every matched trade as
    # divergent — which is exactly how a real signal (a stop that fires on a
    # different bar) gets lost in the noise.
    exit_gap = [(s, p, g) for s, p, g in matched
                if abs(s["net"] - p["net"]) > net_tol]
    trivial = [(s, p, g) for s, p, g in matched
               if 0.005 < abs(s["net"] - p["net"]) <= net_tol]
    off_bar = [m for m in matched if m[2] > 0]

    return {
        "sim_trades": len(sim), "pine_trades": len(pine),
        "matched": len(matched), "sim_only": len(sim_only), "pine_only": len(pine_only),
        "matched_on_a_different_bar": len(off_bar),
        "matched_with_a_different_result": len(exit_gap),
        "matched_within_cost_noise": len(trivial),
        "net_tolerance": net_tol,
        "matched_exactly": len(matched) - len(exit_gap) - len(trivial),
        "sim_only_by_weekday": _weekday(sim_only),
        "pine_only_by_weekday": _weekday(pine_only),
        "pine_only_by_hour": _hours(pine_only),
        "sim_exit_reasons": dict(Counter(r["reason"] for r in sim).most_common()),
        "pine_exit_reasons": dict(Counter(r["reason"] for r in pine).most_common()),
        "avg_net_matched_sim": round(sum(s["net"] for s, _, _ in matched) / len(matched), 2)
                               if matched else 0.0,
        "avg_net_matched_pine": round(sum(p["net"] for _, p, _ in matched) / len(matched), 2)
                                if matched else 0.0,
        "first_pine_only": pine_only[:examples],
        "first_sim_only": sim_only[:examples],
        "first_result_gaps": [
            {"entry": s["entry_time"], "dir": s["dir"], "sim_net": round(s["net"], 2),
             "pine_net": round(p["net"], 2), "sim_exit": s["reason"],
             "pine_exit": p["reason"], "sim_exit_px": s["exit_px"],
             "pine_exit_px": p["exit_px"]}
            for s, p, _ in exit_gap[:examples]],
    }


def render(d: dict) -> str:
    """Human-readable summary — what to look at first."""
    L = [f"  simulator {d['sim_trades']} trades · pine {d['pine_trades']} · "
         f"{d['matched']} gepaard op instapmoment",
         f"    alleen in simulator: {d['sim_only']} · alleen in pine: {d['pine_only']}",
         f"    gepaard maar andere bar: {d['matched_on_a_different_bar']}",
         f"    van de gepaarde: {d['matched_exactly']} identiek · "
         f"{d['matched_within_cost_noise']} binnen kosten-ruis (<= ${d['net_tolerance']:.0f}) · "
         f"{d['matched_with_a_different_result']} materieel anders"]
    if d["matched"]:
        L.append(f"    gemiddelde netto per gepaarde trade: simulator "
                 f"${d['avg_net_matched_sim']:,.2f} vs pine ${d['avg_net_matched_pine']:,.2f}")
    if d["pine_only"]:
        L.append(f"    pine-only per weekdag: {d['pine_only_by_weekday']}")
        L.append(f"    pine-only per uur (ET): {d['pine_only_by_hour']}")
    if d["sim_only"]:
        L.append(f"    simulator-only per weekdag: {d['sim_only_by_weekday']}")
    L.append(f"    exit-redenen simulator: {d['sim_exit_reasons']}")
    L.append(f"    exit-redenen pine:      {d['pine_exit_reasons']}")
    if d["first_result_gaps"]:
        L.append("    eerste trades met dezelfde instap maar een andere uitkomst:")
        for g in d["first_result_gaps"][:6]:
            L.append(f"      {g['entry']}  {'long' if g['dir'] > 0 else 'short'}  "
                     f"sim ${g['sim_net']:>9,.2f} ({g['sim_exit'] or '?'}) vs "
                     f"pine ${g['pine_net']:>9,.2f} ({g['pine_exit'] or '?'})")
    if d["first_pine_only"]:
        L.append("    eerste trades die pine wel doet en de simulator niet:")
        for p in d["first_pine_only"][:6]:
            L.append(f"      {p['entry_time']}  {'long' if p['dir'] > 0 else 'short'}  "
                     f"${p['net']:,.2f}  ({p['reason'] or '?'})")
    return "\n".join(L)
