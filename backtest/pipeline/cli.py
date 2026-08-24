"""Run one pipeline stage, or reset the lab.

    python -m backtest.pipeline.cli plan
    python -m backtest.pipeline.cli coverage    # wat kan trap 1 draaien, wat mist
    python -m backtest.pipeline.cli stage0 --dataset MGC_20y_1m --engine EL_TESORO_MGC_CON_EOD
    python -m backtest.pipeline.cli stage1 --dataset MGC_20y_1m --engine EL_TESORO_MGC_CON_EOD \
        --export path/to/TESORO_export.xlsx
    python -m backtest.pipeline.cli reset --yes      # wipes results/history, KEEPS datasets
"""
from __future__ import annotations

import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import shutil

from . import fleet, state
from .stages import STAGES
from ..lab.paths import datasets_dir, lab_root


def _dataset_path(name: str) -> tuple[str, str]:
    from ..lab.lab_viewer import _datasets
    for d in _datasets():
        if d["name"] == name:
            return d["file"], (d.get("symbol") or "")
    raise SystemExit(f"unknown dataset {name!r} — see 1 · Data")


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


def cmd_coverage(_args):
    """What can trap 1 actually run today, and what data is missing?

    Trap 1 is a hard gate, so this answers the only question that matters while
    it is open: for each TradingView export we hold, is there a dataset that
    covers the market AND the window the export was actually tested over?

    A mini's price history counts for its micro (see fleet.TWIN) — same ticks,
    same trade sequence — but only if it reaches far enough. A 20-year file that
    stops before the export's end date is the failure mode this catches."""
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

    runnable, blocked = 0, []
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

        exact = [d for d in dsets if d["symbol"] == root]
        twins = [d for d in dsets if twin and d["symbol"] == twin]
        usable, short = [], []
        for d in exact + twins:
            covers = (a is None or b is None or
                      (d["first"] is not None and d["last"] is not None
                       and d["first"] <= a and d["last"] >= b))
            (usable if covers else short).append(d)

        if usable:
            runnable += 1
            for d in usable:
                via = "" if d["symbol"] == root else f" (via twin {d['symbol']} — zelfde ticks)"
                print(f"     BRUIKBAAR: {d['name']}{via}")
        for d in short:
            end = f"{d['last']:%Y-%m-%d}" if d["last"] else "?"
            via = "" if d["symbol"] == root else f" (twin {d['symbol']})"
            print(f"     TE KORT: {d['name']}{via} loopt tot {end}, export vraagt tot "
                  f"{b:%Y-%m-%d}" if b else f"     TE KORT: {d['name']}{via}")
        if not usable:
            blocked.append((root, twin, window, bool(short)))
            if not short:
                need = f"{root}" + (f" of {twin}" if twin else "")
                print(f"     GEBLOKKEERD — geen dataset voor {need}.")

    print(f"\n  {runnable} van {len(_exports())} export(s) is nu te draaien op trap 1.")
    if blocked:
        print("\n  ONTBREKENDE DATA (kritiek pad — trap 1 is een harde poort, dus trap 2")
        print("  t/m 9 zijn ongeldig zolang die dichtstaat):")
        for root, twin, window, only_short in blocked:
            need = root + (f" (of {twin}: zelfde tick size, zelfde trades)" if twin else "")
            why = "bestaande dataset loopt niet ver genoeg door" if only_short else "geen dataset"
            print(f"    · 1-minuut {need}, minimaal {window}  — {why}")


def cmd_plan(_args):
    engines = fleet.names()
    rows = state.overview(engines)
    print(f"\n  MEX research pipeline v7 — {len(STAGES)} trappen, {len(engines)} engines\n")
    print(f"    {'engine':<26}{'markt':>6}{'gehaald t/m':>13}   trap-status 0..11")
    for r, s in zip(rows, (fleet.summary())):
        marks = "".join({"passed": "+", "failed": "x", "running": "~",
                         "inconclusive": "?"}.get(v["status"], ".") for v in r["stages"])
        reached = f"trap {r['reached']}" if r["reached"] >= 0 else "—"
        print(f"    {r['engine'].replace('EL_',''):<26}{s['market']:>6}{reached:>13}   {marks}")
    print("\n    + gehaald · x gefaald · ~ loopt · ? inconclusief · . nog niet gedraaid")
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


