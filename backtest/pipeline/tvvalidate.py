"""Stage 10 — TradingView validation (HARD deployment gate).

The last gate before live. Stage 1 proves the engine reproduces Pine's raw
mechanic; stages 2–9 prove the mechanic is worth funding. Stage 10 signs off the
DEPLOYMENT candidate — the frozen config exactly as it will run live, account
overlay and all — against the TradingView export, and it gates on two dimensions
stage 1 measures but does NOT gate on:

  * exit-reason distribution — does our engine flatten via Auto Flat / DLL /
    CAP-LOCK / TP / SL at the SAME rates Pine does? Two engines can match on
    count/PF/WR/split while disagreeing on HOW trades close. For a PA account the
    exit mix is the account overlay's fidelity, and it is what breaches or banks.
  * MFE/MAE — do the per-trade excursions agree? That tests the intrabar path
    (stop/trail/target behaviour bar by bar), not just the endpoints.

Deployment posture: `research_mode=False`. For a PA production config the engine
enforces the per-day rules (Auto Flat, DLL, day cap) but does NOT terminate on a
trailing breach — it resets the overlay and keeps trading (engine.py `_account`),
exactly as the Pine strategy keeps generating trades across the whole window. The
account lifecycle (trailing DD, payouts) is layered on top in stages 6–8, not
here.

Acceptance (ground rule 10): a simulator result is NOT accepted if TradingView
materially disagrees. The data-vendor tolerance of stage 1 carries over — if the
only residual is which bars carry a gap AND the exit mix and excursions agree on
the trades both engines take, the gate is met under a data-parity label.
"""
from __future__ import annotations

from collections import Counter

# Canonical exit categories. Pine and the Python engine name the same events
# differently; both sides normalise into these so the distribution is comparable.
CANON = ("TP", "SL", "AUTO-FLAT", "DLL", "CAP-LOCK", "OTHER")


def exit_category(reason: str) -> str:
    """Map an exit label (Pine OR simulator) to a canonical category.

    Pine writes: "TP|MFE..t|MAE..t", "SL|MFE..t|MAE..t", "Auto Flat",
    "PA Daily Loss Limit", "CAP-LOCK". The Python engine writes: "TP",
    "SL"/"TRAIL"/"RECOV-TRAIL"/"BE-STOP" (all exit AT the stop, so Pine labels
    them SL), "EOD"/"AUTO-FLAT", "PA Daily Loss Limit", "Day-cap"/"Day-trail"
    (the day-profit lock family, Pine's CAP-LOCK)."""
    r = (reason or "").strip().upper()
    if not r:
        return "OTHER"
    if r.startswith("TP"):
        return "TP"
    if r.startswith("SL") or r in ("TRAIL", "RECOV-TRAIL", "BE-STOP"):
        return "SL"
    if r in ("EOD", "AUTO-FLAT") or "AUTO FLAT" in r:
        return "AUTO-FLAT"
    if "DAILY LOSS" in r:
        return "DLL"
    if "CAP-LOCK" in r or r.startswith("DAY-CAP") or r.startswith("DAY-TRAIL"):
        return "CAP-LOCK"
    return "OTHER"


def _distribution(reasons) -> dict:
    c = Counter(exit_category(r) for r in reasons)
    n = sum(c.values()) or 1
    return {k: {"n": c.get(k, 0), "pct": round(100 * c.get(k, 0) / n, 1)}
            for k in CANON if c.get(k, 0)}


def exit_reason_agreement(sim_trades, export, tol_pp: float = 5.0) -> dict:
    """Compare the exit-category distribution of the two trade streams.

    Gate: every category's share is within `tol_pp` percentage points, and the
    total-variation distance (half the summed absolute share gaps) is small. A
    category present on one side and absent on the other is the loudest possible
    disagreement — the account overlay fires an exit the other engine never
    fires — and shows up directly as a per-category gap."""
    sim = [exit_category(getattr(t, "reason", "")) for t in sim_trades
           if getattr(t, "exit_time", None) is not None]
    pine = [exit_category(t.get("exit_reason", "")) for t in export.trades]
    sc = Counter(sim)
    pc = Counter(pine)
    ns = sum(sc.values()) or 1
    np_ = sum(pc.values()) or 1
    rows, worst = [], 0.0
    tv = 0.0
    for k in CANON:
        s_pct = 100 * sc.get(k, 0) / ns
        p_pct = 100 * pc.get(k, 0) / np_
        gap = abs(s_pct - p_pct)
        tv += gap
        if sc.get(k, 0) or pc.get(k, 0):
            rows.append({"category": k, "sim_n": sc.get(k, 0), "pine_n": pc.get(k, 0),
                         "sim_pct": round(s_pct, 1), "pine_pct": round(p_pct, 1),
                         "gap_pp": round(gap, 1)})
        worst = max(worst, gap)
    tv /= 2
    ok = worst <= tol_pp
    return {"ok": ok, "rows": rows, "worst_gap_pp": round(worst, 1),
            "total_variation_pp": round(tv, 1), "tol_pp": tol_pp,
            "sim_distribution": _distribution(sim),
            "pine_distribution": _distribution(pine)}


