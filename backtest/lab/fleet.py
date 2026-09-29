"""Fleet register — the validated / production strategies the desk builds on.

Lives at $LAB_DIR/fleet.json. This is the "list" the pipeline produces: research
→ tested → PROMOTED. A strategy flows in when you promote a run in the cockpit;
the eight ported fleet strategies (Toro/Matador/Dorado/Patron · Rey/Leon ·
Tesoro/Minero) seed the register on first use so you start from the real fleet.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .paths import lab_root

# The already-validated fleet, seeded on first load. PA/Funded phase → "funded",
# Apex Eval phase → "eval".
_SEED = ["EL_TORO", "EL_MATADOR", "EL_DORADO", "EL_PATRON",
         "EL_LEON", "EL_REY", "EL_MINERO", "EL_TESORO"]


def _path():
    return lab_root() / "fleet.json"


def _seed_rows() -> list:
    from ..config import PRESETS
    rows = []
    for n in _SEED:
        c = PRESETS.get(n)
        if not c:
            continue
        status = "funded" if (c.phase_on and "PA" in c.phase) else "eval"
        rows.append({"id": f"preset:{n}", "name": n, "asset": c.contract.symbol,
                     "status": status, "note": "ported fleet strategy",
                     "kpis": None, "run_id": None, "promoted_at": None, "seed": True})
    return rows


def load_fleet() -> list:
    p = _path()
    if not p.exists():
        rows = _seed_rows()
        save_fleet(rows)
        return rows
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def save_fleet(rows: list) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, indent=2, default=str))


def promote(entry: dict) -> list:
    """Add or update a strategy in the fleet, keyed by `id`. Stamps promoted_at."""
    fid = entry.get("id")
    if not fid:
        raise ValueError("promote needs an 'id'")
    rows = [r for r in load_fleet() if r.get("id") != fid]
    entry = dict(entry)
    entry.setdefault("status", "validated")
    entry["seed"] = False
    entry["promoted_at"] = datetime.now(timezone.utc).isoformat()
    rows.append(entry)
    save_fleet(rows)
    return rows


def demote(fid: str) -> list:
    rows = [r for r in load_fleet() if r.get("id") != fid]
    save_fleet(rows)
    return rows
