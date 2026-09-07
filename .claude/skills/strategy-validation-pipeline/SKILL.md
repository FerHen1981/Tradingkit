---
name: strategy-validation-pipeline
description: Twaalf-traps gated onderzoekspijplijn voor het valideren van futures-strategieën, van ruwe 1-minuutdata tot een Pine/TradingView-gevalideerde PA-strategie, afgestemd op de MEX Traders-stack (MGC/MNQ/MES/MYM micros, Apex 50K EOD én Intraday PA, Pine v6 + Python/.NET harness). Gebruik deze skill wanneer de gebruiker een strategie wil valideren, backtesten, stress-testen of promoveren; vraagt of een idee "de moeite waard" is; pariteit, walk-forward, Monte Carlo, out-of-sample of overfitting noemt; een nieuwe markt door de trechter wil halen; of wil beslissen of een script live mag op funded kapitaal. Trigger ook wanneer één stage bij naam gedraaid wordt ("doe een stress test op EL REY") of wanneer een TradingView-export beoordeeld moet worden.
---

# Strategy Validation Pipeline (v7)

Een **gated** pijplijn. Een strategie gaat pas naar trap N+1 als de poort van trap N
aantoonbaar gehaald is. Een poort niet halen is een geldige, bruikbare uitkomst:
leg hem vast en stop. Versoepel nooit een poort halverwege om iets erdoor te krijgen.

De volledige, gezaghebbende methodologie staat in
`references/pipeline-v7-authoritative.md` — dat document is van Ferry en is de bron.
Dit bestand is de werkinstructie eromheen. **Bij twijfel wint het referentiedocument.**

## Het doel is niet winst

Optimaliseer **niet** op netto winst of nominale trefkans. Het primaire doel is:

> **Maximaliseer gebankte payout-dollars per bezette PA-account-dag** (time-for-money)

onder voorwaarde van: positieve intrinsieke edge ná kosten · realistische Pine-pariteit ·
prop-firm DD/DLL/payout-regels · aanvaardbare breach/churn · robuustheid over tijd en
regimes · minimale overfitting.

Account-mechanica kan de rangorde van twee verder identieke trade-engines omdraaien.
Een hogere PF is dus geen bewijs van een betere strategie.

## Niet-onderhandelbare grondregels

1. **Pariteit vóór optimalisatie.** Reproduceer de Pine-semantiek in Python/.NET en
   vergelijk op één vaste baseline vóór er één parameter gezocht wordt.
   Parameteroptimalisatie is **ongeldig** zolang baseline-pariteit onopgelost is.
2. **Geen same-bar fill leakage.** Bij een limit/stop-fill binnen een bar mag de High/Low
   van diezelfde bar niet worden hergebruikt alsof alles ná de fill gebeurde. Zonder
   lower-timeframe/tick-replay geldt: pessimistisch, geen exit op de fill-bar.
3. **18:00 ET is de handelsdaggrens**, niet middernacht. DLL-reset, kwalificerende dagen,
   consistency, dagcaps en payout-lifecycle groeperen op die grens. Kalenderdatum is
   ongeldig voor PA-lifecycle-analyse.
4. **Canonieke CVD = deterministische OHLCV-polariteitsproxy.** Niet de native
   Delta-kolom, niet `ta.requestVolumeDelta()`. Die twee zijn losse experimenten en
   mogen de proxy nooit stilzwijgend vervangen. Drempel per markt opnieuw optimaliseren.
5. **Kosten altijd aan.** Commissie-semantiek expliciet (per zijde vs round-turn).
   Micro-baseline $0,51 per contract per zijde tenzij bewust anders. Slippage 1 tick
   basis, 2–3 ticks in stress.
6. **Geen willekeurige uur-van-de-dag of dag-van-de-week filters.** Regimes mogen alleen
   als ze economisch vooraf gedefinieerd zijn (Asia, London, pre-cash, cash open, OR,
   post-OR, lunch, power hour, settlement, rollover). Uur/dag mag achteraf diagnostisch.
7. **Pre-registreer vóór je data aanraakt.** Hypothese, exacte regels, parameters,
   poortdrempels en testvenster liggen vast voordat resultaten gezien worden.
8. **One-shot out-of-sample.** Het OOS-venster is opgebrand zodra het één keer gebruikt is.
   Een aangepaste variant op datzelfde venster is in-sample; label het zo.
9. **Research-invalidatieregel.** Blijkt achteraf een materiële uitvoerings- of
   pariteitsfout (same-bar leakage, verkeerde tick/unit-semantiek, verkeerde commissie,
   verkeerde daggroepering), dan **vervallen alle rankings die eronder tot stand kwamen**.
   Ze blijven hooguit als historie. De markt herstart vanuit een neutrale zoekruimte; oude
   winnaars mogen geen prior zijn.
10. **TradingView bewaart oude inputs.** Een validatie is ongeldig tot het geëxporteerde
    Properties-tabblad is gecontroleerd tegen de bedoelde configuratie. Staat een filter
    daar OFF, dan is het de OFF-variant — leid nooit af uit de broncode-defaults.
