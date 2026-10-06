#!/usr/bin/env python3
"""Faalt wanneer de publieke momentopname iets beweert wat niet onderbouwd is.

Waarom dit bestaat (D-129). De vorige placeholder droeg echte cijfers: GC en ES
met status `Funded`, NQ met `Evaluatie`, en een tegel "Live 36 mnd" over
2023-2026. Alle drie waren op het moment van schrijven waar. Daarna trok Ferry de
regel "funded edge = alleen GC + ES" in (24-08), ging de vloot naar micros, en
werd 2023-2026 heretiketteerd als validatie (D-18/optie B). De cijfers bleven
staan. Een `sample`-vlag met een banner eroverheen heeft dat niet voorkomen —
een voorbeeldgetal op een resultatenpagina is na een week niet meer van een
resultaat te onderscheiden.

Daarom twee regels, en ze zijn opzettelijk hard:

  1. `sample: true`  =>  elk headline-getal null, `markets` en `equity` leeg.
     Een placeholder mag geen cijfer dragen. Punt.
  2. `status` per markt mag geen oordeel over de edge zijn. Het veld noemt het
     type rekening (funded / evaluatie) en niets anders.

Draait in `make check`. Geen afhankelijkheden.
"""
import json
import pathlib
import sys

SNAPSHOT = pathlib.Path(__file__).resolve().parents[1] / "sites/mex/src/data/public-stats.json"

# Woorden die een oordeel over de edge dragen in plaats van een rekeningtype.
# "gevalideerd" en "bewezen" zijn de twee die er in D-34 al uit moesten; "oos" en
# "out-of-sample" mogen er nooit in komen zolang de klok op nul staat.
VERDICT_WORDS = (
    "gevalideerd", "validated", "bewezen", "proven", "edge",
    "out-of-sample", "oos", "winstgevend", "profitable",
)

ALLOWED_STATUS = {"funded", "evaluatie", "eval", "instant", "gearchiveerd", ""}


def main() -> int:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    problems: list[str] = []

    if data.get("sample") is True:
        for key, value in (data.get("headline") or {}).items():
            if value is not None:
                problems.append(
                    f"sample=true maar headline.{key} = {value!r} — een placeholder "
                    f"mag geen cijfer dragen (regel 1)"
                )
        for name in ("markets", "equity"):
            rows = data.get(name) or []
            if rows:
                problems.append(
                    f"sample=true maar {name} bevat {len(rows)} regel(s) — leeg of "
                    f"geen placeholder (regel 1)"
                )

    for market in data.get("markets") or []:
        status = str(market.get("status") or "")
        low = status.lower()
        if any(w in low for w in VERDICT_WORDS):
            problems.append(
                f"markets[{market.get('symbol')}].status = {status!r} — dat is een "
                f"oordeel over de edge, geen rekeningtype (regel 2)"
            )
        elif low not in ALLOWED_STATUS:
            problems.append(
                f"markets[{market.get('symbol')}].status = {status!r} — onbekend "
                f"rekeningtype; toegestaan: {sorted(ALLOWED_STATUS - {''})}"
            )

    if problems:
        print("public-stats.json — FOUT:", file=sys.stderr)
        for p in problems:
            print(f"  · {p}", file=sys.stderr)
        print(
            "\nZie de kop van scripts/check_public_stats.py voor het waarom (D-129).",
            file=sys.stderr,
        )
        return 1

    flag = "placeholder, leeg" if data.get("sample") else "publicatie"
    print(f"public-stats.json in orde ({flag}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
