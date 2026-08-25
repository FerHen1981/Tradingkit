"""Run one pipeline stage, or reset the lab.

    python -m backtest.pipeline.cli plan
    python -m backtest.pipeline.cli fleet --through 2   # hele vloot, alle trappen
    python -m backtest.pipeline.cli coverage    # wat kan trap 1 draaien, wat mist
    python -m backtest.pipeline.cli report      # laatste trap-1 uitslag per engine
    python -m backtest.pipeline.cli sensitivity --dataset D --engine E
    python -m backtest.pipeline.cli stage0 --dataset MGC_20y_1m --engine EL_TESORO_MGC_CON_EOD
    python -m backtest.pipeline.cli stage1 --dataset MGC_20y_1m --engine EL_TESORO_MGC_CON_EOD \
        --export path/to/TESORO_export.xlsx
    python -m backtest.pipeline.cli stage2 --dataset D --engine E   # structurele edge
    python -m backtest.pipeline.cli reset --yes      # wipes results/history, KEEPS datasets
"""
from __future__ import annotations

import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import shutil
import sys

from . import fleet, state
from .stages import STAGES
from ..lab.paths import datasets_dir, lab_root


def _dataset_path(name: str) -> tuple[str, str]:
    from ..lab.lab_viewer import _datasets
    for d in _datasets():
        if d["name"] == name:
            return d["file"], (d.get("symbol") or "")
    raise SystemExit(f"unknown dataset {name!r} — see 1 · Data")


