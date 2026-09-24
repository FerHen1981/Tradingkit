"""Run registry — recognizable run_ids + an immutable folder per run + index.json.

A run_id is human-readable and carries the asset/strategy/timeframe/lens in the
name, plus a short deterministic fingerprint of the exact config so identical
runs collapse and different ones never collide:

    NQ_El-Toro-v7-PAonly_15m_eval_20260815_a1b2c3
    │  │                  │   │    │        └ fingerprint(spec+asset+tf+lens+dataset)
    │  │                  │   │    └ run date (UTC)
    │  │                  │   └ lens: classic | eval | funded
    │  │                  └ timeframe
    │  └ strategy (slugged)
    └ asset
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .paths import ensure_dirs, index_path, results_dir

# Fields kept out of the (light) index; the full run.json holds everything.
_HEAVY = {"groups", "unmapped", "settings", "desc", "edge_by_regime"}


def slug(s) -> str:
    out = re.sub(r"[^0-9A-Za-z]+", "-", str(s)).strip("-")
    return out or "x"


def fingerprint(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:6]


def make_run_id(asset: str, strategy: str, timeframe: str, lens: str,
                fp: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return (f"{slug(asset)}_{slug(strategy)}_{slug(timeframe)}_{slug(lens)}"
            f"_{when.strftime('%Y%m%d')}_{fp}")


def record_run(meta: dict, artifacts: dict[str, str] | None = None) -> Path:
    """Write results/<run_id>/{run.json, *artifacts} and upsert index.json.

    `meta` must contain 'run_id'. `artifacts` maps filename -> text content
    (e.g. {'kpis.json': ..., 'trades.csv': ...}).
    """
    if "run_id" not in meta:
        raise ValueError("meta must include 'run_id'")
    ensure_dirs()
    d = results_dir() / meta["run_id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps(meta, indent=2, default=str))
    for fname, content in (artifacts or {}).items():
        (d / fname).write_text(content)
    _upsert_index({k: v for k, v in meta.items() if k not in _HEAVY})
    return d


def load_index() -> list[dict]:
    p = index_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _upsert_index(entry: dict) -> None:
    idx = [e for e in load_index() if e.get("run_id") != entry.get("run_id")]
    idx.append(entry)
    index_path().parent.mkdir(parents=True, exist_ok=True)
    index_path().write_text(json.dumps(idx, indent=2, default=str))
