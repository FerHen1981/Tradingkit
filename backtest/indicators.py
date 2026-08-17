"""Vectorised indicator layer (repaint-free, matching the Pine logic).

Everything here is computed once, up front, from confirmed-bar data. The
sequential order/position/account state machine in ``engine.py`` then consumes
these columns bar by bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config


def _pivot_confirmed(values: np.ndarray, k: int, kind: str) -> np.ndarray:
    """Replicate ta.pivotlow/pivothigh(src, k, k) followed by fixnan().

    A pivot at bar b needs k strictly-more-extreme bars on both sides and is
    only *confirmed* k bars later (at b+k). Returns, for every bar i, the price
    of the most recently confirmed pivot as of bar i (NaN before the first).
    """
    n = len(values)
    out = np.full(n, np.nan)
    last = np.nan
    for i in range(n):
        b = i - k                      # candidate pivot bar (confirmed now, at i)
        if b - k >= 0 and b + k < n:   # full window available
            centre = values[b]
            left = values[b - k:b]
            right = values[b + 1:b + k + 1]
            if kind == "low":
                if centre < left.min() and centre < right.min():
                    last = centre
            else:
                if centre > left.max() and centre > right.max():
                    last = centre
        out[i] = last
    return out


def _run_length_positive(delta: np.ndarray) -> np.ndarray:
    """Consecutive count (incl. current) of strictly-positive delta bars."""
    n = len(delta)
    out = np.zeros(n, dtype=np.int64)
    run = 0
    for i in range(n):
        run = run + 1 if delta[i] > 0 else 0
        out[i] = run
    return out


def _run_length_negative(delta: np.ndarray) -> np.ndarray:
    n = len(delta)
    out = np.zeros(n, dtype=np.int64)
    run = 0
    for i in range(n):
        run = run + 1 if delta[i] < 0 else 0
        out[i] = run
    return out


def _ema(x: np.ndarray, length: int) -> np.ndarray:
    """Exponential moving average (alpha = 2/(n+1)), seeded with the first value."""
    n = max(int(length), 1)
    alpha = 2.0 / (n + 1.0)
    out = np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + alpha * (x[i] - out[i - 1])
    return out


def _atr(high, low, close, length):
    """Wilder's ATR (RMA of true range), matching Pine ta.atr."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        pc = close[i - 1]
        tr[i] = max(high[i] - low[i], abs(high[i] - pc), abs(low[i] - pc))
    atr = np.empty(n)
    atr[0] = tr[0]
    alpha = 1.0 / length
    for i in range(1, n):
        atr[i] = atr[i - 1] + alpha * (tr[i] - atr[i - 1])
    return atr


def _session_vwap(hlc3: np.ndarray, vol: np.ndarray, new_session: np.ndarray) -> np.ndarray:
    n = len(hlc3)
    out = np.full(n, np.nan)
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(n):
        if new_session[i]:
            cum_pv = 0.0
            cum_v = 0.0
        cum_pv += hlc3[i] * vol[i]
        cum_v += vol[i]
        out[i] = cum_pv / cum_v if cum_v > 0 else hlc3[i]
    return out


