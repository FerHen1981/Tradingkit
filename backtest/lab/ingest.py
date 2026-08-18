"""Bulk-ingest raw CSV exports into the Lab data room in one step.

    python -m backtest.lab.ingest FILE [FILE ...] --auto
    python -m backtest.lab.ingest --dir /data/lab/incoming --auto
    python -m backtest.lab.ingest "GC 20y 1m CVD.csv" --symbol GC

For each CSV: normalize (→ canonical schema) into datasets/<name>/canonical.csv,
then catalog it (manifest.json). `--auto` infers the symbol from the filename's
first token (NQ, ES, GC, 6E, CL, …). One command loads a whole folder of
deliveries — handy when the browser upload is too heavy for big multi-year files.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from .datasets import write_catalog
from .normalize import to_canonical
from .paths import datasets_dir


def _name_and_symbol(path: Path, symbol: str, auto: bool) -> tuple[str, str]:
    """dataset folder name (sanitized basename) + symbol (forced or inferred)."""
    stem = path.stem
    first = re.split(r"[\s_]+", stem.strip())[0].upper() if stem.strip() else ""
    sym = symbol or (first if auto else "")
    name = re.sub(r"[^0-9A-Za-z]+", "_", stem).strip("_") or "dataset"
    return name, sym


def ingest_one(src: str | Path, symbol: str = "", auto: bool = False) -> dict:
    src = Path(src)
    name, sym = _name_and_symbol(src, symbol, auto)
    ddir = datasets_dir() / name
    ddir.mkdir(parents=True, exist_ok=True)
    canon = ddir / "canonical.csv"
    _, rows = to_canonical(src, canon)
    write_catalog(canon, symbol=sym)
    return {"name": name, "symbol": sym, "rows": rows, "dir": str(ddir)}


def main():
    ap = argparse.ArgumentParser(description="Bulk-ingest raw CSV exports into the Lab data room.")
    ap.add_argument("files", nargs="*", help="CSV files to ingest")
    ap.add_argument("--dir", help="ingest every *.csv in this folder")
    ap.add_argument("--symbol", default="", help="force this symbol for all files (else use --auto)")
    ap.add_argument("--auto", action="store_true", help="infer the symbol from each filename's first token")
    ap.add_argument("--raw", help="job mode (browser upload): normalize+catalog this ONE raw file "
                                 "into its dataset dir, with PROGRESS lines for the Lab UI")
    ap.add_argument("--name", default="", help="dataset folder name (with --raw; default: raw's parent dir)")
    ap.add_argument("--delete-raw", action="store_true",
                    help="remove the raw file after a successful normalize (saves ~its size on disk)")
    a = ap.parse_args()

    if a.raw:
        # Job mode for the browser upload: the HTTP request only streams the file
        # to disk and returns; THIS runs in the background with live progress, so
        # a 1GB export can't hit reverse-proxy/browser timeouts mid-normalize.
        src = Path(a.raw)
        name = a.name or src.parent.name
        ddir = datasets_dir() / name
        ddir.mkdir(parents=True, exist_ok=True)
        canon = ddir / "canonical.csv"

        def prog(done, total):
            print(f"PROGRESS {done} {max(total, 1)} normalizing {name} "
                  f"({done/1e6:.0f}/{total/1e6:.0f} MB)", flush=True)
        _, rows = to_canonical(src, canon, progress=prog)
        write_catalog(canon, symbol=a.symbol)
        if a.delete_raw:
            try:
                src.unlink()
            except OSError:
                pass
        # PREPARE up front: build the parse cache and the recent-3y slice now,
        # so the dataset's first backtest starts in seconds instead of paying a
        # ~1-minute parse — every later job loads a prepared pickle.
        print(f"PROGRESS 97 100 preparing fast caches (one-time)", flush=True)
        try:
            from .. import data as data_mod
            data_mod.load_window(canon, years=3)   # builds .cache.pkl + .recent3y.pkl
        except Exception as e:
            print(f"  note: cache prepare skipped ({e}) — first run will parse the CSV")
        print(f"  ok  dataset '{name}'  symbol {a.symbol or '?'}  ({rows:,} rows) -> {ddir}")
        return

    files = [Path(f) for f in a.files]
    if a.dir:
        files += sorted(Path(a.dir).glob("*.csv"))
    files = [f for f in files if f.exists()]
    if not files:
        ap.error("no CSV files found (pass file paths or --dir FOLDER)")
    if not a.symbol and not a.auto:
        ap.error("give --symbol SYM (same for all) or --auto (infer per filename)")

    ok, fail = 0, 0
    for f in files:
        try:
            r = ingest_one(f, symbol=a.symbol, auto=a.auto)
            print(f"  ok  {f.name}  ->  dataset '{r['name']}'  symbol {r['symbol'] or '?'}  ({r['rows']:,} rows)")
            ok += 1
        except Exception as e:
            print(f"  FAIL  {f.name}  ->  {e}")
            fail += 1
    print(f"\ningested {ok} dataset(s)" + (f", {fail} failed" if fail else "")
          + f" -> {datasets_dir()}")


if __name__ == "__main__":
    main()
