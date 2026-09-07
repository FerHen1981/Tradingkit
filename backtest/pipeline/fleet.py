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

# name -> (symbol, qty, fvg_min, fvg_max, cvd_n, stop, R, expiry, day_exit, act, give, cap,
#          regime, firm_program, sunday)
_SPEC = {
    "EL_BANDIDO_MYM_HF_EOD":     ("MYM", 5,  4,  8, 3, 160, 1.50, 18, "Day-cap (hard target)", 500, 150, 1000, "All sessions", "apex_50k_eod_pa", True),
    "EL_LEON_MYM_CON_EOD_Q2":    ("MYM", 2, 12, 20, 6, 480, 1.25, 24, "Off",                   500, 150,  750, "All sessions", "apex_50k_eod_pa", True),
    "EL_LEON_MYM_CON_INTRA_Q2":  ("MYM", 2, 12, 20, 6, 480, 1.25, 24, "Off",                   500, 150,  750, "All sessions", "apex_50k_intraday_pa", True),
    "EL_LEON_MYM_PROD_EOD":      ("MYM", 3, 12, 20, 6, 480, 1.25, 24, "Off",                   500, 150,  750, "All sessions", "apex_50k_eod_pa", True),
    "EL_MATADOR_MES_PROD_EOD":   ("MES", 6, 10, 22, 6, 120, 1.75,  6, "Off",                   500, 150,  750, "All sessions", "apex_50k_eod_pa", True),
    "EL_PATRON_MGC_AGG_EOD":     ("MGC", 8, 11, 16, 5, 120, 2.25, 12, "Trail + cap",           500, 100,  750, "Liquidity Core", "apex_50k_eod_pa", False),
    "EL_REY_MNQ_PROD_EOD":       ("MNQ", 6,  2,  8, 8, 200, 1.25,  6, "Off",                   500, 150,  750, "All sessions", "apex_50k_eod_pa", True),
    "EL_REY_MNQ_PROD_INTRA":     ("MNQ", 6,  2,  8, 8, 200, 1.25,  6, "Off",                   500, 150,  750, "All sessions", "apex_50k_intraday_pa", True),
    "EL_TESORO_MGC_CON_EOD":     ("MGC", 7, 11, 16, 6, 140, 2.25, 12, "Trail + cap",           500, 100,  750, "Liquidity Core", "apex_50k_eod_pa", False),
}

# Pine-parity pending before live PA deployment (README of the package).
PARITY_PENDING = {"EL_BANDIDO_MYM_HF_EOD"}

# Defects in the released .pine sources that this mirror had to work around.
# Recorded rather than silently normalised: stage 1 may not claim parity with a
# script whose inputs we reinterpreted. `pine/**` is Pine Dev's map — reported,
# not patched (docs/inbox.md 18). The mechanism is kept for future defects.
#
# BANDIDO's day_exit_mode defect is CLOSED (D-61, Pine Dev 25-08): the released
# script had input.string("Cap only", ...) — a defval outside its own options list,
# which does not compile in Pine v6. Pine Dev fixed the source to a valid
# "Day-cap (hard target)", exactly the value this mirror already carried, so the
# interpretation is no longer an interpretation and the exception is removed.
PINE_DEFECTS: dict[str, str] = {}


def engine_config(name: str) -> Config:
    """The Config that mirrors one released Pine script, 1:1."""
    (sym, qty, gmin, gmax, cvdn, stop, r, expiry, dex, act, give, cap,
     regime, program, sunday) = _SPEC[name]
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
        # session window — transcribed, not inherited from Config's defaults.
        # Seven of the nine trade the Sunday Globex open (ET weekday 6); PATRON
        # and TESORO do not. Leaving this to the default Mon-Fri silently drops
        # every Sunday-evening entry, which is a real slice of the trade count.
        trade_days=((6, 0, 1, 2, 3, 4) if sunday else (0, 1, 2, 3, 4)),
        enabled_hours=frozenset(set(range(24)) - {17}),   # 17:00 ET daily break
        use_auto_flat=True, flat_from=(16, 55), flat_until=(18, 0),
        # account layer — transcribed, and it MATTERS for the trade list: the PA
        # daily loss limit closes an open position, so leaving it implicit turns
        # every DLL exit into a full stop-out. Uniform across all nine.
        acct_trail_dd=2000.0, acct_dll=1000.0, consistency_pct=50.0,
        min_payout=500.0, payout_buffer=500.0,
        use_wait_for_cap=True, use_mae_guard=False,
        # account model — the scripts run with "Use firm preset" ON, so the
        # drawdown model comes from the firm program, NOT from the loose input
        # (whose default is "Intraday" in all nine). See drawdown_model().
        dd_model=drawdown_model(program),
        phase="Apex PA",
    )


