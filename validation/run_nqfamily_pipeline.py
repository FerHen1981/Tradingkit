"""Stages 3-7 driver voor El Patron / El Matador / El Dorado x 5 fleet-slots.

Pre-geregistreerd in NQFAMILY_stage1-2_preregistration_20260811.md — gates staan
daar en worden hier niet aangeraakt. Parameters komen uit de CONFIG-berichten die
de scripts zelf verstuurden (alerts-log 10-08), niet uit een reconstructie.

NQ/MNQ draaien mee als referentie zonder gate-krediet: die OOS is op 10-08 al
verbruikt. YM is de enige volledig verse reeks.

Schrijft validation/NQFAMILY_results_20260811.json.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from dataclasses import replace as drep

from backtest import data as dm, indicators as im
from backtest.config import Contract, Config as SigCfg, contract
from backtest.engine import Engine
from backtest.funnel import run_funnel, summarize
from backtest.metrics import kpis, trades_frame

TZ = "America/New_York"

# ---------------------------------------------------------------- contracten --
MNQ = Contract("MNQ", 0.25, 2.0, 0.67)      # micro NQ, gemeten commissie
MYM = Contract("MYM", 1.0, 0.5, 0.67)

# ------------------------------------------------------------------ signalen --
# Gemeenschappelijke kern van de scriptfamilie (identiek in alle drie CONFIGs).
BASE = dict(entry_limit_mode=True, expiry_bars=12, stop_swing=True, pivot_k=3,
            swing_buf_ticks=2.0, max_stop_ticks=72.0, tp_mode="R-multiple",
            r_multiple=2.5, use_breakeven=True, use_trail=True, use_gap_filter=True,
            use_vwap_veto=True, skip_monday_early=True, use_auto_flat=True)

PATRON = SigCfg(name="EL_PATRON", **BASE,
                gap_min_ticks=9.0, gap_max_ticks=13.0, confirm_bars=0,
                be_trigger_ticks=16.0, be_offset_ticks=12.0,
                trail_start_ticks=30.0, trail_buffer_ticks=24.0,
                use_cvd_filter=True, use_cvd_streak=True, cvd_trend_count=4)

DORADO = SigCfg(name="EL_DORADO", **BASE,
                gap_min_ticks=9.0, gap_max_ticks=13.0, confirm_bars=0,
                be_trigger_ticks=20.0, be_offset_ticks=8.0,
                trail_start_ticks=48.0, trail_buffer_ticks=24.0,
                use_cvd_filter=True, use_cvd_streak=True, cvd_trend_count=4)

# CVD uit is een aanname (geen CONFIG in het logvenster) — S5 test het andersom.
MATADOR = SigCfg(name="EL_MATADOR", **BASE,
                 gap_min_ticks=9.0, gap_max_ticks=12.0, confirm_bars=2,
                 be_trigger_ticks=20.0, be_offset_ticks=8.0,
                 trail_start_ticks=48.0, trail_buffer_ticks=24.0,
                 use_cvd_filter=False, use_cvd_streak=False, cvd_trend_count=4)

STRATS = {"EL_PATRON": (PATRON, "pa"), "EL_DORADO": (DORADO, "pa"),
          "EL_MATADOR": (MATADOR, "eval")}

# ------------------------------------------------------- assets en vensters --
# qty genormaliseerd op ~$10 per tick (zie pre-registratie).
SLOTS = {
    "NQ":  dict(dkey="NQ", con=contract("NQ"), qty=2,  dd="EOD",      taint=True),
    "MNQ": dict(dkey="NQ", con=MNQ,            qty=20, dd="EOD",      taint=True),
    "ES":  dict(dkey="ES", con=contract("ES"), qty=1,  dd="EOD",      taint=False),
    "GC":  dict(dkey="GC", con=contract("GC"), qty=1,  dd="Intraday", taint=False),
    "YM":  dict(dkey="YM", con=contract("YM"), qty=2,  dd="EOD",      taint=False),
}

DATA = {"NQ": dm.load("data/NQ_1m_last3y_slim.csv"),
        "ES": dm.load("data/ES_norm.csv"),
        "GC": dm.load("data/GC_norm.csv"),
        "YM": dm.load("data/YM_norm.csv")}

# NQ-set loopt t/m 2026-06-17, de rest t/m 2026-07-31 -> eigen grens per reeks.
SPLIT = {"NQ": pd.Timestamp("2025-12-17", tz=TZ), "ES": pd.Timestamp("2026-01-31", tz=TZ),
         "GC": pd.Timestamp("2026-01-31", tz=TZ), "YM": pd.Timestamp("2026-01-31", tz=TZ)}
R12   = {"NQ": pd.Timestamp("2025-06-17", tz=TZ), "ES": pd.Timestamp("2025-07-31", tz=TZ),
         "GC": pd.Timestamp("2025-07-31", tz=TZ), "YM": pd.Timestamp("2025-07-31", tz=TZ)}
YEARS = [("Y1", "2023-08-02", "2024-08-01"), ("Y2", "2024-08-01", "2025-08-01"),
         ("Y3", "2025-08-01", "2026-08-01")]


def pa_overlay(dd_model):
    return dict(phase="Apex PA", dd_model=dd_model, acct_trail_dd=2500.0,
                acct_dll=1000.0, consistency_pct=50.0, min_payout=500.0,
                payout_buffer=500.0, use_wait_for_cap=True, use_mae_guard=True,
                day_exit_mode="Day-trail (keep peak)", day_trail_usd=300.0)


def eval_overlay(dd_model):
    return dict(phase="Apex Eval", dd_model=dd_model, acct_trail_dd=2500.0,
                acct_goal=3000.0)


def ixs(df, a=None, b=None):
    et = df["et"]; m = pd.Series(True, index=df.index)
    if a is not None: m &= et >= a
    if b is not None: m &= et < b
    ix = df.index[m]
    if not len(ix): return None
    return int(ix[0]), int(ix[-1]) + 1


_ind = {}
def ind_for(dkey, cfg):
    key = (dkey, cfg.gap_min_ticks, cfg.gap_max_ticks, cfg.confirm_bars,
           cfg.use_vwap_veto, cfg.use_cvd_filter, cfg.use_cvd_streak,
           cfg.contract.mintick, cfg.max_stop_ticks)
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
    sdf = df.iloc[a:b].reset_index(drop=True); sind = ind.iloc[a:b].reset_index(drop=True)
    s = summarize(run_funnel(cfg, sdf, sind, step_sessions=5, horizon_sessions=20))
    return dict(metric="pass_rate_pct", value=s["pass_rate_pct"], starts=s["starts"],
                breach_pct=round(100 * s["breach"] / max(s["starts"], 1), 1))


def obj_pa(df, ind, cfg, span):
    if span is None: return None
    a, b = span
    sdf = df.iloc[a:b].reset_index(drop=True); sind = ind.iloc[a:b].reset_index(drop=True)
    r = Engine(cfg, sdf, sind, research_mode=False).run()
    bpb = round(r.pa_total_banked / r.pa_breach_count) if r.pa_breach_count else None
    return dict(metric="banked_per_breach", value=bpb, banked=r.pa_total_banked,
                breaches=r.pa_breach_count)


out = {"_meta": {"prereg": "NQFAMILY_stage1-2_preregistration_20260811.md",
                 "generated": "2026-08-11", "slots": list(SLOTS)}}

for sname, (sig, kind) in STRATS.items():
    fn = obj_eval if kind == "eval" else obj_pa
    for slot, sl in SLOTS.items():
        dkey = sl["dkey"]; df = DATA[dkey]
        ov = (eval_overlay if kind == "eval" else pa_overlay)(sl["dd"])
        cfg = sig.with_(contract=sl["con"], contract_size=float(sl["qty"]), **ov)
        ind = ind_for(dkey, cfg)
        sp, r12 = SPLIT[dkey], R12[dkey]
        s_is, s_oos, s_r12 = ixs(df, None, sp), ixs(df, sp, None), ixs(df, r12, None)

        e = {"taint": sl["taint"], "qty": sl["qty"], "dd_model": sl["dd"]}
        e["is_research"], _ = research(df, ind, cfg, s_is)
        e["recent12m"], _ = research(df, ind, cfg, s_r12)
        e["years"] = {}
        for tag, ya, yb in YEARS:
            e["years"][tag], _ = research(df, ind, cfg,
                                          ixs(df, pd.Timestamp(ya, tz=TZ), pd.Timestamp(yb, tz=TZ)))
        e["obj_is"] = fn(df, ind, cfg, s_is)
        e["obj_r12"] = fn(df, ind, cfg, s_r12)
        e["obj_oos"] = fn(df, ind, cfg, s_oos)
        e["oos_research"], oos_res = research(df, ind, cfg, s_oos)

        if oos_res is not None:
            tf = trades_frame(oos_res)
            if len(tf) > 5:
                pnls = tf["net"].to_numpy(); rng = np.random.default_rng(7); dds = []
                for _ in range(1000):
                    s_ = rng.choice(pnls, len(pnls), replace=True).cumsum()
                    dds.append(float((np.maximum.accumulate(s_) - s_).max()))
                e["mc_p95_maxdd_oos"] = round(float(np.percentile(dds, 95)))

        # S7: 2-tick slippage + dubbele commissie op dezelfde ene OOS-run
        scon = drep(sl["con"], commission_per_contract=sl["con"].commission_per_contract * 2,
                    slippage_ticks=2.0)
        e["stress_oos"] = fn(df, ind, cfg.with_(contract=scon), s_oos)

        out[f"{sname}|{slot}"] = e
        print(f"{sname:<11} {slot:<4} klaar", flush=True)

# ------------------------------------------------- S5 perturbatie (alleen IS) --
# ±20% op de twee parameters die de edge dragen, plus de CVD-aanname van Matador.
pert = {}
for sname, (sig, kind) in STRATS.items():
    fn = obj_eval if kind == "eval" else obj_pa
    dkey = "YM"; df = DATA[dkey]; sl = SLOTS["YM"]          # verse reeks voor perturbatie
    ov = (eval_overlay if kind == "eval" else pa_overlay)(sl["dd"])
    gmin, gmax = sig.gap_min_ticks, sig.gap_max_ticks
    variants = {
        "basis":     {},
        "gap_-20%":  dict(gap_min_ticks=round(gmin * .8, 1), gap_max_ticks=round(gmax * .8, 1)),
        "gap_+20%":  dict(gap_min_ticks=round(gmin * 1.2, 1), gap_max_ticks=round(gmax * 1.2, 1)),
        "stop_-20%": dict(max_stop_ticks=58.0),
        "stop_+20%": dict(max_stop_ticks=86.0),
        "cvd_flip":  dict(use_cvd_filter=not sig.use_cvd_filter,
                          use_cvd_streak=not sig.use_cvd_streak),
    }
    for vname, ovr in variants.items():
        cfg = sig.with_(contract=sl["con"], contract_size=float(sl["qty"]), **ov, **ovr)
        pert[f"{sname}|{vname}"] = fn(df, ind_for(dkey, cfg), cfg, ixs(df, None, SPLIT[dkey]))
        print(f"pert {sname:<11} {vname}", flush=True)
out["pert_YM_IS"] = pert

# ------------------------------------------ S6 onderlinge correlatie (dag-PnL) --
def daily_pnl(sig, dkey, con):
    df = DATA[dkey]
    cfg = sig.with_(contract=con, contract_size=1.0)
    res = Engine(cfg, df, ind_for(dkey, cfg), research_mode=True).run()
    tf = trades_frame(res)
    if not len(tf): return pd.Series(dtype=float)
    tf["d"] = pd.to_datetime(tf["exit_time"]).dt.date
    return tf.groupby("d")["net"].sum()

corr = {}
for dkey, con in (("YM", contract("YM")), ("GC", contract("GC"))):
    series = {n: daily_pnl(s, dkey, con) for n, (s, _) in STRATS.items()}
    j = pd.concat(series, axis=1, join="inner")
    corr[dkey] = {"overlap_days": int(len(j)),
                  "matrix": {a: {b: round(float(j[a].corr(j[b])), 3) for b in j.columns}
                             for a in j.columns}}
    print("corr", dkey, "klaar", flush=True)
out["corr"] = corr

with open("validation/NQFAMILY_results_20260811.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
print("ALLDONE")
