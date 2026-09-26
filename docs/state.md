# Live state

Read this first in every chat. Update it last. If it is stale, nothing below it
can be trusted.

_Last updated: 2026-09-23 (Analyses & Data chat)_

## Live settings — de werkende config (D-75, vervangt D-43)

Bewezen op live fills 1–14 sep 2026 (PA013/018/021/022/023, 325 trades):
**60% trade-winrate, 75% winstdagen, mediaan account-dag +$503.** Na het
uitzetten van de Pine day-trail op 15/9 zakte dit naar het rauwe profiel
(jaar-backtest: 51-53% winstdagen); op 17/9 teruggezet.

### Pine — TES-MGC-C v3.2.0 op MGC1! 1m (per account één chart/alert)

| Groep | Input | Waarde |
|---|---|---|
| Sessie | Market regime · tz · boundary | All sessions · America/New_York · Exchange session (ETH) |
| | Force flat 16:55–18:00 · dagen · uren | On · ma–vr · alle uren On behalve 17 |
| | Sessiefilters | Globex reopen On, Asia Off, London On, US 07-12 On, overige Off |
| Entry | Entry mode · expiry · FVG fill check | Limit @ 50% FVG · 12 bars · On |
| | FVG size filter · confirmation | On, 8–23 ticks · 4 bars |
| | pivK · buf | 3 · 2 |
| Exit | Stop · max stop | Fixed (legacy) **100t** · 100 |
| | TP · R-multiple | Fixed (units) **85t** (0,85 : 1) · 1 (inactief) |
| | Break-even · Trailing | Off · Off |
| Filters | VWAP side veto · Delta filter (CVD) | On · **Off** (cvd=0) |
| | Streak · Longs/Shorts · bias · sweep | On, count 5 · On/On · 0 · 0 |
| Day-guards | **Day-profit exit mode** | **Trail + cap** |
| | Day-trail model · scale | Activation + giveback · Fixed USD |
| | **Activation / giveback / hard cap** | **$250 / $100 / $500 per contract** (zie schaalregel) |
| | Daily risk-gate | Off — DLL zit in Tradovate |
| Account | Phase · firm · DD-model · trailing DD | Developer · manual (preset apex_50k_legacy_pa niet toegepast) · Intraday · 2000 |
| | PA DLL · consistency · min payout · qualifying day | 300 (inactief) · 30% · 500 · 250 |
| | MAE guard · derisk · next payout | off · off · 1 |

NQ (TOR-NQ-HF v1.0.2-NQ-HF-INTRA, eval-only): TP **Fixed 122t** / SL 90t, expiry 9,
FVG 4–12, confirmation 2, CVD **On**, streak 3, monFilter On. Correctie 24/9 uit
alerts-log `d9675`: 122t staat sinds 2 sep op alle eval-charts en is de bedoelde
one-TP-lottery (5 NQ × 122t × $5 = $3.050 ≥ eval-target $3.000); de eerdere notitie
"teruggezet naar 90t" was fout. **Account phase sinds 22/9: Apex Eval** (was Research
(none)): de Pine account-engine is nu actief — ACCOUNT STARTED/HALT-kaarten, blokkade
na EVAL PASSED, en TRAILING BREACH (model) op HWM incl. open P&L (`acctPnL` =
netprofit + openprofit, Intraday-model). Dat is de echte Apex-regel: één trade die
+$75 open heeft gestaan en dan naar SL loopt, breacht een verse 50K op 5 NQ.
**Incident 24/9 (Fills_41, APEX…243) — opgelost via Apex-ticket #1777923:** short 5 NQ
@ 30750.25 (21:13 ET) liep om 21:29 ET ≈ +67t (+$1.675 open) → Apex "unrealized peak
balance" $51.667,25 → trailing floor $49.167,25 (= −$832,75 = −33t vanaf entry). De
spike om 21:34 ET naar 30761 (−43t) zat onder die floor → systeem-liquidatie (order
"ADMIN" = Apex/Tradovate-systeem), fill −36t = −$900. Het ronde bedrag was toeval, geen
regel. De TP werd 14 min later geraakt. Bracket door PMT correct geplaatst; Pine-engine
had dezelfde floor gemodelleerd (Intraday-model), dus engine en Apex kloppen. Account
243 is gefaald; opties: reset of nieuwe account.
**Incident 24/9 (Fills_42, APEX…244):** short 5 NQ @ 30481.75 (07:06 ET), gesloten
07:14 ET @ 30482.00 = −1 tick (−$40,50 incl. commissie), Tradovate meldt *breached*.
Enige mechanisme dat dit oplevert: intraday trailing incl. open winst. Bij MFE ≥ 99t
(+$2.475) staat de floor op ≈ break-even; terugval naar −1t = liquidatie. Zelfde mechanisme als
243 (door Apex bevestigd). Structureel: TP 122t ligt vóórbij de
trail-afstand (100t op 5 NQ); elke MFE in 100–121t die omkeert is een breach. Zie
D-77 voor de near-miss-bescherming.

