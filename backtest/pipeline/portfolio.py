"""Trap 11 — portfolio diversification (the last v7 stage).

Multi-engine, unlike stages 3–9: it measures how the fleet's daily P&L series move
TOGETHER. Two engines that each fund on their own add little to a portfolio if they
lose on the same days and breach on the same days. This stage measures, over the
shared active calendar:
  - pairwise Pearson correlation of daily P&L (0-filled — a day one engine did not
    trade is a real diversification observation: it was flat),
  - loss-day overlap (Jaccard of down-days),
  - breach-day overlap (days each engine's daily net <= -DLL, co-occurrence).

THE GATE IS SUFFICIENCY, NOT A NUMBER. No decorrelation may be claimed before the
fleet has >= min_days of shared active days per pair (default 20; CLAUDE.md and the
v7 methodology). Below that the verdict is `inconclusive`, whatever the correlation
happens to read — the frozen fleet is only days old, so the honest live answer today
is "not enough data yet". On the multi-year validation window there are plenty of
days, but that measures the HISTORICAL correlation; a forward decorrelation claim
still waits for live post-freeze days (D-18).
"""
from __future__ import annotations

import itertools
import math


def _pearson(a: list[float], b: list[float]):
    """Pearson r over paired samples. None if either side has zero variance
    (correlation is undefined against a flat series)."""
    n = len(a)
    if n < 2:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(va * vb)


def _align(series_by_engine: dict[str, dict]) -> tuple[list, dict[str, list[float]]]:
    """Union the session dates and 0-fill each engine onto that shared calendar."""
    dates = sorted({d for s in series_by_engine.values() for d in s})
    cols = {name: [float(s.get(d, 0.0)) for d in dates]
            for name, s in series_by_engine.items()}
    return dates, cols


def _overlap(days_a: set, days_b: set) -> dict:
    """Count + Jaccard of two day-sets."""
    inter = days_a & days_b
    union = days_a | days_b
    return {"both": len(inter), "either": len(union),
            "jaccard": round(len(inter) / len(union), 3) if union else 0.0}


def pairwise(series_by_engine: dict[str, dict], dll_by_engine: dict | None = None) -> list[dict]:
    """Per engine-pair: correlation of daily P&L, shared active days, loss-day and
    breach-day overlap. Engines each hold {session_date: net}."""
    dll_by_engine = dll_by_engine or {}
    dates, cols = _align(series_by_engine)
    traded = {name: set(s) for name, s in series_by_engine.items()}
    loss = {name: {d for d, v in s.items() if v < 0} for name, s in series_by_engine.items()}
    breach = {name: {d for d, v in s.items()
                     if dll_by_engine.get(name) is not None and v <= -abs(dll_by_engine[name])}
              for name, s in series_by_engine.items()}
    rows = []
    for a, b in itertools.combinations(sorted(series_by_engine), 2):
        both_active = sorted(traded[a] & traded[b])
        # correlation on the union calendar (0-filled), which is the economically
        # correct daily series; both_active is what the sufficiency gate counts.
        r = _pearson(cols[a], cols[b])
        rows.append({
            "pair": f"{a} × {b}",
            "a": a, "b": b,
            "days_both_active": len(both_active),
            "corr": round(r, 3) if r is not None else None,
            "loss_overlap": _overlap(loss[a], loss[b]),
            "breach_overlap": (_overlap(breach[a], breach[b])
                               if breach[a] or breach[b] else None),
        })
    return rows


def assess(series_by_engine: dict[str, dict], *, min_days: int = 20,
           corr_hi: float = 0.7, corr_lo: float = 0.3,
           dll_by_engine: dict | None = None,
           window_kind: str = "validation") -> dict:
    """Full trap-11 report + gate. Needs >= 2 engines.

    status:
      inconclusive — any pair has < min_days shared active days (no decorrelation
                     claim permitted), OR correlations land in the partial band.
      failed       — some pair moves together (|r| >= corr_hi): no diversification.
      passed       — every pair is decorrelated (|r| <= corr_lo) over enough days.
    """
    names = sorted(series_by_engine)
    if len(names) < 2:
        return {"status": "inconclusive", "engines": names,
                "verdict": "trap 11 vergelijkt minstens twee engines — geef er meer dan één",
                "pairs": [], "min_days": min_days}

    rows = pairwise(series_by_engine, dll_by_engine)
    active_days = len({d for s in series_by_engine.values() for d in s})
    min_pair_days = min(r["days_both_active"] for r in rows)
    rated = [r for r in rows if r["corr"] is not None]
    # Signed, not absolute: a strong NEGATIVE correlation is a hedge (great for a
    # portfolio); only strong POSITIVE correlation kills diversification. The worst
    # pair is the most positively-correlated one.
    max_corr = max((r["corr"] for r in rated), default=None)
    worst = max(rated, key=lambda r: r["corr"], default=None)

    win_note = ("" if window_kind != "validation" else
                " — gemeten op het validatievenster (pre-freeze); een forward-"
                "decorrelatieclaim vereist live dagen ná het bevriezen (D-18)")

    if min_pair_days < min_days:
        status = "inconclusive"
        verdict = (f"onvoldoende overlappende actieve dagen ({min_pair_days} < {min_days}) "
                   f"— geen decorrelatie-claim toegestaan (grondregel/CLAUDE.md)")
    elif max_corr is None:
        status = "inconclusive"
        verdict = "geen enkel paar had variantie op beide zijden — correlatie ongedefinieerd"
    elif max_corr >= corr_hi:
        status = "failed"
        verdict = (f"engines bewegen samen ({worst['pair']}: r = {max_corr:+.2f} ≥ "
                   f"{corr_hi:.2f}) — geen diversificatiewaarde{win_note}")
    elif max_corr <= corr_lo:
        status = "passed"
        verdict = (f"gedecorreleerd (hoogste paar-r = {max_corr:+.2f} ≤ {corr_lo:.2f}) "
                   f"over ≥{min_days} dagen — diversificatie aangetoond{win_note}")
    else:
        status = "inconclusive"
        verdict = (f"gedeeltelijke correlatie ({worst['pair']}: r = {max_corr:+.2f}, band "
                   f"{corr_lo:.2f}–{corr_hi:.2f}) — zwakke diversificatie{win_note}")

    return {
        "status": status, "verdict": verdict, "engines": names,
        "active_days": active_days, "min_pair_days": min_pair_days,
        "min_days": min_days, "corr_hi": corr_hi, "corr_lo": corr_lo,
        "max_corr": round(max_corr, 3) if max_corr is not None else None,
        "worst_pair": worst["pair"] if worst else None,
        "window_kind": window_kind, "pairs": rows,
    }
