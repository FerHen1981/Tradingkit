"""The v1_0_0 fleet, transcribed from MEX_FLEET_PACKAGE_2026-08-23/01_Scripts.

These are NOT tuned values — they are the exact inputs of the released Pine
scripts, so the Python engine has something to be at parity WITH (stage 1). The
Pine files themselves stay in Pine Dev's map; this module is the backtest-side
mirror and must be updated only when a released script changes.

Uniform across all nine (verified by parsing every .pine): CVD filter ON with a
streak, FVG size filter ON, break-even OFF, trailing OFF, TP = R-multiple,
stop = fixed, pivot k = 3, drawdown model = Intraday, entry = limit @ 50% FVG.
The differences that matter are per market: FVG band, CVD count, stop, R, expiry,
quantity and the day-exit block.
"""
from __future__ import annotations

from ..config import Config, contract

# name -> (symbol, qty, fvg_min, fvg_max, cvd_n, stop, R, expiry, day_exit, act, give, cap, regime)
_SPEC = {
    "EL_BANDIDO_MYM_HF_EOD":     ("MYM", 5,  4,  8, 3, 160, 1.50, 18, "Day-cap (hard target)", 500, 150, 1000, "All sessions"),
    "EL_LEON_MYM_CON_EOD_Q2":    ("MYM", 2, 12, 20, 6, 480, 1.25, 24, "Off",                   500, 150,  750, "All sessions"),
    "EL_LEON_MYM_CON_INTRA_Q2":  ("MYM", 2, 12, 20, 6, 480, 1.25, 24, "Off",                   500, 150,  750, "All sessions"),
    "EL_LEON_MYM_PROD_EOD":      ("MYM", 3, 12, 20, 6, 480, 1.25, 24, "Off",                   500, 150,  750, "All sessions"),
    "EL_MATADOR_MES_PROD_EOD":   ("MES", 6, 10, 22, 6, 120, 1.75,  6, "Off",                   500, 150,  750, "All sessions"),
    "EL_PATRON_MGC_AGG_EOD":     ("MGC", 8, 11, 16, 5, 120, 2.25, 12, "Trail + cap",           500, 100,  750, "Liquidity Core"),
    "EL_REY_MNQ_PROD_EOD":       ("MNQ", 6,  2,  8, 8, 200, 1.25,  6, "Off",                   500, 150,  750, "All sessions"),
    "EL_REY_MNQ_PROD_INTRA":     ("MNQ", 6,  2,  8, 8, 200, 1.25,  6, "Off",                   500, 150,  750, "All sessions"),
    "EL_TESORO_MGC_CON_EOD":     ("MGC", 7, 11, 16, 6, 140, 2.25, 12, "Trail + cap",           500, 100,  750, "Liquidity Core"),
}

# Pine-parity pending before live PA deployment (README of the package).
PARITY_PENDING = {"EL_BANDIDO_MYM_HF_EOD"}


def engine_config(name: str) -> Config:
    """The Config that mirrors one released Pine script, 1:1."""
    sym, qty, gmin, gmax, cvdn, stop, r, expiry, dex, act, give, cap, regime = _SPEC[name]
    return Config(
        name=name,
        contract=contract(sym),
        contract_size=float(qty),
        unit_mode="Ticks",
        # entry: limit at the FVG midpoint, expiring after N bars
        entry_limit_mode=True,
        expiry_bars=int(expiry),
        use_fill_check=True,
        # signal filters
        use_gap_filter=True, gap_min_ticks=float(gmin), gap_max_ticks=float(gmax),
        use_cvd_filter=True, use_cvd_streak=True, cvd_trend_count=int(cvdn),
        cvd_source="proxy",            # canonical OHLCV polarity proxy (v7 rule 4)
        # stop / target
        stop_swing=False, fixed_stop_ticks=float(stop), max_stop_ticks=float(stop),
        pivot_k=3, swing_buf_ticks=2.0,
        tp_mode="R-multiple", r_multiple=float(r),
        use_breakeven=False, use_trail=False,
        # daily management
        day_exit_mode=dex, day_trail_model="Activation + giveback",
        day_trail_activation_usd=float(act), day_trail_giveback_usd=float(give),
        day_cap_usd=float(cap),
        # account model
        dd_model="Intraday",
        phase="Apex PA",
    )


def names() -> list[str]:
    return sorted(_SPEC)


def market(name: str) -> str:
    return _SPEC[name][0]


def summary() -> list[dict]:
    """One row per released engine — what the UI lists as pipeline input."""
    out = []
    for n, s in sorted(_SPEC.items()):
        out.append({"name": n, "market": s[0], "qty": s[1],
                    "fvg": f"{s[2]}-{s[3]}", "cvd": s[4], "stop": s[5], "r": s[6],
                    "expiry": s[7], "day_exit": s[8], "regime": s[12],
                    "parity_pending": n in PARITY_PENDING})
    return out
