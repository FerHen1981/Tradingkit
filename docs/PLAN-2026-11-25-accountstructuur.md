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

## Gelijke maat: het hele pad vanaf aankoop (toegevoegd 25-11, avond)

Per slot, 120 handelsdagen, opnamebeleid $1.000 boven de floor overal, herkopen na breach of einde:

| Route | Netto gem. | Netto mediaan | Slots met uitbetaling | Mediaan dag 1e uitbetaling | Evals per 120 d |
|---|---|---|---|---|---|
| FundedNext Rapid Pro (Toro 4 NQ TP 155 → Tesoro) | $2.269 | $2.203 | 91% | 25 | 7,2 |
| Topstep (Combine 4 NQ → XFA) | $1.999 | $1.568 | 92% | 30 | 7,3 |
| Apex legacy (Toro 5 NQ → PA) | $813 | −$232 | 65% | 67 | 4,2 |
| FundedNext Direct (Tesoro vanaf dag 1) | $393 | $274 | 61% | 65 | 0 |

Direct hoort in het plaatje als cashflow-kandidaat, maar verliest ook op gelijke maat: zijn ene hobbel
($2.100 buffer plus de 20%-regel) duurt langer dan eval én buffer bij Rapid Pro samen.

## Correctie 25-11 (avond): Apex valt weg, en geen firma laat sim-accounts naast live bestaan

Ferry: bij Apex Live worden de 19 PA's afgenomen en is nieuwe aankoop uitgesloten. Officieel nagelezen:
Lucid sluit álle sim-accounts bij live of cash-out (24 uur, geen weigering), trigger o.a. Payout 5;
FundedNext sluit alles bij selectie na 15 Performance Rewards per profiel, geen weigeroptie beschreven;
Topstep en DayTraders idem. De rol "blijvend leveren" kan dus bij geen enkele firma op de sim-kant
gegarandeerd worden; elke firma is een eindig programma met een teller. Gevolg voor het plaatje:

- **Cashflow**: FundedNext Rapid Pro, vijf slots, als eindig programma van ≈ 15 rewards per profiel.
- **Blijvend**: alleen door te spreiden over firma's (FundedNext 5, Topstep 5, Lucid 5) zodat een
  live-sluiting bij één firma de andere niet raakt, en door de tellers te kennen.
- **Live**: een prop-firm-live-account kost altijd de sim-accounts van die firma. Een live-account dat
  niets afneemt is alleen een eigen brokerage-account op eigen kapitaal.

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

## Totaalplaatje v2 (25-11, avond): terug naar $3.500 per maand, plus 50 Apex Live-accounts, zonder vastzittend geld

**Uitgangspunten van Ferry:** Apex heeft 19 × 50K PA's afgenomen (cashflow ≈ $3.500 per maand); hij krijgt
50 Apex Live-accounts; bij Apex bleef ≈ $50.000 in de bonus vault staan door te laat uitbetalen. Dat mag
niet opnieuw gebeuren.

### Laag 1 · sim-funded cashflow (doel ≥ $3.500 per maand ≈ $175 per handelsdag)

| Firma | Slots | Netto per slot per handelsdag (3 j, buffer $1.000) | Teller waarna de firma sluit | Bijdrage |
|---|---|---|---|---|
| FundedNext Rapid Pro | 5 | ≈ $19 | 15 rewards per profiel (≈ 3 volle ladders) → reviewpool, sluiting bij selectie | ≈ $95/dag, eindig: ≈ $16k bruto per profiel |
| Topstep XFA | 5 | ≈ $17 | geen teller, oproep op discretie, niet te weigeren | ≈ $85/dag |
| Lucid Pro/Flex | 5 | ≈ $17–19 (geschat, niet gemeten) | Payout 5 op één account → pool, 24 uur, alles dicht | ≈ $85/dag, eindig |
| **Totaal** | **15** | | | **≈ $265/dag ≈ $5.300/maand** (3-jaarsgemiddelde; oktober-achtige maanden het dubbele) |

Instroom: El Toro 4 NQ (FundedNext/Lucid 1 dag, Topstep 3 dagen). Funded: El Tesoro 2 MGC + dagregels.
Elke firma is een eindig programma: FundedNext en Lucid lopen per profiel leeg; daarna nieuwe firma's uit de
lijst (DayTraders 15 sim, Alpha, BluSky) of de live-laag.

### Laag 2 · 50 Apex Live-accounts

Regels zoals bekend (review 15-10, niet door Apex bevestigd): $0 start, $3.000 EOD-trailing, 3 mini / 30 micro,
geen DLL, 90%, dagelijkse uitbetaling van alles boven $3.100 vanaf $500. Gemeten op die lijn (3 j, 1 tick):

| Engine | Afgaan ≤ 250 d | Kans op uitbetaling | Gem. uitbetaald per account per 250 d |
|---|---|---|---|
| El Rey 2 MNQ (Pine-defaults) | 0% | 92% | $2.390 |
| El Tesoro 1 MGC TP 120 | 14% | 54% | $700 |
| El Tesoro 1 MGC TP 85 | 58% | 39% | $566 |
| El Tesoro 2 MGC | ≥ 98% | — | — |

50 identieke accounts zijn één weddenschap × 50, niet vijftig onafhankelijke: ze winnen en verliezen op
dezelfde dag. Spreiden over twee engines (El Rey MNQ en El Tesoro 1 MGC TP 120) is de enige spreiding die
beschikbaar is, en de correlatie MGC–MNQ is nog niet gemeten. Indicatief: 50 × El Rey 2 MNQ ≈ $120k per 250
handelsdagen (≈ $10k per maand) bij 0% gemeten breach; 50 × El Tesoro 1 MGC TP 120 ≈ $35k. Voorwaarden: platform,
datafeed en bot-toestemming van Apex Live, en de pariteitspoort van El Rey.

### Laag 3 · regels tegen vastzittend geld

1. **Uitbetalen op elke eerste mogelijkheid**, nooit wachten op een hoger plafond. Uitzondering: de $1.000-buffer
   in weken met dagen ≥ $150, en die alleen op de sim-kant.
2. **Nooit meer dan één uitbetaling aan onuitbetaalde winst op een account laten staan.** Op Apex Live: dagelijks
   alles boven $3.100 eruit; daar kan niets blijven staan.
3. **Tellers in het register**: FundedNext 15 rewards, Lucid Payout 5, Topstep discretie, Apex-regels zodra bekend.
   Het aantal lopende rewards per profiel wordt bijgehouden in de Accounts-DB en elke ochtend getoond.
4. **Payout-radar in de Dagstart-taak** (beheer SM): per account "vandaag uitbetaalbaar: ja/nee, bedrag, wat
   ontbreekt (dagen, consistentie, buffer)". Dat is de automatisering van regel 1.
5. **Bonus-vault-achtige regels vooraf kennen**: bij elke nieuwe firma vóór aankoop vastleggen wat er met niet-
   uitbetaalde winst gebeurt bij live-overgang, sluiting of inactiviteit.

### Wat er nu eerst moet

1. Apex Live: platform, datafeed, bots, termijn, en wat er met niet-uitbetaalde PA-winst gebeurt (vault-regel).
2. FundedNext: 5 Rapid Pro-evals; Topstep: 5 Combines; Lucid: regels op de site nalezen, dan 5 evals.
3. Payout-radar in de Dagstart-taak en de tellers in de Accounts-DB (SM).
4. Meting die nog ontbreekt: correlatie MGC–MNQ op dagbasis; El Rey-pariteit; de ruimte-ladder per firma.
