#!/usr/bin/env python3
"""D-154 — poort op de vier dagstops in de dertien v1_0_0-scripts.

Drie dingen, en de eerste is de belangrijkste:

1. ALLE VIJF INPUTS STAAN OP 0. Dat is de hele voorwaarde waaronder deze release mag:
   zolang ze uit staan is het gedrag ongewijzigd. Eén script met een andere default zou
   dat stilletjes breken, en een default is precies het soort ding dat bij een
   regeneratie of een merge verschuift (D-68, D-75, D-108, D-111, D-115, D-124).

2. DE SEMANTIEK STAAT LETTERLIJK IN DE BRON. Niet "er staat iets dat erop lijkt": de
   regels die de betekenis dragen worden exact vergeleken. `_net <= 0` (exact 0 telt als
   verlies), `_before >= lossAfterPlusUSD` (de dag-P&L VOOR de trade), de uurpositie
   binnen de handelsdag in plaats van op de kalenderklok, en het feit dat de drie vlaggen
   `dayHalted` voeden in plaats van een eigen sluitpad te hebben.

3. EEN REFERENTIEMODEL op dezelfde regels, met de gevallen die fout kunnen gaan.
   Dat is geen bewijs dat Pine hetzelfde doet -- het is de controle dat de regel die in
   de bron staat ook de regel is die we bedoelden.

Exit 0 = alles klopt. Exit 1 = een script wijkt af, met de naam erbij.
"""
from __future__ import annotations
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PINE = sorted((ROOT / "pine").glob("MEX_EL_*_v1_0_0.pine"))

# De defaults die deze release veilig maken. Naam -> verwachte default als tekst.
DEFAULTS = {
    "maxLossStreak": "0",
    "maxWinStreak": "0",
    "lossAfterPlusUSD": "0",
    "dayTrailGiveback2USD": "0",
    "dayTrail2FromHour": "0",
}

# Regels die de betekenis dragen. Wijkt er één af, dan is de semantiek veranderd zonder
# dat iemand het aan de inputnamen kan zien.
REQUIRED = [
    ("for _i = dexClosedSeen to strategy.closedtrades - 1",
     "de lus over nieuwe gesloten trades (er kan meer dan één per bar sluiten)"),
    ("float _net    = strategy.closedtrades.profit(_i) - strategy.closedtrades.commission(_i)",
     "netto incl. commissie, zoals de day-trail rekent"),
    ("        if _net <= 0",
     "exact 0 telt als VERLIES"),
    ("            if lossAfterPlusUSD > 0 and _before >= lossAfterPlusUSD",
     "de +X-regel meet de dag-P&L VOOR de trade"),
    ("        if maxLossStreak > 0 and dexLossStreak >= maxLossStreak",
     "0 = uit, en de k-de verliezer sluit"),
    ("        if maxWinStreak > 0 and dexWinStreak >= maxWinStreak",
     "0 = uit, en de k-de winnaar sluit"),
    ("int  _dexHourPos    = (hour(time, activeTz) - rgRollHour + 24) % 24",
     "het uur wordt BINNEN de handelsdag gemeten, niet op de kalenderklok"),
    ("    dexClosedSeen := strategy.closedtrades",
     "de leespositie in de tradehistorie loopt door"),
    ("or dexStreakLossHit or dexStreakWinHit or dexLossAfterPlus)",
     "de drie vlaggen voeden dayHalted en hebben geen eigen sluitpad"),
    ('dexStreakLossHit ? "STREAK-LOSS" : dexStreakWinHit ? "STREAK-WIN" : dexLossAfterPlus ? "LOSS-AFTER-PLUS"',
     "de redenen zoals afgesproken"),
    ('dayTrailHit ? (dexTrail2Active ? "DAY-TRAIL-2" : "Day-trail")',
     "DAY-TRAIL-2 alleen als giveback-2 werkelijk actief was"),
]

# Wat op de dagroll leeg moet. `dexClosedSeen` staat er bewust NIET bij.
RESETS = ["dexLossStreak    := 0", "dexWinStreak     := 0", "dexDayRealized   := 0.0",
          "dexStreakLossHit := false", "dexStreakWinHit  := false", "dexLossAfterPlus := false"]


def model(nets, max_loss, max_win, plus_x):
    """Dezelfde regels als de bron, als los model."""
    stk_l = stk_w = 0
    day = 0.0
    hit_l = hit_w = hit_p = False
    for net in nets:
        before = day
        day += net
        if net <= 0:
            stk_l += 1
            stk_w = 0
            if plus_x > 0 and before >= plus_x:
                hit_p = True
        else:
            stk_w += 1
            stk_l = 0
        if max_loss > 0 and stk_l >= max_loss:
            hit_l = True
        if max_win > 0 and stk_w >= max_win:
            hit_w = True
    return hit_l, hit_w, hit_p


CASES = [
    ("vijf verliezen op rij, max 5", [-100] * 5, 5, 0, 0, (True, False, False)),
    ("vier verliezen, max 5", [-100] * 4, 5, 0, 0, (False, False, False)),
    ("een winnaar breekt de reeks", [-100, -100, 50, -100, -100, -100], 5, 0, 0, (False, False, False)),
    ("exact 0 telt als verlies", [-100, -100, -100, -100, 0], 5, 0, 0, (True, False, False)),
    ("drie winsten op rij, max 3", [50, 50, 50], 0, 3, 0, (False, True, False)),
    ("+150 en dan een verlies", [100, 100, -50], 0, 0, 150, (False, False, True)),
    ("+150 pas NA het verlies gehaald", [100, -50, 100], 0, 0, 150, (False, False, False)),
    ("alles uit -> nooit een halt", [-100] * 9, 0, 0, 0, (False, False, False)),
]


def main() -> int:
    bad = []
    for path in PINE:
        src = path.read_text(encoding="utf-8")
        name = path.name.replace("_v1_0_0.pine", "")
        for var, want in DEFAULTS.items():
            m = re.search(rf"^{var}\s*= input\.(?:int|float)\(\s*([^,]+),", src, re.M)
            if m is None:
                bad.append(f"{name}: input {var} ontbreekt")
            elif m.group(1).strip() != want:
                bad.append(f"{name}: {var} heeft default {m.group(1).strip()}, moet {want} zijn "
                           f"-- met een andere default is het gedrag NIET ongewijzigd")
        for needle, why in REQUIRED:
            if needle not in src:
                bad.append(f"{name}: {why} -- regel niet gevonden")
        for r in RESETS:
            if r not in src:
                bad.append(f"{name}: dagreset mist `{r}`")
        if "dexClosedSeen   := 0" in src or "dexClosedSeen := 0\n" in src.split("if isNewTradingDay")[-1][:800]:
            bad.append(f"{name}: dexClosedSeen wordt op de dagroll gereset -- dan worden de "
                       f"trades van gisteren opnieuw geteld")

    print(f"{len(PINE)} scripts · vijf inputs op 0 · {len(REQUIRED)} semantiekregels · "
          f"{len(RESETS)} resetregels")
    print()
    print("Referentiemodel op dezelfde regels:")
    for label, nets, m_l, m_w, p_x, exp in CASES:
        got = model(nets, m_l, m_w, p_x)
        ok = got == exp
        if not ok:
            bad.append(f"model: {label} gaf {got}, verwacht {exp}")
        print(f"  {'OK  ' if ok else 'FOUT'} {label}")
    print()
    if bad:
        for b in bad:
            print("FOUT:", b)
        return 1
    print("Alles klopt. Alle vier de dagstops staan in dertien scripts UIT, dus het gedrag")
    print("is ongewijzigd tot iemand ze aanzet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
