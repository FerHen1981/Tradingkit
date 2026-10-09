"""Stages 3-7 compute driver for the NQ fleet validation (pre-registered
in NQ_fleet_stage1-2_preregistration_20260810.md — do not edit gates here).

Outputs validation/NQ_fleet_results_20260810.json with every number the
stage reports need. OOS is touched exactly once per config (+ one stress rerun,
reported as stress, per the pre-registration).
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from backtest import data as dm, indicators as im
from backtest.config import PRESETS, EL_TORO, contract
from backtest.engine import Engine, extract
from backtest.funnel import run_funnel, summarize
from backtest.metrics import kpis, trades_frame
from tools.legacy_accounts_analysis import GC_SIG, ES_SIG

CVD_OFF = dict(use_cvd_filter=False, use_cvd_streak=False)
DATA = "data/NQ_1m_last3y_slim.csv"
OOS_START = pd.Timestamp("2025-12-17", tz="America/New_York")
Y = [("Y1", "2023-06-18", "2024-06-18"), ("Y2", "2024-06-18", "2025-06-18"),
     ("Y3", "2025-06-18", "2026-06-18")]
R12_START = pd.Timestamp("2025-06-17", tz="America/New_York")

TORO = EL_TORO.with_(name="TORO_EVAL", gap_max_ticks=12.0, **CVD_OFF)      # 9-12, conf2, q5
DORADO = PRESETS["EL_DORADO_TUNED"].with_(name="DORADO_PA", **CVD_OFF)     # 9-12, conf0, dt300, q2
PATRON = PRESETS["EL_PATRON"].with_(name="PATRON_PA", day_trail_usd=300.0, **CVD_OFF)

out = {}
df = dm.load(DATA)
et = df["et"]

def slice_ix(a=None, b=None):
    m = pd.Series(True, index=df.index)
    if a is not None: m &= et >= a
    if b is not None: m &= et < b
    ix = df.index[m]
    return int(ix[0]), int(ix[-1]) + 1

def sub(df_, ind_, a, b):
    return df_.iloc[a:b].reset_index(drop=True), ind_.iloc[a:b].reset_index(drop=True)

def research(cfg, ind, a, b):
    sdf, sind = sub(df, ind, a, b)
    res = Engine(cfg, sdf, sind, research_mode=True).run()
    k = kpis(res)
    return dict(trades=k.get("trades", 0), pf=k.get("profit_factor", 0),
                win=k.get("win_rate_pct", 0), net=k.get("net_profit", 0),
                maxdd=k.get("max_drawdown", 0)), res

def funnel(cfg, ind, a, b):
    sdf, sind = sub(df, ind, a, b)
    s = summarize(run_funnel(cfg, sdf, sind, step_sessions=5, horizon_sessions=20))
    return dict(starts=s["starts"], passr=s["pass_rate_pct"],
                breach=round(100*s["breach"]/max(s["starts"],1),1),
                timeout=round(100*s["timeout"]/max(s["starts"],1),1))

def pa(cfg, ind, a, b):
    sdf, sind = sub(df, ind, a, b)
    r = Engine(cfg, sdf, sind, research_mode=False).run()
    return dict(banked=r.pa_total_banked, breaches=r.pa_breach_count,
                milk=r.pa_milk_count,
                bpb=round(r.pa_total_banked/r.pa_breach_count, 0) if r.pa_breach_count else None)

is_a, is_b = slice_ix(None, OOS_START)
oos_a, oos_b = slice_ix(OOS_START, None)
r12_a, r12_b = slice_ix(R12_START, None)

# ---------------- per config: S3/S4 + one-shot OOS ----------------
for cfg in (TORO, DORADO, PATRON):
    c = cfg.with_(contract=contract("NQ"))
    ind = im.compute(df, c)
    e = {}
    # S3: IS trade count
    e["is_research"], is_res = research(c, ind, is_a, is_b)
    # S4: per regime year + recent 12m (research/contract lens)
    e["years"] = {}
    for tag, a_, b_ in Y:
        aa, bb = slice_ix(pd.Timestamp(a_, tz="America/New_York"), pd.Timestamp(b_, tz="America/New_York"))
        e["years"][tag], _ = research(c, ind, aa, bb)
    e["recent12m"], _ = research(c, ind, r12_a, r12_b)
    # account lens (objective), IS + recent12m + ONE-SHOT OOS
    if c.name == "TORO_EVAL":
        e["obj_is"] = funnel(c, ind, is_a, is_b)
        e["obj_r12"] = funnel(c, ind, r12_a, r12_b)
        e["obj_oos"] = funnel(c, ind, oos_a, oos_b)
    else:
        e["obj_is"] = pa(c, ind, is_a, is_b)
        e["obj_r12"] = pa(c, ind, r12_a, r12_b)
        e["obj_oos"] = pa(c, ind, oos_a, oos_b)
    e["oos_research"], oos_res = research(c, ind, oos_a, oos_b)
    # Monte Carlo p5 max-drawdown from OOS trade PnLs (account-DD lens)
    tf = trades_frame(oos_res)
    if len(tf):
        pnls = tf["net"].to_numpy()
        rng = np.random.default_rng(42)
        dds = []
        for _ in range(1000):
            s_ = rng.choice(pnls, size=len(pnls), replace=True).cumsum()
            dds.append(float((np.maximum.accumulate(s_) - s_).max()))
        e["mc_p5_maxdd_oos"] = float(np.percentile(dds, 95))
        e["oos_trades_n"] = int(len(pnls))
    out[c.name] = e
    print(c.name, "done", flush=True)

# ---------------- S5: perturbations, IS ONLY (TORO objective) ----------------
pert = {}
base_is = out["TORO_EVAL"]["obj_is"]["passr"]
variants = {
    "gap_7_10":  dict(gap_min_ticks=7.0, gap_max_ticks=10.0),
    "gap_11_14": dict(gap_min_ticks=11.0, gap_max_ticks=14.0),
    "stop_58":   dict(max_stop_ticks=58.0),
    "stop_86":   dict(max_stop_ticks=86.0),
    "confirm_0": dict(confirm_bars=0),
    "confirm_4": dict(confirm_bars=4),
    "SENS_delta_ON": dict(use_cvd_filter=True, use_cvd_streak=True),
}
for name, ov in variants.items():
    c = TORO.with_(contract=contract("NQ"), **ov)
    ind = im.compute(df, c)
    pert[name] = funnel(c, ind, is_a, is_b)
    print("pert", name, "done", flush=True)
out["perturbations_IS"] = dict(base_passr=base_is, variants=pert)

# ---------------- S7: stress on OOS (2-tick slip, doubled commission) --------
stress = {}
nq_stress = contract("NQ")
from dataclasses import replace as drep
nq_stress = drep(nq_stress, commission_per_contract=3.10, slippage_ticks=2.0)
for cfg in (TORO, DORADO, PATRON):
    c = cfg.with_(contract=nq_stress)
    ind = im.compute(df, c)
    if c.name == "TORO_EVAL":
        stress[c.name] = funnel(c, ind, oos_a, oos_b)
    else:
        stress[c.name] = pa(c, ind, oos_a, oos_b)
    print("stress", c.name, "done", flush=True)
out["stress_OOS"] = stress

# ---------------- S6: daily-PnL correlation vs GC (Minero) / ES (León) ------
def daily_pnl(sym, sig, path):
    d2 = dm.load(path)
    c = sig.with_(contract=contract(sym))
    ind2 = im.compute(d2, c)
    res = Engine(c, d2, ind2, research_mode=True).run()
    tf = trades_frame(res)
    tf["d"] = pd.to_datetime(tf["exit_time"]).dt.date
    return tf.groupby("d")["net"].sum()

c = TORO.with_(contract=contract("NQ"))
ind = im.compute(df, c)
res = Engine(c, df, ind, research_mode=True).run()
tfn = trades_frame(res); tfn["d"] = pd.to_datetime(tfn["exit_time"]).dt.date
nq_d = tfn.groupby("d")["net"].sum()
cors = {}
for sym, sig, path in (("GC", GC_SIG, "data/GC_norm.csv"), ("ES", ES_SIG, "data/ES_norm.csv")):
    od = daily_pnl(sym, sig, path)
    join = pd.concat([nq_d, od], axis=1, join="inner")
    join.columns = ["nq", sym.lower()]
    cors[f"TORO_vs_{sym}"] = dict(corr=round(float(join["nq"].corr(join[sym.lower()])), 3),
                                  overlap_days=int(len(join)))
    print("corr", sym, "done", flush=True)
out["correlations"] = cors

with open("validation/NQ_fleet_results_20260810.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
print("ALLDONE")
