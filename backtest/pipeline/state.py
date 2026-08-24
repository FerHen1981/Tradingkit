"""Per-engine stage status — the visible spine of the pipeline.

Advisory, not enforcing (Ferry, 2026-08-20): running a stage out of order is
allowed, but the record always shows which earlier gates are unmet, so a result
produced ahead of its gate is visibly provisional. `blocked_by` names the unmet
HARD gates below a stage — the ones that, per ground rule 1, make downstream
numbers invalid rather than merely early.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .stages import BY_KEY, STAGES
from ..lab.paths import lab_root

_VALID = ("todo", "running", "passed", "failed", "inconclusive")


def _path():
    return lab_root() / "pipeline_state.json"


def load() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save(state: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, default=str))


def record(engine: str, stage_key: str, status: str, summary: str = "",
           artifact: str = "", detail: dict | None = None) -> dict:
    """Write the outcome of one stage for one engine."""
    if stage_key not in BY_KEY:
        raise ValueError(f"unknown stage {stage_key!r}")
    if status not in _VALID:
        raise ValueError(f"status must be one of {_VALID}")
    st = load()
    st.setdefault(engine, {})[stage_key] = {
        "status": status, "summary": summary, "artifact": artifact,
        "detail": detail or {}, "at": datetime.now(timezone.utc).isoformat()}
    save(st)
    return st


def engine_view(engine: str, state: dict | None = None) -> list[dict]:
    """All twelve stages for one engine, with what blocks what."""
    st = (state if state is not None else load()).get(engine, {})
    out, unmet_hard = [], []
    for s in STAGES:
        rec = st.get(s.key) or {}
        status = rec.get("status", "todo")
        out.append({"n": s.n, "key": s.key, "title": s.title, "gate": s.gate,
                    "hard": s.hard, "note": s.note, "status": status,
                    "summary": rec.get("summary", ""), "at": rec.get("at", ""),
                    "artifact": rec.get("artifact", ""),
                    "blocked_by": list(unmet_hard)})
        if s.hard and status != "passed":
            unmet_hard.append(f"{s.n} · {s.title}")
    return out


def overview(engines: list[str]) -> list[dict]:
    """One row per engine for the plan table: how far it actually got."""
    st = load()
    rows = []
    for e in engines:
        view = engine_view(e, st)
        passed = [v for v in view if v["status"] == "passed"]
        failed = [v for v in view if v["status"] == "failed"]
        # furthest CONSECUTIVE stage reached — the honest progress number
        reached = -1
        for v in view:
            if v["status"] == "passed":
                reached = v["n"]
            else:
                break
        rows.append({"engine": e, "reached": reached, "passed": len(passed),
                     "failed": len(failed),
                     "hard_open": [v["title"] for v in view if v["hard"] and v["status"] != "passed"],
                     "stages": [{"n": v["n"], "status": v["status"]} for v in view]})
    return rows
