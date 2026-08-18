"""Run diagnostics — explain a backtest result FROM THE DATA (framework goal).

The backtester must not be a TradingView-style pass/fail runner. Given a run's
trades, this reads the per-trade adverse/favorable excursions the engine already
records (mae_ticks / mfe_ticks), the realized move, and the exit reasons, and
turns them into plain, data-derived statements about WHY the config performed as
it did — "stops ~2x wider than the adverse move 90% of winners ever showed", "TP
too far: only 12% of trades ever reached it", "winners give back 40% of their
peak" — with no pre-assumption that the current parameters are right. Those are
exactly the levers the fine-grained sweep (backtest.sweep) then tunes.

Phase 1 of the diagnose/instrument/sweep trio. Pure Python + pandas, unit-safe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _pct(x) -> float:
    return round(100 * float(x), 1)


def _finding(code: str, severity: str, message: str, **evidence) -> dict:
    return {"code": code, "severity": severity, "message": message, "evidence": evidence}


def diagnose_trades(df: pd.DataFrame, cfg, drawdown: float = 2_500.0) -> dict:
    """df: a trades_frame (dir, qty, entry_px, exit_px, reason, net, mfe_ticks,
    mae_ticks). cfg: the Config the run used (stop/TP/contract). Returns
    {summary, exit_mix, stop, target, give_back, risk, findings} where findings
    is a ranked list of plain-language, data-derived statements."""
    n = len(df)
    if n == 0:
        return {"summary": {"trades": 0}, "findings": [
            _finding("no-trades", "high",
                     "No trades were taken — the entry filters gated every signal. "
                     "Check the filter/threshold instrumentation (backtest.sweep --filters).")]}

    net = df["net"].to_numpy(dtype=float)
    mae = df["mae_ticks"].to_numpy(dtype=float)          # adverse excursion, ticks
    mfe = df["mfe_ticks"].to_numpy(dtype=float)          # favorable excursion, ticks
    win_mask = net > 0
    loss_mask = ~win_mask
    findings: list[dict] = []

    # ---- exit-reason mix -------------------------------------------------
    reasons = df["reason"].value_counts(normalize=True).to_dict()
    exit_mix = {k: _pct(v) for k, v in reasons.items()}
    stop_reasons = {"SL", "BE-STOP", "TRAIL", "RECOV-TRAIL"}
    stop_share = sum(v for k, v in reasons.items() if k in stop_reasons)
    tp_share = float(reasons.get("TP", 0.0))
    eod_share = float(reasons.get("EOD", 0.0))
    if stop_share >= 0.55:
        findings.append(_finding(
            "stop-dominated", "high",
            f"{_pct(stop_share)}% of trades exit on a stop and only {_pct(tp_share)}% on target — "
            "the target is rarely reached before the stop or the day-exit fires.",
            stop_share=_pct(stop_share), tp_share=_pct(tp_share)))
    if eod_share >= 0.35:
        findings.append(_finding(
            "eod-dominated", "medium",
            f"{_pct(eod_share)}% of trades are force-closed at end of day (EOD) — "
            "positions rarely resolve to a stop or target within the session.",
            eod_share=_pct(eod_share)))

    # ---- stop width vs the adverse move winners actually needed ----------
    stop_block = None
    if not getattr(cfg, "stop_swing", False):
        stop_ticks = float(getattr(cfg, "fixed_stop_ticks", 0.0) or 0.0)
        win_mae = mae[win_mask]
        p50 = float(np.percentile(win_mae, 50)) if win_mask.any() else 0.0
        p90 = float(np.percentile(win_mae, 90)) if win_mask.any() else 0.0
        stop_block = {"stop_ticks": stop_ticks, "winner_mae_p50": round(p50, 1),
                      "winner_mae_p90": round(p90, 1),
                      "loss_mae_p50": round(float(np.percentile(mae[loss_mask], 50)), 1) if loss_mask.any() else 0.0}
        if stop_ticks > 0 and p90 > 0:
            ratio = stop_ticks / p90
            stop_block["stop_over_p90"] = round(ratio, 2)
            if ratio >= 1.8:
                findings.append(_finding(
                    "stop-too-wide", "high",
                    f"Stop is {stop_ticks:.0f} ticks but 90% of WINNERS never drew more than "
                    f"{p90:.0f} ticks against you ({ratio:.1f}x). Each loss is oversized for the "
                    "room your winners actually use — tightening the stop cuts loss size with "
                    "little effect on win rate.",
                    stop_ticks=stop_ticks, winner_mae_p90=round(p90, 1), ratio=round(ratio, 2)))
            elif stop_ticks <= p50 and p50 > 0:
                findings.append(_finding(
                    "stop-too-tight", "high",
                    f"Stop is {stop_ticks:.0f} ticks, below the {p50:.0f}-tick adverse move HALF "
                    "your winners showed — you are likely stopping out trades that would have won.",
                    stop_ticks=stop_ticks, winner_mae_p50=round(p50, 1)))

    # ---- target vs favorable excursion -----------------------------------
    target_block = None
    tp_mode = getattr(cfg, "tp_mode", "")
    if "Fixed" in str(tp_mode):
        tp_ticks = float(getattr(cfg, "tp_fixed_ticks", 0.0) or 0.0)
        reach = float(np.mean(mfe >= tp_ticks)) if tp_ticks > 0 else 0.0
        p50_mfe = float(np.percentile(mfe, 50))
        p75_mfe = float(np.percentile(mfe, 75))
        target_block = {"tp_ticks": tp_ticks, "reach_rate_pct": _pct(reach),
                        "mfe_p50": round(p50_mfe, 1), "mfe_p75": round(p75_mfe, 1)}
        if tp_ticks > 0 and reach <= 0.20:
            findings.append(_finding(
                "target-too-far", "high",
                f"Target is {tp_ticks:.0f} ticks but only {_pct(reach)}% of trades ever reached it "
                f"(median favorable move {p50_mfe:.0f} ticks). The target is set beyond where price "
                "usually goes — most trades resolve short of it.",
                tp_ticks=tp_ticks, reach_rate_pct=_pct(reach), mfe_p50=round(p50_mfe, 1)))
        elif tp_ticks > 0 and p75_mfe >= 1.8 * tp_ticks:
            findings.append(_finding(
                "target-too-close", "medium",
                f"Target is {tp_ticks:.0f} ticks but 25% of trades ran past {p75_mfe:.0f} ticks — "
                "you may be capping winners well short of the move that was available.",
                tp_ticks=tp_ticks, mfe_p75=round(p75_mfe, 1)))

    # ---- give-back: peak (MFE) vs the move actually realized on winners ---
    give_back = None
    mintick = float(getattr(getattr(cfg, "contract", None), "mintick", 0.0) or 0.0)
    if mintick > 0 and win_mask.any():
        w = df[win_mask]
        realized = ((w["exit_px"].to_numpy(dtype=float) - w["entry_px"].to_numpy(dtype=float))
                    * w["dir"].to_numpy(dtype=float) / mintick)
        peak = w["mfe_ticks"].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            frac = np.where(peak > 0, (peak - realized) / peak, 0.0)
        avg_gb = float(np.nanmean(np.clip(frac, 0, 1)))
        give_back = {"avg_giveback_pct": _pct(avg_gb),
                     "winner_peak_ticks_p50": round(float(np.percentile(peak, 50)), 1),
                     "winner_realized_ticks_p50": round(float(np.percentile(realized, 50)), 1)}
        if avg_gb >= 0.35:
            findings.append(_finding(
                "high-giveback", "medium",
                f"Winners give back {_pct(avg_gb)}% of their peak favorable move before exit — "
                "the exit (no/late breakeven or a loose trail) lets profit evaporate.",
                avg_giveback_pct=_pct(avg_gb)))

    # ---- single-loss size vs the funded drawdown buffer ------------------
    risk = None
    losses = net[loss_mask]
    if losses.size:
        worst = float(losses.min())
        avg_loss = float(losses.mean())
        risk = {"avg_loss": round(avg_loss, 2), "worst_loss": round(worst, 2),
                "drawdown_buffer": drawdown,
                "worst_pct_of_buffer": _pct(abs(worst) / drawdown) if drawdown else None,
                "avg_pct_of_buffer": _pct(abs(avg_loss) / drawdown) if drawdown else None}
        if drawdown and abs(worst) >= 0.5 * drawdown:
            findings.append(_finding(
                "loss-vs-drawdown", "high",
                f"A single worst loss is ${abs(worst):,.0f} — {_pct(abs(worst)/drawdown)}% of the "
                f"${drawdown:,.0f} trailing drawdown. The position is too large for the account: "
                "a normal losing streak breaches before any edge compounds.",
                worst_loss=round(worst, 2), drawdown=drawdown))

    sev_rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: sev_rank.get(f["severity"], 3))
    return {
        "summary": {"trades": n, "win_rate_pct": _pct(win_mask.mean()),
                    "net": round(float(net.sum()), 2)},
        "exit_mix": exit_mix, "stop": stop_block, "target": target_block,
        "give_back": give_back, "risk": risk, "findings": findings,
    }


def diagnose_signals(ind: pd.DataFrame, cfg, veto_counts: dict | None = None) -> dict:
    """Phase 2 — explain the FILTERING from the data, no assumption the thresholds
    fit. Compares the configured FVG-size band / CVD-streak / VWAP veto to the
    actual per-bar distribution in `ind`, and folds in the engine's veto
    attribution (veto_counts, from a diag-mode run) to say where signals die.
    Returns {fvg, cvd, vwap, vetoes, findings}."""
    findings: list[dict] = []
    mintick = float(getattr(getattr(cfg, "contract", None), "mintick", 0.0) or 0.0)

    # ---- FVG size band vs the real FVG-size distribution -----------------
    fvg = None
    if {"fvg_dir", "fvg_top", "fvg_bot"}.issubset(ind.columns) and mintick > 0:
        d = ind["fvg_dir"].to_numpy()
        top = ind["fvg_top"].to_numpy(dtype=float)
        bot = ind["fvg_bot"].to_numpy(dtype=float)
        size = np.abs(top - bot) / mintick                 # FVG size in ticks
        real = size[(d != 0) & np.isfinite(size) & (size > 0)]
        if real.size and getattr(cfg, "use_gap_filter", False) and str(cfg.unit_mode) == "Ticks":
            lo = float(cfg.gap_min_ticks)
            hi = float(cfg.gap_max_ticks)
            inside = float(np.mean((real >= lo) & (real <= hi)))
            too_small = float(np.mean(real < lo))
            too_big = float(np.mean(real > hi))
            fvg = {"band_ticks": [lo, hi], "n_fvgs": int(real.size),
                   "inside_pct": _pct(inside), "too_small_pct": _pct(too_small),
                   "too_big_pct": _pct(too_big),
                   "size_p50": round(float(np.percentile(real, 50)), 1),
                   "size_p90": round(float(np.percentile(real, 90)), 1)}
            if inside <= 0.15:
                dom = "smaller" if too_small >= too_big else "larger"
                findings.append(_finding(
                    "fvg-band-mismatch", "high",
                    f"The FVG-size band {lo:.0f}-{hi:.0f} ticks accepts only {_pct(inside)}% of the "
                    f"FVGs in this data (median FVG is {fvg['size_p50']:.0f} ticks) — {_pct(max(too_small, too_big))}% "
                    f"are {dom} than the band. The gap filter barely matches this instrument/timeframe.",
                    band=[lo, hi], inside_pct=_pct(inside), size_p50=fvg["size_p50"]))

    # ---- CVD streak restrictiveness --------------------------------------
    cvd = None
    if {"bull_cvd", "bear_cvd"}.issubset(ind.columns):
        bull = ind["bull_cvd"].to_numpy(bool)
        bear = ind["bear_cvd"].to_numpy(bool)
        pass_rate = float(np.mean(bull | bear))
        cvd = {"streak_count": int(getattr(cfg, "cvd_trend_count", 0)),
               "bars_pass_pct": _pct(pass_rate)}
        if getattr(cfg, "use_cvd_filter", False) and pass_rate <= 0.10:
            findings.append(_finding(
                "cvd-too-strict", "medium",
                f"The CVD filter (streak {cvd['streak_count']}) leaves only {_pct(pass_rate)}% of bars "
                "tradeable — it may be gating most of the signal flow.",
                bars_pass_pct=_pct(pass_rate)))

    # ---- VWAP veto restrictiveness ---------------------------------------
    vwap = None
    if {"veto_long", "veto_short"}.issubset(ind.columns):
        vl = ind["veto_long"].to_numpy(bool)
        vs = ind["veto_short"].to_numpy(bool)
        vwap = {"long_ok_pct": _pct(float(np.mean(vl))), "short_ok_pct": _pct(float(np.mean(vs)))}

    # ---- engine veto attribution (where primary signals actually die) ----
    vetoes = None
    if veto_counts and veto_counts.get("primary"):
        p = veto_counts["primary"]
        vetoes = {"primary_signals": p, "passed": veto_counts.get("passed", 0),
                  "passed_pct": _pct(veto_counts.get("passed", 0) / p)}
        for key, label in (("cvd", "CVD"), ("vwap", "VWAP"), ("regime", "regime"),
                           ("time", "time-of-day"), ("confluence", "confluence")):
            c = veto_counts.get(key, 0)
            if c:
                vetoes[f"{key}_killed_pct"] = _pct(c / p)
        worst = max((("cvd", "CVD direction"), ("vwap", "VWAP veto"), ("regime", "regime gate"),
                     ("time", "time-of-day gate"), ("confluence", "confluence conditions")),
                    key=lambda kv: veto_counts.get(kv[0], 0))
        wc = veto_counts.get(worst[0], 0)
        if wc and wc / p >= 0.5:
            findings.append(_finding(
                "signals-killed", "high",
                f"Of {p:,} primary entry signals, only {vetoes['passed_pct']}% survive the filters — "
                f"the {worst[1]} alone kills {_pct(wc/p)}%. Most of the strategy's raw signals never "
                "become trades.",
                primary=p, passed_pct=vetoes["passed_pct"], top_filter=worst[1]))

    sev_rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: sev_rank.get(f["severity"], 3))
    return {"fvg": fvg, "cvd": cvd, "vwap": vwap, "vetoes": vetoes, "findings": findings}