def _minutes(ts):
    import pandas as pd
    if ts is None:
        return None
    t = pd.Timestamp(ts)
    if t.tz is not None:
        t = t.tz_localize(None)
    return int(t.value // 60_000_000_000)


def _pine_excursion_ticks(t: dict, cfg) -> tuple:
    """(mfe_ticks, mae_ticks) for a Pine trade, in the engine's own unit.

    Prefer the tick fingerprint Pine embeds in TP/SL exit comments — same unit,
    no conversion. Fall back to the excursion USD columns (÷ point value ÷ tick ÷
    qty) for Auto Flat / DLL / CAP-LOCK exits that carry no fingerprint."""
    if "pine_exit_mfe_ticks" in t:
        return float(t["pine_exit_mfe_ticks"]), float(t["pine_exit_mae_ticks"])
    ct = cfg.contract
    qty = float(t.get("qty") or 1) or 1.0
    per_tick = ct.pointvalue * ct.mintick * qty
    if per_tick <= 0:
        return None, None
    return (abs(float(t.get("mfe_usd") or 0.0)) / per_tick,
            abs(float(t.get("mae_usd") or 0.0)) / per_tick)


def _pair(sim_trades, export, tol_minutes: int = 2):
    """Greedy nearest-time, same-direction pairing — the same alignment
    tracediff uses, but carrying the excursion fields tracediff drops."""
    sim = []
    for t in sim_trades:
        if getattr(t, "exit_time", None) is None:
            continue
        m = _minutes(t.entry_time)
        if m is None:
            continue
        sim.append({"t": m, "dir": int(t.dir), "mfe": float(t.mfe_ticks),
                    "mae": float(t.mae_ticks)})
    pine = []
    for t in export.trades:
        m = _minutes(t.get("entry_time"))
        if m is None:
            continue
        pine.append({"t": m, "dir": t["dir"], "raw": t})
    sim.sort(key=lambda r: r["t"])
    pine.sort(key=lambda r: r["t"])
    used, pairs = set(), []
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
            pairs.append((s, pine[best]))
    return pairs


def excursion_agreement(sim_trades, export, cfg, tol_minutes: int = 2,
                        tol_ticks: float = 4.0) -> dict:
    """MFE/MAE agreement on trades BOTH engines take (paired on entry time+dir).

    Unpaired trades cannot contribute — there is no counterpart to compare an
    excursion against — so this measures path fidelity on the shared trades only,
    and reports how many pairs it had. Gate: the median absolute tick difference
    for MFE and for MAE both sit under `tol_ticks`; on 1-minute bars a few ticks
    of excursion difference is bar-aggregation, more is a different intrabar path."""
    import statistics as st

    pairs = _pair(sim_trades, export, tol_minutes)
    mfe_diffs, mae_diffs, examples = [], [], []
    for s, p in pairs:
        p_mfe, p_mae = _pine_excursion_ticks(p["raw"], cfg)
        if p_mfe is None:
            continue
        dm = abs(s["mfe"] - p_mfe)
        da = abs(s["mae"] - p_mae)
        mfe_diffs.append(dm)
        mae_diffs.append(da)
        if len(examples) < 12:
            examples.append({"entry": str(p["raw"].get("entry_time")),
                             "dir": s["dir"], "sim_mfe": round(s["mfe"], 1),
                             "pine_mfe": round(p_mfe, 1), "sim_mae": round(s["mae"], 1),
                             "pine_mae": round(p_mae, 1)})
    n = len(mfe_diffs)
    if not n:
        return {"ok": False, "paired": 0, "reason": "geen gepaarde trades met "
                "vergelijkbare excursie", "tol_ticks": tol_ticks}
    med_mfe = st.median(mfe_diffs)
    med_mae = st.median(mae_diffs)
    ok = med_mfe <= tol_ticks and med_mae <= tol_ticks
    return {"ok": ok, "paired": n, "tol_ticks": tol_ticks,
            "median_mfe_diff_ticks": round(med_mfe, 2),
            "median_mae_diff_ticks": round(med_mae, 2),
            "max_mfe_diff_ticks": round(max(mfe_diffs), 1),
            "max_mae_diff_ticks": round(max(mae_diffs), 1),
            "within_tol_pct": round(100 * sum(
                1 for a, b in zip(mfe_diffs, mae_diffs)
                if a <= tol_ticks and b <= tol_ticks) / n, 1),
            "examples": examples}


def evaluate(sim_trades, cfg, export, kpi_compare, trade_diff,
             data_parity_evidence) -> dict:
    """Validate the deployment run against the export across all trap-10 dimensions.

    The caller runs the engine ONCE in deployment posture (`research_mode=False`)
    and hands in `sim_trades`, the KPI comparison (parity.compare — the dimensions
    shared with stage 1), the trade-level `trade_diff` (tracediff.diff), and the
    stage-1 `data_parity_evidence` (whether the trade-count residual is provably
    the vendor). Stage 10 ADDS the exit-mix and excursion gates on top, so a
    trade-count residual is tolerated only when nothing about HOW the shared
    trades behave disagrees.
    """
    kpi = kpi_compare
    td = trade_diff
    exits = exit_reason_agreement(sim_trades, export)
    exc = excursion_agreement(sim_trades, export, cfg)

    # timing: of the trades both engines take, how many land on the SAME bar
    matched = td.get("matched") or 0
    off_bar = td.get("matched_on_a_different_bar") or 0
    same_bar_pct = round(100 * (matched - off_bar) / matched, 1) if matched else 0.0
    pine_n = td.get("pine_trades") or 0
    matched_pct = round(100 * matched / pine_n, 1) if pine_n else 0.0
    timing_ok = matched_pct >= 70.0 and same_bar_pct >= 90.0

    dims = {
        "kpi": {"ok": kpi["pass"], "detail": "trade count / PF / WR / long-short"},
        "timing": {"ok": timing_ok, "matched_pct": matched_pct,
                   "same_bar_pct": same_bar_pct,
                   "detail": f"{matched_pct}% van pine's trades gepaard, "
                             f"{same_bar_pct}% op dezelfde bar"},
        "exit_reasons": {"ok": exits["ok"], "worst_gap_pp": exits["worst_gap_pp"],
                         "detail": f"grootste categorie-afwijking {exits['worst_gap_pp']}pp "
                                   f"(limiet {exits['tol_pp']:.0f}pp)"},
        "excursion": {"ok": exc["ok"], "detail": (
            f"mediane MFE-afwijking {exc.get('median_mfe_diff_ticks')}t, "
            f"MAE {exc.get('median_mae_diff_ticks')}t (limiet {exc['tol_ticks']:.0f}t)"
            if exc.get("paired") else exc.get("reason", "geen paren"))},
    }
    all_ok = all(d["ok"] for d in dims.values())

    # Data-parity escape (ground rule 10): the only failing dimension is the KPI
    # trade-count check, that residual is provably the vendor (stage-1 evidence),
    # AND the behaviour of the shared trades agrees — exit mix and excursion both
    # ok. Then TradingView does NOT materially disagree about the engine; it sees
    # different bars. Accepted under a data-parity label, never as exact.
    non_kpi_ok = dims["timing"]["ok"] and dims["exit_reasons"]["ok"] and dims["excursion"]["ok"]
    dp_ok = (not all_ok and not kpi["pass"] and data_parity_evidence.get("eligible")
             and non_kpi_ok)

    if all_ok:
        status = "passed"
        verdict = ("TradingView bevestigt de deployment-kandidaat: trades, timing, "
                   "exit-redenen, MFE/MAE en PF komen allemaal overeen — vrij voor live")
    elif dp_ok:
        status = "data_parity"
        verdict = ("TradingView is het eens over de engine: exit-mix en MFE/MAE komen "
                   "overeen op de gedeelde trades; het enige verschil is welke bars een "
                   "gap dragen (databron). Deployment-poort GEHAALD met label data-pariteit")
    else:
        status = "failed"
        failed = [k for k, d in dims.items() if not d["ok"]]
        verdict = ("TradingView is het NIET eens — afwijkende dimensie(s): "
                   + ", ".join(failed) + ". Onderzoek de eerste afwijkende trades, "
                   "NIET opnieuw optimaliseren (grondregel 10)")

    return {"status": status, "verdict": verdict, "dimensions": dims,
            "kpi": kpi, "trade_diff": td, "exit_reasons": exits, "excursion": exc,
            "sim_trades": len([t for t in sim_trades
                               if getattr(t, "exit_time", None) is not None]),
            "pine_trades": pine_n, "matched": matched,
            "same_bar_pct": same_bar_pct, "matched_pct": matched_pct,
            "data_parity": dp_ok}
