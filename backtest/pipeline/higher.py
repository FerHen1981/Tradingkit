"""Stages 3–9 of the v7 pipeline — from a validated mechanic to a funded engine.

Each function takes the engine's frozen Config and a prepared dataframe and
returns a dict with a `status` (passed / inconclusive / failed), a plain-Dutch
`verdict`, and the measured evidence. They never optimise — the parameters are
frozen (changing them is a new research round from stage 1). They MEASURE
whether the frozen mechanic survives the question each stage asks.

  3 regimes        — where does the edge live, and is it concentrated?
  4 plateau        — is it a broad plateau or a sharp (overfit) peak?
  5 sizing         — does the full stop fit under the DLL; is PF size-invariant?
  6 daily_mgmt     — does day management earn payout-$, or only smooth equity?
  7 pa_lifecycle   — does a funded account survive under EOD and Intraday DD?
  8 time_for_money — banked payout-$ per occupied account-day (THE objective)
  9 prod_vs_harvest— does the edge stand without hour/day cherry-picking?
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict

import numpy as np

from .. import indicators as im
from ..engine import Engine


# --- shared -------------------------------------------------------------------

def _run(cfg, df, research=True):
    """Run the engine and return its Result."""
    return Engine(cfg, df, im.compute(df, cfg), research_mode=research).run()


def _edge(nets) -> dict:
    """Expectancy / PF / win-rate / net for a list of trade P&Ls."""
    nets = [float(x) for x in nets]
    n = len(nets)
    if not n:
        return {"trades": 0, "net": 0.0, "pf": 0.0, "wr": 0.0, "expectancy": 0.0}
    wins = [x for x in nets if x > 0]
    gl = -sum(x for x in nets if x <= 0)
    return {"trades": n, "net": round(sum(nets), 2),
            "pf": round(sum(wins) / gl, 2) if gl > 0 else float("inf"),
            "wr": round(100 * len(wins) / n, 1),
            "expectancy": round(sum(nets) / n, 2)}


def _one_contract(cfg):
    """Strip sizing and day caps: the intrinsic mechanic, like stage 2."""
    return dataclasses.replace(cfg, contract_size=1.0, day_exit_mode="Off")


# --- stage 3 · regime diagnostics --------------------------------------------

def stage3(cfg, df, engine) -> dict:
    """Report the edge IN / OUT / ALL for each regime. A regime earns the right
    to be a filter only if its effect is both robust and economically sensible —
    this stage does NOT filter, it exposes where the edge lives so a later,
    economically-motivated choice can be made (never day×hour cherry-picking)."""
    base = _one_contract(cfg)
    res = _run(base, df)
    if not res.trades:
        return {"status": "failed", "verdict": "geen trades — geen regime-diagnose", "by_regime": {}}

    labels = im.regime_labels(df, base)
    lab = np.asarray(labels)
    # attribute each trade to the regime at its entry bar
    all_nets = [float(t.net) for t in res.trades if t.exit_time is not None]
    by_reg = defaultdict(list)
    for t in res.trades:
        if t.exit_time is None:
            continue
        r = lab[t.entry_bar] if 0 <= t.entry_bar < len(lab) else "?"
        by_reg[str(r)].append(float(t.net))

    total = _edge(all_nets)
    rows = {}
    for reg, nets in sorted(by_reg.items(), key=lambda kv: -sum(kv[1])):
        e_in = _edge(nets)
        e_out = _edge([x for r, xs in by_reg.items() if r != reg for x in xs])
        rows[reg] = {"in": e_in, "out": e_out,
                     "share_pct": round(100 * len(nets) / total["trades"], 1)}

    # concentration: how much of the net comes from the single best regime?
    best = max(rows.items(), key=lambda kv: kv[1]["in"]["net"]) if rows else (None, None)
    best_share = (round(100 * best[1]["in"]["net"] / total["net"], 1)
                  if best[0] and total["net"] > 0 else None)
    concentrated = best_share is not None and best_share > 70 and len(rows) > 1

    status = "inconclusive" if concentrated else "passed"
    verdict = (f"edge geconcentreerd: {best_share}% van de netto komt uit regime "
               f"'{best[0]}' — een regimefilter is pas geldig als dat economisch "
               f"verklaarbaar is, niet als curve-fit"
               if concentrated else
               f"edge gespreid over {len(rows)} regimes; geen enkel regime draagt "
               f"de winst alleen — regime-diagnose compleet")
    return {"status": status, "verdict": verdict, "total": total,
            "by_regime": rows, "best_regime": best[0], "best_share_pct": best_share}


# --- stage 4 · plateau / robustness ------------------------------------------

def _sub_periods(res, key):
    """{period: [net,...]} keyed by year or year-quarter of the exit."""
    out = defaultdict(list)
    for t in res.trades:
        if t.exit_time is None:
            continue
        ts = t.exit_time
        k = ts.year if key == "year" else f"{ts.year}Q{(ts.month - 1) // 3 + 1}"
        out[k].append(float(t.net))
    return out


def stage4(cfg, df, engine) -> dict:
    """Broad plateau, not a sharp peak. Two independent checks:

    (a) SUB-PERIOD robustness — positive across most years and quarters, and both
        LONG and SHORT contribute (an edge carried by one side is fragile).
    (b) PARAMETER neighbourhood — nudging the frozen stop / R / FVG band by one
        step must not collapse the edge. A sharp peak that only works at the
        exact frozen values is overfit; a plateau survives its neighbourhood.
    """
    base = _one_contract(cfg)
    res = _run(base, df)
    if not res.trades:
        return {"status": "failed", "verdict": "geen trades", "years": {}, "neighbourhood": []}

    years = {y: _edge(n) for y, n in _sub_periods(res, "year").items()}
    quarters = {q: _edge(n) for q, n in _sub_periods(res, "quarter").items()}
    longs = _edge([float(t.net) for t in res.trades if t.dir > 0 and t.exit_time])
    shorts = _edge([float(t.net) for t in res.trades if t.dir < 0 and t.exit_time])

    pos_y = sum(1 for e in years.values() if e["expectancy"] > 0)
    pos_q = sum(1 for e in quarters.values() if e["expectancy"] > 0)
    both_sides = longs["expectancy"] > 0 and shorts["expectancy"] > 0

    # parameter neighbourhood: +/- 1 step on the levers that define the setup
    neigh = []
    for attr, step in (("fixed_stop_ticks", cfg.contract.mintick and 10),
                       ("r_multiple", 0.25), ("gap_min_ticks", 1), ("gap_max_ticks", 2)):
        for sign in (-1, 1):
            val = getattr(cfg, attr) + sign * step
            if val <= 0:
                continue
            m = dataclasses.replace(base, **{attr: float(val),
                                             **({"max_stop_ticks": float(val)}
                                                if attr == "fixed_stop_ticks" else {})})
            r = _run(m, df)
            e = _edge([float(t.net) for t in r.trades if t.exit_time])
            neigh.append({"param": attr, "delta": sign * step, "value": float(val),
                          "pf": e["pf"], "trades": e["trades"], "net": e["net"]})

    # a plateau: neighbours stay profitable (PF>1) and near the base PF
    prof_neigh = sum(1 for x in neigh if x["pf"] > 1.0)
    plateau = neigh and prof_neigh >= 0.7 * len(neigh)

    robust = (pos_y >= max(1, round(0.6 * len(years)))
              and pos_q >= max(1, round(0.6 * len(quarters))) and both_sides)
    ok = robust and plateau
    if ok:
        verdict = (f"plateau: positief in {pos_y}/{len(years)} jaren, {pos_q}/{len(quarters)} "
                   f"kwartalen, LONG én SHORT positief, en {prof_neigh}/{len(neigh)} "
                   f"parameterburen blijven winstgevend")
    elif robust and not plateau:
        verdict = (f"SCHERPE PIEK: sub-periodes houden stand maar slechts {prof_neigh}/"
                   f"{len(neigh)} parameterburen blijven winstgevend — de edge leunt op "
                   f"de exacte bevroren waarden (overfit-risico)")
    else:
        reasons = []
        if pos_y < max(1, round(0.6 * len(years))):
            reasons.append(f"maar {pos_y}/{len(years)} jaren positief")
        if not both_sides:
            reasons.append("één handelsrichting draagt de edge")
        verdict = "NIET ROBUUST: " + "; ".join(reasons or ["sub-periodes wisselvallig"])
    status = "passed" if ok else ("inconclusive" if (robust or plateau) else "failed")
    return {"status": status, "verdict": verdict, "years": years, "quarters": quarters,
            "long": longs, "short": shorts, "neighbourhood": neigh,
            "plateau": plateau, "robust": robust}


# --- stage 5 · sizing & pro-rata risk ----------------------------------------

def stage5(cfg, df, engine) -> dict:
    """The full stop, in dollars at the engine's contract size, must sit UNDER the
    daily loss limit before slippage/commission — otherwise one stop can breach a
    day. And sizing may change throughput and risk but NOT the intrinsic PF:
    the per-contract edge is the same at 1 and at N."""
    ct = cfg.contract
    qty = float(cfg.contract_size)
    stop_ticks = float(cfg.max_stop_ticks or cfg.fixed_stop_ticks)
    stop_usd_1 = stop_ticks * ct.mintick * ct.pointvalue
    stop_usd_n = stop_usd_1 * qty
    dll = float(cfg.acct_dll or 0)
    slip_usd = float(ct.slippage_ticks) * ct.mintick * ct.pointvalue * qty
    comm_usd = float(ct.commission_per_contract) * qty * 2
    worst = stop_usd_n + slip_usd + comm_usd
    fits = dll <= 0 or worst < dll

    # PF invariance: 1 contract vs N contracts (costs scale, PF barely moves)
    pf1 = _edge([float(t.net) for t in _run(_one_contract(cfg), df).trades if t.exit_time])
    cfgn = dataclasses.replace(cfg, day_exit_mode="Off")     # N contracts, no day caps
    pfn = _edge([float(t.net) for t in _run(cfgn, df).trades if t.exit_time])
    pf_gap = (abs(pf1["pf"] - pfn["pf"]) / pf1["pf"] if pf1["pf"] else 1.0)
    invariant = pf_gap <= 0.15

    ok = fits and invariant
    if ok:
        verdict = (f"sizing gezond: volledige stop ${stop_usd_n:,.0f} + kosten = ${worst:,.0f} "
                   f"< DLL ${dll:,.0f}; PF {pf1['pf']} (1) vs {pfn['pf']} ({qty:.0f}) — "
                   f"grootte verandert doorvoer, niet de edge")
    elif not fits:
        verdict = (f"STOP TE GROOT: één volledige stop ${worst:,.0f} (incl. kosten) ≥ DLL "
                   f"${dll:,.0f} — één verliestrade kan de dag al breachen")
    else:
        verdict = (f"PF NIET GROOTTE-INVARIANT: {pf1['pf']} (1) vs {pfn['pf']} ({qty:.0f}), "
                   f"{pf_gap*100:.0f}% verschil — sizing raakt de intrinsieke edge (verdacht)")
    status = "passed" if ok else "failed"
    return {"status": status, "verdict": verdict, "stop_usd_per_contract": round(stop_usd_1, 2),
            "stop_usd_total": round(stop_usd_n, 2), "worst_case_usd": round(worst, 2),
            "dll": dll, "fits_under_dll": fits, "pf_1": pf1["pf"], "pf_n": pfn["pf"],
            "pf_invariant": invariant, "qty": qty}


# --- stages 6/7/8 · account overlay ------------------------------------------

def _daily(res):
    from ..funded import daily_from_trades
    return daily_from_trades(res.trades)


def _funded(res, cfg, drawdown_type):
    from ..funded import simulate_funded, summarize
    daily = _daily(res)
    fr = simulate_funded(daily, account_size=50_000, drawdown_type=drawdown_type,
                         drawdown=float(cfg.acct_trail_dd or 2500),
                         daily_loss_limit=float(cfg.acct_dll) if cfg.acct_dll else None)
    s = summarize(fr)
    days = s["trading_days"] or 0
    s["banked_per_account_day"] = round(s["withdrawable"] / days, 2) if days else 0.0
    return s


def stage6(cfg, df, engine) -> dict:
    """Day management (cap / giveback / activation) is judged on payout economics,
    not on cosmetic equity smoothness. Compare banked payout-$ per account-day
    WITH the engine's day-exit block versus WITHOUT it."""
    dd_type = "eod_trailing" if cfg.dd_model == "EOD" else "intraday_trailing"
    without = _funded(_run(dataclasses.replace(cfg, day_exit_mode="Off"), df, research=False),
                      cfg, dd_type)
    with_ = _funded(_run(cfg, df, research=False), cfg, dd_type)

    b0, b1 = without["banked_per_account_day"], with_["banked_per_account_day"]
    breach0, breach1 = without["breached"], with_["breached"]
    saves_breach = breach0 and not breach1
    helps = b1 >= b0 - 1e-9
    # both banking nothing (e.g. both breach) is not evidence either way
    if b0 <= 0 and b1 <= 0:
        return {"status": "inconclusive",
                "verdict": (f"geen payout in beide varianten (mét breach: {with_['breached']}, "
                            f"zonder: {without['breached']}) — dagbeheer niet te beoordelen op "
                            f"deze data/periode"),
                "with_day_mgmt": with_, "without_day_mgmt": without}
    ok = helps or saves_breach
    if saves_breach and not helps:
        verdict = (f"dagbeheer voorkomt een breach (zonder: {without['breach_reason']}) — "
                   f"gerechtvaardigd ondanks lagere payout/dag")
    elif helps:
        verdict = (f"dagbeheer verdient payout: ${b1}/account-dag mét vs ${b0} zonder")
    else:
        verdict = (f"dagbeheer kost payout: ${b1}/account-dag mét vs ${b0} zonder, en "
                   f"voorkomt geen breach — cosmetische equity-gladheid, geen economie")
    return {"status": "passed" if ok else "inconclusive", "verdict": verdict,
            "with_day_mgmt": with_, "without_day_mgmt": without}


