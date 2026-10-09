#!/usr/bin/env python3
"""Inventory scattered local files so they can be triaged instead of copied.

Moving C:\\ to a server moves the mess with it. This walks the folders you point
it at, classifies what it finds, spots duplicates, and writes a CSV you can act
on. Nothing is moved, renamed or deleted — it only looks.

Runs on Windows with a plain Python install; standard library only.

Usage
-----
    python tools\\inventory_local.py C:\\Trading C:\\Users\\me\\Downloads
    python tools\\inventory_local.py C:\\Trading --out inventory.csv --min-mb 1

Then send me the CSV (or just the summary it prints) and we decide per class what
moves to the bucket, what goes into the repo, and what goes to the attic.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# class -> (extensions, where it belongs once tidied)
CLASSES: dict[str, tuple[set[str], str]] = {
    "dataset":   ({".csv", ".parquet", ".pq", ".feather", ".txt", ".tsv"},
                  "object storage + data/manifest.json"),
    "database":  ({".db", ".sqlite", ".sqlite3"},
                  "server volume (with backups)"),
    "pine":      ({".pine"}, "repo: pine/"),
    "code":      ({".py", ".ipynb", ".sh", ".ps1", ".js", ".ts", ".sql"},
                  "repo (or delete if superseded)"),
    "config":    ({".yaml", ".yml", ".json", ".ini", ".env", ".toml"},
                  "repo, or secrets manager — never the bucket"),
    "document":  ({".md", ".pdf", ".docx", ".xlsx", ".doc", ".xls", ".rtf", ".odt"},
                  "Notion, or repo docs/"),
    "image":     ({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"},
                  "attic unless referenced"),
    "archive":   ({".zip", ".7z", ".rar", ".gz", ".tar", ".zst"},
                  "unpack and re-classify, or attic"),
}
EXT_TO_CLASS = {ext: name for name, (exts, _) in CLASSES.items() for ext in exts}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "$RECYCLE.BIN",
             "System Volume Information", "AppData", ".cache", "site-packages"}

# A dataset export is big and columnar; a 2 KB .csv is a note, not a dataset.
DATASET_MIN_BYTES = 5 * 1024 * 1024

CHUNK = 1 << 20


def classify(path: Path, size: int) -> str:
    cls = EXT_TO_CLASS.get(path.suffix.lower(), "other")
    if cls == "dataset" and size < DATASET_MIN_BYTES:
        return "document" if path.suffix.lower() in (".txt", ".md") else "other"
    return cls


def fingerprint(path: Path, size: int) -> str:
    """Cheap content key: size + first and last megabyte. Full hashes of
    multi-hundred-MB exports would make this unusable on a laptop."""
    h = hashlib.sha256(str(size).encode())
    try:
        with path.open("rb") as fh:
            h.update(fh.read(CHUNK))
            if size > 2 * CHUNK:
                fh.seek(-CHUNK, os.SEEK_END)
                h.update(fh.read(CHUNK))
    except OSError:
        return ""
    return h.hexdigest()[:16]


def short(path: str, width: int) -> str:
    """Trim from the left — the filename is the part worth reading."""
    return path if len(path) <= width else "…" + path[-(width - 1):]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} PB"


def walk(roots: list[Path], min_bytes: int) -> list[dict]:
    rows: list[dict] = []
    for root in roots:
        if not root.exists():
            print(f"  ! skipping {root} — not found", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                           and not d.startswith(".")]
            for name in filenames:
                p = Path(dirpath) / name
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size < min_bytes:
                    continue
                rows.append({
                    "path": str(p),
                    "name": name,
                    "class": classify(p, st.st_size),
                    "bytes": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
                    "fingerprint": "",
                })
    return rows


def find_duplicates(rows: list[dict]) -> dict[str, list[dict]]:
    """Only fingerprint files whose size collides — that is where duplicates live,
    and it keeps us from reading every file on the disk."""
    by_size: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_size[r["bytes"]].append(r)

    groups: dict[str, list[dict]] = defaultdict(list)
    for size, candidates in by_size.items():
        if len(candidates) < 2:
            continue
        for r in candidates:
            r["fingerprint"] = fingerprint(Path(r["path"]), size)
            if r["fingerprint"]:
                groups[r["fingerprint"]].append(r)
    return {k: v for k, v in groups.items() if len(v) > 1}


def report(rows: list[dict], dupes: dict[str, list[dict]]) -> None:
    total = sum(r["bytes"] for r in rows)
    print(f"\n  {len(rows):,} files, {human(total)} total\n")

    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_class[r["class"]].append(r)

    print("  By class")
    print("  " + "-" * 74)
    for cls in sorted(by_class, key=lambda c: -sum(r["bytes"] for r in by_class[c])):
        items = by_class[cls]
        size = sum(r["bytes"] for r in items)
        dest = CLASSES.get(cls, (set(), "decide case by case"))[1]
        print(f"  {cls:<10} {len(items):>6} files  {human(size):>10}   → {dest}")

    print("\n  Largest files")
    print("  " + "-" * 74)
    for r in sorted(rows, key=lambda r: -r["bytes"])[:15]:
        print(f"  {human(r['bytes']):>10}  {r['modified']}  {short(r['path'], 56)}")

    if dupes:
        wasted = sum(sum(r["bytes"] for r in g[1:]) for g in dupes.values())
        print(f"\n  Duplicates: {len(dupes)} groups, {human(wasted)} recoverable")
        print("  " + "-" * 74)
        for group in sorted(dupes.values(), key=lambda g: -g[0]["bytes"])[:8]:
            print(f"  {human(group[0]['bytes']):>10}  ×{len(group)}")
            for r in group[:3]:
                print(f"              {short(r['path'], 62)}")
    else:
        print("\n  No duplicates found.")

    stale = [r for r in rows if r["modified"] < "2025-01-01"]
    if stale:
        size = sum(r["bytes"] for r in stale)
        print(f"\n  Untouched since 2025: {len(stale):,} files, {human(size)} "
              "— attic candidates.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", type=Path, help="folders to scan")
    ap.add_argument("--out", type=Path, default=Path("inventory.csv"))
    ap.add_argument("--min-mb", type=float, default=0.1,
                    help="ignore files smaller than this (default 0.1 MB)")
    args = ap.parse_args()

    print(f"\n▌ scanning {', '.join(str(r) for r in args.roots)}")
    rows = walk(args.roots, int(args.min_mb * 1024 * 1024))
    if not rows:
        print("  nothing found above the size threshold.")
        return 0

    dupes = find_duplicates(rows)
    report(rows, dupes)

    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "name", "class", "bytes",
                                           "modified", "fingerprint"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["class"], -r["bytes"])))
    print(f"\n  written: {args.out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