_DD_BY_TYPE = {"eod_trailing": "EOD", "intraday_trailing": "Intraday",
               "static": "Static"}


def drawdown_model(program: str) -> str:
    """The drawdown model a firm program implies, read from data/propfirms.json.

    All nine scripts ship with "Use firm preset (fills account rules below)" ON,
    so `f_firmRules` overwrites the loose "Drawdown Model" input at runtime
    (Pine Dev, D-20 / 2026-08-20). Reading the input default instead would put
    every engine on Intraday and silently mis-model seven of them."""
    try:
        from ..firms import raw_programs
        for prog in raw_programs():
            if prog.get("key") == program:
                tl = prog.get("targets_limits") or {}
                dt = tl.get("drawdown_type")
                if dt in _DD_BY_TYPE:
                    return _DD_BY_TYPE[dt]
    except Exception:
        pass
    # Fall back to the key itself rather than guessing Intraday for everything.
    return "Intraday" if "intraday" in program else "EOD"


def firm_program(name: str) -> str:
    return _SPEC[name][13]


def trades_sunday(name: str) -> bool:
    return _SPEC[name][14]


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
                    "firm_program": s[13], "dd_model": drawdown_model(s[13]),
                    "sunday": s[14],
                    "parity_pending": n in PARITY_PENDING,
                    "pine_defect": PINE_DEFECTS.get(n, "")})
    return out


# --- price-series substitution -------------------------------------------------
# A micro and its mini share a tick size and differ only by point value (exactly
# 10x for ES/NQ/YM/GC). Every distance the fleet uses is in TICKS and the target
# is an R-multiple, so the two produce the SAME trade sequence on the same prices:
# measured on 1,051,200 bars, MES and ES gave 295/295 trades, identical win rate
# and identical long/short split. Only the dollar P&L scales — and PF moved by
# 0.01 purely because commission is a flat per-contract cost that does not scale.
#
# That holds for the CONTRACT SPEC. It does NOT hold for the BARS, and for this
# fleet that distinction decides stage 1.
#
# MEASURED, 24-08: on ES data MATADOR matched only 46 of 121 Pine entries. Of the
# 75 it missed, 39 were unavailable (we held a position), 1 was a limit that
# never filled, and all 35 remaining ones had NO FVG OF THAT DIRECTION in our
# window. Our detection is not at fault: transcribed literally from the Pine
# source and compared over 520,861 bars it is identical — same direction, same
# size, same band-pass, 17,417 in-band gaps on both sides.
#
# So Pine saw gaps where ES has none, which means the bars differ. That is not
# noise but microstructure: a fair-value gap IS a liquidity artefact, and MES is
# a thinner book than ES. A minute where the micro prints a 12-tick gap is a
# minute where the mini, with far more participants, traded through every tick.
#
# Conclusion: the twin route is fine for stage 2+ (statistical properties) but
# CANNOT establish stage-1 parity for a gap-based strategy. That gate needs the
# real market's bars. The substitution stays available — it is never silent, the
# CLI says so and the artifact records it — but stage 1 warns.
_TWIN = {"MES": "ES", "MYM": "YM", "MNQ": "NQ", "MGC": "GC", "M2K": "RTY"}
TWIN = {**_TWIN, **{v: k for k, v in _TWIN.items()}}


# Signal generation that depends on gaps between bars — see the note above.
GAP_BASED = True


def acceptable_symbols(name: str) -> tuple[str, str | None]:
    """(the engine's own market, its price-series twin or None)."""
    m = market(name)
    return m, TWIN.get(m)
