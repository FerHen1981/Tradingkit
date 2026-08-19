#!/usr/bin/env python3
"""Kopieer de merkfonts naar elke plek die ze zelf moet serveren.

De fonts staan één keer in packages/brand/src/fonts. Ze kunnen daar niet blijven
staan: Vite laat relatieve url()'s in CSS uit een workspace-pakket ongemoeid en
kopieert de bestanden niet mee, waardoor ze op de gebouwde site 404 geven. Ze
horen dus in public/ van elke site, waar ze ongewijzigd worden overgenomen.

    python3 web/scripts/sync_fonts.py          # kopieer
    python3 web/scripts/sync_fonts.py --check   # faal als iets ontbreekt of afwijkt

Draait in `make build` en in `make check`.
"""
from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/brand/src/fonts"
TARGETS = [
    ROOT / "sites/mex/public/fonts",
    ROOT / "sites/ppt/public/fonts",
]


def main() -> int:
    check = "--check" in sys.argv
    fonts = sorted(SOURCE.glob("*.woff2"))
    if not fonts:
        print(f"geen fonts gevonden in {SOURCE}", file=sys.stderr)
        return 1

    problems: list[str] = []
    copied = 0

    for target in TARGETS:
        if not check:
            target.mkdir(parents=True, exist_ok=True)
        for font in fonts:
            dest = target / font.name
            same = dest.exists() and filecmp.cmp(font, dest, shallow=False)
            if same:
                continue
            if check:
                problems.append(
                    f"{dest.relative_to(ROOT)}: "
                    + ("ontbreekt" if not dest.exists() else "wijkt af van de bron")
                )
            else:
                shutil.copy2(font, dest)
                copied += 1

        # Een achtergebleven font uit een vorige versie wordt wél geserveerd en
        # is daarmee net zo verwarrend als een ontbrekend bestand.
        if target.exists():
            names = {f.name for f in fonts}
            for stale in target.glob("*.woff2"):
                if stale.name in names:
                    continue
                if check:
                    problems.append(f"{stale.relative_to(ROOT)}: staat niet meer in de bron")
                else:
                    stale.unlink()

    if problems:
        print(f"{len(problems)} verschil(len) tussen bron en doelmappen:", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        print("\nDraai: python3 web/scripts/sync_fonts.py", file=sys.stderr)
        return 1

    if check:
        print(f"{len(fonts)} font(s) gelijk in {len(TARGETS)} doelmappen.")
    else:
        print(f"{len(fonts)} font(s) → {len(TARGETS)} doelmappen ({copied} bijgewerkt).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
