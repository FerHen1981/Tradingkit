"""Stage 0 — data audit.

Gate: coverage, timezone, OHLC continuity, volume/Delta coverage, tick size,
point value, commission and roll artefacts established; a normalized dataset and
a quality report exist.

Nothing downstream is trustworthy if the data underneath is not understood, so
this stage reports rather than judges: it states what the data IS, and flags the
conditions that would silently corrupt later stages (a dead Delta column, gaps
in coverage, prices that jump on a contract roll).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import contract


def audit(df: pd.DataFrame, symbol: str = "") -> dict:
    """Data-quality report for one normalized dataset."""
    n = len(df)
    et = df["et"]
    out: dict = {"bars": n, "symbol": symbol,
                 "first": str(et.iloc[0]), "last": str(et.iloc[-1]),
                 "timezone": str(et.dt.tz), "findings": []}
    add = lambda sev, msg, **ev: out["findings"].append({"severity": sev, "message": msg, "evidence": ev})

    # --- coverage ------------------------------------------------------------
    span_days = (et.iloc[-1] - et.iloc[0]).days
    sessions = df["session_date"].nunique() if "session_date" in df.columns else None
    out["span_days"] = span_days
    out["sessions"] = int(sessions) if sessions is not None else None
    out["years"] = round(span_days / 365.25, 1)
    if out["timezone"] is None or "New_York" not in str(out["timezone"]):
        add("high", f"Timestamps are not in America/New_York ({out['timezone']}) — the 18:00 ET "
                    "session boundary cannot be trusted.", tz=str(out["timezone"]))

    # --- continuity: missing minutes inside a session ------------------------
    d = et.diff().dropna()
    step = d.mode().iloc[0] if len(d) else pd.Timedelta(minutes=1)
    out["bar_interval"] = str(step)
    gaps = d[d > step]
    big = d[d > pd.Timedelta(hours=6)]          # weekends/holidays are expected
    out["gaps_over_interval"] = int(len(gaps))
    out["gaps_over_6h"] = int(len(big))
    intra = gaps[gaps <= pd.Timedelta(hours=6)]
    out["intrasession_gap_minutes"] = int(intra.sum().total_seconds() // 60) if len(intra) else 0
    if len(intra):
        add("medium", f"{len(intra):,} gaps inside sessions "
                      f"({out['intrasession_gap_minutes']:,} missing minutes) — thin or halted periods.",
            count=int(len(intra)))

    # --- OHLC sanity ---------------------------------------------------------
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    bad = int(np.sum((h < l) | (h < o) | (h < c) | (l > o) | (l > c)))
    out["ohlc_violations"] = bad
    if bad:
        add("high", f"{bad:,} bars violate OHLC ordering (high<low or open/close outside range).", n=bad)
    flat = int(np.sum((h == l) & (o == c)))
    out["flat_bars"] = flat
    out["flat_bars_pct"] = round(100 * flat / n, 2) if n else 0.0

    # --- volume / Delta coverage --------------------------------------------
    for col in ("Volume", "Delta", "CVD_close"):
        if col not in df.columns:
            out[f"{col}_present"] = False
            continue
        v = df[col].to_numpy(float)
        nz = int(np.count_nonzero(v))
        out[f"{col}_present"] = True
        out[f"{col}_nonzero_pct"] = round(100 * nz / n, 2) if n else 0.0
    if out.get("Delta_present") and out.get("Delta_nonzero_pct", 0) < 1.0:
        add("high", "The native Delta column is effectively empty "
                    f"({out.get('Delta_nonzero_pct')}% non-zero). Any CVD filter driven from it "
                    "would block every trade. The canonical OHLCV polarity proxy is unaffected "
                    "and is what the pipeline uses (ground rule 4).",
            nonzero_pct=out.get("Delta_nonzero_pct"))

    # --- contract spec -------------------------------------------------------
    if symbol:
        try:
            ct = contract(symbol)
            out["contract"] = {"symbol": ct.symbol, "mintick": ct.mintick,
                               "pointvalue": ct.pointvalue, "commission": ct.commission_per_contract}
            rng = float(np.nanmedian(h - l)) / ct.mintick if ct.mintick else 0
            out["median_bar_range_ticks"] = round(rng, 1)
            if rng and (rng < 1 or rng > 200):
                add("high", f"Median bar range is {rng:.0f} ticks for {ct.symbol} — the tick size "
                            "in CONTRACTS is likely wrong for this data.", median_ticks=round(rng, 1))
        except KeyError:
            add("high", f"Symbol {symbol!r} is not in backtest.config CONTRACTS — tick size, point "
                        "value and commission are unknown, so every dollar figure would be wrong.")
    else:
        add("medium", "No symbol on this dataset — contract specs cannot be verified.")

    # --- contract roll artefacts --------------------------------------------
    prev_close = np.concatenate([[np.nan], c[:-1]])
    jump = np.abs(c - prev_close)
    med_rng = float(np.nanmedian(h - l)) or 1.0
    rolls = int(np.sum(jump > 10 * med_rng))
    out["roll_like_jumps"] = rolls
    if rolls:
        add("medium", f"{rolls} bar-to-bar jumps larger than 10x the median bar range — likely "
                      "contract rolls; check whether the series is back-adjusted.", count=rolls)

    sev = {f["severity"] for f in out["findings"]}
    out["verdict"] = "high" in sev and "attention" or ("clean" if not sev else "notes")
    return out