### Tradovate Auto Liq — per account (hard, realized + open)

Uit de fills afgeleid (dag eindigt op de trade die het ronde bedrag overschrijdt):

| Account | Qty vóór 15/9 | Daily target | DLL |
|---|---:|---:|---:|
| PA013 | 4–6 | $500 → $900 (8 sep) | $700 |
| PA018 | 2–4 | $900 | $700 |
| PA021 | 2–3 | $500 | ≥ $560 (niet geraakt) |
| PA022 | 2–4 | $500 | ≥ $560 (niet geraakt) |
| PA023 | 3 | $600 | $400 |
| PA024 | 3 | ~$750 | $500 |

### Schaalregel — guards per contract × qty

Alle $-guards zijn per contract gedefinieerd en schalen lineair met qty.
Vaste $-bedragen worden bij hogere qty in trade-eenheden strakker: bij qty 4 armt
de trail na 1 TP, geeft 25t/ct terug, cap = 1,5 TP, DLL = 1,75 SL — de dag is na
2-3 trades voorbij en de winst/verlies-verhouding klapt om.

| 34 rauwe dagen (3 aug–17 sep), guards 250/100/500 + DLL 700 | qty 1 | qty 2 | qty 3 | qty 4 | qty 6 |
|---|---:|---:|---:|---:|---:|
| Vast in $ — net per contract | $4.861 | $2.522 | $941 | $282 | −$57 |
| Vast in $ — trades/dag · winstdagen | 11,4 · 82% | 6,4 · 79% | 4,3 · 59% | 3,2 · 44% | 2,0 · 59% |
| Geschaald (×qty) — net per contract | $4.861 | $4.861 | $4.861 | $4.861 | $4.861 |
| Geschaald — trades/dag · winstdagen | 11,4 · 82% | idem | idem | idem | idem |

Per contract: activation 250 · giveback 100 · cap 500 · DLL 300–700.
Bij qty 2: **$500 / $200 / $1.000 / $600** (DLL 3×SL; 700/ct is boven de
testbare grens van de jaardata). Bij qty 1: $250 / $100 / $500 / $300.

**Apex-plafond op de schaling.** De Apex-regels staan in vaste dollars:
consistency-cap payout-1 = 30% × $4.100 = **$1.230** per dag, trailing DD $2.500.
Geschaalde cap 500/ct past tot **qty 2** ($1.000; best-day jaar $1.163). Bij
qty 3 wordt de best-day $1.744 en breekt de consistency; bij qty 4 $2.325.
**Daarom qty ≤ 2 voor dit profiel.** Correctie 19/9 uit het Apex-dashboard: de
consistency-noemer is de **totale accountwinst (balance − $50.000)**, niet de winst
sinds de laatste payout (PA013 na payout: best-day $555 / $5.557 = 9,99%). De teller
is de beste dag sinds de laatste payout. Per account geldt dus:
`daily target ≤ min(30% × (balance − 50.000), huidige best-day)` — een dag boven de
huidige best-day verhoogt de lat. Na een payout wordt de cap ruimer, niet strakker.