def _f_or_none(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _resolve_export(name: str) -> str:
    """Accept either a path or a bare export name.

    The lab UI resolves names against the export directories; the CLI used to
    hand its argument straight to openpyxl, so `--export FOO.xlsx` failed with a
    FileNotFoundError unless you happened to be standing in the right folder."""
    from pathlib import Path

    from ..lab.lab_viewer import _export_dirs, _export_path, _exports
    p = Path(name).expanduser()
    if p.is_file():
        return str(p)
    found = _export_path(name)
    if found is not None:
        return str(found)
    known = _exports()
    where = ", ".join(str(d) for d in _export_dirs()) or "(geen exportmap)"
    raise SystemExit(
        f"export {name!r} niet gevonden. Gezocht in: {where}\n"
        + ("  beschikbaar:\n" + "\n".join(f"    {x}" for x in known) if known
           else "  er staan daar geen .xlsx-bestanden"))


def _dt(value):
    """Parse a manifest timestamp ('24-08-2025 18:00:00 -04:00') to a naive date."""
    from datetime import datetime
    txt = str(value or "").strip()
    for fmt in ("%d-%m-%Y %H:%M:%S %z", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


# A dataset that stops shortly before the export's end is still usable: stage 1
# gates on trade count within 10%, so a window shortfall well under that cannot
# by itself blow the gate. Half the trade tolerance is the line — beyond it the
# comparison stops being about engine semantics and starts being about missing bars.
SHORT_TAIL_TOLERANCE = 0.05

# Below this share of entries aligning with the export, matching KPIs are not
# evidence of the same engine — see the note at the gate in cmd_stage1.
MIN_PAIRED_PCT = 70.0


def window_overlap(ds_first, ds_last, exp_start, exp_end) -> dict:
    """How much of the export's window a dataset actually covers."""
    if not all((ds_first, ds_last, exp_start, exp_end)):
        return {"known": False, "missing_frac": None, "missing_days": None,
                "verdict": "onbekend"}
    span = (exp_end - exp_start).days or 1
    lo, hi = max(ds_first, exp_start), min(ds_last, exp_end)
    have = max((hi - lo).days, 0)
    missing = max(span - have, 0)
    frac = missing / span
    verdict = ("volledig" if missing == 0 else
               "bijna volledig" if frac <= SHORT_TAIL_TOLERANCE else "te kort")
    return {"known": True, "missing_frac": round(frac, 4), "missing_days": missing,
            "span_days": span, "first_gap_days": max((lo - exp_start).days, 0),
            "tail_gap_days": max((exp_end - hi).days, 0), "verdict": verdict}


def cmd_coverage(_args):
    """What can trap 1 actually run today, and what data is missing?

    Trap 1 is a hard gate, so this answers the only question that matters while
    it is open: for each TradingView export we hold, is there a dataset that
    covers the market AND (near enough) the window the export was tested over?

    A mini's price history counts for its micro (see fleet.TWIN) — same ticks,
    same trade sequence. A short tail is reported in days rather than waved
    through or treated as fatal."""
    from ..lab.lab_viewer import _datasets, _export_dirs, _export_path, _exports
    from .parity import export_window, read_export

    dsets = [{"name": d["name"], "symbol": (d.get("symbol") or "").upper(),
              "first": _dt(d.get("first")), "last": _dt(d.get("last")),
              "rows": d.get("rows")} for d in _datasets()]
    print(f"\n  trap 1 · dekking — {len(_exports())} export(s), {len(dsets)} dataset(s)")
    print(f"  exports gezocht in: {', '.join(str(d) for d in _export_dirs()) or '(geen map)'}\n")
    if dsets:
        print("  aanwezige datasets:")
        for d in dsets:
            span = (f"{d['first']:%Y-%m-%d} -> {d['last']:%Y-%m-%d}"
                    if d["first"] and d["last"] else "venster onbekend")
            print(f"    {d['name']:<28} {d['symbol']:<5} {span}"
                  f"{'  ' + format(d['rows'], ',') + ' bars' if d['rows'] else ''}")
        print()
    else:
        print("  GEEN datasets geladen — upload ze onder 1 · Data.\n")

    runnable, blocked, caveats = 0, [], []
    for nm in _exports():
        f = _export_path(nm)
        if f is None:
            continue
        exp = read_export(str(f))
        a, b = export_window(exp)
        root = "".join(c for c in str(exp.properties.get("Symbol") or "").split(":")[-1]
                       if c.isalpha())
        twin = fleet.TWIN.get(root)
        window = f"{a:%Y-%m-%d} -> {b:%Y-%m-%d}" if a and b else "onleesbaar"
        print(f"  {nm}")
        print(f"     markt {root} · getest {window} · {exp.n_trades} trades")

        best = None
        for d in [x for x in dsets if x["symbol"] in (root, twin) and x["symbol"]]:
            ov = window_overlap(d["first"], d["last"], a, b)
            rank = {"volledig": 0, "bijna volledig": 1, "onbekend": 2, "te kort": 3}
            if best is None or rank[ov["verdict"]] < rank[best[1]["verdict"]]:
                best = (d, ov)
            via = "" if d["symbol"] == root else f" (twin {d['symbol']} — zelfde ticks)"
            if ov["verdict"] == "volledig":
                print(f"     BRUIKBAAR: {d['name']}{via} — dekt het hele venster")
            elif ov["verdict"] == "bijna volledig":
                print(f"     BRUIKBAAR: {d['name']}{via} — mist {ov['missing_days']} dag(en) "
                      f"({ov['missing_frac']*100:.1f}% van het venster; loopt tot "
                      f"{d['last']:%Y-%m-%d}). Onder de 10%-tolerantie op trade count, "
                      f"dus niet de oorzaak als trap 1 faalt — wordt wel vastgelegd.")
            elif ov["verdict"] == "te kort":
                print(f"     TE KORT: {d['name']}{via} dekt {100-ov['missing_frac']*100:.0f}% "
                      f"van het venster (loopt tot {d['last']:%Y-%m-%d}, export vraagt tot "
                      f"{b:%Y-%m-%d})")
            else:
                print(f"     VENSTER ONBEKEND: {d['name']}{via} heeft geen datums in "
                      f"zijn manifest — opnieuw catalogiseren")

        if best and best[1]["verdict"] in ("volledig", "bijna volledig"):
            runnable += 1
            if best[1]["verdict"] == "bijna volledig":
                caveats.append((root, best[1]["missing_days"]))
        else:
            blocked.append((root, twin, window, best is not None))
            if best is None:
                need = root + (f" of {twin}" if twin else "")
                print(f"     GEBLOKKEERD — geen dataset voor {need}.")

    print(f"\n  {runnable} van {len(_exports())} export(s) is nu te draaien op trap 1.")
    for root, days in caveats:
        print(f"    let op: {root} mist de laatste {days} dag(en) van het exportvenster")
    if blocked:
        print("\n  ONTBREKENDE DATA (kritiek pad — trap 1 is een harde poort, dus trap 2")
        print("  t/m 9 zijn ongeldig zolang die dichtstaat):")
        for root, twin, window, partial in blocked:
            need = root + (f" (of {twin}: zelfde tick size, zelfde trades)" if twin else "")
            why = "bestaande dataset dekt te weinig" if partial else "geen dataset"
            print(f"    · 1-minuut {need}, minimaal {window}  — {why}")


def cmd_sensitivity(args):
    """Measure how much a one-tick price difference moves this engine's trades.

    Answers whether a substitute price series (a mini standing in for its micro)
    can carry stage-1 parity at all."""
    from .. import data as dm
    from .sensitivity import survival, verdict
    path, sym = _dataset_path(args.dataset)
    cfg = fleet.engine_config(args.engine)
    df = dm.load(path)
    if args.since:
        df = dm.slice_dates(df, since=args.since)
    if args.until:
        df = dm.slice_dates(df, until=args.until)
    print(f"tick-gevoeligheid · {args.engine} op {args.dataset} ({sym or '?'})")
    print(f"  {len(df):,} bars · tick {cfg.contract.mintick} · "
          f"{int(args.prob*100)}% van de bars krijgt +/- 1 tick op O/H/L/C")

    r = survival(df, cfg, seeds=tuple(range(1, args.seeds + 1)), prob=args.prob,
                 mode=args.mode,
                 progress=lambda i, n: print(f"  run {i+1}/{n} ...", flush=True))
    print(f"\n  basislijn: {r['baseline_trades']} trades"
          + (f" uit {r['baseline_placed']} limieten ({r['baseline_fill_pct']}% gevuld)"
             if r.get("baseline_placed") else ""))
    for run in r["runs"]:
        print(f"    seed {run['seed']}: {run['trades']} trades, {run['kept']} op dezelfde "
              f"bar en richting -> {run['survival_pct']}% overleeft"
              + (f" · fill {run['fill_pct']}%" if run.get("fill_pct") is not None else ""))
    if r.get("fill_pct_range"):
        lo, hi = r["fill_pct_range"]
        pl = r.get("placed_range")
        print(f"\n  fill-ratio {lo}%–{hi}% door tick-ruis (basislijn {r['baseline_fill_pct']}%)")
        if pl:
            print(f"  geplaatste limieten {pl[0]}–{pl[1]} (basislijn {r['baseline_placed']})")
            drift = abs((pl[0] + pl[1]) / 2 - r["baseline_placed"]) / r["baseline_placed"]
            if drift > 0.03:
                print(f"  LET OP: het aantal plaatsingen verschuift zelf {drift*100:.0f}%, dus de")
                print(f"  fill-ratio-band meet deels het instrument. Lees hem niet als een "
                      f"symmetrische ruisband.")
    if r.get("trade_count_range"):
        lo, hi = r["trade_count_range"]
        print(f"\n  aantal trades door tick-ruis: {lo}-{hi} "
              f"(spreiding {r['trade_count_spread_pct']}% van de basislijn)")
        print(f"  -> ligt de trade-count-afwijking met pine binnen deze spreiding, dan is "
              f"die dataruis, geen engine-fout")
    print(f"\n  gemiddeld {r['mean_survival_pct']}% overleeft (laagste {r['min_survival_pct']}%)")
    print(f"  {verdict(r)}")
    art = _write_artifact(args.engine, "tick-gevoeligheid", r)
    print(f"  artefact {art}")
    print("STAGE_JSON " + json.dumps({"stage": "sensitivity", "report": r}, default=str),
          flush=True)


def cmd_report(args):
    """Cross-engine view of the latest stage-1 result, read back from artifacts.

    `plan` says WHICH gates are open; this says HOW far off each engine is, on
    one screen, without re-running anything. Reading the stored artifacts rather
    than re-simulating is the point: ground rule 11 says every stage leaves one,
    so the evidence should be answerable after the fact."""
    import glob
    from collections import Counter

    root = lab_root() / "artifacts"
    files = sorted(glob.glob(str(root / "*_trap1_pariteit_*.json")))
    latest = {}
    for f in files:
        eng = os.path.basename(f).split("_trap1_pariteit_")[0]
        latest[eng] = f                      # sorted by name -> newest date last
    if not latest:
        print(f"\n  geen trap-1 artefacten in {root}")
        return

    print(f"\n  trap 1 · laatste uitslag per engine ({len(latest)} van "
          f"{len(fleet.names())} engines gedraaid)\n")
    hdr = (f"    {'engine':<22}{'trades':>11}{'PF':>12}{'gepaard':>8}"
           f"{'a-g':>6}{'poort':>13}")
    print(hdr)
    rows = []
    for eng, f in sorted(latest.items()):
        d = json.loads(open(f).read())
        c = d.get("comparison") or {}
        sim, pine = c.get("sim") or {}, c.get("pine") or {}
        td = d.get("trade_diff") or {}
        m = td.get("matched")
        n = td.get("sim_trades") or sim.get("trades") or 0
        pair = f"{100*m/n:.0f}%" if m is not None and n else "—"
        st = d.get("status") or ("passed" if d.get("pass") else "failed")
        st_lbl = {"passed": "GEHAALD", "data_parity": "= data-par.",
                  "inconclusive": "? inconcl.", "failed": "x gezakt"}.get(st, st)
        print(f"    {eng.replace('EL_',''):<22}"
              f"{str(sim.get('trades', '?')) + '/' + str(pine.get('trades', '?')):>11}"
              f"{str(sim.get('profit_factor', '?')) + '/' + str(pine.get('profit_factor', '?')):>12}"
              f"{pair:>8}{('ja' if d.get('as_tested') else 'nee'):>6}{st_lbl:>13}")
        rows.append((eng, d, c, td))
    print("\n    kolommen tonen simulator/pine\n")

    for eng, d, c, td in rows:
        print(f"  {eng.replace('EL_','')}")
        w = d.get("window") or {}
        cov = w.get("coverage") or {}
        src = d.get("price_series_borrowed_from")
        print(f"    dataset {d.get('dataset')}"
              + (f" (prijsreeks geleend van {src})" if src else "")
              + f" · {w.get('bars', '?'):,} bars"
              + (f" · dekking {100-(cov.get('missing_frac') or 0)*100:.1f}%" if cov else ""))
        if d.get("as_tested_changes"):
            print(f"    als-getest overgenomen: "
                  + ", ".join(f"{k} {v[0]!r}->{v[1]!r}"
                              for k, v in sorted(d["as_tested_changes"].items())))
        for chk in c.get("checks") or []:
            mark = "ok " if chk["ok"] else "XX "
            print(f"      {mark}{chk['name']:<18}{str(chk['sim']):>12} vs "
                  f"{str(chk['pine']):>12}   {chk['detail']}")
        oc = d.get("order_counts") or {}
        if oc.get("placed"):
            print(f"      orders: {oc['placed']} geplaatst -> {oc['filled']} gevuld "
                  f"({100*oc['filled']/oc['placed']:.0f}%) · {oc['expired']} verlopen · "
                  f"{oc.get('cancelled_flat', 0)} flat · {oc.get('cancelled_halt', 0)} halte")
        po = d.get("pine_only_split") or {}
        if po.get("pine_only"):
            print(f"      pine-only: {po['we_placed_but_never_filled']} limiet-niet-gevuld · "
                  f"{po.get('we_were_in_a_position', 0)} wij in positie · "
                  f"{po['we_never_placed']} geen order")
        if td:
            print(f"      gepaard {td.get('matched')}/{td.get('sim_trades')} · "
                  f"alleen-sim {td.get('sim_only')} · alleen-pine {td.get('pine_only')} · "
                  f"materieel anders {td.get('matched_with_a_different_result')}")
            for side in ("sim_exit_reasons", "pine_exit_reasons"):
                mix = Counter()
                for k, v in (td.get(side) or {}).items():
                    mix[k.split("|")[0].strip() if "|" in k else k] += v
                tot = sum(mix.values()) or 1
                label = "simulator" if side.startswith("sim") else "pine     "
                print(f"      exits {label}: "
                      + "  ".join(f"{k} {100*v/tot:.0f}%" for k, v in mix.most_common(5)))
        print()



def cmd_stage2(args):
    """Stage 2 — structural edge, from scratch.

    Does the RAW signal mechanic (FVG + CVD + fixed stop + R-target + expiry) have
    a positive intrinsic edge AFTER costs, on 1 contract, with NO PA sizing and NO
    day caps? This is the question stage 1 does not answer: stage 1 proves we
    reproduce Pine; stage 2 asks whether the thing we reproduce actually makes
    money on its own terms before any account mechanics dress it up.

    Ground rule 1: this is only meaningful once stage 1 holds. The pipeline is
    advisory (Ferry 20-08), so an open stage-1 gate warns rather than blocks.
    """
    import dataclasses
    from collections import defaultdict

    from .. import data as dm, indicators as im
    from ..engine import Engine
    from ..metrics import kpis

    path, sym = _dataset_path(args.dataset)
    base = fleet.engine_config(args.engine)
    own, twin = fleet.acceptable_symbols(args.engine)

    # advisory stage-1 check
    from . import state as _state
    view = {v["key"]: v for v in _state.engine_view(args.engine)}
    p1 = (view.get("parity") or {}).get("status", "todo")
    print(f"trap 2 · structurele edge · {args.engine} op {args.dataset}")
    if p1 not in ("passed", "data_parity"):
        print(f"  LET OP: trap 1 staat op '{p1}' voor deze engine — grondregel 1 zegt dat een")
        print(f"  edge-meting pas geldig is ná pariteit. Draai eerst stage1. (advies, niet blokkerend)")
    else:
        print(f"  trap 1: {p1} — edge-meting is geldig (grondregel 1).")

    # 1 contract, no account overlay, no day caps: the intrinsic mechanic only.
    cfg = dataclasses.replace(base, contract_size=1.0, day_exit_mode="Off")
    df = dm.load(path)
    if args.since:
        df = dm.slice_dates(df, since=args.since)
    if args.until:
        df = dm.slice_dates(df, until=args.until)
    print(f"  {len(df):,} bars {df['et'].iloc[0]} -> {df['et'].iloc[-1]} · 1 contract · "
          f"geen PA-sizing, geen dagcaps · kosten AAN")

    res = Engine(cfg, df, im.compute(df, cfg), research_mode=True).run()
    k = kpis(res)
    if not k.get("trades"):
        print("  GEEN trades — geen edge te meten."); 
        _write_and_record_stage2(args.engine, args.dataset, k, {}, "failed", "geen trades")
        return

    # per calendar year: an edge that lives in one year is not structural
    by_year = defaultdict(list)
    for t in res.trades:
        if getattr(t, "exit_time", None) is not None:
            by_year[t.exit_time.year].append(float(t.net))
    years = {}
    for y, nets in sorted(by_year.items()):
        wins = [x for x in nets if x > 0]; gl = -sum(x for x in nets if x <= 0)
        years[y] = {"trades": len(nets), "net": round(sum(nets), 2),
                    "pf": round(sum(wins) / gl, 2) if gl > 0 else float("inf"),
                    "expectancy": round(sum(nets) / len(nets), 2)}

    print(f"\n  volledige periode: {k['trades']} trades · net ${k['net_profit']:,.0f} · "
          f"PF {k['profit_factor']} · WR {k['win_rate_pct']}% · "
          f"verwachting ${k['expectancy']}/trade (na ${k['total_commission']:,.0f} commissie)")
    print(f"    long/short {k['longs']}/{k['shorts']} · max drawdown ${k['max_drawdown']:,.0f}")
    print(f"\n  per kalenderjaar (edge in één jaar is geen structurele edge):")
    for y, r in years.items():
        flag = "" if r["expectancy"] > 0 else "   <- negatief"
        print(f"    {y}: {r['trades']:>4} trades · net ${r['net']:>9,.0f} · PF {r['pf']:<5} · "
              f"E ${r['expectancy']:>7}/trade{flag}")

    pos_years = sum(1 for r in years.values() if r["expectancy"] > 0)
    edge = k["expectancy"] > 0 and k["profit_factor"] > 1.0
    robust = pos_years >= max(1, round(0.6 * len(years)))
    status = "passed" if (edge and robust) else ("inconclusive" if edge else "failed")
    if edge and robust:
        verdict = (f"EDGE AANWEZIG: positieve verwachting na kosten, en positief in "
                   f"{pos_years}/{len(years)} jaren")
    elif edge:
        verdict = (f"ZWAK: wél positieve verwachting over de hele periode, maar slechts "
                   f"{pos_years}/{len(years)} jaren positief — leunt op een deel van de reeks")
    else:
        verdict = (f"GEEN EDGE: verwachting ${k['expectancy']}/trade, PF {k['profit_factor']} "
                   f"— de kale mechaniek verdient na kosten niet")
    print(f"\n  POORT: {status.upper()} — {verdict}")
    _write_and_record_stage2(args.engine, args.dataset, k, years, status, verdict)


def _write_and_record_stage2(engine, dataset, k, years, status, verdict):
    from . import state as _state
    art = _write_artifact(engine, "trap2_structurele-edge",
                          {"dataset": dataset, "kpis": k,
                           "by_year": {str(y): r for y, r in years.items()},
                           "status": status, "verdict": verdict})
    _state.record(engine, "structural_edge", status, summary=verdict, artifact=art)
    print(f"  artefact {art}")
    print("STAGE_JSON " + json.dumps({"stage": 2, "kpis": k, "by_year": years,
                                      "status": status}, default=str), flush=True)


def cmd_scorecard(args):
    """Rich performance scorecard for one engine on one dataset — the Analysis view.

    Not a pipeline gate: it does not judge pass/fail, it MEASURES. Runs the engine
    once and reports the full performance picture (equity curve, streaks, best/worst,
    per-side split, MFE/MAE, hold time, exit-reason edge). Default posture is
    DEPLOYMENT (research_mode=False — the engine as it runs live, account overlay on);
    --raw strips to the 1-contract intrinsic mechanic (no PA sizing, no day caps),
    the same view stage 2 uses."""
    import dataclasses
    from .. import data as dm, indicators as im
    from ..engine import Engine
    from . import scorecard as sc

    path, sym = _dataset_path(args.dataset)
    base = fleet.engine_config(args.engine)
    posture = "raw (1 contract, geen overlay)" if args.raw else "deployment (overlay aan)"
    print(f"scorecard · {args.engine} op {args.dataset} · {posture}")

    cfg = (dataclasses.replace(base, contract_size=1.0, day_exit_mode="Off")
           if args.raw else base)
    df = dm.load(path)
    if args.since:
        df = dm.slice_dates(df, since=args.since)
    if args.until:
        df = dm.slice_dates(df, until=args.until)
    if df.empty:
        raise SystemExit(f"dataset {args.dataset!r} bevat geen bars in het gevraagde venster.")

    def _card(frame):
        res = Engine(cfg, frame, im.compute(frame, cfg), research_mode=not args.raw).run()
        c = sc.scorecard(res)
        c["engine"], c["dataset"] = args.engine, args.dataset
        c["posture"] = "raw" if args.raw else "deploy"
        c["window_bars"] = len(frame)
        return c

    def _summary(tag, c):
        k = c["kpis"]
        if not k.get("trades"):
            print(f"  [{tag}] GEEN trades"); return
        print(f"  [{tag}] {k['trades']} trades · net ${k['net_profit']:,.0f} · PF {k['profit_factor']} · "
              f"WR {k['win_rate_pct']}% · E ${k['expectancy']}/trade · maxDD ${k['max_drawdown']:,.0f}")

    # ---- IS / OOS split (overfit view) ----
    if args.holdout_days:
        is_df, oos_df, cutoff = dm.holdout_split(df, args.holdout_days)
        if is_df.empty or oos_df.empty:
            raise SystemExit(f"holdout van {args.holdout_days} dagen laat geen in-sample "
                             f"óf out-of-sample bars over op dit venster.")
        print(f"  IS/OOS-split op {cutoff} · in-sample {len(is_df):,} bars · "
              f"out-of-sample {len(oos_df):,} bars (laatste {args.holdout_days} dagen)")
        is_c, oos_c = _card(is_df), _card(oos_df)
        _summary("IS ", is_c); _summary("OOS", oos_c)
        is_pf = float(is_c["kpis"].get("profit_factor") or 0)
        oos_pf = float(oos_c["kpis"].get("profit_factor") or 0)
        retain = round(oos_pf / is_pf, 2) if is_pf > 0 else 0.0
        # The overfit gate, same threshold verify.py uses: the edge must survive
        # unseen data, not just look good where it was measured.
        holds = (oos_c["kpis"].get("trades", 0) >= 10 and oos_pf >= 1.0 and retain >= 0.6)
        verdict = (f"edge houdt stand out-of-sample: OOS PF {oos_pf} is {int(retain*100)}% "
                   f"van IS PF {is_pf}" if holds else
                   f"edge verzwakt out-of-sample: OOS PF {oos_pf} vs IS PF {is_pf} "
                   f"(retain {retain}, drempel 0.60) — overfit-risico")
        print(f"\n  OVERFIT-CHECK: {'✓' if holds else '✗'} {verdict}")
        payload = {"is": is_c, "oos": oos_c, "cutoff": str(cutoff),
                   "holdout_days": args.holdout_days, "retain": retain,
                   "holds": holds, "verdict": verdict,
                   "engine": args.engine, "dataset": args.dataset,
                   "posture": is_c["posture"]}
        art = _write_artifact(args.engine, "scorecard_isoos", payload)
        print(f"  artefact {art}")
        print("ISOOS_JSON " + json.dumps(payload, default=str), flush=True)
        return

    print(f"  {len(df):,} bars {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")
    card = _card(df)
    card["window"] = {"since": args.since, "until": args.until, "bars": len(df)}
    _summary("", card)
    if card.get("trades"):
        bd = card["by_direction"]
        print(f"    long {bd['long']['trades']} (net ${bd['long']['net']:,.0f}, PF {bd['long']['pf']}) · "
              f"short {bd['short']['trades']} (net ${bd['short']['net']:,.0f}, PF {bd['short']['pf']})")
        ex = card["excursion"]
        print(f"    MFE ø {ex['avg_mfe_ticks']}t · MAE ø {ex['avg_mae_ticks']}t · "
              f"hold ø {card['hold_time_bars']['avg']} bars · "
              f"streak +{card['streaks']['longest_win']}/-{card['streaks']['longest_loss']}")
    art = _write_artifact(args.engine, "scorecard", card)
    print(f"  artefact {art}")
    print("SCORECARD_JSON " + json.dumps(card, default=str), flush=True)


def _fleet_dataset_for(market):
    """Best dataset for a market: the real micro if present, else its twin,
    preferring the one whose window reaches furthest."""
    from ..lab.lab_viewer import _datasets
    from .cli import _dt as _pdt   # noqa
    from . import fleet as _fleet
    twin = _fleet.TWIN.get(market)
    cands = []
    for d in _datasets():
        sym = (d.get("symbol") or "").upper()
        if sym == market:
            cands.append((0, d))
        elif sym == twin:
            cands.append((1, d))
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], -(t[1].get("rows") or 0)))
    return cands[0][1]["name"]


