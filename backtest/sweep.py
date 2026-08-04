"""Parameter sweeps.

Money-management parameters (R-multiple, break-even, trailing, day-trail, TP)
do NOT affect the indicator layer, so for those sweeps we compute indicators and
extract arrays ONCE and only re-run the engine per variant — a big speed-up.

Signal parameters (gap size, confirm_bars, cvd, vwap) DO affect indicators; pass
``recompute_indicators=True`` for those.
"""
from __future__ import annotations

import pandas as pd

from .config import Config
from .engine import Engine, extract
from . import indicators as ind_mod
from .metrics import kpis


def run_variant(df, base_ind_arrays, cfg: Config, research: bool = False,
                df_for_ind: pd.DataFrame = None, recompute_indicators: bool = False):
    if recompute_indicators:
        ind = ind_mod.compute(df_for_ind, cfg)
        arrays = extract(df_for_ind, ind)
    else:
        arrays = base_ind_arrays
    eng = Engine(cfg, research_mode=research, arrays=arrays)
    res = eng.run()
    k = kpis(res)
    k["banked"] = round(res.pa_total_banked, 0)
    k["breaches"] = res.pa_breach_count
    k["milk"] = res.pa_milk_count
    return k


def mm_sweep(df, base_cfg: Config, variants: list[tuple[str, dict]], research: bool = False):
    """variants: list of (label, override-dict). Indicators computed once from base_cfg."""
    ind = ind_mod.compute(df, base_cfg)
    arrays = extract(df, ind)
    rows = []
    for label, ov in variants:
        cfg = base_cfg.with_(**ov)
        k = run_variant(df, arrays, cfg, research=research)
        k["label"] = label
        rows.append(k)
    return rows


def print_table(rows: list[dict], cols=None):
    cols = cols or ["label", "trades", "win_rate_pct", "profit_factor", "expectancy",
                    "net_profit", "max_drawdown", "banked", "breaches"]
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print("  " + "  ".join(c.ljust(widths[c]) for c in cols))
    print("  " + "  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  " + "  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