def stage7(cfg, df, engine) -> dict:
    """Run the funded account under BOTH Apex 50K drawdown models — EOD and
    Intraday — AND at two sizings: the frozen contract size and 1 contract.

    The two sizings separate two very different failures: a strategy whose EDGE
    cannot fund even at 1 contract, versus one that funds at 1 contract but whose
    FROZEN full size breaches a fresh account before the trailing floor locks
    (the .pine scales in via its derisk logic; the frozen config does not). Both
    are reported so the distinction is visible, not hidden behind one verdict."""
    intended = "eod" if cfg.dd_model == "EOD" else "intraday"

    def at(qty_cfg):
        res = _run(qty_cfg, df, research=False)
        return {"eod": _funded(res, qty_cfg, "eod_trailing"),
                "intraday": _funded(res, qty_cfg, "intraday_trailing")}

    full = at(cfg)
    one = at(dataclasses.replace(cfg, contract_size=1.0))
    full_ok = not full[intended]["breached"] and full[intended]["payouts"] > 0
    one_ok = not one[intended]["breached"] and one[intended]["payouts"] > 0

    if full_ok:
        status, verdict = "passed", (
            f"overleeft en betaalt uit onder {cfg.dd_model} op volle grootte "
            f"({cfg.contract_size:.0f} ct): {full[intended]['payouts']} payouts, "
            f"${full[intended]['withdrawable']:,.0f} gebankt")
    elif one_ok:
        status, verdict = "inconclusive", (
            f"funderbaar op 1 contract ({one[intended]['payouts']} payouts) maar de "
            f"BEVROREN {cfg.contract_size:.0f} ct breacht een vers account "
            f"({full[intended]['breach_reason']}) — vraagt om contract-scaling "
            f"(de .pine derisk-logica), niet gemodelleerd in de bevroren config")
    else:
        status, verdict = "failed", (
            f"haalt geen payout onder {cfg.dd_model}, zelfs niet op 1 contract"
            + (f" (breach: {one[intended]['breach_reason']})" if one[intended]["breached"] else ""))
    return {"status": status, "verdict": verdict, "intended_model": cfg.dd_model,
            "full_size": full, "one_contract": one, "frozen_qty": cfg.contract_size,
            "note": "Intraday trailt op gerealiseerde P&L, niet op ongerealiseerde MFE — "
                    "conservatief gelabeld (grondregel trap 7)"}


