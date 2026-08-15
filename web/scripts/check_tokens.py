#!/usr/bin/env python3
"""Fail if the portal's copy of the brand tokens has drifted from the source.

The sites import `packages/brand/src/styles/tokens.css`; the portal ships its
own copy because it deploys separately and cannot depend on the npm workspace.
Two copies of a palette drift silently, so this compares the tokens that appear
in both and reports any that disagree.

    python3 web/scripts/check_tokens.py

Exits non-zero on drift, so it can sit in CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/brand/src/styles/tokens.css"
COPY = ROOT / "portal/app/static/portal.css"

TOKEN_RE = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);", re.MULTILINE)


def first_definitions(path: Path) -> dict[str, str]:
    """Tokens as defined in the first (default) :root block only.

    Later blocks are the light/dark overrides; comparing those would compare
    themes rather than the palette.
    """
    text = path.read_text(encoding="utf-8")
    start = text.index(":root")
    end = text.index("}", start)
    return {
        name: " ".join(value.split())
        for name, value in TOKEN_RE.findall(text[start:end])
    }


def main() -> int:
    if not SOURCE.exists() or not COPY.exists():
        print(f"missing file: {SOURCE if not SOURCE.exists() else COPY}", file=sys.stderr)
        return 1

    source = first_definitions(SOURCE)
    copy = first_definitions(COPY)

    shared = sorted(set(source) & set(copy))
    drift = [(name, source[name], copy[name]) for name in shared if source[name] != copy[name]]

    if drift:
        print("Brand token drift between the sites and the portal:\n")
        for name, want, got in drift:
            print(f"  {name}")
            print(f"    tokens.css : {want}")
            print(f"    portal.css : {got}")
        print(f"\n{len(drift)} token(s) disagree. Update portal.css to match.")
        return 1

    print(f"{len(shared)} shared token(s) in step between tokens.css and portal.css.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
