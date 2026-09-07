#!/usr/bin/env python3
"""Integriteitscontrole op de begrippenlijst.

De lijst leunt op twee soorten verwijzingen die stilletjes kunnen breken: een
`sources`-id dat niet in sources.json staat, en een `related`-slug die naar een
begrip wijst dat niet (meer) bestaat. Beide leveren geen bouwfout op — de pagina
rendert gewoon zonder die bron of dat verband — en dat is precies waarom ze hier
worden afgevangen.

Daarnaast geldt één redactionele afspraak: een begrip met `authority: true`
moet ook daadwerkelijk een bron hebben, anders suggereert de badge op de pagina
een gezag dat er niet is.

Wederkerigheid van verwijzingen wordt bewust NIET gecontroleerd. De termpagina
toont naast de eigen `related` ook de begrippen die naar dít begrip verwijzen,
dus een eenzijdige verwijzing is aan beide kanten zichtbaar. Daarop
waarschuwen zou tientallen meldingen opleveren voor een probleem dat niet
bestaat — en waarschuwingen die altijd afgaan, leest niemand meer.

    python3 web/scripts/check_glossary.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "sites/ppt/src/content/glossary"
SOURCES = ROOT / "sites/ppt/src/data/sources.json"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.S)


def parse_list(block: str, key: str) -> list[str]:
    """Pull a simple YAML list out of the frontmatter.

    Deliberately not a YAML parser: the frontmatter here is generated and has a
    fixed shape, and a dependency-free check is one that actually gets run.
    """
    match = re.search(rf"^{key}:\s*(\[\]|)\s*$", block, re.M)
    if not match:
        return []
    if match.group(1) == "[]":
        return []
    start = block.index(match.group(0)) + len(match.group(0))
    items: list[str] = []
    for line in block[start:].splitlines():
        if line.startswith("  - "):
            items.append(line[4:].strip())
        elif line.strip() and not line.startswith(" "):
            break
    return items


def parse_scalar(block: str, key: str) -> str:
    match = re.search(rf"^{key}:\s*(.+)$", block, re.M)
    return match.group(1).strip().strip('"') if match else ""


def main() -> int:
    if not GLOSSARY.exists():
        print(f"geen begrippenlijst gevonden op {GLOSSARY}", file=sys.stderr)
        return 1

    sources = set(json.loads(SOURCES.read_text(encoding="utf-8"))["sources"])
    entries: dict[str, dict] = {}

    for path in sorted(GLOSSARY.glob("*.mdx")):
        match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
        if not match:
            print(f"  {path.name}: geen frontmatter", file=sys.stderr)
            return 1
        block = match.group(1)
        entries[path.stem] = {
            "term": parse_scalar(block, "term"),
            "category": parse_scalar(block, "category"),
            "authority": parse_scalar(block, "authority") == "true",
            "sources": parse_list(block, "sources"),
            "related": parse_list(block, "related"),
        }

    errors: list[str] = []
    warnings: list[str] = []

    for slug, entry in entries.items():
        for source_id in entry["sources"]:
            if source_id not in sources:
                errors.append(f"{slug}: onbekende bron-id '{source_id}'")

        for other in entry["related"]:
            if other not in entries:
                errors.append(f"{slug}: verwijst naar onbekend begrip '{other}'")

        if entry["authority"] and not entry["sources"]:
            errors.append(f"{slug}: authority=true maar geen bron opgegeven")

        if not entry["term"]:
            errors.append(f"{slug}: geen term")

    used = {s for e in entries.values() for s in e["sources"]}
    for unused in sorted(sources - used):
        warnings.append(f"bron '{unused}' wordt door geen enkel begrip gebruikt")

    by_category: dict[str, int] = {}
    for entry in entries.values():
        by_category[entry["category"]] = by_category.get(entry["category"], 0) + 1

    print(f"{len(entries)} begrippen, {len(sources)} bronnen")
    for category, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        print(f"  {category:<12} {count}")
    authority = sum(1 for e in entries.values() if e["authority"])
    print(f"  {'met bron':<12} {authority}")

    if warnings:
        print(f"\n{len(warnings)} waarschuwing(en):")
        for warning in warnings:
            print(f"  · {warning}")

    if errors:
        print(f"\n{len(errors)} FOUT(en):", file=sys.stderr)
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        return 1

    print("\nAlle bronnen en verwijzingen kloppen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