### Per-account set (26 sep, stand Tradovate na sluiting — vervangt 23 sep)

Weg per 28/9: PA021 (breached) en de evals 238, 240–245, 247, 248, 251, 252. Erbij: PA
uit eval 249 (gehaald) en 2 nieuwe 50K. Volledig schema met schaal-ladder en payout-
projectie: `fleet_startschema_2026-09-28.pdf` (scratchpad/Ferry, niet in repo).

| Account | Product | Balans | Ruimte | Qty | Pine act/gb/cap | TV target | TV DLL | Status |
|---|---|---:|---:|---:|---|---:|---:|---|
| PA013 | Legacy 50K | 55.242 | 5.142 | 3 | 750 / 300 / 1.500 | $1.500 | $1.200 | #1 ontvangen 10/9; **#2 $2.000** zodra 5 kwal.dagen vol; na #2 ruimte 3.142 → qty 2 tot 53.700 |
| PA018 | Legacy 50K | 56.007 | 5.907 | 4 | 1.000 / 400 / 2.000 | $2.000 | $1.600 | #1 geblokkeerd door best-day $2.504 → balans ≥ 58.348; cap 2.000 verhoogt de lat niet |
| PA022 | Legacy 50K | 52.671 | 2.571 | 2 | 500 / 200 / 1.000 | $1.000 | $800 | +1.429 tot max #1 (54.100) |
| PA023 | Intraday 4.0 | 50.585 | 485 | 1 | 250 / 100 / 500 | $500 | $200 | TV DLL was 1.000; 2 verliesdagen tot liq; best $621 → consistency 50% vraagt winst ≥ 1.242 |
| PA024 | Intraday 4.0 | 49.000 | 511 | 1 | 250 / 100 / 500 | $500 | $200 | TV DLL was 1.000; 2 verliesdagen tot liq |
| PA025 | Legacy 50K | 48.723 | 1.006 | 1 | 250 / 100 / 500 | $500 | $300 | ⅓-regel |
| PA026 | Legacy 50K | 50.788 | 1.642 | 1 | 250 / 100 / 500 | $500 | $400 | best $1.010 → winst ≥ 3.367 vóór #1 |
| PA027 | Legacy 50K | 49.913 | 1.767 | 1 | 250 / 100 / 500 | $500 | $400 | |
| PA028 | Legacy 50K | 49.023 | 1.250 | 1 | 250 / 100 / 500 | $500 | $400 | |
| PA029 | Legacy 50K | 48.945 | 1.411 | 1 | 250 / 100 / 500 | $500 | $400 | nieuw (ex-239) |
| PA ex-249, Nieuw A/B | Legacy 50K | 50.000 | 2.500 | 1 | 250 / 100 / 500 | $500 | $400 | qty 2 bij lock |
| 253–257 | 50K eval | 50.000 | 2.500 | 5 NQ | geen day-guards | — | — | lottery; 250 ($219 ruimte) niet handelbaar |

Week 21–25 sep live: alle PA's negatief tot vlak (013 −196, 018 −600, 023 −1.065, 025 −1.028,
028 −910, 029 −1.055); backtest qty 2 zelfde week +315 (ma/wo/vr verlies in de US-sessie).

Pine voor alle PA's: TP **Fixed 85t** (export d8ac1 draaide op R-multiple 1 = 100t, dat
is níet de live waarde), Day-profit exit mode **Trail + cap**, Daily risk-gate **Off**.

**Qty-plafond = consistency, niet ruimte.** Best-day ≤ 30% × (balans − 50.000) op het
moment van aanvragen; cap = $500/ct ⇒ max qty = ⌊0,3 × winst / 500⌋: winst 3.400 → 2,
5.000 → 3, 6.667 → 4, 8.334 → 5. Ruimte-eis (3 DLL-dagen à $400/ct): qty 2 ≥ 2.400,
3 ≥ 3.600, 4 ≥ 4.800. Een payout verlaagt de noemer: eerst aanvragen, dán opschalen.
De 8-dagen-regel is de klok; qty 2 vult elke trede binnen die 8 dagen.

