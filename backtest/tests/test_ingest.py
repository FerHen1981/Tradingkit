"""Bulk dataset ingest — normalize + catalog raw exports in one step."""
import csv
import json
import os

from backtest.lab import ingest, paths


def _raw(path, sym="NQ"):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["DateTime", "Open", "High", "Low", "Close", "Volume", "Delta"])
        for i in range(4):
            w.writerow([f"2024-01-02 09:3{i}:00", 100+i, 101+i, 99+i, 100+i, 50, 2])


def test_name_and_symbol_inference():
    from pathlib import Path
    n, s = ingest._name_and_symbol(Path("GC 20y 1m CVD (2).csv"), "", auto=True)
    assert s == "GC" and n == "GC_20y_1m_CVD_2"
    n, s = ingest._name_and_symbol(Path("whatever.csv"), "ES", auto=False)
    assert s == "ES"                       # forced symbol wins


def test_ingest_one_normalizes_and_catalogs(tmp_path):
    os.environ["LAB_DIR"] = str(tmp_path)
    src = tmp_path / "NQ 1m.csv"
    _raw(src)
    r = ingest.ingest_one(src, auto=True)
    assert r["symbol"] == "NQ" and r["rows"] == 4
    dd = paths.datasets_dir() / r["name"]
    assert (dd / "canonical.csv").exists()
    man = json.loads((dd / "manifest.json").read_text())
    assert man["symbol"] == "NQ"
