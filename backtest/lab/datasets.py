"""Dataset catalog — validate a delivered 1-minute file and write its manifest.

Stdlib only (no pandas) so it stays cheap and testable: the header is read with
csv, the first/last data rows are found by seeking, the row count by streaming,
and a sha256 fingerprints the file for dedup/provenance.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

from .paths import datasets_dir

# Mirror backtest.data.REQUIRED so a catalogued file is guaranteed loadable.
REQUIRED = ["DateTime", "Open", "High", "Low", "Close", "Volume", "Delta"]
ORDERFLOW = ["CVD_close", "BuyVolume", "SellVolume"]


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _header(path: Path) -> list[str]:
    with open(path, newline="") as f:
        return next(csv.reader(f))


def _parse_row(line: str) -> list[str]:
    return next(csv.reader([line])) if line else []


def _first_last(path: Path) -> tuple[str, str]:
    """First and last data lines (stdlib, big-file friendly via seek-from-end)."""
    with open(path, "rb") as f:
        f.readline()                       # header
        first = f.readline().decode("utf-8", "replace").strip()
        last = first
        try:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b"\n":
                f.seek(-2, os.SEEK_CUR)
            tail = f.readline().decode("utf-8", "replace").strip()
            if tail:
                last = tail
        except OSError:
            pass                           # tiny file: last == first
    return first, last


def _count_rows(path: Path) -> int:
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return max(n - 1, 0)                    # minus header


def catalog(csv_path: str | Path, symbol: str = "", timeframe: str = "1m") -> dict:
    """Validate columns and build a manifest dict for a delivered dataset file."""
    csv_path = Path(csv_path)
    cols = _header(csv_path)
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        raise ValueError(f"dataset missing required columns: {missing} (have {cols})")

    first, last = _first_last(csv_path)
    dt_i = cols.index("DateTime")

    def _dt(line: str):
        row = _parse_row(line)
        return row[dt_i] if len(row) > dt_i else None

    return {
        "name": csv_path.stem,
        "file": csv_path.name,
        "symbol": symbol,
        "timeframe": timeframe,
        "columns": cols,
        "has_orderflow": all(c in cols for c in ("BuyVolume", "SellVolume")),
        "has_cvd": "CVD_close" in cols,
        "rows": _count_rows(csv_path),
        "first_dt": _dt(first),
        "last_dt": _dt(last),
        "bytes": csv_path.stat().st_size,
        "sha256": sha256_file(csv_path),
    }


def write_catalog(csv_path: str | Path, symbol: str = "", timeframe: str = "1m",
                  dest_dir: str | Path | None = None) -> Path:
    """Catalog a file and drop its manifest.json next to it (or under datasets/<name>/)."""
    csv_path = Path(csv_path)
    m = catalog(csv_path, symbol=symbol, timeframe=timeframe)
    dest = Path(dest_dir) if dest_dir else datasets_dir() / m["name"]
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "manifest.json").write_text(json.dumps(m, indent=2))
    return dest / "manifest.json"


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Catalog a delivered dataset file.")
    ap.add_argument("csv")
    ap.add_argument("--symbol", default="", help="contract symbol (NQ, ES, GC, ...)")
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--dest", help="where to write manifest.json (default datasets/<name>/)")
    a = ap.parse_args()
    path = write_catalog(a.csv, symbol=a.symbol, timeframe=a.timeframe, dest_dir=a.dest)
    print(f"manifest -> {path}")
    print(json.dumps(json.loads(Path(path).read_text()), indent=2))


if __name__ == "__main__":
    _main()
