"""Run one pipeline stage, or reset the lab.

    python -m backtest.pipeline.cli plan
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

    exp = read_export(args.export)
    pa = audit_properties(exp, cfg)
    print(f"\n  Properties-audit (grondregel 10): {pa['mismatches']} afwijking(en)")
    print(f"    symbool {pa['symbol']} · commissie {pa['commission']} · slippage {pa['slippage']}")
    print(f"    venster {pa['start']} -> {pa['end']}")
    for r in pa["rows"]:
        if not r["ok"]:
            print(f"    AFWIJKING {r['label']}: export={r['export']} vs config={r['config']}")
    if pa["mismatches"]:
        print("    De export test een ANDERE configuratie dan deze engine — de vergelijking")
        print("    hieronder is daarmee niet gezaghebbend. Los dit eerst op.")

    df = dm.load(path)
    if args.since:
        df = dm.slice_dates(df, since=args.since)
    if args.until:
        df = dm.slice_dates(df, until=args.until)
    print(f"\n  simulator op {len(df):,} bars {df['et'].iloc[0]} -> {df['et'].iloc[-1]}")
    k = kpis(Engine(cfg, df, im.compute(df, cfg), research_mode=True).run())
    cmp_ = compare(k, exp)
    print(f"\n    {'check':<18}{'simulator':>14}{'pine':>14}   ")
    for c in cmp_["checks"]:
        print(f"    {c['name']:<18}{str(c['sim']):>14}{str(c['pine']):>14}   "
              f"{'ok' if c['ok'] else 'AFWIJKING'} — {c['detail']}")
    ok = cmp_["pass"] and not pa["mismatches"]
    art = _write_artifact(args.engine, "trap1_pariteit",
                          {"properties_audit": pa, "comparison": cmp_})
    state.record(args.engine, "parity", "passed" if ok else "failed",
                 summary=cmp_["verdict"], artifact=art,
                 detail={"mismatches": pa["mismatches"], "checks": cmp_["checks"]})
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