**Alternatief op record (jaar-optimum, strak):** qty 2, geen Pine trail, Tradovate
target $400 / DLL $300 → 4 payouts/jaar, 9% verse-breach, $16,4k/jaar, 53% winstdagen.
Het adem-profiel hierboven op qty 2 over het jaar: 3 payouts, 46% breach (bij DLL 600),
$13,4k, 56% winstdagen — beter in goede periodes (aug–sep: 82%), slechter in de staart.
Keuze Ferry 18/9: adem-profiel; herzien na 4 weken live op de sample-check.

## D-77 — Eval near-miss: intraday trailing vs TP 122t (24 sep 2026, mechanisme bevestigd; trailing-stop = voorstel)

**Bewijs.** Fills_42 (APEX…244): 5 NQ short, −1 tick gerealiseerd, account *breached*.
Verklaring: Apex-trailing op evals volgt de HWM inclusief open winst. Op 5 NQ is de
trail-afstand $2.500 = 100t; de TP staat op 122t. Een trade met MFE 100–121t die
terugvalt naar de entry wordt op ≈ break-even geliquideerd. Zelfde mechanisme bij 241
(23/9): MFE 89t → floor −$275 → SL −$2.365 = breach. Dit zit in de structuur (target
$3.000 > trail $2.500), niet in een instelling: elke weg naar +$3.000 loopt door de
zone waar een volledige terugval een breach is.