def _fleet_export_for(engine):
    """Export whose filename encodes this engine (BRAND_MKT_PROFILE_<SYM>1m_date)."""
    import re
    from ..lab.lab_viewer import _exports
    for nm in _exports():
        stem = re.sub(r"_[A-Z0-9]+1m_.*$", "", nm)   # drop _MES1m_2026-08-23.xlsx
        if "EL_" + stem == engine:
            return nm
    return None


def cmd_fleet(args):
    """Run every engine through the pipeline up to --through, in one command.

    Resolves each engine's dataset (real micro, else twin) and its validation
    export automatically, applies --as-tested (a no-op when the export already
    matches), and prints the board at the end. Engines without an export cannot
    clear the hard parity gate — that is stated, not hidden."""
    import subprocess

    through = args.through
    engines = fleet.names()
    print(f"\n  vloot-run · trap 0 t/m {through} · {len(engines)} engines\n")
    py = sys.executable
    base = [py, "-m", "backtest.pipeline.cli"]
    # Common window: the micros start 2023-08-24. Aligning every engine (incl.
    # the 14-year GC twin used for the gold engines) to the same span makes the
    # comparison fair AND keeps the multi-run stages off the 4.29M-bar GC file
    # that otherwise OOMs on a 2-core box.
    window = ["--since", args.since] if args.since else ["--since", "2023-08-24"]

    def _run(stage_args, tag):
        try:
            r = subprocess.run(base + stage_args, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        line = [ln for ln in r.stdout.splitlines() if "POORT:" in ln]
        if r.returncode != 0 and not line:
            err = (r.stderr.strip().splitlines() or ["fout"])[-1]
            return f"FOUT: {err[:70]}"
        return (line[-1].split("POORT:")[-1].strip() if line else "klaar")

    for eng in engines:
        short = eng.replace("EL_", "")
        ds = _fleet_dataset_for(fleet.market(eng))
        exp = _fleet_export_for(eng)
        print(f"  {short}")
        if not ds:
            print(f"    — geen dataset voor markt {fleet.market(eng)} · overgeslagen")
            continue
        r0 = _run(["stage0", "--dataset", ds, "--engine", eng], "0")
        print(f"    trap 0  {r0}   [{ds}]")
        if through >= 1:
            if exp:
                r1 = _run(["stage1", "--dataset", ds, "--engine", eng,
                           "--export", exp, "--as-tested"], "1")
                print(f"    trap 1  {r1}   [{exp}]")
            else:
                print(f"    trap 1  GEEN EXPORT — pariteit niet toetsbaar (harde poort blijft open)")
        if through >= 2:
            r2 = _run(["stage2", "--dataset", ds, "--engine", eng] + window, "2")
            print(f"    trap 2  {r2}")
        for n in range(3, min(through, 9) + 1):
            rn = _run([f"stage{n}", "--dataset", ds, "--engine", eng] + window, str(n))
            print(f"    trap {n}  {rn}")
        print()

    print("  ── eindstand ──")
    subprocess.run(base + ["plan"])



_HIGHER_KEY = {3: "regimes", 4: "plateau", 5: "sizing", 6: "daily_mgmt",
               7: "pa_lifecycle", 8: "time_for_money", 9: "prod_vs_harvest"}


def _run_higher(n, args):
    """Stages 3-9 share the same shape: load data, run the frozen engine, record."""
    from .. import data as dm
    from . import higher, state as _state
    from .stages import BY_N
    path, sym = _dataset_path(args.dataset)
    cfg = fleet.engine_config(args.engine)
    stage = BY_N[n]
    print(f"trap {n} · {stage.title} · {args.engine} op {args.dataset}")
    p1 = {v["key"]: v for v in _state.engine_view(args.engine)}.get("parity", {}).get("status", "todo")
    if p1 not in ("passed", "data_parity"):
        print(f"  LET OP: trap 1 staat op '{p1}' — grondregel 1: geldig pas ná pariteit "
              f"(advies, niet blokkerend)")
    df = dm.load(path)
    if args.since:
        df = dm.slice_dates(df, since=args.since)
    if args.until:
        df = dm.slice_dates(df, until=args.until)
    fn = getattr(higher, f"stage{n}")
    rep = fn(cfg, df, args.engine)
    print(f"  {rep['verdict']}")
    art = _write_artifact(args.engine, f"trap{n}_{stage.key}", {"dataset": args.dataset, **rep})
    _state.record(args.engine, _HIGHER_KEY[n], rep["status"], summary=rep["verdict"], artifact=art)
    print(f"\n  POORT: {rep['status'].upper()} — {rep['verdict']}")
    print(f"  artefact {art}")
    print("STAGE_JSON " + json.dumps({"stage": n, **rep}, default=str), flush=True)


def cmd_stage3(args): _run_higher(3, args)
def cmd_stage4(args): _run_higher(4, args)
def cmd_stage5(args): _run_higher(5, args)
def cmd_stage6(args): _run_higher(6, args)
def cmd_stage7(args): _run_higher(7, args)
def cmd_stage8(args): _run_higher(8, args)
def cmd_stage9(args): _run_higher(9, args)


def cmd_plan(_args):
    engines = fleet.names()
    rows = state.overview(engines)
    print(f"\n  MEX research pipeline v7 — {len(STAGES)} trappen, {len(engines)} engines\n")
    print(f"    {'engine':<26}{'markt':>6}{'gehaald t/m':>13}   trap-status 0..11")
    for r, s in zip(rows, (fleet.summary())):
        marks = "".join({"passed": "+", "data_parity": "=", "failed": "x",
                         "running": "~", "inconclusive": "?"}.get(v["status"], ".")
                        for v in r["stages"])
        reached = f"trap {r['reached']}" if r["reached"] >= 0 else "—"
        print(f"    {r['engine'].replace('EL_',''):<26}{s['market']:>6}{reached:>13}   {marks}")
    print("\n    + gehaald · = data-pariteit · x gefaald · ~ loopt · ? inconclusief · . nog niet gedraaid")
    hard = [r for r in rows if r["hard_open"]]
    if hard:
        print(f"\n  {len(hard)}/{len(rows)} engines hebben een OPEN HARDE POORT — parameteroptimalisatie")
        print("  daaronder is ongeldig (grondregel 1).")
    for n, why in sorted(fleet.PINE_DEFECTS.items()):
        print(f"\n  ! BRONDEFECT {n.replace('EL_','')} — {why}")


def cmd_stage0(args):
    from .. import data as dm
    from .audit import audit
    path, sym = _dataset_path(args.dataset)
    print(f"trap 0 · data-audit · {args.dataset} ({sym or '?'})")
    df = dm.load(path)
    rep = audit(df, sym)
    print(f"  {rep['bars']:,} bars · {rep['first'][:10]} -> {rep['last'][:10]} · {rep['years']}j · "
          f"{rep['sessions']} sessies · tz {rep['timezone']}")
    for k in ("ohlc_violations", "gaps_over_6h", "intrasession_gap_minutes",
              "Delta_nonzero_pct", "median_bar_range_ticks", "roll_like_jumps"):
        if k in rep:
            print(f"  {k:<26} {rep[k]}")
    for f in rep["findings"]:
        print(f"  [{f['severity']}] {f['message']}")
    art = _write_artifact(args.engine or args.dataset, "trap0_data-audit", rep)
    ok = not any(f["severity"] == "high" for f in rep["findings"])
    if args.engine:
        state.record(args.engine, "data_audit", "passed" if ok else "failed",
                     summary=f"{rep['bars']:,} bars, {rep['years']}j, "
                             f"{len(rep['findings'])} bevinding(en)", artifact=art)
    print(f"\n  POORT: {'GEHAALD' if ok else 'NIET GEHAALD'} — artefact {art}")
    print("STAGE_JSON " + json.dumps({"stage": 0, "report": rep, "pass": ok}, default=str), flush=True)


def _data_parity_evidence(cmp_, pa, td, po, clean) -> dict:
    """Is a trade-count miss provably the DATA, not the engine?

    Every condition here is a wall against a false green. If any fails, the gate
    is a plain failure — data-parity is not a softer synonym for "close enough".
    """
    reasons, blocked = [], None
    checks = {c["name"]: c for c in cmp_.get("checks", [])}

    def fail(msg):
        nonlocal blocked
        blocked = msg
        return {"eligible": False, "blocked": msg, "reasons": []}

    if not clean:
        return fail("de Properties/omgevings-audit is niet schoon")
    # exactly one KPI check may fail, and it must be trade count
    failing = [n for n, c in checks.items() if not c["ok"]]
    if failing != ["trade count"]:
        return fail(f"meer dan alleen trade count zakt ({failing or 'niets'})")
    # we must take FEWER trades (missing gaps), not more
    tc = checks["trade count"]
    if not (int(tc["sim"]) < int(tc["pine"])):
        return fail("we doen niet MINDER trades dan pine — een tekort door "
                    "ontbrekende data zou minder geven")
    # of the entries that DID align, essentially all must agree materially
    matched = td.get("matched") or 0
    agree = (td.get("matched_exactly", 0) + td.get("matched_within_cost_noise", 0))
    if matched < 20 or agree < 0.9 * matched:
        return fail(f"te weinig gepaarde trades zijn het eens "
                    f"({agree}/{matched}) — de engine is niet bewezen gelijk")
    # the missing signals must be DATA (no gap in our bars), never a filter
    # disagreement (band / streak / gate). explain_missing populates this.
    em = po.get("_explain") or {}
    engine_side = {k: v for k, v in (em.get("reasons") or {}).items()
                   if k != "geen FVG van die richting in het venster"}
    if engine_side:
        return fail(f"gemiste signalen wijzen deels op de engine, niet de data: "
                    f"{engine_side}")
    reasons.append(f"{agree} van {matched} gepaarde trades identiek of binnen kosten-ruis")
    reasons.append(f"trade count {tc['sim']} < {tc['pine']} (wij missen gaps, doen er niet bij)")
    if em.get("checked"):
        near = em.get("near_roll", 0)
        reasons.append(f"alle {em['checked']} ontbrekende signalen zijn 'geen gap in onze "
                       f"bars'; {near} binnen 10 dagen van een kwartaal-roll")
    reasons.append("FVG-detectie bewezen identiek aan de Pine-formule (zie tests)")
    return {"eligible": True, "blocked": None, "reasons": reasons}


def _prepare_export_run(args, *, header):
    """Shared front-matter for the two export-comparison gates (trap 1 & trap 10).

    Resolve the dataset + engine config, verify the price series is an acceptable
    symbol (own or twin, never silently), read and audit the export against the
    config (ground rule 10), optionally adopt the export's inputs (--as-tested)
    and its costs, and trim the dataset to the window TradingView actually tested.
    Both gates rest on exactly this being done the same way — the re-audit after
    cost/input adoption in particular is a correctness requirement, not a nicety,
    so it lives in one place. Returns everything either gate needs to run and
    judge the engine against the export."""
    from .. import data as dm
    from .parity import audit_properties, read_export
    path, sym = _dataset_path(args.dataset)
    cfg = fleet.engine_config(args.engine)
    for line in header:
        print(line)

    # The dataset supplies PRICES; the contract spec comes from the engine config.
    # A mini's history is therefore a valid stand-in for its micro (same tick
    # size, same trade sequence) — but never silently: running MGC prices under a
    # MES engine would be nonsense, and a substitution that is not recorded is
    # exactly what ground rule 4 forbids.
    own, twin = fleet.acceptable_symbols(args.engine)
    ds_sym = (sym or "").upper()
    substituted = None
    if not ds_sym:
        print(f"  LET OP: dataset {args.dataset!r} heeft geen symbool in zijn manifest — "
              f"kan niet controleren of dit {own}-data is.")
    elif ds_sym == own:
        pass
    elif ds_sym == twin:
        substituted = ds_sym
        print(f"  PRIJSREEKS GELEEND: {ds_sym}-data onder de {own}-contractspec.")
        if fleet.GAP_BASED:
            print(f"    WAARSCHUWING: deze vloot handelt fair-value gaps, en een gap is een "
                  f"liquiditeitsartefact.")
            print(f"    {ds_sym} en {own} zijn aparte orderboeken met andere diepte, dus ze "
                  f"gapen op andere minuten.")
            print(f"    Gemeten op MATADOR: van de 35 gemiste signalen had er 0 een FVG in "
                  f"ons venster, terwijl")
            print(f"    onze detectie bit-voor-bit gelijk is aan de Pine-bron. Trap 1 kan "
                  f"hiermee dus GEEN pariteit")
            print(f"    aantonen — daarvoor zijn de echte {own}-bars nodig. De uitslag "
                  f"hieronder blijft bruikbaar als")
            print(f"    diagnose, niet als bewijs.")
    else:
        raise SystemExit(
            f"dataset {args.dataset!r} is {ds_sym}-data, maar {args.engine} handelt {own}"
            + (f" (twin {twin} zou ook mogen)" if twin else "")
            + ". Trap 1 op de verkeerde markt meet niets.")

    exp = read_export(_resolve_export(args.export))
    pa = audit_properties(exp, cfg)
    print(f"\n  Properties-audit (grondregel 10): dekking {pa['coverage_pct']}% "
          f"({pa['checked']} velden), {pa['mismatches']} input-afwijking(en), "
          f"{pa['environment_mismatches']} omgevings-afwijking(en)")
    print(f"    symbool {pa['symbol']} · {pa['timeframe']} · commissie {pa['commission']} · "
          f"slippage {pa['slippage']} · firm {pa['firm_program']}")
    print(f"    getest venster {pa['window_start']} -> {pa['window_end']}")
    for r in pa["environment"]:
        if not r["ok"]:
            print(f"    OMGEVING  {r['label']}: export={r['export']} vs config={r['config']}"
                  + (f"  ({r['note']})" if r["note"] else ""))
    for r in pa["rows"]:
        if not r["ok"]:
            print(f"    AFWIJKING {r['label']}: export={r['export']} vs config={r['config']}")
    if pa["missing"]:
        print(f"    NIET TE CONTROLEREN ({len(pa['missing'])} veld(en) ontbreken in de sheet): "
              f"{', '.join(pa['missing'][:6])}{' ...' if len(pa['missing']) > 6 else ''}")
    tested_changes = {}
    if pa["mismatches"] and args.as_tested:
        from .parity import as_tested
        cfg, tested_changes = as_tested(cfg, pa)
        print("    ALS-GETEST: de export-waarden zijn overgenomen zodat de ENGINE meetbaar")
        print("    wordt. Een geslaagde poort betekent dan pariteit met DEZE EXPORT, niet")
        print("    met de vrijgegeven .pine — welke van de twee de bedoeling is, blijft open.")
        for attr, (was, now) in sorted(tested_changes.items()):
            print(f"      {attr}: {was!r} -> {now!r}")
        pa = audit_properties(exp, cfg)
        print(f"    na overname: {pa['mismatches']} input-afwijking(en)")
    elif pa["mismatches"] or pa["environment_mismatches"]:
        print("    De export test een ANDERE configuratie dan deze engine — de vergelijking")
        print("    hieronder is daarmee niet gezaghebbend. Draai met --as-tested om de")
        print("    engine tóch te meten tegen wat er werkelijk getest is.")

    # Reproduce the export's COSTS, not our registry's. Ground rule 10 says the
    # export is the truth about what was tested; running the same trades at a
    # different commission builds a known difference into the comparison and
    # leaves it there. On MATADOR that was $1.68 per trade (6 contracts x 2 sides
    # x $0.14), which is small but shows up on every single matched trade.
    import dataclasses as _dc
    exp_com = _f_or_none(pa["commission"])
    exp_slip = _f_or_none(str(pa["slippage"] or "").split()[0] if pa["slippage"] else None)
    costs = {}
    if exp_com is not None and abs(exp_com - cfg.contract.commission_per_contract) > 1e-9:
        costs["commission_per_contract"] = exp_com
    if exp_slip is not None and abs(exp_slip - cfg.contract.slippage_ticks) > 1e-9:
        costs["slippage_ticks"] = exp_slip
    if costs:
        was = {k: getattr(cfg.contract, k) for k in costs}
        cfg = _dc.replace(cfg, contract=_dc.replace(cfg.contract, **costs))
        print(f"  KOSTEN UIT DE EXPORT overgenomen: {was} -> {costs} "
              f"(grondregel 10 — we reproduceren die run, niet onze registry)")
        # Re-audit against the adopted costs. Without this the gate keeps failing
        # on the very difference we just removed.
        pa = audit_properties(exp, cfg)

    df = dm.load(path)
    # Default the simulated window to what TradingView actually tested. Comparing
    # a 19-year simulation against a 1-year export produces a trade-count gap that
    # says nothing about parity, so the window is aligned unless explicitly set.
    since, until = args.since, args.until
    if not since and pa["window_start"]:
        since = pa["window_start"].strftime("%Y-%m-%d")
        print(f"\n  venster overgenomen uit de export: --since {since}")
    if not until and pa["window_end"]:
        until = pa["window_end"].strftime("%Y-%m-%d")
        print(f"  venster overgenomen uit de export: --until {until}")
    if since:
        df = dm.slice_dates(df, since=since)
    if until:
        df = dm.slice_dates(df, until=until)
    if df.empty:
        raise SystemExit(
            f"de dataset {args.dataset!r} bevat geen bars in het exportvenster "
            f"{since} -> {until}. Trap 1 is niet te draaien zonder overlappende data.")

    # How much of the export's window these bars actually cover. A short tail is
    # not fatal, but a comparison run on 80% of the window is not evidence about
    # engine semantics, so the number goes in the artifact either way.
    ov = window_overlap(df["et"].iloc[0].tz_localize(None) if df["et"].iloc[0].tzinfo
                        else df["et"].iloc[0],
                        df["et"].iloc[-1].tz_localize(None) if df["et"].iloc[-1].tzinfo
                        else df["et"].iloc[-1],
                        pa["window_start"], pa["window_end"])
    if ov["known"] and ov["missing_days"]:
        note = ("onder de tolerantie op trade count" if ov["verdict"] == "bijna volledig"
                else "BOVEN de tolerantie — een afwijkend aantal trades zegt hier weinig "
                     "over de engine")
        print(f"  dekking: {100 - ov['missing_frac']*100:.1f}% van het exportvenster, "
              f"{ov['missing_days']} dag(en) ontbreken ({note})")
    return {"cfg": cfg, "df": df, "exp": exp, "pa": pa, "since": since,
            "until": until, "ov": ov, "substituted": substituted, "own": own,
            "ds_sym": ds_sym, "tested_changes": tested_changes, "costs": costs}


def cmd_stage1(args):
    from .. import indicators as im
    from ..engine import Engine
    from ..metrics import kpis
    from .parity import compare
    prep = _prepare_export_run(args, header=[
        f"trap 1 · Pine-pariteit · {args.engine} op {args.dataset}",
        "  POORT: bijna gelijk aantal trades + materieel vergelijkbare WR/PF. HARDE POORT."])
    cfg, df, exp, pa = prep["cfg"], prep["df"], prep["exp"], prep["pa"]
    since, until, ov = prep["since"], prep["until"], prep["ov"]
    substituted, tested_changes, costs = prep["substituted"], prep["tested_changes"], prep["costs"]
    ds_sym = prep["ds_sym"]

    print(f"\n  simulator op {len(df):,} bars {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")
    # research_mode=False on purpose. It disables the whole account overlay
    # (engine.py: `if not self.research and cfg.phase_on`), so with it ON the
    # simulator has no PA daily loss limit, no day-trail and no day-cap — while
    # the Pine script runs all three. That turned every DLL exit into a full
    # stop-out and was worth ~11 percentage points of the exit mix.
    ind = im.compute(df, cfg)
    res = Engine(cfg, df, ind, research_mode=False).run()
    k = kpis(res)
    cmp_ = compare(k, exp)
    print(f"\n    {'check':<18}{'simulator':>14}{'pine':>14}   ")
    for c in cmp_["checks"]:
        print(f"    {c['name']:<18}{str(c['sim']):>14}{str(c['pine']):>14}   "
              f"{'ok' if c['ok'] else 'AFWIJKING'} — {c['detail']}")
    # In-band gap rate: the statistic to compare directly once the real micro
    # bars arrive. If the micro gaps materially more often than its mini, that
    # settles the microstructure explanation with a number.
    import numpy as _np
    _pass = _np.asarray(ind["fvg_pass"])
    gap_rate = round(100 * float(_pass.sum()) / max(len(_pass), 1), 3)
    print(f"\n  FVG's binnen de band {cfg.gap_min_ticks:.0f}-{cfg.gap_max_ticks:.0f} ticks: "
          f"{int(_pass.sum()):,} op {len(_pass):,} bars ({gap_rate}%)")
    if substituted:
        print(f"    vergelijk dit getal met de echte {fleet.market(args.engine)}-data zodra "
              f"die er is — dat toetst de microstructuur-verklaring")

    oc = res.order_counts or {}
    if oc.get("placed"):
        print(f"\n  orderlevenscyclus: {oc['placed']} limieten geplaatst -> "
              f"{oc['filled']} gevuld ({100*oc['filled']/oc['placed']:.1f}%), "
              f"{oc['expired']} verlopen, {oc['cancelled_flat']} geannuleerd door het "
              f"flat-venster, {oc['cancelled_halt']} door een daghalte")
        print(f"    (pine deed {exp.n_trades} trades; als onze fill-ratio hoog is en we "
              f"toch minder trades doen,\n     dan zit het verschil in het aantal SIGNALEN, "
              f"niet in de uitvoering)")

    from .tracediff import (classify_pine_only, diff as trace_diff,
                            explain_missing, render as trace_render)
    td = trace_diff(res.trades, exp)
    po = classify_pine_only(res.placements, exp, res.trades, cfg.expiry_bars)
    ex = None
    if po["pine_only"]:
        print(f"\n  trades die pine deed en wij niet ({po['pine_only']}):")
        print(f"    {po['we_placed_but_never_filled']} keer lag er wél een limiet die niet "
              f"vulde ({po['placed_share_pct']}%)")
        print(f"    {po['we_were_in_a_position']} keer zaten we zelf in een positie "
              f"({po['blocked_share_pct']}%) — signaal was niet beschikbaar")
        print(f"    {po['we_never_placed']} keer waren we vrij en hadden toch geen order")
        print(f"    -> {po['verdict']}")
        if po.get("first_never_placed") is not None and po["we_never_placed"]:
            ex = explain_missing(df, ind, cfg, po["_never_placed_all"], cfg.expiry_bars)
            print(f"\n  waarom hadden wij daar geen order ({ex['checked']} gevallen):")
            for reason, cnt in ex["reasons"].items():
                print(f"    {cnt:>4}x  {reason}")
            if ex.get("near_roll") is not None and (ex["near_roll"] or ex["away_from_roll"]):
                tot = ex["near_roll"] + ex["away_from_roll"]
                print(f"    waarvan {ex['near_roll']}/{tot} binnen 10 dagen van een kwartaal-roll "
                      f"(Mar/Jun/Sep/Dec) — hoog = vendor/roll-verschil, niet de engine")
                print(f"    per maand: {ex['by_month']}")
    po["_explain"] = ex or {}
    if not cmp_["pass"] or args.diff:
        print("\n  trade-voor-trade (grondregel 1: onderzoek de afwijkingen, "
              "her-optimaliseer niet)")
        print(trace_render(td))

    # Aggregate agreement is necessary, not sufficient. Two engines can land on
    # the same trade count, PF and win rate while taking largely different
    # trades — on a borrowed price series that is even likely. Calling that
    # "parity" is the false green ground rule 9 exists to prevent, so a KPI pass
    # with weak trade-level overlap is recorded as INCONCLUSIVE, not passed.
    paired = td.get("matched") or 0
    n_sim = td.get("sim_trades") or 0
    pair_pct = round(100 * paired / n_sim, 1) if n_sim else 0.0
    clean = (not pa["mismatches"] and not pa["environment_mismatches"]
             and not pa["missing"])
    ok = cmp_["pass"] and clean
    weak = ok and pair_pct < MIN_PAIRED_PCT

    # DATA-PARITY (besluit Ferry 24-08): when the only failing KPI check is trade
    # count, and every difference is provably the DATA rather than the engine,
    # the hard gate is met with an explicit data-parity label instead of exact.
    # This is deliberately hard to trip — it is the false green ground rule 9
    # exists to prevent — so ALL of the following must hold:
    dp = _data_parity_evidence(cmp_, pa, td, po, clean)
    if status_is_data_parity := (not ok and dp["eligible"]):
        status = "data_parity"
    elif ok and not weak:
        status = "passed"
    elif ok and weak:
        status = "inconclusive"
    else:
        status = "failed"

    if status == "data_parity":
        print(f"\n  DATA-PARITEIT: de enige gezakte KPI-check is trade count, en het "
              f"tekort is aantoonbaar de databron:")
        for line in dp["reasons"]:
            print(f"    · {line}")
        print(f"  De engine is bewezen gelijk aan de export; het verschil zit in welke "
              f"bars een gap dragen.")
        print(f"  Harde poort GEHAALD met label data-pariteit (niet exact). Vastgelegd "
              f"in het artefact.")
    elif dp["blocked"]:
        print(f"\n  (data-pariteit niet van toepassing: {dp['blocked']})")
    if weak:
        print(f"\n  LET OP: alle KPI-checks slagen, maar slechts {pair_pct}% van de "
              f"instapmomenten paart met de export.")
        print(f"  Dezelfde totalen uit grotendeels ándere trades is geen pariteit — "
              f"gemarkeerd als INCONCLUSIEF,")
        print(f"  niet als gehaald. Op een geleende prijsreeks is dit te verwachten; "
              f"met de echte bars hoort dit boven {MIN_PAIRED_PCT}% te komen.")
    art = _write_artifact(args.engine, "trap1_pariteit",
                          {"properties_audit": pa, "comparison": cmp_,
                           "trade_diff": td,
                           "costs_from_export": costs,
                           "as_tested": bool(tested_changes),
                           "paired_pct": pair_pct, "status": status,
                           "in_band_gap_rate_pct": gap_rate,
                           "order_counts": oc,
                           "pine_only_split": {k: v for k, v in po.items()
                                               if not k.startswith("_")},
                           "as_tested_changes": {k: [v[0], v[1]]
                                                 for k, v in tested_changes.items()},
                           "dataset": args.dataset, "dataset_symbol": ds_sym,
                           "price_series_borrowed_from": substituted,
                           "window": {"since": since, "until": until, "bars": len(df),
                                      "coverage": ov}})
    state.record(args.engine, "parity", status,
                 summary=(("PARITEIT via databron — engine bewezen gelijk, tekort is de "
                           "datavendor" if status == "data_parity" else cmp_["verdict"])
                          + (f" [prijsreeks geleend van {substituted}]" if substituted else "")
                          + (" [ALS-GETEST: gemeten tegen de export-inputs, niet tegen de "
                             ".pine-bron]" if tested_changes else "")),
                 artifact=art,
                 detail={"mismatches": pa["mismatches"], "checks": cmp_["checks"],
                         "price_series_borrowed_from": substituted,
                         "paired_pct": pair_pct})
    label = {"passed": "GEHAALD", "data_parity": "GEHAALD (data-pariteit)",
             "inconclusive": "INCONCLUSIEF", "failed": "NIET GEHAALD"}[status]
    verdict_line = ("engine bewezen gelijk aan de export; het resterende trade-count-tekort "
                    "is de databron (zie de bewijsregels hierboven), niet de engine — trap 2 "
                    "is hiermee geldig" if status == "data_parity" else cmp_["verdict"])
    print(f"\n  POORT: {label} — {verdict_line}")
    print(f"  artefact {art}")
    print("STAGE_JSON " + json.dumps({"stage": 1, "properties": pa, "comparison": cmp_,
                                      "pass": ok}, default=str), flush=True)


def cmd_stage10(args):
    """Trap 10 — TradingView-validatie, de laatste harde poort vóór live.

    Draait de bevroren engine in DEPLOYMENT-houding (account-overlay aan, precies
    zoals hij live gaat) tegen de export en poort op de dimensies die trap 1 wel
    toont maar niet afdwingt: de exit-reden-verdeling en de MFE/MAE per trade —
    de account-overlay-fideliteit en het intrabar-pad die live geld kosten of
    bankieren."""
    from .. import indicators as im
    from ..engine import Engine
    from ..metrics import kpis
    from .parity import compare
    from .tracediff import classify_pine_only, diff as trace_diff, explain_missing
    from . import tvvalidate
    prep = _prepare_export_run(args, header=[
        f"trap 10 · TradingView-validatie · {args.engine} op {args.dataset}",
        "  POORT: trades, timing, exit-redenen, MFE/MAE en PF komen overeen. "
        "HARDE DEPLOYMENT-POORT."])
    cfg, df, exp, pa = prep["cfg"], prep["df"], prep["exp"], prep["pa"]
    since, until, ov = prep["since"], prep["until"], prep["ov"]
    substituted = prep["substituted"]
    tested_changes, costs = prep["tested_changes"], prep["costs"]

    print(f"\n  simulator (deployment-houding, account-overlay AAN) op {len(df):,} bars "
          f"{df['et'].iloc[0]} -> {df['et'].iloc[-1]}")
    # research_mode=False: the per-day PA rules (Auto Flat, DLL, day cap) run, and
    # for a PA production account the engine RESETS on a trailing breach instead of
    # terminating (engine.py `_account`) — exactly as the Pine strategy keeps
    # trading across the whole window. The account lifecycle lives in stages 6-8.
    ind = im.compute(df, cfg)
    res = Engine(cfg, df, ind, research_mode=False).run()
    k = kpis(res)
    cmp_ = compare(k, exp)

    # Trade-level pieces for the shared data-parity evidence (same as stage 1): a
    # trade-count residual is only forgiven when it is provably the vendor.
    td = trace_diff(res.trades, exp)
    po = classify_pine_only(res.placements, exp, res.trades, cfg.expiry_bars)
    if po.get("we_never_placed") and po.get("_never_placed_all"):
        po["_explain"] = explain_missing(df, ind, cfg, po["_never_placed_all"], cfg.expiry_bars)
    else:
        po["_explain"] = {}
    clean = (not pa["mismatches"] and not pa["environment_mismatches"] and not pa["missing"])
    dp = _data_parity_evidence(cmp_, pa, td, po, clean)

    ev = tvvalidate.evaluate(res.trades, cfg, exp, cmp_, td, dp)

    print(f"\n    {'dimensie':<16}{'status':>10}")
    for name, d in ev["dimensions"].items():
        print(f"    {name:<16}{('ok' if d['ok'] else 'AFWIJKING'):>10}   {d['detail']}")

    print("\n  exit-redenen (categorie · simulator vs pine):")
    for r in ev["exit_reasons"]["rows"]:
        flag = "" if r["gap_pp"] <= ev["exit_reasons"]["tol_pp"] else "  <- afwijking"
        print(f"    {r['category']:<11} {r['sim_n']:>4} ({r['sim_pct']:>5.1f}%) vs "
              f"{r['pine_n']:>4} ({r['pine_pct']:>5.1f}%)  d{r['gap_pp']:>4.1f}pp{flag}")

    exc = ev["excursion"]
    if exc.get("paired"):
        print(f"\n  MFE/MAE op {exc['paired']} gepaarde trades: mediane afwijking "
              f"MFE {exc['median_mfe_diff_ticks']}t · MAE {exc['median_mae_diff_ticks']}t "
              f"(limiet {exc['tol_ticks']:.0f}t); {exc['within_tol_pct']}% binnen tolerantie")
    else:
        print(f"\n  MFE/MAE: {exc.get('reason', 'geen gepaarde trades')}")

    if ev["status"] == "data_parity":
        print(f"\n  DATA-PARITEIT: exit-mix en MFE/MAE komen overeen op de gedeelde trades; "
              f"het enige verschil is de databron.")

    status = ev["status"]
    art = _write_artifact(args.engine, "trap10_tv-validatie", {
        "comparison": cmp_, "dimensions": ev["dimensions"],
        "exit_reasons": ev["exit_reasons"], "excursion": ev["excursion"],
        "trade_diff": td, "status": status,
        "matched_pct": ev["matched_pct"], "same_bar_pct": ev["same_bar_pct"],
        "as_tested": bool(tested_changes), "costs_from_export": costs,
        "as_tested_changes": {k2: [v[0], v[1]] for k2, v in tested_changes.items()},
        "dataset": args.dataset, "price_series_borrowed_from": substituted,
        "window": {"since": since, "until": until, "bars": len(df), "coverage": ov}})
    state.record(args.engine, "tv_validation", status,
                 summary=ev["verdict"]
                 + (f" [prijsreeks geleend van {substituted}]" if substituted else "")
                 + (" [ALS-GETEST: gemeten tegen de export-inputs]" if tested_changes else ""),
                 artifact=art,
                 detail={"dimensions": {k2: v["ok"] for k2, v in ev["dimensions"].items()},
                         "price_series_borrowed_from": substituted})
    label = {"passed": "GEHAALD", "data_parity": "GEHAALD (data-pariteit)",
             "failed": "NIET GEHAALD"}[status]
    print(f"\n  POORT: {label} — {ev['verdict']}")
    if substituted:
        print(f"  LET OP: prijsreeks geleend van {substituted} — een deployment-poort hoort "
              f"op de echte {prep['own']}-bars te draaien; dit is diagnose, geen vrijgave.")
    print(f"  artefact {art}")
    print("STAGE_JSON " + json.dumps(
        {"stage": 10, "dimensions": ev["dimensions"], "exit_reasons": ev["exit_reasons"],
         "excursion": ev["excursion"], "status": status,
         "pass": status in ("passed", "data_parity")}, default=str), flush=True)


def _write_artifact(engine: str, tag: str, payload: dict) -> str:
    """Ground rule 11 — every stage leaves an artifact."""
    from datetime import datetime
    d = lab_root() / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{engine}_{tag}_{datetime.now().strftime('%Y%m%d')}.json"
    f.write_text(json.dumps(payload, indent=2, default=str))
    return str(f)


def cmd_reset(args):
    """Clear accumulated lab history. Datasets are never touched."""
    root = lab_root()
    targets = [root / "results", root / "artifacts", root / "index.json",
               root / "pipeline_state.json"]
    targets += list(root.glob("candidates_seed*.json")) + list(root.glob("verified_seed*.json"))
    existing = [t for t in targets if t.exists()]
    keep = datasets_dir()
    print(f"lab root {root}")
    print(f"  BEHOUDEN: {keep} ({len(list(keep.glob('*'))) if keep.exists() else 0} datasets, incl. caches)")
    if not existing:
        print("  niets op te ruimen — de historie is al leeg.")
        return
    for t in existing:
        print(f"  {'verwijderen' if args.yes else 'zou verwijderen'}: {t}")
    if not args.yes:
        print("\n  droogloop. Voeg --yes toe om het echt te doen.")
        return
    for t in existing:
        shutil.rmtree(t) if t.is_dir() else t.unlink()
    print("\n  historie gewist; datasets ongemoeid.")


def main():
    ap = argparse.ArgumentParser(description="MEX research pipeline v7 — stage runner.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan").set_defaults(fn=cmd_plan)
    pf = sub.add_parser("fleet"); pf.set_defaults(fn=cmd_fleet)
    pf.add_argument("--through", type=int, default=2,
                    help="hoogste trap om te draaien (default 2)")
    pf.add_argument("--since", help="gemeenschappelijk startvenster (default 2023-08-24)")
    sub.add_parser("coverage").set_defaults(fn=cmd_coverage)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    ps = sub.add_parser("sensitivity"); ps.set_defaults(fn=cmd_sensitivity)
    ps.add_argument("--dataset", required=True)
    ps.add_argument("--engine", required=True, choices=fleet.names())
    ps.add_argument("--since"); ps.add_argument("--until")
    ps.add_argument("--prob", type=float, default=0.35,
                    help="aandeel bars dat een tick verschuift (default 0.35)")
    ps.add_argument("--seeds", type=int, default=3)
    ps.add_argument("--mode", choices=("shift", "independent"), default="shift",
                    help="shift = hele bar verschuift, range blijft behouden (default); "
                         "independent = O/H/L/C los, verbreedt bars (oude gedrag)")

    p0 = sub.add_parser("stage0"); p0.set_defaults(fn=cmd_stage0)
    p0.add_argument("--dataset", required=True); p0.add_argument("--engine", default="")

    p1 = sub.add_parser("stage1"); p1.set_defaults(fn=cmd_stage1)
    p1.add_argument("--dataset", required=True)
    p1.add_argument("--engine", required=True, choices=fleet.names())
    p1.add_argument("--export", required=True, help="TradingView .xlsx export of the same engine")
    p1.add_argument("--since"); p1.add_argument("--until")
    p1.add_argument("--as-tested", action="store_true",
                    help="neem de export-inputs over waar ze van de .pine-bron afwijken, "
                         "zodat de engine meetbaar wordt (grondregel 10 blijft gemeld)")
    p1.add_argument("--diff", action="store_true",
                    help="toon de trade-voor-trade vergelijking ook als de poort slaagt")

    p2 = sub.add_parser("stage2"); p2.set_defaults(fn=cmd_stage2)
    p2.add_argument("--dataset", required=True)
    p2.add_argument("--engine", required=True, choices=fleet.names())
    p2.add_argument("--since"); p2.add_argument("--until")
    _p3 = sub.add_parser("stage3"); _p3.set_defaults(fn=cmd_stage3)
    _p3.add_argument("--dataset", required=True)
    _p3.add_argument("--engine", required=True, choices=fleet.names())
    _p3.add_argument("--since"); _p3.add_argument("--until")
    _p4 = sub.add_parser("stage4"); _p4.set_defaults(fn=cmd_stage4)
    _p4.add_argument("--dataset", required=True)
    _p4.add_argument("--engine", required=True, choices=fleet.names())
    _p4.add_argument("--since"); _p4.add_argument("--until")
    _p5 = sub.add_parser("stage5"); _p5.set_defaults(fn=cmd_stage5)
    _p5.add_argument("--dataset", required=True)
    _p5.add_argument("--engine", required=True, choices=fleet.names())
    _p5.add_argument("--since"); _p5.add_argument("--until")
    _p6 = sub.add_parser("stage6"); _p6.set_defaults(fn=cmd_stage6)
    _p6.add_argument("--dataset", required=True)
    _p6.add_argument("--engine", required=True, choices=fleet.names())
    _p6.add_argument("--since"); _p6.add_argument("--until")
    _p7 = sub.add_parser("stage7"); _p7.set_defaults(fn=cmd_stage7)
    _p7.add_argument("--dataset", required=True)
    _p7.add_argument("--engine", required=True, choices=fleet.names())
    _p7.add_argument("--since"); _p7.add_argument("--until")
    _p8 = sub.add_parser("stage8"); _p8.set_defaults(fn=cmd_stage8)
    _p8.add_argument("--dataset", required=True)
    _p8.add_argument("--engine", required=True, choices=fleet.names())
    _p8.add_argument("--since"); _p8.add_argument("--until")
    _p9 = sub.add_parser("stage9"); _p9.set_defaults(fn=cmd_stage9)
    _p9.add_argument("--dataset", required=True)
    _p9.add_argument("--engine", required=True, choices=fleet.names())
    _p9.add_argument("--since"); _p9.add_argument("--until")

    p10 = sub.add_parser("stage10"); p10.set_defaults(fn=cmd_stage10)
    p10.add_argument("--dataset", required=True)
    p10.add_argument("--engine", required=True, choices=fleet.names())
    p10.add_argument("--export", required=True, help="TradingView .xlsx export of the same engine")
    p10.add_argument("--since"); p10.add_argument("--until")
    p10.add_argument("--as-tested", action="store_true",
                     help="neem de export-inputs over waar ze van de .pine-bron afwijken "
                          "(grondregel 10 blijft gemeld)")
    p10.add_argument("--diff", action="store_true",
                     help="toon de trade-voor-trade vergelijking ook als de poort slaagt")

    psc = sub.add_parser("scorecard"); psc.set_defaults(fn=cmd_scorecard)
    psc.add_argument("--dataset", required=True)
    psc.add_argument("--engine", required=True, choices=fleet.names())
    psc.add_argument("--since"); psc.add_argument("--until")
    psc.add_argument("--raw", action="store_true",
                     help="1 contract, geen account-overlay/dagcaps — de intrinsieke mechaniek "
                          "(default is deployment-houding, overlay aan)")
    psc.add_argument("--holdout-days", type=int, default=0,
                     help="splits in in-sample + laatste N dagen out-of-sample en meet beide "
                          "(overfit-check met retain-ratio)")


    pr = sub.add_parser("reset"); pr.set_defaults(fn=cmd_reset)
    pr.add_argument("--yes", action="store_true")

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
