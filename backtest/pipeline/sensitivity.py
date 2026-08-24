"""How much does this engine's trade list move when prices move one tick?

Stage 1 asks whether the Python engine reproduces the Pine engine. That question
only has a clean answer when both run on the SAME bars. When a mini's history
stands in for its micro (fleet.TWIN), the bars are NOT the same: ES and MES are
separate order books that agree on price but not always on the tick.

Whether that matters is an empirical question about the strategy, not a matter
of opinion, and it is answerable without any MES data: perturb the series we do
have by a tick and see how much of the trade list survives. Three mechanics in
this fleet compound tick sensitivity —

  * entry is a LIMIT at 50% of the gap: one tick decides fill or no fill;
  * the FVG size filter is a narrow tick band (10-22 on MATADOR): one tick moves
    a gap in or out of the band;
  * the canonical CVD proxy is sign(close - open) with a streak requirement: on a
    bar that closes at its open, one tick flips polarity and breaks the streak.

If a one-tick jitter already rewrites half the trade list, then a substitute
price series can never establish trade-level parity, and stage 1 needs the real
market's bars. That is a finding about the METHOD, not a failure of the engine.
"""
from __future__ import annotations

import numpy as np


def jitter(df, mintick: float, prob: float = 0.35, seed: int = 0):
    """A copy of `df` where some bars differ by one tick.

    Models the disagreement between two venues quoting the same instrument:
    each of open/high/low/close may independently sit a tick either side. OHLC
    consistency is restored afterwards so the result is still a valid bar."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    n = len(out)
    for col in ("Open", "High", "Low", "Close"):
        step = rng.choice([-1.0, 0.0, 1.0], size=n, p=[prob / 2, 1 - prob, prob / 2])
        out[col] = out[col].to_numpy() + step * mintick
    hi = np.maximum.reduce([out["High"].to_numpy(), out["Open"].to_numpy(),
                            out["Close"].to_numpy()])
    lo = np.minimum.reduce([out["Low"].to_numpy(), out["Open"].to_numpy(),
                            out["Close"].to_numpy()])
    out["High"], out["Low"] = hi, lo
    return out


def _keys(trades, minutes=1):
    """(entry minute bucket, direction) per closed trade."""
    import pandas as pd
    out = []
    for t in trades:
        if getattr(t, "exit_time", None) is None:
            continue
        ts = pd.Timestamp(t.entry_time)
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        out.append((int(ts.value // (60_000_000_000 * minutes)), int(t.dir)))
    return out


def survival(df, cfg, seeds=(1, 2, 3), prob: float = 0.35, progress=None) -> dict:
    """Fraction of the trade list that survives a one-tick jitter.

    Returns the baseline trade count, and per seed how many trades still appear
    at the same entry bar and direction."""
    from .. import indicators as im
    from ..engine import Engine

    base_res = Engine(cfg, df, im.compute(df, cfg), research_mode=False).run()
    base = base_res.trades
    base_keys = _keys(base)
    base_oc = base_res.order_counts or {}
    base_set = set(base_keys)
    rows = []
    for i, seed in enumerate(seeds):
        if progress:
            progress(i, len(seeds))
        jdf = jitter(df, cfg.contract.mintick, prob=prob, seed=seed)
        gres = Engine(cfg, jdf, im.compute(jdf, cfg), research_mode=False).run()
        got_keys = _keys(gres.trades)
        kept = len(base_set & set(got_keys))
        oc = gres.order_counts or {}
        rows.append({"seed": seed, "trades": len(got_keys), "kept": kept,
                     "survival_pct": round(100 * kept / len(base_keys), 1)
                                     if base_keys else 0.0,
                     "placed": oc.get("placed"), "filled": oc.get("filled"),
                     "fill_pct": round(100 * oc["filled"] / oc["placed"], 1)
                                 if oc.get("placed") else None})
    surv = [r["survival_pct"] for r in rows]
    fills = [r["fill_pct"] for r in rows if r["fill_pct"] is not None]
    base_fill = (round(100 * base_oc["filled"] / base_oc["placed"], 1)
                 if base_oc.get("placed") else None)
    return {
        "baseline_trades": len(base_keys),
        "baseline_placed": base_oc.get("placed"),
        "baseline_fill_pct": base_fill,
        "fill_pct_range": [min(fills), max(fills)] if fills else None,
        "jitter_prob": prob,
        "runs": rows,
        "mean_survival_pct": round(sum(surv) / len(surv), 1) if surv else 0.0,
        "min_survival_pct": min(surv) if surv else 0.0,
    }


def verdict(r: dict) -> str:
    m = r["mean_survival_pct"]
    if m >= 90:
        return ("robuust: een tick verschil verandert de tradelijst nauwelijks, dus een "
                "vervangende prijsreeks kan pariteit op trade-niveau dragen")
    if m >= 70:
        return ("gevoelig: een deel van de tradelijst verschuift door een tick, dus een "
                "vervangende reeks kost dekking maar sluit pariteit niet uit")
    return ("TICK-KRITISCH: een tick verschil herschrijft een groot deel van de tradelijst. "
            "Een vervangende prijsreeks kan NOOIT pariteit op trade-niveau aantonen — "
            "trap 1 heeft de bars van de echte markt nodig")