def stage8(cfg, df, engine) -> dict:
    """Time-for-money — the objective. Banked payout-$ per occupied account-day.

    Reported at the frozen size AND at 1 contract, because a config that breaches
    at full size still has a real per-day throughput at the survivable size —
    and banked-$/day at a size that breaches on day 20 is a mirage."""
    dd_type = "eod_trailing" if cfg.dd_model == "EOD" else "intraday_trailing"

    def metrics(qty_cfg):
        res = _run(qty_cfg, df, research=False)
        s = _funded(res, qty_cfg, dd_type)
        daily = _daily(res)
        dll = float(qty_cfg.acct_dll or 0)
        s["dll_hits"] = sum(1 for v in daily.values() if dll and v <= -dll)
        return s

    full = metrics(cfg)
    one = metrics(dataclasses.replace(cfg, contract_size=1.0))
    # the objective is measured at the sizing that actually survives to pay out
    survivor = full if (not full["breached"] and full["banked_per_account_day"] > 0) else one
    at_full = survivor is full
    per_day = survivor["banked_per_account_day"]
    ok = per_day > 0 and not survivor["breached"]
    size_lbl = f"{cfg.contract_size:.0f} ct" if at_full else "1 ct (volle grootte breacht)"
    if ok:
        verdict = (f"${per_day}/bezette account-dag op {size_lbl} · {survivor['payouts']} payouts "
                   f"(P1 na {survivor['days_to_first_payout']} handelsdagen) · "
                   f"{survivor['dll_hits']} DLL-hits")
    else:
        verdict = (f"geen gebankte payout, ook niet op 1 contract: "
                   + (survivor["breach_reason"] if survivor["breached"]
                      else f"${per_day}/account-dag"))
    return {"status": "passed" if ok else "failed", "verdict": verdict,
            "banked_per_account_day": per_day, "measured_at_full_size": at_full,
            "frozen_qty": cfg.contract_size, "full_size": full, "one_contract": one,
            "payouts": survivor["payouts"], "days_to_first_payout": survivor["days_to_first_payout"],
            "dll_hits": survivor["dll_hits"], "trading_days": survivor["trading_days"],
            "breached": survivor["breached"], "withdrawable": survivor["withdrawable"],
            "per_month": survivor["per_month"]}


