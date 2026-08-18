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


def _ma(x: np.ndarray, length: int, kind: str = "EMA") -> np.ndarray:
    """Moving average — EMA (default) or SMA — as a full-length array."""
    n = max(int(length), 1)
    if kind == "SMA":
        return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()
    return _ema(x, n)


def _rsi(close: np.ndarray, length: int) -> np.ndarray:
    """Wilder RSI (0-100), seeded on the first diff. NaN at bar 0."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    avg_gain = avg_loss = 0.0
    L = max(int(length), 1)
    for i in range(1, n):
        ch = close[i] - close[i - 1]
        g = ch if ch > 0 else 0.0
        l = -ch if ch < 0 else 0.0
        if i == 1:
            avg_gain, avg_loss = g, l
        else:
            avg_gain = (avg_gain * (L - 1) + g) / L
            avg_loss = (avg_loss * (L - 1) + l) / L
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _cross_dir(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """+1 the bar `a` crosses above `b`, -1 the bar it crosses below, else 0."""
    n = len(a)
    above = a > b
    out = np.zeros(n, dtype=np.int64)
    out[1:] = np.where(above[1:] & ~above[:-1], 1,
                       np.where(~above[1:] & above[:-1], -1, 0))
    return out


def _order_block_dir(open_, high, low, close, atr, impulse_atr, max_age, mit_pct):
    """Order-block mitigation entry (continuation). An impulse bar (body >=
    impulse_atr*ATR) marks the last opposite candle before it as an OB zone;
    a later bar that trades back into that zone fires an entry. Lookahead-safe:
    the OB is built from bars <= i, mitigation is tested on the current bar, and
    an OB never fires on the bar that created it. One-shot per zone."""
    n = len(close)
    out = np.zeros(n, dtype=np.int64)
    bull_top = bull_bot = np.nan; bull_age = -1
    bear_top = bear_bot = np.nan; bear_age = -1
    for i in range(1, n):
        # age existing OBs, expire the stale ones
        if bull_age >= 0:
            bull_age += 1
            if bull_age > max_age:
                bull_top = bull_bot = np.nan; bull_age = -1
        if bear_age >= 0:
            bear_age += 1
            if bear_age > max_age:
                bear_top = bear_bot = np.nan; bear_age = -1
        # mitigation (OB set on a prior bar) -> fire, one-shot
        if not np.isnan(bull_top):
            trig = bull_top - mit_pct * (bull_top - bull_bot)
            if low[i] <= trig:
                out[i] = 1
                bull_top = bull_bot = np.nan; bull_age = -1
        if out[i] == 0 and not np.isnan(bear_top):
            trig = bear_bot + mit_pct * (bear_top - bear_bot)
            if high[i] >= trig:
                out[i] = -1
                bear_top = bear_bot = np.nan; bear_age = -1
        # detect a new impulse this bar -> record the opposite candle as the OB
        thr = impulse_atr * atr[i]
        if thr > 0:
            body = close[i] - open_[i]
            if body >= thr:                       # up-impulse -> bullish OB
                for j in range(i - 1, max(i - 6, -1), -1):
                    if close[j] < open_[j]:
                        bull_bot, bull_top, bull_age = low[j], high[j], 0
                        break
            elif -body >= thr:                    # down-impulse -> bearish OB
                for j in range(i - 1, max(i - 6, -1), -1):
                    if close[j] > open_[j]:
                        bear_bot, bear_top, bear_age = low[j], high[j], 0
                        break
    return out


def _cvd_div_dir(low, high, close, cvd, k):
    """Price/CVD divergence at confirmed pivots (reversal). Bullish = price lower
    low but CVD higher low; bearish = price higher high but CVD lower high. Uses
    the same pivot window as _pivot_confirmed (confirmed at b+k), so it is
    lookahead-safe and fires on the confirmation bar."""
    n = len(close)
    out = np.zeros(n, dtype=np.int64)
    prev_pl = prev_pl_cvd = np.nan
    prev_ph = prev_ph_cvd = np.nan
    for i in range(n):
        b = i - k
        if b - k < 0 or b + k >= n:
            continue
        cl = low[b]
        if cl < low[b - k:b].min() and cl < low[b + 1:b + k + 1].min():
            if not np.isnan(prev_pl) and cl < prev_pl and cvd[b] > prev_pl_cvd:
                out[i] = 1
            prev_pl, prev_pl_cvd = cl, cvd[b]
        ch = high[b]
        if ch > high[b - k:b].max() and ch > high[b + 1:b + k + 1].max():
            if out[i] == 0 and not np.isnan(prev_ph) and ch > prev_ph and cvd[b] < prev_ph_cvd:
                out[i] = -1
            prev_ph, prev_ph_cvd = ch, cvd[b]
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


def _adx(high, low, close, length):
    """Wilder's ADX (trend strength, 0-100). +DM/-DM and TR are Wilder-smoothed
    (RMA, alpha=1/length), +DI/-DI derived, DX = 100*|+DI--DI|/(+DI+-DI), and ADX
    is the RMA of DX. Matches Pine ta.adx conventions."""
    n = len(close)
    length = max(int(length), 1)
    tr = np.empty(n); pdm = np.zeros(n); mdm = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        pc = close[i - 1]
        tr[i] = max(high[i] - low[i], abs(high[i] - pc), abs(low[i] - pc))
    alpha = 1.0 / length
    atr = np.empty(n); rpdm = np.empty(n); rmdm = np.empty(n)
    atr[0], rpdm[0], rmdm[0] = tr[0], pdm[0], mdm[0]
    for i in range(1, n):
        atr[i] = atr[i - 1] + alpha * (tr[i] - atr[i - 1])
        rpdm[i] = rpdm[i - 1] + alpha * (pdm[i] - rpdm[i - 1])
        rmdm[i] = rmdm[i - 1] + alpha * (mdm[i] - rmdm[i - 1])
    eps = 1e-12
    pdi = 100.0 * rpdm / (atr + eps)
    mdi = 100.0 * rmdm / (atr + eps)
    dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi + eps)
    adx = np.empty(n); adx[0] = dx[0]
    for i in range(1, n):
        adx[i] = adx[i - 1] + alpha * (dx[i] - adx[i - 1])
    return adx


# Objective regime labels (framework §6). A defensible v1 subset of the full
# taxonomy — Transition/Exhaustion/Expansion are left for a later refinement.
REGIME_LABELS = ("Strong Bull Trend", "Controlled Bull Trend", "Strong Bear Trend",
                 "Controlled Bear Trend", "Compression", "Low-Volatility Range",
                 "High-Volatility Range", "Indecision")


def classify_regime(df: pd.DataFrame, cfg) -> dict:
    """L1 regime classifier — the framework's gatekeeper (lab/FRAMEWORK.md §1/§6).

    Combines a 3-EMA trend stack (fast/mid/slow) + slow-MA slope, ADX for trend
    strength, and an ATR volatility percentile into one per-bar regime label.
    Pure/objective: same bars + knobs -> same tags. Returns numeric axes
    (`trend` -2..2, `vol_bucket` 0..2, `vol_dir` -1..1, `adx`) plus the string
    `regime` array, so both humans and the sampler (step 4) can consume it."""
    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    close = df["Close"].to_numpy(dtype=float)
    n = len(df)
    fast = _ema(close, cfg.regime_ma_fast)
    mid = _ema(close, cfg.regime_ma_mid)
    slow = _ema(close, cfg.regime_ma_slow)
    adx = _adx(high, low, close, cfg.adx_len)
    atr = _atr(high, low, close, cfg.atr_len)

    # ATR volatility percentile via rolling quantiles (vectorized, C-backed).
    w = max(int(cfg.regime_atr_lookback), 5)
    atr_s = pd.Series(atr)
    q33 = atr_s.rolling(w, min_periods=w).quantile(0.33).to_numpy()
    q66 = atr_s.rolling(w, min_periods=w).quantile(0.66).to_numpy()
    vol_bucket = np.where(np.isnan(q33), 1,
                          np.where(atr < q33, 0, np.where(atr > q66, 2, 1))).astype(int)

    sl = max(int(cfg.regime_slope_lookback), 1)
    vol_dir = np.zeros(n, dtype=int)
    slow_slope = np.zeros(n)
    if n > sl:
        vol_dir[sl:] = np.sign(atr[sl:] - atr[:-sl]).astype(int)
        slow_slope[sl:] = slow[sl:] - slow[:-sl]

    strong = adx >= cfg.adx_trend
    up_stack = (close > fast) & (fast > mid) & (mid > slow) & (slow_slope > 0)
    dn_stack = (close < fast) & (fast < mid) & (mid < slow) & (slow_slope < 0)
    up_soft = (close > slow) & (mid > slow)
    dn_soft = (close < slow) & (mid < slow)

    trend = np.zeros(n, dtype=int)
    trend = np.where(up_soft & strong, 1, trend)
    trend = np.where(dn_soft & strong, -1, trend)
    trend = np.where(up_stack & ~strong, 1, trend)     # stack but weak ADX = controlled
    trend = np.where(dn_stack & ~strong, -1, trend)
    trend = np.where(up_stack & strong, 2, trend)      # full stack + strong ADX
    trend = np.where(dn_stack & strong, -2, trend)

    warm = np.arange(n) < max(int(cfg.regime_ma_slow), w)
    regime = np.select(
        [warm, trend == 2, trend == -2, trend == 1, trend == -1,
         (trend == 0) & (vol_bucket == 0), (trend == 0) & (vol_bucket == 2)],
        ["Indecision", "Strong Bull Trend", "Strong Bear Trend",
         "Controlled Bull Trend", "Controlled Bear Trend",
         "Compression", "High-Volatility Range"],
        default="Low-Volatility Range").astype(object)
    return {"adx": adx, "trend": trend, "vol_bucket": vol_bucket,
            "vol_dir": vol_dir, "regime": regime}


# Above this many bars, classify the regime on a 15-minute resample and
# broadcast the labels back — regime is a higher-timeframe concept (MA200 +
# Wilder ADX span days), so the label is unchanged while the cost drops from
# ~47s to ~2s on a 20-year 1m frame (measured). Single source of truth for the
# engine's regime gate AND run.py's regime tag / edge attribution.
REGIME_RESAMPLE_ABOVE = 400_000


def _regime_15m_parts(df: pd.DataFrame, cfg):
    """Classify on a lean 15m HLC resample; return (labels_15m, positions) where
    positions maps every source bar onto its 15m label index."""
    s = df[["et", "High", "Low", "Close"]].set_index("et")
    r = pd.DataFrame({"High": s["High"].resample("15min").max(),
                      "Low": s["Low"].resample("15min").min(),
                      "Close": s["Close"].resample("15min").last()}).dropna().reset_index()
    lab = classify_regime(r, cfg)["regime"]
    # compare times as int64 ns: .to_numpy() on a tz-aware column yields an OBJECT
    # array of Timestamps, and searchsorted over 4.3M of those costs ~30s vs 0.7s
    # on int64 (measured; positions identical).
    r_ns = r["et"].astype("int64").to_numpy()
    d_ns = df["et"].astype("int64").to_numpy()
    pos = np.clip(np.searchsorted(r_ns, d_ns, side="right") - 1, 0, len(lab) - 1)
    return lab, pos


def regime_labels(df: pd.DataFrame, cfg, resample_above: int = REGIME_RESAMPLE_ABOVE):
    """Per-bar regime labels for `df`, resample-accelerated on big 1m frames."""
    if len(df) <= resample_above or "et" not in df.columns:
        return classify_regime(df, cfg)["regime"]
    lab, pos = _regime_15m_parts(df, cfg)
    return lab[pos]


def regime_gate(df: pd.DataFrame, cfg, allowed, resample_above: int = REGIME_RESAMPLE_ABOVE):
    """Boolean per-bar gate: is the bar's regime in `allowed`? On big frames the
    membership test runs on the 15m labels (a few hundred k) and only the BOOLEANS
    are broadcast — never millions of object strings (np.isin on a 4.3M object
    array alone cost ~40s; this path is ~3s total)."""
    allowed = list(allowed)
    if len(df) <= resample_above or "et" not in df.columns:
        return np.isin(classify_regime(df, cfg)["regime"], allowed)
    lab, pos = _regime_15m_parts(df, cfg)
    return np.isin(lab, allowed)[pos]


def regime_summary(labels) -> dict:
    """Collapse a per-bar regime label array into a run summary: the dominant
    tradeable regime + a distribution (warm-up 'Indecision' excluded from the
    shares but reported as its own fraction)."""
    import collections
    labels = list(np.asarray(labels, dtype=object))
    total = len(labels) or 1
    counts = collections.Counter(labels)
    indef = counts.pop("Indecision", 0)
    denom = sum(counts.values()) or 1
    dist = {k: round(v / denom, 4)
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}
    dominant = max(counts, key=counts.get) if counts else "Indecision"
    return {"dominant": dominant, "distribution": dist,
            "indecision_frac": round(indef / total, 4), "bars": len(labels)}


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


def compute(df: pd.DataFrame, cfg: Config, progress=None) -> pd.DataFrame:
    # optional progress ticks so the pre-engine indicator build (≈35s on a 20y 1m
    # frame) shows movement instead of a silent "starting". 6 milestones over the
    # expensive early blocks. Off by default (parallel mill passes nothing).
    _STEPS = 6
    def _tick(k):
        if progress:
            progress(k, _STEPS)
    d = df
    high = d["High"].to_numpy(dtype=float)
    low = d["Low"].to_numpy(dtype=float)
    close = d["Close"].to_numpy(dtype=float)
    open_ = d["Open"].to_numpy(dtype=float)
    vol = d["Volume"].to_numpy(dtype=float)
    delta = d["Delta"].to_numpy(dtype=float)
    cvd = (d["CVD_close"].to_numpy(dtype=float) if "CVD_close" in d.columns
           else np.cumsum(delta))
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
    _tick(1)

    # --- Swing pivots (confirmed) ---------------------------------------------
    out["piv_low"] = _pivot_confirmed(low, cfg.pivot_k, "low")
    out["piv_high"] = _pivot_confirmed(high, cfg.pivot_k, "high")
    _tick(2)

    # --- Session VWAP ----------------------------------------------------------
    hlc3 = (high + low + close) / 3.0
    out["vwap"] = _session_vwap(hlc3, vol, new_session)
    _tick(3)

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
    _tick(4)

    # --- ATR (computed above; reused for the ATR unit mode) -------------------
    out["atr"] = atr

    # --- Regime gate (causal) --------------------------------------------------
    # Empty filter = trade every regime (all True, no cost). Otherwise the per-bar
    # regime tag (no look-ahead) must be in the allowed set for an entry to fire.
    # regime_labels() classifies on a 15m resample above 400k bars (same labels,
    # ~47s -> ~2s on 20y 1m — this block was the '8% computing indicators' stall)
    # and keeps the gate consistent with run.py's regime tag / edge attribution.
    if cfg.regime_filter:
        out["regime_ok"] = regime_gate(d, cfg, cfg.regime_filter)
    else:
        out["regime_ok"] = np.ones(n, dtype=bool)
    _tick(5)

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

    # --- Break-of-structure entry (Level B generator) -------------------------
    # Momentum/continuation: a bullish break fires the bar the close crosses
    # ABOVE the last confirmed swing high; bearish the bar it closes BELOW the
    # last confirmed swing low. Reuses the same lookahead-safe pivots as the
    # swing stops (pivot_k) — piv_high/piv_low are the price of the most recently
    # CONFIRMED pivot as of bar i, so comparing close[i] to them uses no future
    # data. Fires once on the transition (ta.crossover against a stepped level).
    if cfg.use_bos_entry:
        ph = out["piv_high"].to_numpy()
        pl = out["piv_low"].to_numpy()
        above = close > ph              # NaN reference (pre-first-pivot) -> False
        below = close < pl
        bos = np.zeros(n, dtype=np.int64)
        bos[1:] = np.where(above[1:] & ~above[:-1], 1,
                           np.where(below[1:] & ~below[:-1], -1, 0))
        out["bos_dir"] = bos
    else:
        out["bos_dir"] = np.zeros(n, dtype=np.int64)

    ph_arr = out["piv_high"].to_numpy()
    pl_arr = out["piv_low"].to_numpy()

    # --- Change of character (CHoCH) — first counter-break of structure --------
    # Reversal complement of BOS: after price has been making the break one way,
    # the FIRST close back through the opposite confirmed swing flags a regime
    # flip. Modelled as a crossover the OTHER way vs BOS, so a bullish CHoCH =
    # close crosses back above the swing high after trading below the swing low.
    if cfg.use_choch_entry:
        below_lo = close < pl_arr
        above_hi = close > ph_arr
        choch = np.zeros(n, dtype=np.int64)
        # long CHoCH: was below the swing low, now closes above the swing high
        # short CHoCH: was above the swing high, now closes below the swing low
        choch[1:] = np.where(above_hi[1:] & below_lo[:-1], 1,
                             np.where(below_lo[1:] & above_hi[:-1], -1, 0))
        out["choch_dir"] = choch
    else:
        out["choch_dir"] = np.zeros(n, dtype=np.int64)

    # --- Liquidity sweep + reclaim (reversal) ---------------------------------
    # Bullish: the bar's low takes out the last confirmed swing low (sweeps the
    # resting liquidity) but the CLOSE reclaims back above it. Bearish mirror.
    if cfg.use_liq_sweep:
        swept_lo = (low < pl_arr) & (close > pl_arr)
        swept_hi = (high > ph_arr) & (close < ph_arr)
        liq = np.where(swept_lo, 1, np.where(swept_hi, -1, 0)).astype(np.int64)
        out["liq_dir"] = liq
    else:
        out["liq_dir"] = np.zeros(n, dtype=np.int64)

    # --- CVD divergence at pivots (reversal) ----------------------------------
    if cfg.use_cvd_div:
        out["cvddiv_dir"] = _cvd_div_dir(low, high, close, cvd, int(cfg.cvd_div_pivot_k))
    else:
        out["cvddiv_dir"] = np.zeros(n, dtype=np.int64)

    # --- Order-block mitigation (continuation) --------------------------------
    if cfg.use_order_block:
        out["ob_dir"] = _order_block_dir(open_, high, low, close, atr,
                                         cfg.ob_impulse_atr, int(cfg.ob_max_age), cfg.ob_mit_pct)
    else:
        out["ob_dir"] = np.zeros(n, dtype=np.int64)

    # --- Momentum / displacement bar (momentum) -------------------------------
    # Enter WITH a bar whose body is >= momentum_body_atr * ATR (a displacement /
    # opening-drive impulse). Direction = sign of the bar body.
    if cfg.use_momentum:
        body = close - open_
        thr = cfg.momentum_body_atr * atr
        mom = np.where((body >= thr) & (thr > 0), 1,
                       np.where((-body >= thr) & (thr > 0), -1, 0)).astype(np.int64)
        out["mom_dir"] = mom
    else:
        out["mom_dir"] = np.zeros(n, dtype=np.int64)

    # --- MACD line / signal cross (momentum, classic) -------------------------
    if cfg.use_macd_cross:
        macd_line = _ema(close, cfg.macd_fast) - _ema(close, cfg.macd_slow)
        signal = _ema(macd_line, cfg.macd_signal)
        out["macd_dir"] = _cross_dir(macd_line, signal)
    else:
        out["macd_dir"] = np.zeros(n, dtype=np.int64)

    # --- RSI reversion — exit of oversold/overbought (mean reversion) ---------
    if cfg.use_rsi_rev:
        rsi = _rsi(close, cfg.rsi_length)
        os_prev = np.zeros(n, dtype=bool); ob_prev = np.zeros(n, dtype=bool)
        os_prev[1:] = rsi[:-1] <= cfg.rsi_os      # was oversold on the prior bar
        ob_prev[1:] = rsi[:-1] >= cfg.rsi_ob
        rr = np.where(os_prev & (rsi > cfg.rsi_os), 1,      # crossed back up out of OS -> long
                      np.where(ob_prev & (rsi < cfg.rsi_ob), -1, 0)).astype(np.int64)
        out["rsi_dir"] = rr
    else:
        out["rsi_dir"] = np.zeros(n, dtype=np.int64)

    # --- Donchian channel break (breakout/breakdown, classic) -----------------
    if cfg.use_donchian:
        dl = int(cfg.donchian_len)
        upper = pd.Series(high).rolling(dl, min_periods=dl).max().shift(1).to_numpy()
        lower = pd.Series(low).rolling(dl, min_periods=dl).min().shift(1).to_numpy()
        up = close > upper; dn = close < lower
        don = np.zeros(n, dtype=np.int64)
        don[1:] = np.where(up[1:] & ~up[:-1], 1, np.where(dn[1:] & ~dn[:-1], -1, 0))
        out["don_dir"] = don
    else:
        out["don_dir"] = np.zeros(n, dtype=np.int64)

    # --- Moving-average trend pullback (trend following / pullback) -----------
    # In an uptrend (fast MA > slow MA) enter when the bar dips to/through the
    # fast MA but closes back above it (a pullback-and-resume). Bearish mirror.
    if cfg.use_ma_pullback:
        fast = _ma(close, cfg.ma_fast, cfg.ma_type)
        slow = _ma(close, cfg.ma_slow, cfg.ma_type)
        up_tr = fast > slow
        long_pb = up_tr & (low <= fast) & (close > fast)
        short_pb = (~up_tr) & (high >= fast) & (close < fast)
        mp = np.where(long_pb, 1, np.where(short_pb, -1, 0)).astype(np.int64)
        # guard the NaN warm-up (rolling SMA leaves leading NaN -> comparisons False)
        mp[np.isnan(slow)] = 0
        out["mapb_dir"] = mp
    else:
        out["mapb_dir"] = np.zeros(n, dtype=np.int64)

    # --- Bollinger-band extreme reversion (mean reversion / range) ------------
    # Long when the bar pokes below the lower band but closes back inside;
    # short when it pokes above the upper band and closes back inside.
    if cfg.use_bb_revert:
        bl = int(cfg.bb_len)
        cs = pd.Series(close)
        basis = cs.rolling(bl, min_periods=bl).mean().to_numpy()
        sd = cs.rolling(bl, min_periods=bl).std(ddof=0).to_numpy()
        upper = basis + cfg.bb_mult * sd
        lower = basis - cfg.bb_mult * sd
        long_rv = (low < lower) & (close > lower)
        short_rv = (high > upper) & (close < upper)
        bb = np.where(long_rv, 1, np.where(short_rv, -1, 0)).astype(np.int64)
        bb[np.isnan(sd)] = 0
        out["bb_dir"] = bb
    else:
        out["bb_dir"] = np.zeros(n, dtype=np.int64)

    _tick(6)
    return out