def compute(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    d = df
    high = d["High"].to_numpy(dtype=float)
    low = d["Low"].to_numpy(dtype=float)
    close = d["Close"].to_numpy(dtype=float)
    vol = d["Volume"].to_numpy(dtype=float)
    delta = d["Delta"].to_numpy(dtype=float)
    new_session = d["new_session"].to_numpy(dtype=bool)
    mintick = cfg.contract.mintick
    n = len(d)

    out = pd.DataFrame(index=d.index)

    # --- Fair-value gap (3-bar) ------------------------------------------------
    # bullish: low[i] >= high[i-2]  -> gap (top=low[i], bottom=high[i-2])
    # bearish: low[i-2] >= high[i]  -> gap (top=low[i-2], bottom=high[i])
    h2 = np.concatenate([[np.nan, np.nan], high[:-2]])
    l2 = np.concatenate([[np.nan, np.nan], low[:-2]])
    fvg_dir = np.zeros(n, dtype=np.int64)
    fvg_top = np.full(n, np.nan)
    fvg_bot = np.full(n, np.nan)
    bull = low >= h2
    bear = l2 >= high
    fvg_dir = np.where(bear & ~bull, -1, np.where(bull, 1, 0))
    fvg_dir[:2] = 0
    fvg_top = np.where(fvg_dir > 0, low, np.where(fvg_dir < 0, l2, np.nan))
    fvg_bot = np.where(fvg_dir > 0, h2, np.where(fvg_dir < 0, high, np.nan))
    fvg_size = np.abs(fvg_top - fvg_bot)
    fvg_mid = (fvg_top + fvg_bot) / 2.0

    # Gap-size thresholds are unit_mode-aware. For %/ATR they are PER-BAR so the
    # filter scales with price / volatility — essential for high-price (BTC) or
    # 5x-price-range assets where fixed ticks/points don't fit. Ticks mode is
    # unchanged (scalar), so NQ/ES/GC behaviour is identical.
    atr = _atr(high, low, close, cfg.atr_len)
    if cfg.unit_mode == "ATR":
        gmin = cfg.gap_min_ticks * atr
        gmax = cfg.gap_max_ticks * atr
    elif cfg.unit_mode == "%":
        gmin = close * cfg.gap_min_ticks / 100.0
        gmax = close * cfg.gap_max_ticks / 100.0
    elif cfg.unit_mode == "Points":
        gmin = cfg.gap_min_ticks
        gmax = cfg.gap_max_ticks
    else:  # Ticks
        gmin = cfg.ticks(cfg.gap_min_ticks)
        gmax = cfg.ticks(cfg.gap_max_ticks)
    if cfg.use_gap_filter:
        fvg_pass = (~np.isnan(fvg_size)) & (fvg_size >= gmin) & (fvg_size <= gmax) & (fvg_size > 0)
    else:
        fvg_pass = fvg_dir != 0

    out["fvg_dir"] = fvg_dir
    out["fvg_top"] = fvg_top
    out["fvg_bot"] = fvg_bot
    out["fvg_mid"] = fvg_mid
    out["fvg_pass"] = fvg_pass

    # --- Swing pivots (confirmed) ---------------------------------------------
    out["piv_low"] = _pivot_confirmed(low, cfg.pivot_k, "low")
    out["piv_high"] = _pivot_confirmed(high, cfg.pivot_k, "high")

    # --- Session VWAP ----------------------------------------------------------
    hlc3 = (high + low + close) / 3.0
    out["vwap"] = _session_vwap(hlc3, vol, new_session)

    # --- Volume-delta direction + streak --------------------------------------
    bull_run = _run_length_positive(delta)
    bear_run = _run_length_negative(delta)
    if cfg.use_cvd_filter:
        if cfg.use_cvd_streak:
            bull_cvd = bull_run >= cfg.cvd_trend_count
            bear_cvd = bear_run >= cfg.cvd_trend_count
        else:
            bull_cvd = delta > 0
            bear_cvd = delta < 0
    else:
        bull_cvd = np.ones(n, dtype=bool)
        bear_cvd = np.ones(n, dtype=bool)
    out["bull_cvd"] = bull_cvd
    out["bear_cvd"] = bear_cvd

    # --- ATR (computed above; reused for the ATR unit mode) -------------------
    out["atr"] = atr

    # --- VWAP veto -------------------------------------------------------------
    if cfg.use_vwap_veto:
        out["veto_long"] = close > out["vwap"].to_numpy()
        out["veto_short"] = close < out["vwap"].to_numpy()
    else:
        out["veto_long"] = True
        out["veto_short"] = True

    # --- EMA crossover entry (Level B generator) ------------------------------
    if cfg.use_ema_cross:
        ef = _ema(close, cfg.ema_fast)
        es = _ema(close, cfg.ema_slow)
        above = ef > es
        cross = np.zeros(n, dtype=np.int64)
        cross[1:] = np.where(above[1:] & ~above[:-1], 1,
                             np.where(~above[1:] & above[:-1], -1, 0))
        out["ema_cross_dir"] = cross
    else:
        out["ema_cross_dir"] = np.zeros(n, dtype=np.int64)

    return out
