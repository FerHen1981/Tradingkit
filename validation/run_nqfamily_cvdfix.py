"""Tweede pass: GC en YM opnieuw, nu met echte volume-delta.

Waarom dit nodig is: ES_norm/GC_norm/YM_norm hebben een Delta-kolom die
identiek nul is. Patron en Dorado draaien met het CVD-filter AAN, dus die
konden op die reeksen per definitie geen enkele trade doen — nul trades was
een datakwestie, geen uitslag. GC_cvd.csv en YM_cvd.csv bevatten wel echte
delta; voor ES bestaat zo'n bestand niet.

Draait dezelfde stages 3-7 als de hoofdrun en schrijft
validation/NQFAMILY_results_cvdfix_20260811.json.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from dataclasses import replace as drep

from backtest import data as dm, indicators as im
from backtest.config import contract
from backtest.engine import Engine
from backtest.funnel import run_funnel, summarize
from backtest.metrics import kpis, trades_frame

import importlib.util, sys
spec = importlib.util.spec_from_file_location("_base", "validation/run_nqfamily_pipeline.py")

# de configs overnemen zonder de hoofdrun opnieuw uit te voeren
from backtest.config import Config as SigCfg
BASE = dict(entry_limit_mode=True, expiry_bars=12, stop_swing=True, pivot_k=3,
            swing_buf_ticks=2.0, max_stop_ticks=72.0, tp_mode="R-multiple",
            r_multiple=2.5, use_breakeven=True, use_trail=True, use_gap_filter=True,
            use_vwap_veto=True, skip_monday_early=True, use_auto_flat=True)
PATRON = SigCfg(name="EL_PATRON", **BASE, gap_min_ticks=9.0, gap_max_ticks=13.0,
                confirm_bars=0, be_trigger_ticks=16.0, be_offset_ticks=12.0,
                trail_start_ticks=30.0, trail_buffer_ticks=24.0,
                use_cvd_filter=True, use_cvd_streak=True, cvd_trend_count=4)
DORADO = SigCfg(name="EL_DORADO", **BASE, gap_min_ticks=9.0, gap_max_ticks=13.0,
                confirm_bars=0, be_trigger_ticks=20.0, be_offset_ticks=8.0,
                trail_start_ticks=48.0, trail_buffer_ticks=24.0,
                use_cvd_filter=True, use_cvd_streak=True, cvd_trend_count=4)
MATADOR = SigCfg(name="EL_MATADOR", **BASE, gap_min_ticks=9.0, gap_max_ticks=12.0,
                 confirm_bars=2, be_trigger_ticks=20.0, be_offset_ticks=8.0,
                 trail_start_ticks=48.0, trail_buffer_ticks=24.0,
                 use_cvd_filter=False, use_cvd_streak=False, cvd_trend_count=4)
STRATS = {"EL_PATRON": (PATRON, "pa"), "EL_DORADO": (DORADO, "pa"),
          "EL_MATADOR": (MATADOR, "eval")}

TZ = "America/New_York"
DATA = {"GC": dm.load("data/GC_cvd.csv"), "YM": dm.load("data/YM_cvd.csv")}
SLOTS = {"GC": dict(dkey="GC", con=contract("GC"), qty=1, dd="Intraday"),
         "YM": dict(dkey="YM", con=contract("YM"), qty=2, dd="EOD")}
SPLIT = pd.Timestamp("2026-01-31", tz=TZ)
R12 = pd.Timestamp("2025-07-31", tz=TZ)
YEARS = [("Y1", "2023-08-02", "2024-08-01"), ("Y2", "2024-08-01", "2025-08-01"),
         ("Y3", "2025-08-01", "2026-08-01")]


def pa_overlay(dd):
    return dict(phase="Apex PA", dd_model=dd, acct_trail_dd=2500.0, acct_dll=1000.0,
                consistency_pct=50.0, min_payout=500.0, payout_buffer=500.0,
                use_wait_for_cap=True, use_mae_guard=True,
                day_exit_mode="Day-trail (keep peak)", day_trail_usd=300.0)


def eval_overlay(dd):
    return dict(phase="Apex Eval", dd_model=dd, acct_trail_dd=2500.0, acct_goal=3000.0)


def ixs(df, a=None, b=None):
    et = df["et"]; m = pd.Series(True, index=df.index)
    if a is not None: m &= et >= a
    if b is not None: m &= et < b
    ix = df.index[m]
    return (int(ix[0]), int(ix[-1]) + 1) if len(ix) else None


_ind = {}
def ind_for(dkey, cfg):
    key = (dkey, cfg.gap_min_ticks, cfg.gap_max_ticks, cfg.confirm_bars,
           cfg.use_vwap_veto, cfg.use_cvd_filter, cfg.use_cvd_streak, cfg.contract.mintick)
    if key not in _ind:
        _ind[key] = im.compute(DATA[dkey], cfg)
    return _ind[key]


def research(df, ind, cfg, span):
    if span is None: return dict(trades=0, pf=0, win=0, net=0), None
    a, b = span
    sdf = df.iloc[a:b].reset_index(drop=True); sind = ind.iloc[a:b].reset_index(drop=True)
    res = Engine(cfg, sdf, sind, research_mode=True).run()
    k = kpis(res)
    return dict(trades=k.get("trades", 0), pf=round(k.get("profit_factor", 0), 3),
                win=round(k.get("win_rate_pct", 0), 1), net=round(k.get("net_profit", 0))), res


def obj_eval(df, ind, cfg, span):
    if span is None: return None
    a, b = span
    s = summarize(run_funnel(cfg, df.iloc[a:b].reset_index(drop=True),
                             ind.iloc[a:b].reset_index(drop=True),
                             step_sessions=5, horizon_sessions=20))
    return dict(metric="pass_rate_pct", value=s["pass_rate_pct"], starts=s["starts"],
                breach_pct=round(100 * s["breach"] / max(s["starts"], 1), 1))


def obj_pa(df, ind, cfg, span):
    if span is None: return None
    a, b = span
    r = Engine(cfg, df.iloc[a:b].reset_index(drop=True),
               ind.iloc[a:b].reset_index(drop=True), research_mode=False).run()
    return dict(metric="banked_per_breach",
                value=round(r.pa_total_banked / r.pa_breach_count) if r.pa_breach_count else None,
                banked=r.pa_total_banked, breaches=r.pa_breach_count)


out = {"_meta": {"note": "GC/YM met echte volume-delta (GC_cvd.csv / YM_cvd.csv)",
                 "generated": "2026-08-11"}}
for sname, (sig, kind) in STRATS.items():
    fn = obj_eval if kind == "eval" else obj_pa
    for slot, sl in SLOTS.items():
        df = DATA[sl["dkey"]]
        ov = (eval_overlay if kind == "eval" else pa_overlay)(sl["dd"])
        cfg = sig.with_(contract=sl["con"], contract_size=float(sl["qty"]), **ov)
        ind = ind_for(sl["dkey"], cfg)
        s_is, s_oos, s_r12 = ixs(df, None, SPLIT), ixs(df, SPLIT, None), ixs(df, R12, None)
        e = {"qty": sl["qty"], "dd_model": sl["dd"], "data": "cvd"}
        e["is_research"], _ = research(df, ind, cfg, s_is)
        e["recent12m"], _ = research(df, ind, cfg, s_r12)
        e["years"] = {t: research(df, ind, cfg,
                      ixs(df, pd.Timestamp(a, tz=TZ), pd.Timestamp(b, tz=TZ)))[0]
                      for t, a, b in YEARS}
        e["obj_is"] = fn(df, ind, cfg, s_is)
        e["obj_r12"] = fn(df, ind, cfg, s_r12)
        e["obj_oos"] = fn(df, ind, cfg, s_oos)
        e["oos_research"], oos_res = research(df, ind, cfg, s_oos)
        if oos_res is not None:
            tf = trades_frame(oos_res)
            if len(tf) > 5:
                p = tf["net"].to_numpy(); rng = np.random.default_rng(7)
                dds = [float((np.maximum.accumulate(c := rng.choice(p, len(p), replace=True).cumsum()) - c).max())
                       for _ in range(1000)]
                e["mc_p95_maxdd_oos"] = round(float(np.percentile(dds, 95)))
        scon = drep(sl["con"], commission_per_contract=sl["con"].commission_per_contract * 2,
                    slippage_ticks=2.0)
        e["stress_oos"] = fn(df, ind, cfg.with_(contract=scon), s_oos)
        out[f"{sname}|{slot}"] = e
        print(f"{sname:<11} {slot:<3} klaar", flush=True)

with open("validation/NQFAMILY_results_cvdfix_20260811.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
print("ALLDONE")
