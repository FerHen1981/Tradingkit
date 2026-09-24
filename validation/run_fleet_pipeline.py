"""Stages 3-7 driver for GC/ES/MGC/MES x eval/funded (pre-registered in
FLEET_stage1-2_preregistration_20260810.md; GC/ES 'OOS' labeled TAINTED there).
Writes validation/FLEET_results_20260810.json.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from dataclasses import replace as drep

from backtest import data as dm, indicators as im
from backtest.config import Contract, contract
from backtest.engine import Engine, extract
from backtest.funnel import run_funnel, summarize
from backtest.metrics import kpis, trades_frame
from tools.legacy_accounts_analysis import GC_SIG, ES_SIG
from tools.funded_flywheel_sim import GC_FUNDED, ES_FUNDED

MGC = Contract("MGC", 0.1, 10.0, 0.67)     # measured commission (Tradovate fills)
MES = Contract("MES", 0.25, 5.0, 0.67)

def pa_overlay(dd_model, trail_dd):
    return dict(phase="Apex PA", dd_model=dd_model, acct_trail_dd=float(trail_dd),
                acct_dll=1000.0, consistency_pct=50.0, min_payout=500.0,
                payout_buffer=500.0, use_wait_for_cap=True, use_mae_guard=True,
                day_exit_mode="Day-trail (keep peak)", day_trail_usd=300.0)

def eval_overlay(dd_model):
    return dict(phase="Apex Eval", dd_model=dd_model, acct_trail_dd=2500.0,
                acct_goal=3000.0)

CFGS = {
    # id: (data, signal_cfg, contract, qty, overlay, kind)
    "GC_EVAL":    ("GC", GC_SIG, contract("GC"), 1, eval_overlay("Intraday"), "eval"),
    "GC_FUNDED":  ("GC", GC_FUNDED, contract("GC"), 2,
                   pa_overlay("Intraday", 6500), "pa"),
    "ES_EVAL":    ("ES", ES_SIG, contract("ES"), 1, eval_overlay("EOD"), "eval"),
    "ES_FUNDED":  ("ES", ES_FUNDED, contract("ES"), 2,
                   pa_overlay("Intraday", 6500), "pa"),
    "MGC_EVAL":   ("GC", GC_SIG, MGC, 10, eval_overlay("Intraday"), "eval"),
    "MGC_FUNDED": ("GC", GC_FUNDED, MGC, 8, pa_overlay("EOD", 2500), "pa"),
    "MES_EVAL":   ("ES", ES_SIG, MES, 10, eval_overlay("EOD"), "eval"),
    "MES_FUNDED": ("ES", ES_SIG.with_(tp_mode="R-multiple"), MES, 5,
                   pa_overlay("EOD", 2500), "pa"),
}
# MES_FUNDED uses the Rey signal (== ES_FUNDED signal); fix below to reuse ind.
CFGS["MES_FUNDED"] = ("ES", ES_FUNDED, MES, 5, pa_overlay("EOD", 2500), "pa")

DATA = {"GC": dm.load("data/GC_norm.csv"), "ES": dm.load("data/ES_norm.csv")}
TZ = "America/New_York"
OOS = pd.Timestamp("2026-01-31", tz=TZ)
R12 = pd.Timestamp("2025-07-31", tz=TZ)
YEARS = [("Y1", "2023-08-02", "2024-08-01"), ("Y2", "2024-08-01", "2025-08-01"),
         ("Y3", "2025-08-01", "2026-08-01")]

def ixs(df, a=None, b=None):
    et = df["et"]; m = pd.Series(True, index=df.index)
    if a is not None: m &= et >= a
    if b is not None: m &= et < b
    ix = df.index[m]; return int(ix[0]), int(ix[-1]) + 1

_ind_cache = {}
def ind_for(dkey, cfg):
    # indicators depend on the signal layer + mintick; cache per signal name+band
    key = (dkey, cfg.name, cfg.gap_min_ticks, cfg.gap_max_ticks, cfg.confirm_bars,
           cfg.use_vwap_veto, cfg.contract.mintick, cfg.max_stop_ticks)
    if key not in _ind_cache:
        _ind_cache[key] = im.compute(DATA[dkey], cfg)
    return _ind_cache[key]

def research(df, ind, cfg, a, b):
    sdf = df.iloc[a:b].reset_index(drop=True); sind = ind.iloc[a:b].reset_index(drop=True)
    res = Engine(cfg, sdf, sind, research_mode=True).run()
    k = kpis(res)
    return dict(trades=k.get("trades", 0), pf=k.get("profit_factor", 0),
                win=k.get("win_rate_pct", 0), net=round(k.get("net_profit", 0))), res

def funnel(df, ind, cfg, a, b):
    sdf = df.iloc[a:b].reset_index(drop=True); sind = ind.iloc[a:b].reset_index(drop=True)
    s = summarize(run_funnel(cfg, sdf, sind, step_sessions=5, horizon_sessions=20))
    return dict(starts=s["starts"], passr=s["pass_rate_pct"],
                breach=round(100*s["breach"]/max(s["starts"],1),1),
                timeout=round(100*s["timeout"]/max(s["starts"],1),1))

def pa(df, ind, cfg, a, b):
    sdf = df.iloc[a:b].reset_index(drop=True); sind = ind.iloc[a:b].reset_index(drop=True)
    r = Engine(cfg, sdf, sind, research_mode=False).run()
    return dict(banked=r.pa_total_banked, breaches=r.pa_breach_count, milk=r.pa_milk_count,
                bpb=round(r.pa_total_banked/r.pa_breach_count) if r.pa_breach_count else None)

out = {}
for cid, (dkey, sig, con, qty, ov, kind) in CFGS.items():
    df = DATA[dkey]
    cfg = sig.with_(contract=con, contract_size=float(qty), **ov)
    ind = ind_for(dkey, cfg)
    a_is, b_is = ixs(df, None, OOS); a_o, b_o = ixs(df, OOS, None); a_r, b_r = ixs(df, R12, None)
    e = {}
    e["is_research"], _ = research(df, ind, cfg, a_is, b_is)
    e["years"] = {}
    for tag, ya, yb in YEARS:
        aa, bb = ixs(df, pd.Timestamp(ya, tz=TZ), pd.Timestamp(yb, tz=TZ))
        e["years"][tag], _ = research(df, ind, cfg, aa, bb)
    e["recent12m"], _ = research(df, ind, cfg, a_r, b_r)
    fn = funnel if kind == "eval" else pa
    e["obj_is"] = fn(df, ind, cfg, a_is, b_is)
    e["obj_r12"] = fn(df, ind, cfg, a_r, b_r)
    e["obj_oos"] = fn(df, ind, cfg, a_o, b_o)          # quasi-OOS [TAINTED] for signal choice
    e["oos_research"], oos_res = research(df, ind, cfg, a_o, b_o)
    tf = trades_frame(oos_res)
    if len(tf):
        pnls = tf["net"].to_numpy(); rng = np.random.default_rng(7); dds = []
        for _ in range(1000):
            s_ = rng.choice(pnls, len(pnls), replace=True).cumsum()
            dds.append(float((np.maximum.accumulate(s_) - s_).max()))
        e["mc_p5_maxdd_oos"] = round(float(np.percentile(dds, 95)))
    # stress (quasi-OOS): 2-tick slip + doubled commission
    scon = drep(con, commission_per_contract=con.commission_per_contract*2, slippage_ticks=2.0)
    scfg = cfg.with_(contract=scon)
    e["stress_oos"] = fn(df, ind, scfg, a_o, b_o)
    out[cid] = e
    print(cid, "done", flush=True)

# perturbations, IS only, on the eval funnels (signal-level)
def pert_block(dkey, base_sig, con, variants):
    df = DATA[dkey]; res = {}
    for name, ovr in variants.items():
        cfg = base_sig.with_(contract=con, contract_size=1.0,
                             **eval_overlay("Intraday" if dkey == "GC" else "EOD"), **ovr)
        ind = ind_for(dkey, cfg)
        a_is, b_is = ixs(df, None, OOS)
        res[name] = funnel(df, ind, cfg, a_is, b_is)
        print("pert", dkey, name, flush=True)
    return res

out["pert_GC_IS"] = pert_block("GC", GC_SIG, contract("GC"), {
    "gap_6_15": dict(gap_min_ticks=6., gap_max_ticks=15.),
    "gap_12_21": dict(gap_min_ticks=12., gap_max_ticks=21.),
    "stop_80": dict(fixed_stop_ticks=80., max_stop_ticks=80.),
    "stop_120": dict(fixed_stop_ticks=120., max_stop_ticks=120.),
    "confirm_2": dict(confirm_bars=2),
})
out["pert_ES_IS"] = pert_block("ES", ES_SIG, contract("ES"), {
    "gap_6_12": dict(gap_min_ticks=6., gap_max_ticks=12.),
    "gap_12_18": dict(gap_min_ticks=12., gap_max_ticks=18.),
    "stop_80": dict(fixed_stop_ticks=80., max_stop_ticks=80.),
    "stop_120": dict(fixed_stop_ticks=120., max_stop_ticks=120.),
    "confirm_0": dict(confirm_bars=0),
})

# micro funded qty sensitivity (IS)
qs = {}
for cid, qlist in (("MGC_FUNDED", [6, 10]), ("MES_FUNDED", [3, 6])):
    dkey, sig, con, qty, ov, kind = CFGS[cid]
    df = DATA[dkey]
    for q in qlist:
        cfg = sig.with_(contract=con, contract_size=float(q), **ov)
        ind = ind_for(dkey, cfg)
        a_is, b_is = ixs(df, None, OOS)
        qs[f"{cid}_q{q}"] = pa(df, ind, cfg, a_is, b_is)
        print("qty", cid, q, flush=True)
out["qty_sens_IS"] = qs

# GC<->ES daily-PnL correlation (research, full window)
def daily(dkey, sig, con):
    df = DATA[dkey]
    cfg = sig.with_(contract=con)
    ind = ind_for(dkey, cfg)
    res = Engine(cfg, df, ind, research_mode=True).run()
    tf = trades_frame(res); tf["d"] = pd.to_datetime(tf["exit_time"]).dt.date
    return tf.groupby("d")["net"].sum()
g = daily("GC", GC_SIG, contract("GC")); s = daily("ES", ES_SIG, contract("ES"))
j = pd.concat([g, s], axis=1, join="inner"); j.columns = ["gc", "es"]
out["corr_GC_ES"] = dict(corr=round(float(j["gc"].corr(j["es"])), 3), overlap_days=int(len(j)))

with open("validation/FLEET_results_20260810.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
print("ALLDONE")
