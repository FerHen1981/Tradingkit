"""Filesystem layout for the Backtest Lab data room.

    $LAB_DIR (default /data/lab)
      datasets/<name>/data.csv + manifest.json    # big 1m source files you deliver
      results/<run_id>/run.json + kpis.json + ...  # one immutable folder per run
      index.json                                   # registry of every run (the cockpit reads this)

Everything here lives on the VPS only; big files never go in git.
"""
from __future__ import annotations

import os
from pathlib import Path


def lab_root() -> Path:
    return Path(os.environ.get("LAB_DIR", "/data/lab"))


def datasets_dir() -> Path:
    return lab_root() / "datasets"


def results_dir() -> Path:
    return lab_root() / "results"


def index_path() -> Path:
    return lab_root() / "index.json"


def ensure_dirs() -> None:
    for d in (datasets_dir(), results_dir()):
        d.mkdir(parents=True, exist_ok=True)