def cmd_stage1(args):
    from .. import data as dm, indicators as im
    from ..engine import Engine
    from ..metrics import kpis
    from .parity import audit_properties, compare, read_export
    path, sym = _dataset_path(args.dataset)
    cfg = fleet.engine_config(args.engine)
    print(f"trap 1 · Pine-pariteit · {args.engine} op {args.dataset}")
    print("  POORT: bijna gelijk aantal trades + materieel vergelijkbare WR/PF. HARDE POORT.")

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
        print(f"  PRIJSREEKS GELEEND: {ds_sym}-data onder de {own}-contractspec. Zelfde tick "
              f"size, dus dezelfde trades; alleen de $-P&L schaalt. Wordt vastgelegd "
              f"in het artefact.")
    else:
        raise SystemExit(
            f"dataset {args.dataset!r} is {ds_sym}-data, maar {args.engine} handelt {own}"
            + (f" (twin {twin} zou ook mogen)" if twin else "")
            + ". Trap 1 op de verkeerde markt meet niets.")

    exp = read_export(args.export)
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
    if pa["mismatches"] or pa["environment_mismatches"]:
        print("    De export test een ANDERE configuratie dan deze engine — de vergelijking")
        print("    hieronder is daarmee niet gezaghebbend. Los dit eerst op.")

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
    print(f"\n  simulator op {len(df):,} bars {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")
    k = kpis(Engine(cfg, df, im.compute(df, cfg), research_mode=True).run())
    cmp_ = compare(k, exp)
    print(f"\n    {'check':<18}{'simulator':>14}{'pine':>14}   ")
    for c in cmp_["checks"]:
        print(f"    {c['name']:<18}{str(c['sim']):>14}{str(c['pine']):>14}   "
              f"{'ok' if c['ok'] else 'AFWIJKING'} — {c['detail']}")
    ok = (cmp_["pass"] and not pa["mismatches"]
          and not pa["environment_mismatches"] and not pa["missing"])
    art = _write_artifact(args.engine, "trap1_pariteit",
                          {"properties_audit": pa, "comparison": cmp_,
                           "dataset": args.dataset, "dataset_symbol": ds_sym,
                           "price_series_borrowed_from": substituted,
                           "window": {"since": since, "until": until, "bars": len(df)}})
    state.record(args.engine, "parity", "passed" if ok else "failed",
                 summary=cmp_["verdict"] + (f" [prijsreeks geleend van {substituted}]"
                                            if substituted else ""),
                 artifact=art,
                 detail={"mismatches": pa["mismatches"], "checks": cmp_["checks"],
                         "price_series_borrowed_from": substituted})
    print(f"\n  POORT: {'GEHAALD' if ok else 'NIET GEHAALD'} — {cmp_['verdict']}")
    print(f"  artefact {art}")
    print("STAGE_JSON " + json.dumps({"stage": 1, "properties": pa, "comparison": cmp_,
                                      "pass": ok}, default=str), flush=True)


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
    sub.add_parser("coverage").set_defaults(fn=cmd_coverage)

    p0 = sub.add_parser("stage0"); p0.set_defaults(fn=cmd_stage0)
    p0.add_argument("--dataset", required=True); p0.add_argument("--engine", default="")

    p1 = sub.add_parser("stage1"); p1.set_defaults(fn=cmd_stage1)
    p1.add_argument("--dataset", required=True)
    p1.add_argument("--engine", required=True, choices=fleet.names())
    p1.add_argument("--export", required=True, help="TradingView .xlsx export of the same engine")
    p1.add_argument("--since"); p1.add_argument("--until")

    pr = sub.add_parser("reset"); pr.set_defaults(fn=cmd_reset)
    pr.add_argument("--yes", action="store_true")

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
