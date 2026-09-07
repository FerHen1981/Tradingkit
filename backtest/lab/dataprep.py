"""Dataset preparation for the Data tab — validate (audit) and aggregate (resample).

Two operations that both need pandas, so they run as a subprocess the UI spawns,
each emitting one JSON line the browser parses (AUDIT_JSON / AGGREGATE_JSON) — the
same contract the scorecard and stage runners use.

  audit     — run the data-quality report (pipeline.audit) on a dataset.
  aggregate — resample a 1-minute dataset to a coarser timeframe and STORE it as a
              new, browsable dataset (canonical.csv + manifest.json). The engine can
              already resample on the fly at run time; this persists the result so
              it shows up in the catalog and can be measured/analysed like any other.

Resampling reuses data.resample_tf (session-aligned to 18:00 ET, gap-safe). NB the
pipeline gates are validated on 1-minute data — an aggregated dataset is for
analysis/exploration, not for re-running trap 1 against a 1m TradingView export.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .paths import datasets_dir


def _resolve(name: str) -> tuple[str, str]:
    """(canonical_csv_path, symbol) for a dataset name."""
    sub = datasets_dir() / name
    f = next((p for p in (sub / "canonical.csv", sub / "data.csv") if p.exists()), None)
    if f is None:
        raise SystemExit(f"dataset {name!r} niet gevonden onder {datasets_dir()}")
    sym = ""
    man = sub / "manifest.json"
    if man.exists():
        try:
            sym = json.loads(man.read_text()).get("symbol", "") or ""
        except Exception:
            pass
    return str(f), sym


def cmd_audit(args):
    from .. import data as dm
    from ..pipeline.audit import audit
    path, sym = _resolve(args.dataset)
    print(f"data-audit · {args.dataset} ({sym or '?'})")
    rep = audit(dm.load(path), sym)
    rep["dataset"], rep["symbol"] = args.dataset, sym
    print("AUDIT_JSON " + json.dumps(rep, default=str), flush=True)


def _to_canonical(agg):
    """Rebuild the canonical schema (DateTime + OHLCV + optional order-flow) from a
    resampled frame so data.load can read it straight back. DateTime is written in
    the delivered DAY-FIRST, offset-aware shape ("02-01-2025 18:00:00 -0500"): the
    loader parses with dayfirst=True, so an ISO YYYY-MM-DD would be mis-read as
    YYYY-DD-MM and silently smear the dates across months."""
    import pandas as pd
    dt = agg["et"].dt.strftime("%d-%m-%Y %H:%M:%S %z")    # "02-01-2025 18:00:00 -0500"
    cols = {"DateTime": dt, "Open": agg["Open"], "High": agg["High"],
            "Low": agg["Low"], "Close": agg["Close"],
            "Volume": agg["Volume"] if "Volume" in agg.columns else 0,
            "Delta": agg["Delta"] if "Delta" in agg.columns else 0}
    for opt in ("CVD_close", "BuyVolume", "SellVolume"):
        if opt in agg.columns:
            cols[opt] = agg[opt]
    return pd.DataFrame(cols)


def cmd_aggregate(args):
    from .. import data as dm
    from ..config import tf_minutes
    from .datasets import write_catalog
    path, sym = _resolve(args.dataset)
    if tf_minutes(args.tf) <= 1:                # also validates the label
        raise SystemExit(f"{args.tf} is niet grofmaziger dan 1m — niets te aggregeren.")
    name = args.name or f"{args.dataset}_{args.tf}"
    dest = datasets_dir() / name
    if dest.exists() and not args.overwrite:
        raise SystemExit(f"dataset {name!r} bestaat al — kies een andere --name of --overwrite.")

    print(f"aggregeren · {args.dataset} -> {args.tf} · nieuwe dataset {name!r}")
    agg = dm.resample_tf(dm.load(path), args.tf)
    out = _to_canonical(agg)
    dest.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest / "canonical.csv", index=False)
    write_catalog(dest / "canonical.csv", symbol=sym, timeframe=args.tf)
    res = {"dataset": name, "source": args.dataset, "timeframe": args.tf,
           "symbol": sym, "rows": int(len(out)),
           "first": str(agg["et"].iloc[0]), "last": str(agg["et"].iloc[-1])}
    print(f"  {res['rows']:,} bars geschreven · {res['first']} -> {res['last']}")
    print("AGGREGATE_JSON " + json.dumps(res, default=str), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dataset-prep: validate / aggregate.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("audit"); pa.set_defaults(fn=cmd_audit)
    pa.add_argument("--dataset", required=True)
    pg = sub.add_parser("aggregate"); pg.set_defaults(fn=cmd_aggregate)
    pg.add_argument("--dataset", required=True)
    pg.add_argument("--tf", required=True, help="doel-timeframe (5m,15m,30m,1h,...)")
    pg.add_argument("--name", help="naam van de nieuwe dataset (default <dataset>_<tf>)")
    pg.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
