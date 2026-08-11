# Stages 3-7 — uitslagen · Patrón · Matador · Dorado × 5 fleet-slots

**Rapport:** https://claude.ai/code/artifact/5901bfd1-3ce5-4bef-9268-73cb4706963d
**Pre-registratie:** `NQFAMILY_stage1-2_preregistration_20260811.md` (gates ongewijzigd)
**Data:** `NQFAMILY_results_20260811.json` + `NQFAMILY_results_cvdfix_20260811.json`

## Eindstand: 0 van de 15 combinaties door de gates

| | NQ ⛔ | MNQ ⛔ | ES | GC | YM ✅vers |
|---|---|---|---|---|---|
| **Patrón** | S4 FAIL (PF 1,14) | S4 FAIL (0,97) | onbeslist | **S4 FAIL (1,04)** | S4 FAIL (0,89) |
| **Dorado** | S4 FAIL (1,10) | S4 FAIL (0,95) | onbeslist | S4 FAIL (0,92) | S4 FAIL (0,88) |
| **Matador** | S4 FAIL (0,99) | S4 FAIL (0,85) | S4 FAIL (0,90) | S4 FAIL (0,93) | S4 FAIL (0,90) |

⛔ = OOS verbruikt op 10-08, telt niet voor een gate.

## S3 — engine-validatie: PASS waar de data compleet is

Kosten aan (commissie per contract + 1 tick), ≥100 IS-trades gehaald op elke reeks met
bruikbare data. Matador: 5.710 (NQ) · 1.620 (ES) · 3.298 (GC) · 4.385 (YM).
Patrón/Dorado: 1.219/1.214 (NQ) · 675/672 (GC) · 938/930 (YM).

**ES voor Patrón en Dorado: ONBESLIST.** Zie de datakwestie hieronder.

## S4 — bulk-backtest: FAIL op alle vijftien

Gate: PF recente 12 maanden ≥ 1,20 ná kosten. **Hoogste meting in de hele matrix: 1,04**
(Patrón op GC). Alle andere liggen tussen 0,85 en 1,14.

Het jaarverloop wijst dezelfde kant op — en dat is het echte signaal:

| | Y1 | Y2 | Y3 |
|---|---|---|---|
| Patrón GC | 1,15 | 1,05 | 1,04 |
| Patrón YM | 1,13 | 0,72 | 0,90 |
| Dorado GC | 1,09 | 0,99 | 0,93 |
| Dorado YM | 1,14 | 0,72 | 0,88 |
| Matador GC | 1,02 | 0,90 | 0,93 |
| Matador YM | 0,97 | 0,84 | 0,90 |

In jaar 1 staat de winstfactor overal boven of rond de 1, daarna zakt hij weg. Dat is het
**spiegelbeeld** van het patroon dat de skill voor intraday NQ beschrijft (edge geconcentreerd
in de recente 12 maanden). Hier dooft de edge uit in plaats van aan te trekken. Een uitrol naar
nieuwe assets zou dus niet alleen op de gate stuklopen, maar ook op de richting.

**Formeel stopt de pipeline hier.** Alles hieronder is diagnostisch en geeft geen gate-krediet.

## De datakwestie die eerst opgelost moest worden

De eerste run gaf **nul trades** voor Patrón en Dorado op ES, GC en YM. Dat leek een
vernietigende uitslag. Oorzaak bleek de data: de kolom `Delta` in `ES_norm.csv`, `GC_norm.csv`
en `YM_norm.csv` is **identiek nul**. Beide scripts draaien met CVD-filter aan én een
streak-eis van 4 — met delta ≡ 0 kan die voorwaarde nooit waar worden.

Twee onafhankelijke bevestigingen uit de perturbatietest:
- Patrón/Dorado met CVD **uit** handelen wél op YM (bpb 290 en 181).
- Matador (filter uit) viel juist terug naar **0** zodra het filter áán ging.

`GC_cvd.csv` en `YM_cvd.csv` bevatten wel echte delta; die zes cellen zijn opnieuw gedraaid en
die cijfers staan in de matrix. **Voor ES bestaat geen delta-bestand** — die twee cellen blijven
onbeslist. Niet gezakt: onbeslist.

Dit is precies waarom nul-resultaten altijd eerst technisch verklaard moeten worden. Zonder die
controle stond er nu "Patrón faalt op drie assets" in het rapport, en dat was onwaar geweest.

## S5 — robuustheid (diagnostisch, op YM in-sample)

| | basis | gap −20% | gap +20% | stop −20% | stop +20% | CVD omgekeerd |
|---|---|---|---|---|---|---|
| Matador | 21,6 | 16,8 (−22%) | **4,8 (−78%)** | 13,6 (−37%) | 19,2 (−11%) | 0,0 (−100%)* |

\* artefact van de nul-delta-reeks, zie hierboven.

Matador verliest **78%** bij een 20% bredere FVG-band. Dat is geen plateau maar een scherpe
piek — het profiel van een parameter die op de data gekozen is. Ook de −37% bij een strakkere
stop valt buiten de 30%-marge uit de gate.

## S7 — stress (diagnostisch: 2-tick slippage + dubbele commissie)

| | doel OOS | onder stress | Δ |
|---|---|---|---|
| Matador GC | 27,3 | 22,7 | −17% |
| Matador NQ ⛔ | 54,5 | 22,7 | −58% |
| Matador YM | 18,2 | 4,5 | **−75%** |
| Dorado GC | 500 | 300 | −40% |
| Patrón GC | 500 | 0 | **−100%** |

Alleen Matador op GC houdt binnen de 50%-marge stand. Dat is één cel van de vijftien, en die
was al op S4 gestopt.

## Conclusie

De hypothese uit de pre-registratie — *de edge is niet NQ-specifiek en draagt ongewijzigd over* —
is **niet bevestigd**. Sterker: hij faalt ook op YM, de reeks die nooit voor enige parameterkeuze
is gebruikt en die dus het zwaarst weegt.

Mijn vooraf uitgesproken verwachting (Patrón en Dorado zakken opnieuw, Matador heeft de beste
papieren) klopte maar half: Matador is niet beter, hij zakt alleen ergens anders. **Patrón op GC
is met PF 1,04 de sterkste cel van de matrix** — niet Matador.

### Wat ik hiermee zou doen

1. **Niet uitrollen naar nieuwe assets.** Getest en niet bevestigd, ook op verse data.
2. **De S4-gate expliciet ter discussie stellen.** Deze scripts zijn gebouwd om via de
   Apex-trechter te renderen, niet om op contractniveau PF 1,2 te halen. Óf de gate past niet bij
   deze scriptklasse, óf de scripts halen de lat niet. Dat is een keuze die vastgelegd moet
   worden — anders schuift de lat elke run een beetje op, en dan is de pipeline waardeloos.
3. **ES-delta aanschaffen** als je die twee cellen wilt beslissen.
4. **Matrixstatus "geparkeerd/sim-only" voor Dorado en Patrón blijft staan.** Deze run geeft geen
   enkele reden om die te herzien.

### Wat deze run níét zegt

- NQ/MNQ tellen niet mee (OOS verbruikt op 10-08).
- ES is voor Patrón/Dorado onbeslist, niet gezakt.
- Parameters zijn bewust **niet** per asset hertuned — dat was de hypothese. Hertunen is een
  andere, zwakkere claim en vraagt een verse OOS.
- Matadors CVD-stand is een aanname (geen CONFIG in het logvenster).
- QQQ en BTC: geen 1m-dataset in de repo.
- S8-S10 zijn niet bereikt en dus niet beoordeeld.
