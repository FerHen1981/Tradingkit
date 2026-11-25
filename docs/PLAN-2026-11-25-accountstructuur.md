# Accountstructuur — cashflow, blijvende funded, live (stand 25-11-2026)

Opgesteld door de SM op verzoek van Ferry ("maak daar eens een compleet plaatje van"). Alle cijfers komen uit
de metingen van 24/25-11 (`docs/DECISIONS.md`, scripts in de SM-scratchpad `live-sim/`): El Toro op de
3-jaars NQ-reeks, El Tesoro op de 3-jaars MGC-reeks met dagregels, de negen echte Apex-dagreeksen van
okt–nov, en de officiële regelpagina's van FundedNext, Topstep, MFFU en DayTraders (Apex en Lucid:
reviews, hun sites weigeren automatische lezers). In-sample; OOS-regel D-18 blijft gelden.

## Drie rollen, drie soorten accounts

| Rol | Wat het moet doen | Beste gemeten invulling | Capaciteit | Kosten per funded | Wat het levert |
|---|---|---|---|---|---|
| **A · Cashflow nu** | binnen twee weken geld | **FundedNext Rapid Pro**: El Toro 4 NQ TP 155 (62% pass, 1 dag) → El Tesoro 2 MGC; opname met $1.000 buffer in goede maanden | 5 funded tegelijk, 10 nieuwe per maand, 15 evals naast elkaar | ≈ $257 | 71% krijgt een uitbetaling, mediaan dag 9; 3-jaars gem. $847 bruto per account; okt-achtige maand $1.300–3.000; plafond $5.500 bruto, dan stopt het account |
| **B · Blijvend leveren** | accounts die niet eindigen | **Topstep XFA** (geen plafond op uitbetalingen) naast de **Apex PA's** (20) | Topstep 5 XFA's; Apex 19 van 20 bezet | Topstep ≈ $182–243; Apex ≈ $466 | Topstep $25 per account-dag (3 j), Apex $13; maar op 2 MGC breacht vrijwel elk account binnen 60 d — blijvend leveren vraagt de ruimte-ladder (1 ct tot de lock, dan 2), nog niet gemodelleerd |
| **C · Live** | echt geld, eigen regels | **El Rey 2 MNQ** (0% breach / 250 d, $2.390) of El Tesoro 1 MGC TP 120 als meetaccount (14% breach, $700) | Apex Live: opt-in; Topstep LFA: geen bots → valt af | — | El Tesoro 2 MGC op een $3.000-lijn: ≥ 98% breach, niet doen |

**Niet in het plaatje:** FundedNext Direct (25% krijgt ooit een uitbetaling, 20%-regel), MFFU Builder (1 account
per persoon), DayTraders (live 1 contract, sim-kant 15 maar regels onvolledig), Lucid tot de regels officieel
nagelezen zijn (mogelijk tweede FundedNext: 5 funded, 10 totaal).

## Hoe de drie rollen samenhangen

1. **Instroom** loopt via El Toro-evals: FundedNext Rapid Pro (1 dag), Topstep Combine (4 NQ, 1 hit per
   dag, 52% in 3 dagen), Apex (5 NQ one-hit, 49%). El Tesoro als eval-engine kost 3–5 weken en valt af.
2. **Elke geslaagde eval krijgt El Tesoro 2 MGC met dagregels.** Opnamebeleid per regime: lopen de eerste
   dagen op ≥ $150, dan $1.000 boven de floor laten staan (0 breaches op de echte oktobermaand); hangt het
   rond $30, dan meteen opnemen.
3. **FundedNext-accounts zijn een lopende band**: elk eindigt na 5 uitbetalingen, dus de eval-pijplijn blijft
   draaien om de vijf slots gevuld te houden. Topstep- en Apex-accounts blijven bestaan tot een breach.
4. **Live komt uit de vloot, niet uit de sim-cijfers**: alleen een engine die op een $3.000-lijn gemeten
   overleeft (El Rey 2 MNQ), of een meetaccount van 1 contract om de echte slippage te meten.

## Totale capaciteit sim-funded

FundedNext 5 + Topstep 5 + Apex 20 (+ Lucid 5 na verificatie) = 30–35 funded accounts naast elkaar, allemaal
op Tradovate of Rithmic. Reverse hedging over accounts is bij elke firma verboden; kopiëren tussen eigen
accounts is bij FundedNext en Topstep toegestaan.

## Risico's en open punten

- **Welk chart draaiden 034–041?** Die accounts maakten in oktober $150–200 per dag; hun dagreeks wijkt af
  van 026 (bevroren set). Zolang dat niet bekend is, meet de sim mogelijk een andere set dan die "lucratief"
  was.
- **Topstep roept op naar live en dat is niet te weigeren**; op het live-account mag geen bot draaien. Een
  XFA-vloot kan dus op een willekeurig moment gesloten worden.
- **FundedNext kan bij selectie alle sim-accounts sluiten**; of dat te weigeren is, staat nergens.
- **Pariteitspoorten**: El Rey (MNQ) en de pijplijnvertaling van El Tesoro staan open; de sim is een
  benadering (49% Apex-referentie waar de Pine-export 39% gaf).
- **Oktober was uitzonderlijk**: 3-jaars gemiddelde 2 MGC = $26 per dag, oktober $150–200.
- **Slippage**: alle funded-cijfers op sim-fills (1 tick stop, 0 entry). Elke tick stop-slippage kost El
  Tesoro ≈ $2.300 per contract per 3 jaar.

## Wat er van Ferry nodig is

1. Welk chart/welke set draaide op 034–041.
2. Regels van Lucid en Apex (aantal accounts, live) van de sites zelf.
3. Bevestiging van Apex Live: platform, datafeed, bots toegestaan.
4. Keuze: FundedNext-evals starten met El Toro 4 NQ TP 155 (nieuwe set → nieuwe meting en OOS-klok), of
   met TP 122 (57%, bestaande set).
