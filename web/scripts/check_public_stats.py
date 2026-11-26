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

Daarom drie regels, en ze zijn opzettelijk hard:

  1. `sample: true`  =>  elk headline-getal null, `markets` en `equity` leeg.
     Een placeholder mag geen cijfer dragen. Punt.
  2. `status` per markt mag geen oordeel over de edge zijn. Het veld noemt het
     type rekening (funded / evaluatie) en niets anders.
  3. `sample: false` =>  de twee canonieke poorten uit `mex_units.roles` lopen
     over de hele payload. Dat is de regel die bij een ECHTE publicatie bijt,
     waar regel 1 en 2 alleen de placeholder dekken (D-129, restregel uit D-131).

Regel 3 in Ferry's woorden (07-10): *"ik wil ze niet zien al gerealiseerde winst
alleen een telling in aantallen"* — **een aantal mag evals meenemen, een bedrag
nooit.** Die twee helften zijn precies de twee bestaande poorten, dus er hoefde
niets om; er moest er een bij:

  - `assert_no_currency`     — bewaakt BEDRAGEN. Dit is de helft van Ferry's
    regel die hier moest landen. `headline.trades = 717` mag dus blijven staan,
    ook met 19 eval-trades erin: een aantal is geen bedrag.
  - `assert_no_eval_metrics` — bewaakt de SCHEIDING. Eval-tellers per status
    (`passed`, `breached`, `50k_eq`) horen in `for_public_evals()`, niet
    vermengd in de gewone payload. Ferry staat aantallen toe via dat aparte
    slot, niet ernaast.

Ze worden GEIMPORTEERD uit `middleware/app/mex_units/roles.py` en niet
nagebouwd. Dat is de canonieke module (D-132) en daarmee de enige plek waar de
verboden sleutels staan; een tweede rijtje hier zou precies de drift zijn die
D-132 opruimt.

Draait in `make check`. Geen externe afhankelijkheden.
"""
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

try:
    from middleware.app.mex_units.roles import (  # noqa: E402
        assert_no_currency,
        assert_no_eval_metrics,
    )
except ImportError as exc:  # pragma: no cover
    print(
        f"kan de canonieke poorten niet importeren uit "
        f"middleware/app/mex_units/roles.py: {exc}\n"
        f"Die module is de single source voor de verboden sleutels (D-132); "
        f"dit script houdt bewust geen eigen kopie.",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

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

    # Regel 3 — bij een echte publicatie lopen de canonieke poorten over alles.
    # Bij een placeholder heeft dit geen zin: die is per regel 1 al leeg.
    if data.get("sample") is not True:
        for gate, wat in (
            (assert_no_currency, "bedrag"),
            (assert_no_eval_metrics, "vermengde eval-metriek"),
        ):
            try:
                gate(data)
            except ValueError as exc:
                problems.append(f"{wat} in een gepubliceerde payload: {exc} (regel 3)")

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

    if data.get("sample") is True:
        print("public-stats.json in orde (placeholder, leeg — regels 1 en 2).")
    else:
        print("public-stats.json in orde (publicatie — regels 2 en 3, poorten gepasseerd).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
