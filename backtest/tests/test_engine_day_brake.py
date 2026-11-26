"""Day loss-brake parity with Pine v3.8.0 (D-113).

Before D-113 `engine.py` modelled Pine's DELETED `dllHit`: it halted the day when
raw running-P&L crossed `-cfg.acct_dll` (the firm value). The live scripts brake on
the STRICTEST of the owner-rem (`sl_per_contract × stops × qty`) and the firm DLL,
measured on `lossBasisEff` (min of realized and running), not raw running-P&L.

These tests drive `Engine._account` directly with crafted account state so the brake
point is exact and independent of signal/fill logic. `_open_profit` is stubbed where a
floating position is needed; everywhere else the position is flat so running == realized.
"""
from __future__ import annotations

import numpy as np

from backtest.config import Config
from backtest.engine import Engine


def _arrays(n: int = 1, close: float = 100.0) -> dict:
    """The minimal numpy-array bundle Engine.__init__ reads directly (bypasses extract)."""
    f = np.zeros(n, dtype=float)
    b = np.zeros(n, dtype=bool)
    i = np.zeros(n, dtype=np.int64)
    return {
        "open": f.copy(), "high": f.copy(), "low": f.copy(),
        "close": np.full(n, close, dtype=float),
        "time": i.copy(), "mod": i.copy(), "weekday": i.copy(), "new_session": b.copy(),
        "fvg_dir": i.copy(), "fvg_top": f.copy(), "fvg_bot": f.copy(), "fvg_mid": f.copy(),
        "fvg_pass": b.copy(), "piv_low": f.copy(), "piv_high": f.copy(), "atr": f.copy(),
        "bull_cvd": b.copy(), "bear_cvd": b.copy(),
        "veto_long": b.copy(), "veto_short": b.copy(), "regime_ok": np.ones(n, dtype=bool),
    }


def _pa_engine(**cfg_kw) -> Engine:
    base = dict(name="BRAKE_TEST", phase="Apex PA", dd_model="EOD",
                acct_dll=1000.0, acct_trail_dd=2000.0, contract_size=2.0,
                day_exit_mode="Off")          # isolate the DLL brake from day-trail/cap
    base.update(cfg_kw)
    eng = Engine(Config(**base), arrays=_arrays())
    eng.risk_base = 0.0                        # today_real = net_profit - risk_base
    return eng


def _halted_at(eng: Engine, net_profit: float) -> bool:
    eng.net_profit = net_profit
    eng.day_halted = False
    eng.halt_reason = ""
    eng._account(0)
    return eng.day_halted and eng.halt_reason == "PA Daily Loss Limit"


# --- owner-rem binds when it is the stricter of the two ----------------------
def test_owner_rem_brakes_before_the_firm_dll():
    # qty 2 -> owner-rem = 100 * 4 * 2 = $800 < firm $1000, so $800 binds.
    eng = _pa_engine(contract_size=2.0)
    assert not _halted_at(eng, -750.0), "should not halt above the $800 owner-rem"
    assert _halted_at(eng, -850.0), "should halt once past the $800 owner-rem"


# --- firm DLL binds when the owner-rem is looser -----------------------------
def test_firm_dll_binds_when_owner_rem_is_looser():
    # qty 3 -> owner-rem = 100 * 4 * 3 = $1200 > firm $1000, so $1000 binds.
    eng = _pa_engine(contract_size=3.0)
    assert not _halted_at(eng, -950.0), "should not halt above the $1000 firm DLL"
    assert _halted_at(eng, -1050.0), "should halt once past the $1000 firm DLL"


# --- the override replaces the formula ---------------------------------------
def test_owner_dll_override_sets_the_limit():
    eng = _pa_engine(contract_size=3.0, owner_dll_override=600.0)
    assert not _halted_at(eng, -550.0)
    assert _halted_at(eng, -650.0), "override of $600 should bind below both formula and firm"


# --- the brake measures lossBasisEff, not raw running-P&L --------------------
def test_brake_measures_realized_loss_not_running_with_open_profit():
    # Realized -$1200, +$500 floating -> running -$700. The OLD engine braked on
    # running (-700 > -1000 firm) and would NOT halt. lossBasisEff = min(realized,
    # running) = -1200 <= -1000, so the parity engine halts. qty 3 keeps the owner-rem
    # ($1200) looser than the firm ($1000) so the firm value is the binding limit.
    eng = _pa_engine(contract_size=3.0)
    eng.pos = 1.0
    eng._open_profit = lambda i: 500.0
    assert _halted_at(eng, -1200.0), "deep realized loss must halt despite open profit"


# --- both terms absent -> no brake at all ------------------------------------
def test_no_brake_when_owner_disabled_and_firm_inactive():
    # Apex Eval Intraday -> firm_dll_active is False (not PA, not EOD-eval); with the
    # owner-rem disabled there is no daily loss limit and the day never halts on loss.
    eng = _pa_engine(phase="Apex Eval", dd_model="Intraday", owner_dll_enabled=False)
    eng.net_profit = -5000.0
    eng.day_halted = False
    eng.halt_reason = ""
    eng._account(0)
    assert not eng.day_halted, "no owner-rem and no firm DLL -> no day-loss brake"