**Voorstel (nog niet live).** Pine Enable Trailing **On**, Trail Activation MFE ≈ 95t,
Trail Buffer 10t op de eval-charts. Een near-miss sluit dan op ≈ +85t (+$2.125) in
plaats van op −1t: account leeft met ~$2.100 ruimte en nog $875 tot target. Vervolg
handmatig: qty 2 NQ, TP 122t (+$1.220 → pass), SL 90t (−$900, twee pogingen). Kosten:
trades die tussen 95t en 122t heen-en-weer gaan en daarna alsnog de TP halen, worden
nu op de trail gesloten; niet te kwantificeren zonder NQ-export met MFE/MAE. Mechanisme
door Apex bevestigd (ticket #1777923, 243): floor = unrealized peak − $2.500, ook
intra-trade. Op 5 NQ is het hele budget 100t swing vanaf de beste open stand; MFE ≥ 10t
gevolgd door een volle SL (90t) is al een breach. Test vóór live: El Toro HF export
met Enable Trailing On (activation 40t / buffer 40t) naast Off, tel TP-exits en
trail-exits ≥ +40t.

## D-76 — Day-trail en DLL herijkt op export d8ac1 (23 sep 2026)

**Bewijs.** TES-MGC-C export `d8ac1` (24 jun–23 sep, qty 4, TP R-multiple 1 = 100t,
exit mode Off, gate Off = rauwe stroom): 1.063 trades, 65 dagen, $26.258, 63%
winstdagen, best-day $4.293, worst −$3.772, max DD op dagsommen $5.107. Guards
gesimuleerd op trade-closes (per contract, ×4 op deze run):

| Variant per contract | Totaal/ct | Winstdagen | Best-day/ct | Worst/ct | Max DD/ct |
|---|---:|---:|---:|---:|---:|
| rauw | 6.564 | 63% | 1.073 | −943 | 1.277 |
| 125 / 50 / 250 (= de ingevulde 500/200/1.000 op qty 4) | 4.668 | 78% | 337 | −943 | 1.277 |
| **250 / 100 / 500** (D-75) | 6.554 | 69% | 594 | −943 | 1.277 |
| alleen cap 500 | 7.128 | 65% | 594 | −943 | 1.277 |
| 250 / 100 / 500 + DLL 300 (3 SL) | 4.846 | 62% | 594 | −324 | 1.095 |
| 250 / 100 / 500 + **DLL 400 (4 SL)** | 5.462 | 68% | 594 | −424 | 822 |
| 250 / 100 / 500 + DLL 225 (= $900 op qty 4) | 3.939 | 52% | 594 | −220 | 1.430 |

**Beslissing.** (1) Cap $500/ct blijft: kost niets aan totaal en drukt de best-day van
$1.073 naar $594/ct (consistency). (2) Trail 250/100/500 per contract blijft; lagere
activation/giveback koopt winstdagen-% voor 25–30% totaal. (3) **DLL van 3 naar 4 SL
per contract: $400/ct** (qty 2 → $800) — beste totaal/DD-verhouding; DLL ≤ ⅓ van de
ruimte tot liq gaat vóór. (4) Qty 2 pas na de lock (balans ≥ $52.600) en ruimte ≥ $2.400;
verse 50K op qty 2 + DLL 300–400/ct overleeft de slechtste start van de reeks (25–26 jun).

**Schaal-ladder (26/9).** Twee regels, de strengste wint. (1) Ruimte: qty ≤ ⌊(balans −
liq-niveau) / 1.200⌋ (3 DLL-dagen à $400/ct); DLL = 400 × qty maar ≤ ⅓ ruimte. (2) Consistency
op aanvraagmoment: qty ≤ ⌊0,3 × winst_bij_aanvraag / 500⌋; vóór payout #1 is die winst vast
(safety net + trede 1): 50K → qty ≤ 2, 250K → ≤ 5, 300K → ≤ 6. Legacy 50K na de lock
(balans ≥ 52.600, liq 50.100), aanvragen op max zonder buffer: qty 2 vanaf 52.600, qty 3
vanaf 55.000, qty 4 vanaf 56.700, qty 5 vanaf 58.400. Met de $2.000-buffer (aanvraag pas
op safety net + buffer + trede) is qty 3 al vanaf cyclus 1 mogelijk en qty 4 vanaf cyclus 3.
Afschalen: direct als balans onder de drempel van de huidige qty zakt (na een payout of
een DLL-dag), nooit wachten tot de aanvraag. Vers: 50K qty 1 tot lock; 250K qty 3 tot
lock (256.600); 300K qty 4 tot lock (307.600); één DLL-dag laat dan nog twee over.

**Activatie-check 26/9 (drie samples, geschaald naar qty 2, giveback 200, cap 1.000):**
30d `2dc43`: act 500 → 6.173, 400 → 6.090, 300 → 5.525, 200 → 3.205. 65d `d8ac1`:
400–500 → 13.108 (69% winstdagen), 200–300 → 9.605, uit → 14.259. Jaar `89aa5`: 400 →
14.047 (optimum), 500 → 13.388, 300 → 12.711, uit → 10.166. Robuuste zone **$400–500 op
qty 2 = $200–250 per contract**; lager kost in elk sample 10–45%. Giveback 100 en 200
zijn op trade-closes identiek (één verlies = $204); 300 kost winstdagen. Geen wijziging.

**Beperking.** Op qty 4 is één trade ±$400: giveback 100–300 en activation 400–600 zijn
op trade-closes identiek. Pine's intraday trail (open P&L) is niet reproduceerbaar; de
sim is een bovengrens. Deze run is TP 100t; live blijft 85t (jaardata `89aa5`).

Bronbestand (upload, niet in repo): TES-MGC-C export `66a9acf3…d8ac1` (23 sep).

## D-75 — Werkende live-config vastgelegd + schaalregel guards (18 sep 2026)

Genummerd D-75 om botsing met de board-nummering te vermijden (board zit op D-74);
de D-43 hieronder is de oudere Analyses-chat-nummering.

**Bewijs.** Fills 35–40 (1–16 sep, 6 accounts, 389 trades): vóór 15/9 60% op trades,
75% op account-dagen, mediaan +$503, avg verliezer −$126; ná 15/9 (day-trail uit)
avg verliezer −$237. Alerts-log `ae004`: enige config-verschil vóór/ná 15/9 op MGC =
Day-profit exit Trail+cap → Off (plus 021/025 op 450/450/900); op NQ TP 90 → 122.
Backtests `1b4a6` (34d rauw) en `89aa5` (jaar): fixed-$ guards halveren per-contract-
rendement bij elke qty-stap; geschaald is per contract exact gelijk.

**Beslissing.** (1) Pine day-trail 250/100/500 per contract is het werkende mechanisme —
blijft aan. (2) Alle $-guards schalen met qty; qty ≤ 2 vanwege de consistency-cap.
(3) DLL en target blijven hard in Tradovate (middleware-gate is dormant, Pine-gate heeft
feestdag-resetbug: 8 sep). (4) NQ TP terug op 90t.

**Niet opgelost.** Jaar-niveau breach-risico van het adem-profiel (46% bij qty 2 /
DLL 600) versus 9% voor het strakke profiel; DLL > 3×SL per contract niet testbaar op
de jaardata. Sample-check 16 okt 2026: winstdagen, mediaan-dag en breaches per account
tegen deze tabel.

Bronbestanden (uploads, niet in repo): Fills_35–40.csv, TradingView_Alerts_Log
2026-09-17 ae004, TES-MGC-C exports 1b4a6 / df588 / ff116 / 89aa5 / 6ae1c.

## D-43 — Buffer-gedreven per-account sizing + hard Tradovate-limits (28 aug 2026)

**Waarom.** Fleet-optimalisatie-analyse op de MGC1! 1-jaars backtest (config
`91469a71`, TP 85t Fixed) laat zien: mediaan-dag ligt op qty 5-6 tussen $400-500
= precies in target. Netto/jaar wordt niet gedood door lage winrate maar door
~1-op-10 tilt-dagen van −$3k tot −$6k. Concreet voorbeeld: 2 weken 14-28 aug
2026 leverden qty 5 in totaal +$1.826 op — maar 10 van de 11 handelsdagen waren
gemiddeld +$568 (in target). Eén dag (17 aug, −$3.862) at 10 winstdagen op.

**Beslissing.** Twee dingen tegelijk:
1. **Day-target en DLL worden hard in Tradovate ingesteld** (niet via de Pine
   `Daily risk-gate`). Reden: Ferry heeft controle in het broker-platform, geen
   afhankelijkheid van Pine-phase (Developer vs Apex PA). Verlies daarmee wél de
   simulatie-mogelijkheid in de backtester — accepteren, want live-fills wegen
   toch al 2× (evidence-weighting hoger in dit document).
2. **Sizing is per-account, gedreven door DIST TO AUTO LIQ** (= runway naar
   trailing-DD-liq). Formule staat hierboven onder "Live settings". Kern: qty
   moet zó laag zijn dat één full-loss trade (`qty × 100t × $1`) niet meer dan
   ~40% van de dagelijkse DLL raakt.

**Waarom niet DLL uit en discount-accounts vervangen.** Discount-accounts kosten
$19/stuk (Ferry heeft pipeline). Reset-kosten dus niet de bottleneck. Maar
opportunity-cost is dat wél: elk gebreached account levert 0 payout ipv de
$16-41k/jaar per overlevend account. DLL AAN verlaagt breach-rate van ~50-60%
naar ~5-15% op basis van Python-sim over de 1-jaars data. Delta = $18-22k/maand
fleet-winst. Discount-economics vervangen dat niet.

**Waarom niet één vaste qty over alle 6 accounts.** PA015 met qty 6 = één SL
van $600 op $581 buffer = instant breach. Uniform sizen negeert de spread in
buffer-staat en verspilt de kleinere accounts. Buffer-modes maken elke account
op zijn eigen tempo bruikbaar.

**Openstaande validatie.** Deze regels zijn afgeleid uit één 1-jaars backtest
en één 2-weken live-slice. Herzien na 2 handelsweken live (uiterlijk 11 sep
2026): klopt de mediaan-dag met de backtest-verwachting per qty? Zo nee — de
regels aanpassen, geen nieuwe fleet-uitrol tot de discrepantie verklaard is.

**Niet in scope:** BE-lock / trail-tick-parameters. Vorige poging (backtest
`4d22f520`) toonde dat die knoppen de edge doden (jaar-netto −$302k op MGC).
Blijven uit.

## Datasets

## Datasets

Tracked in `data/manifest.json` (not yet created). No analysis may cite a dataset
that is not registered there.

| Symbol | Range | CVD valid from | Rows | Source | Status |
|---|---|---|---|---|---|
| NQ | 2023-06-18 → 2026-06-17 | **unknown** | ~1.1M | TradingView 1m export | in use, CVD depth unverified |

## In-sample / out-of-sample

Defined on the **CVD-valid window**, not the calendar.

- **In-sample**: everything before the final 3 years.
- **Out-of-sample**: the **last 3 years**, reserved — this is the window intended
  for the public track record on the site.
- **Walk-forward**: `funnel.py` restarts a fresh eval at many points inside the
  in-sample window. This is how configs get chosen; the 3-year block is not
  touched during selection.
- **Sealed holdout**: the most recent 12 months sit *inside* the OOS block and are
  opened last, once a config is frozen. One look, one verdict.

⚠ **The 2023-2026 window is currently burnt.** The roll/OpEx factory was tuned on
it (`CLAUDE.md`: "validated, 3y OOS"), so as things stand it is in-sample by use
and cannot honestly be presented as out-of-sample on a public site. Two ways back:

1. **Re-select on pre-2023 only** and leave the 3 years genuinely untouched. Clean,
   and it makes the site claim true — but it needs CVD history reaching back
   before 2023, which is exactly the open question.
2. **Relabel** the 3 years as *validation* and let the true out-of-sample be
   forward: live results from the day a config is frozen.

Option 2 always works and costs nothing but patience. Option 1 depends on the feed.

## Evidence weighting — actual overrules backtest

Live fills carry more information than simulated ones, so they weigh **2×**:

```
E_blend = (2·N_live·E_live + N_bt·E_bt) / (2·N_live + N_bt)
```

Two things this must not become:

- **A number that never moves.** Live samples are dozens of trades against
  thousands of backtest trades, so even at 2× the blend barely shifts early on.
  Report `N_live` next to every blended figure, or the weighting is decoration.
- **An average that hides a broken model.** When live *disagrees structurally* —
  slippage per venue, fill rates, latency — the backtest is not one noisy opinion
  to be averaged, it is **miscalibrated and must be re-run** with the measured
  values. That is what "actual overrules" means. The Phase 6 reconciliation layer
  already measures slippage in ticks per trade × venue, so this veto is instrumented;
  it just needs wiring into the metrics.

## Units — how pips and ticks are made comparable

Three different jobs, three different normalisations. Mixing them is how a
"9-tick gap" gets copied from NQ to GC and quietly means something else.

| Layer | Unit | Why |
|---|---|---|
| Signal geometry (gap size, stop, TP, trail) | **ATR multiples** (`--unit-mode ATR`) | Ticks are instrument-native and do not port. ATR self-scales to each instrument's volatility. |
| Trade outcome | **R** (risk multiples) | Every trade risks 1R by construction, so R compares across instruments and strategies. |
| Account / goal outcome | **DD-units** = % of that account's trailing-drawdown allowance | This is the prop-firm-native unit. Both goals are *defined* in it: an eval is "+target before -1.0 DD", funded survival is "never touch -1.0 DD". |

DD-units are the primary reporting unit. They make GC on a 50k Apex directly
comparable to 6E on a 100k FTMO, which dollars and percentages of balance do not.

## Open decisions (blocking)

1. **How far back does real per-bar `Delta` actually go?** Source is **Quantower**,
   so depth is set by the *connection* behind it, not by Quantower. Run
   `tools/validate_dataset.py` on a single pilot export — it prints the CVD
   boundary. That boundary is the research window. See `docs/data_export.md`.
   → *Needed from Ferry: which data connection/vendor.*
2. **Data hosting.** ~500 MB CSV per symbol per 15y: too large for git (100 MB/file
   hard limit) and for the LFS free tier. Proposed: Parquet+zstd (4-10× smaller,
   `validate_dataset.py --to-parquet`) published as **GitHub Release assets**,
   fetched per analysis. Requires a Parquet branch in `backtest/data.py` (not yet
   built).
3. **Continuous-contract stitching** — back-adjusted or raw-spliced? This strategy
   reads 3-bar fair-value gaps, and a raw roll gap can manufacture a signal that
   never traded. Roll dates, if exportable, let us mask instead of guess.
4. **BTC**: CME futures start Dec 2017 (max ~8.5y). Contract spec in `config.py:42`
   marked **verify** (BTC=5 vs MBT micro).
5. **FX futures multipliers** (`6E/6B/6J/6A/6S/6C`) marked **verify** in
   `config.py:44-49`. Both 4 and 5 resolve from Quantower's Symbol Info panel:
   tick size, tick value, multiplier, full-size vs micro.

## Settled

- **Micros**: not exported. Same price series as full-size; only the multiplier
  differs and it already lives in `config.py` `CONTRACTS`. CVD is read from the
  liquid full-size contract even when trading micros.
- **QQQ and other non-tradables**: not strategy datasets, but they *do* go through
  the mill as **context series** for correlation work (see below).
- **1-minute is the storage base.** `data.py:resample()` is session-aligned and
  sums `Delta`/`BuyVolume`/`SellVolume`; volume delta is additive, so every higher
  timeframe is derivable. Only intrabar ordering is lost — a short tick or 1s
  window would let us price the engine's pessimistic stop-first assumption.

## The fleet problem — why accounts liquidate together

Four accounts hitting liquidation at once is not four bad accounts, it is **one
position held four times**. `middleware/app/risk.py` gates per account
(`_halted` is a per-account, per-day set); nothing sees the portfolio. And the
funded edges are NQ/ES/GC — NQ and ES correlate around 0.9, so fanning one
strategy across them is leverage wearing the costume of diversification.

This makes correlation analysis (incl. the non-tradable context series) a
first-class part of Goal B, not a curiosity, and it means the Goal-B tooling must
model the **fleet**: N accounts, correlated returns, per-firm rules → distribution
of accounts alive at T, accounts reaching 6/6, and P(≥k simultaneous breaches).
`funnel.py` today models one account at a time.

## Infrastructure

Target and migration order in `docs/infrastructure.md`. Short version: only the
middleware, journal, dashboards and scheduled jobs need 24/7 — Quantower does not,
because the corpus is a monthly refresh, not live infrastructure. One VPS
(2-4 vCPU / 8 GB / 80 GB) runs everything; `middleware/deploy/setup.sh` already
provisions it in one command. Nothing has been created yet.

Before anything moves: `tools/inventory_local.py` over the local folders, so the
scattered `C:\` files get triaged rather than relocated.

## Skills

| Skill | Goal | State |
|---|---|---|
| `/eval-throughput` | A — pass evals fast | built; terminal report, dashboard pending |
| `/payout-throughput` | B — milk to 6/6 payouts | built; terminal report, dashboard pending |
| `/heatmap` | — | demoted to diagnostic; no longer a decision instrument |

Metrics live in `backtest/goals.py`, reachable as
`python3 -m backtest.run --goal {eval,payout}`. Both walk-forward via `funnel.py`;
both refuse a dataset that is not CVD-valid.

## Not started

- **The two dashboards** (one URL per goal) — waiting on real data so they can be
  verified against real output rather than synthetic.
- **The fleet model** — N accounts, correlated returns, per-firm rules,
  P(≥k simultaneous breaches). This is what answers the 4×-liquidation question;
  the per-account report explicitly does not.
- `recap` skill (fixed weekly format).
- Parquet reader in `backtest/data.py` (the loader is CSV-only).
- Wiring reconciliation's measured slippage into the metrics, so "live overrules"
  recalibrates rather than averages.
