# Stage 1-2 — pre-registratie · El Patrón · El Matador · El Dorado × 5 assets

**Datum:** 11 augustus 2026 · **Status:** vastgelegd vóór enige backtest van deze run.
Gates komen uit de skill en worden hier niet aangepast. Wijzigt een regel, dan herstart
de pipeline bij stage 2 — niet bij de stage waar het uitkwam.

## S1 · Waar de regels vandaan komen (bronlabeling)

Deze run onderzoekt **geen nieuw idee**. De drie scripts bestaan en draaiden live; de vraag is
of hun edge **buiten NQ** standhoudt. Bronlabeling conform grondregel 3:

- **(a) Geverifieerde bron — de scripts zelf.** Alle parameters hieronder komen uit de
  CONFIG-berichten die de scripts zelf verstuurden, gelezen uit
  `TradingView_Alerts_Log_20260810_5250e.csv`. Dat is machine-geschreven bewijs, geen reconstructie.
- **(b) Praktijk-aanname.** El Matador heeft **geen** CONFIG-regel in het logvenster. Zijn
  FVG-band (9-12) en confirm-venster (2) komen uit de bevroren inputlijst in de alertnaam;
  de **aan/uit-status van het CVD-filter is niet bewezen**. De fleet-notitie in Notion zegt
  "delta UIT". Dat is hier de aanname, en hij wordt in S5 als sensitiviteit getest — niet als feit.
- **(c) Modelhypothese.** Dat een op NQ gekozen parameterset zonder aanpassing naar GC/ES/YM
  overdraagbaar zou zijn, is een hypothese. Deze run test precies dat.

## S2 · Exacte regels (mechanisch, geen discretie)

Gemeenschappelijk: entry limit @ 50% FVG, expiry 12 bars, swing-structuur-stop (pivot K=3,
buffer 2 ticks, max stop 72 ticks), TP R-multiple 2.5, maandagochtend-filter aan,
auto-flat 16:55 ET, VWAP-veto aan.

| | El Patrón | El Dorado | El Matador |
|---|---|---|---|
| FVG-band (ticks) | 9-13 | 9-13 | 9-12 |
| Confirm-venster | 0 | 0 | 2 |
| Break-even (trig/offset) | 16 / 12 | 20 / 8 | 20 / 8 |
| Trail (start/buffer) | 30 / 24 | 48 / 24 | 48 / 24 |
| CVD-filter + streak | aan, 4 | aan, 4 | **uit** (aanname, zie S1b) |
| Modus | Apex PA | Apex PA | Apex Eval |
| Bron | CONFIG PA014 04-08 | CONFIG PA013 30-07 | alertnaam (geen CONFIG) |

**Parameteraantal:** 11 vrije parameters per script, alle drie afkomstig van dezelfde
scriptfamilie. Patrón en Dorado verschillen **uitsluitend** in break-even en trail —
dat maakt hun onderlinge correlatie een expliciet aandachtspunt in S6.

## De centrale hypothese

> De FVG-retrace-edge van deze scripts is niet NQ-specifiek. Getransplanteerd **zonder één
> parameter aan te passen** houdt hij op ES, GC en YM een positieve verwachting door de
> Apex-lens.

Falsificeerbaar: het gaat om de tick-band ongewijzigd overzetten. Zou ik per asset
hertunen, dan is dat een ánder, veel zwakker bewijs en vraagt het een verse OOS.

## Assets en positiegrootte

Vijf fleet-slots. De tick-waarde is genormaliseerd op ±$10 per tick, zodat verschillen in
uitkomst uit de **edge** komen en niet uit positiegrootte:

| Slot | Serie | Qty | $/tick |
|---|---|---|---|
| NQ | NQ 1m | 2 | 10,00 |
| MNQ | NQ 1m (micro-specs) | 20 | 10,00 |
| ES | ES 1m | 1 | 12,50 |
| GC | GC 1m | 1 | 10,00 |
| YM | YM 1m | 2 | 10,00 |

MNQ deelt de NQ-koersreeks; het is geen vijfde onafhankelijke test maar een aparte
fleet-slot met eigen kosten- en DD-verhouding. **Onafhankelijke koersreeksen: 4.**
Voor QQQ en BTC is geen 1m-dataset in de repo — die kan ik niet testen.

## Vensters en de one-shot-regel — lees dit vóór de uitslagen

| Serie | In-sample | Out-of-sample (one-shot) | Status |
|---|---|---|---|
| NQ / MNQ | 2023-06-18 → 2025-12-17 | 2025-12-17 → 2026-06-17 | ⛔ **VERBRUIKT** |
| ES | 2023-08-02 → 2026-01-31 | 2026-01-31 → 2026-07-31 | ⚠️ zie hieronder |
| GC | 2023-08-02 → 2026-01-31 | 2026-01-31 → 2026-07-31 | ⚠️ zie hieronder |
| YM | 2023-08-02 → 2026-01-31 | 2026-01-31 → 2026-07-31 | ✅ **volledig vers** |

**NQ is verbruikt en telt niet mee voor een gate.** De NQ-OOS is op 10 augustus al één keer
aangeraakt voor precies deze scripts, en Dorado/Patrón zijn daar op **S7 gezakt**
(bpb −71% onder stress). Die uitslag opnieuw draaien met een variant zou p-hacking zijn.
NQ-cijfers verschijnen hieronder uitsluitend als referentie, zonder gate-krediet.

**ES/GC gedeeltelijk belast:** die reeksen zijn op 10 augustus gebruikt om de GC/ES-signalen
te zoeken. Voor *deze* scripts is daar echter **geen parameter op gekozen** — de instellingen
komen ongewijzigd van NQ. Er is dus geen selectie-vrijheidsgraad op ES/GC, en de run telt als
one-shot. Wel eerlijk vermeld: ik heb eerdere GC/ES-uitkomsten gezien, dus volledig blind is
het niet.

**YM is de zuivere test.** Nooit gebruikt, in geen enkele eerdere run, voor geen enkele
parameterkeuze. Spreken de assets elkaar tegen, dan weegt YM het zwaarst.

## Gates (overgenomen uit de skill, niet aangepast)

| Stage | Gate |
|---|---|
| S3 | geen look-ahead (shift-check), kosten aan, ≥100 IS-trades, reproduceerbaar uit config |
| S4 | per-regime-jaar gerapporteerd; recente 12 maanden PF ≥ 1,2 ná kosten |
| S5 | WFE (OOS/IS op doelmetriek) ≥ 0,5; ±20% perturbatie blijft binnen 30% van basis; MC p5 maxDD binnen DD-budget |
| S6 | correlatie dagelijkse PnL vs bestaande fleet < 0,7; voegt toe aan fleet-mediaan |
| S7 | 2-tick slippage + dubbele commissie: doelmetriek zakt < 50% |
| S8 | risico ≤1% per trade, daglimiet in het script |
| S9 | auto-stop-regels gedefinieerd, alert-pad getest |
| S10 | ≥4 weken papertrading met wekelijkse live-vs-backtest-vergelijking |

**Doelmetriek** (grondregel 5 — Apex-lens, niet ruwe PnL):
Patrón/Dorado (PA) → **banked per breach**. Matador (Eval) → **pass-rate** in de startdag-sweep.

## Vooraf uitgesproken verwachting

Op grond van de S7-afwijzing op NQ verwacht ik dat Patrón en Dorado **opnieuw op S7 zakken**,
ook op de nieuwe assets: hun edge zat dicht bij de kostendrempel en dat is een
asset-onafhankelijke zwakte. Matador heeft de beste papieren. Dit staat hier zodat de
uitslag hem kan tegenspreken.