11. **Elke trap levert een artefact**, benoemd `<strategie>_<trap>_<jjjjmmdd>`.
12. **Geen verzonnen bronnen.** Scheid verifieerbare publicaties, praktijkfolklore en
    eigen hypotheses; presenteer de derde nooit als de eerste.

## De trappen en hun poorten

| # | Trap | Poort om door te mogen |
|---|---|---|
| 0 | Data-audit | Dekking, tijdzone, OHLC-continuïteit, volume/Delta-dekking, ticksize, point value, commissie en roll-artefacten vastgesteld; genormaliseerde dataset + kwaliteitsrapport bestaan |
| 1 | **Pine-pariteitsengine** | Python/.NET vs Pine op één vaste baseline: bijna gelijk aantal trades én materieel vergelijkbare WR/PF. **Harde poort — hieronder is niets geldig** |
| 2 | Structurele edge, from scratch | Positieve intrinsieke edge ná kosten op 1 contract. Nog géén PA-sizing of dagcaps. Seed niet met het optimum van een andere markt |
| 3 | Regime-diagnostiek | Elk regime IN/OUT/ALL gerapporteerd; een regime wordt alleen filter als het effect robuust én economisch verklaarbaar is |
| 4 | Robuustheid / plateau | Breed plateau i.p.v. scherp maximum; houdt stand per jaar/kwartaal en in rollende vensters; LONG en SHORT apart gecontroleerd |
| 5 | Contractgrootte & pro-rata risico | Volledige stop in dollars ligt onder de geldende DLL vóór slippage/commissie; grootte verandert doorvoer en risico, niet de intrinsieke PF |
| 6 | Dagelijkse P&L-sturing | Dagcap/giveback/activatie beoordeeld op payout-economie, niet op cosmetische equity-gladheid |
| 7 | PA-lifecycle-modellen | Apex 50K EOD **én** Intraday gedraaid; Intraday modelleert ongerealiseerde MFE die de trailing HWM optrekt (of is expliciet als conservatief gelabeld) |
| 8 | Time-for-money | Gebankte payout-$ per bezette account-dag gerapporteerd, met payout #1-conversie, P2–P6, dagen tot P1, breach-cijfers en DLL-hits |
| 9 | Production vs Harvest | Twee kandidaten behouden; geen van beide leunt op uur/dag-cherrypicking. Production = overleving en robuustheid; Harvest = doorvoer en time-for-money |
| 10 | **TradingView-validatie** | Properties-audit gedaan; trades, timing, exit-redenen, P&L, MFE/MAE, LONG/SHORT en PF komen overeen met de simulator. **Harde deployment-poort** |
| 11 | Portefeuille-diversificatie | Dagelijkse P&L-correlatie en overlap in verlies-/breachdagen gemeten over **minstens 20–30 actieve dagen**. Claim geen decorrelatie daarvoor |

Trap 10 faalt? Onderzoek de eerste afwijkende trades — *niet* opnieuw optimaliseren.
Een simulatorresultaat is niet geldig als TradingView het materieel tegenspreekt.

## Snelle strategieën verdienen extra achterdocht

Bij korte holdtijden, krappe stops/targets, hoge frequentie of dunne edge per trade moet
de optimizer straffen: veel same-bar exits · edge die verdwijnt bij +1 tick slippage ·
edge die door transactiekosten wordt gedomineerd · payoffs die onrealistisch precieze
fills vereisen. Zulke strategieën worden pas Production/Harvest als ze winstgevend
blijven onder baseline-kosten, +1 tick tegenslippage én een conservatief intrabar-model.

## De vloot en de bevroren engines

Merknamen zijn vaste strategie-persoonlijkheden; markt en profiel zitten in de titel.
Shorttitle ≤ 10 tekens. **EL TORO is voorbehouden aan evaluatie-accounts.**

De bevroren, gevalideerde parameters staan in `references/frozen-engines.md`.
Optimaliseer een bevroren engine **niet** stilzwijgend — een wijziging daar is een
nieuwe onderzoeksronde vanaf trap 1, geen tweak.

## Een trap draaien

1. Noem welke trap draait en herhaal de poort vóór er werk gebeurt.
2. Draai de analyse (Python-harness voor data; TradingView/Trader.dev MCP voor Pine).
3. Rapporteer tegen de poort — expliciet gehaald of niet gehaald.
4. Schrijf het artefact weg.
5. Bij niet gehaald: stop, en beschrijf wat er zou moeten veranderen om het wél te halen.

`references/stage-prompts-legacy.md` bevat de oudere per-trap prompttemplates; ze zijn
bruikbaar als steiger maar volgen de tien-traps-indeling van vóór v7.

## Wat deze skill niet doet

Accounttoewijzing, vlootallocatie, correlatie-budgetten per account en cashflow-prognoses
horen bij de Chief-of-Staff-rol, niet bij validatie. Die staan bewust buiten deze skill.
