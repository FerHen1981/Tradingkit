#!/usr/bin/env python3
"""v3.12.0 §2A — poort op de payout-poort en de accountstart.

Vier eigenschappen, en elk ervan is een keer fout gegaan:

1. DE PAYOUT-POORT HOUDT GEEN ENTRY MEER TEGEN. Geen enkel script mag `pmtBlock` nog
   zetten vanuit de payout-tak. Dit is de vierde ronde op deze klasse (D-123, D-125,
   D-146) en de drie eerdere maakten de voorwaarde strakker in plaats van hem weg te
   halen -- dus wordt hier op de AFWEZIGHEID getoetst, niet op de vorm.

2. DE ACCOUNTLAAG MEET VANAF DE ACCOUNTSTART. Nergens mag de accountlaag nog
   `acctPnlOffset + strategy.netprofit` lezen; dat is de fantoombalans die een account
   van 19 oktober tien maanden winst liet tellen. De dag- en risk-gate-lagen mogen de
   ruwe `strategy.netprofit` wel gebruiken -- dat zijn deltas binnen een dag of sessie.

3. EEN NIET-INGEVULDE ACCOUNTSTART HANDELT NIET. Alleen de balans op nul zetten zou ook
   de trailing-drawdown-breach uitzetten (floor -$2.000 tegen stand 0), en dan ruil je een
   fantoombalans voor een account zonder breach-halt. `canTrade` moet `acctStartMissing`
   dus eisen, en er moet een zichtbaar label zijn.

4. DE DEFAULT LIGT IN DE TOEKOMST, en fase `Developer` telt tóch vanaf de eerste bar --
   anders komt elke backtest stil op nul te staan.

Exit 0 = alles klopt. Exit 1 = een script wijkt af, met de naam erbij.
"""
from __future__ import annotations
import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PINE = sorted((ROOT / "pine").glob("MEX_EL_*_v1_0_0.pine"))

FORBIDDEN = [
    ("pmtBlock := isPA", "de payout-tak zet pmtBlock weer -- een payout mag geen entry tegenhouden"),
    ("acctPnlOffset + strategy.netprofit",
     "de accountlaag leest de ruwe strategy.netprofit weer -- dat is de fantoombalans terug"),
]

REQUIRED = [
    ("var float acctStartNet = na",
     "de accountstart-meter ontbreekt"),
    ("float acctNetSinceStart = acctStarted ? strategy.netprofit - acctStartNet : 0.0",
     "acctNetSinceStart ontbreekt of rekent anders"),
    ('if na(acctStartNet) and (time >= acctStart or (accountPhase == "Developer" and barstate.isfirst))',
     "fase Developer telt niet meer vanaf de eerste bar -- dan komt elke backtest op nul"),
    ("bool acctStartMissing = phaseOn and not acctStarted",
     "acctStartMissing ontbreekt"),
    ("and not acctStartMissing",
     "canTrade eist acctStartMissing niet -- een chart zonder accountstart zou blijven handelen"),
    ("var label acctStartWarnLbl = na",
     "het zichtbare label bij een niet-ingevulde accountstart ontbreekt"),
    ("SCRIPT-BALANS, NIET APEX",
     "de PAYOUT-kaart zegt niet dat het de script-balans is en niet die van Apex"),
]

# De accountlaag moet door acctNetSinceStart gaan. Dit zijn de vier plekken.
ACCOUNT_LAYER = [
    "float acctPnL      = acctPnlOffset + acctNetSinceStart - paResetPnLPrev + strategy.openprofit",
    "float acctRealized = acctPnlOffset + acctNetSinceStart - paResetPnLPrev",
    "    maeSodProfit := acctPnlOffset + acctNetSinceStart",
    "acctPnlOffset + acctNetSinceStart - paResetPnLPrev)",
]


def main() -> int:
    bad = []
    today = dt.date.today()
    for path in PINE:
        src = path.read_text(encoding="utf-8")
        name = path.name.replace("_v1_0_0.pine", "")
        # Commentaar eerst eruit: een uitleg die de oude regel citeert is geen code.
        code = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith("//"))

        for needle, why in FORBIDDEN:
            if needle in code:
                bad.append(f"{name}: {why}")
        for needle, why in REQUIRED:
            if needle not in code:
                bad.append(f"{name}: {why}")
        for needle in ACCOUNT_LAYER:
            if needle not in code:
                bad.append(f"{name}: accountlaag-regel ontbreekt of wijkt af: {needle[:52]}")

        m = re.search(r"^acctStart = input\.time\(timestamp\(\"[^\"]+\", (\d{4}), (\d+), (\d+),", code, re.M)
        if m is None:
            bad.append(f"{name}: acctStart is geen input.time met een expliciete datum")
        else:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d <= today:
                bad.append(f"{name}: acctStart-default {d} ligt NIET in de toekomst -- een "
                           f"niet-ingevulde chart zou weer een balans verzinnen")

    print(f"{len(PINE)} scripts · {len(FORBIDDEN)} verboden vormen · {len(REQUIRED)} vereiste "
          f"regels · {len(ACCOUNT_LAYER)} accountlaag-regels · default in de toekomst")
    if bad:
        print()
        for b in bad:
            print("FOUT:", b)
        return 1
    print()
    print("De payout-poort houdt in geen enkel script nog een entry tegen, de accountlaag")
    print("meet vanaf de accountstart, en een chart zonder accountstart handelt niet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