# --- stage 9 · production vs harvest -----------------------------------------

def stage9(cfg, df, engine) -> dict:
    """Two candidates kept; neither leans on hour/day cherry-picking. For a single
    engine this checks the fragility side: does the edge SURVIVE when the
    fine-grained hour and weekday filters are neutralised (trade every session
    hour, every weekday)? An edge that only exists with a specific hour/day mask
    is cherry-picked, not structural."""
    base = _one_contract(cfg)
    with_filter = _edge([float(t.net) for t in _run(base, df).trades if t.exit_time])

    # neutralise the fine-grained gates: all hours, all weekdays
    neutral = dataclasses.replace(base,
                                  enabled_hours=frozenset(range(24)),
                                  trade_days=(0, 1, 2, 3, 4, 5, 6))
    without_filter = _edge([float(t.net) for t in _run(neutral, df).trades if t.exit_time])

    # the edge is structural if it stays positive without the mask; the mask may
    # improve it, but must not be the ONLY reason there is an edge
    survives = without_filter["expectancy"] > 0 and without_filter["pf"] > 1.0
    mask_share = (round(100 * (with_filter["net"] - without_filter["net"])
                        / with_filter["net"], 1) if with_filter["net"] > 0 else None)
    ok = survives
    verdict = (f"edge is structureel: zonder uur/dag-masker nog PF {without_filter['pf']}, "
               f"E ${without_filter['expectancy']}/trade (masker draagt {mask_share}% van de "
               f"netto bij, maar is niet de enige reden)"
               if survives else
               f"CHERRY-PICK: zonder uur/dag-masker verdampt de edge "
               f"(PF {without_filter['pf']}, E ${without_filter['expectancy']}/trade) — "
               f"de winst leunt op het masker, niet op een structurele edge")
    return {"status": "passed" if ok else "failed", "verdict": verdict,
            "with_filter": with_filter, "without_filter": without_filter,
            "mask_contribution_pct": mask_share}
