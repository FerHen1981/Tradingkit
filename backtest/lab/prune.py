"""Prune the Lab data room — safely remove runs and keep index.json consistent.

Deleting a results/<run_id>/ folder by hand leaves a stale entry in index.json,
so the cockpit lists runs that 404. This tool removes the folders AND rebuilds
index.json from what actually survives on disk, so the registry always matches.

Examples
--------
    # see everything first (nothing is touched)
    python -m backtest.lab.prune --list

    # preview a removal (dry-run is implied until you add --yes)
    python -m backtest.lab.prune --match NQ_v

    # actually remove the framework demo runs + rebuild the index
    python -m backtest.lab.prune --match NQ_v --yes

    # drop everything older than 30 days
    python -m backtest.lab.prune --older-than 30 --yes

    # just repair the index to match disk (remove orphan entries)
    python -m backtest.lab.prune --reindex --yes

Filters combine with AND. With no filter, only --reindex is allowed (a no-op on
the run folders), so you can never wipe the whole room by forgetting a flag.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone

from .paths import index_path, results_dir
from .runs import _HEAVY, load_index


def _run_dirs() -> list:
    d = results_dir()
    return sorted([p for p in d.iterdir() if p.is_dir()]) if d.exists() else []


def _meta(run_dir) -> dict:
    rj = run_dir / "run.json"
    if rj.exists():
        try:
            return json.loads(rj.read_text())
        except Exception:
            pass
    return {"run_id": run_dir.name}


def _age_days(meta: dict) -> float | None:
    ts = meta.get("created_at")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None


def _rebuild_index() -> int:
    """Rewrite index.json from the run.json files still on disk (light fields
    only, matching record_run's _HEAVY exclusion). Returns the surviving count."""
    idx = []
    for p in _run_dirs():
        m = _meta(p)
        idx.append({k: v for k, v in m.items() if k not in _HEAVY})
    index_path().parent.mkdir(parents=True, exist_ok=True)
    index_path().write_text(json.dumps(idx, indent=2, default=str))
    return len(idx)


def main():
    ap = argparse.ArgumentParser(description="Prune Lab runs; keep index.json consistent.")
    ap.add_argument("--list", action="store_true", help="list every run and exit (touches nothing)")
    ap.add_argument("--match", help="remove runs whose run_id contains this substring")
    ap.add_argument("--kind", help="remove runs of this kind (spec|preset|generated)")
    ap.add_argument("--older-than", type=float, metavar="DAYS",
                    help="remove runs created more than DAYS days ago")
    ap.add_argument("--reindex", action="store_true",
                    help="rebuild index.json from disk (drop orphan entries); no filter needed")
    ap.add_argument("--yes", action="store_true", help="actually delete (without this it is a dry-run)")
    args = ap.parse_args()

    dirs = _run_dirs()
    if args.list:
        idx_n = len(load_index())
        print(f"{len(dirs)} run folder(s) on disk · {idx_n} entr(y/ies) in index.json\n")
        for p in dirs:
            m = _meta(p)
            age = _age_days(m)
            pf = (m.get("kpis") or {}).get("profit_factor")
            print(f"  {p.name}")
            print(f"      kind={m.get('kind','?')} strat={m.get('strategy','?')} "
                  f"tf={m.get('timeframe','?')} PF={pf} "
                  f"age={f'{age:.1f}d' if age is not None else '?'}")
        return

    has_filter = any([args.match, args.kind, args.older_than is not None])
    if not has_filter and not args.reindex:
        ap.error("no filter given. Use --match/--kind/--older-than to select runs, "
                 "--reindex to only repair the index, or --list to look first.")

    victims = []
    for p in dirs:
        m = _meta(p)
        if args.match and args.match not in p.name:
            continue
        if args.kind and m.get("kind") != args.kind:
            continue
        if args.older_than is not None:
            age = _age_days(m)
            if age is None or age < args.older_than:
                continue
        if has_filter:
            victims.append(p)

    if has_filter:
        verb = "Removing" if args.yes else "[dry-run] would remove"
        print(f"{verb} {len(victims)} run(s):")
        for p in victims:
            print(f"  - {p.name}")
        if args.yes:
            for p in victims:
                shutil.rmtree(p, ignore_errors=True)

    if args.yes:
        n = _rebuild_index()
        print(f"\nindex.json rebuilt: {n} run(s) remain.")
    elif has_filter:
        print(f"\n(dry-run — nothing deleted. Re-run with --yes to apply, then the "
              f"index is rebuilt automatically.)")
    elif args.reindex:
        print("(dry-run — add --yes to rewrite index.json from disk.)")


if __name__ == "__main__":
    main()
