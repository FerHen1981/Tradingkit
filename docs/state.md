# Live state

Read this first in every chat. Update it last. If it is stale, nothing below it
can be trusted.

_Last updated: 2026-10-02 (Analyses & Data chat)_

> **Het doel (besluit Ferry 2 okt 2026):** continuïteit op dagbasis, en per account het maximum
> van elke payout-trede in zo kort mogelijke tijd. Niet maximale winst op de strategie. Elke
> aanbeveling in dit bestand wordt gelezen op twee meetlatten, in deze volgorde: breach-kans en
> gelijkmatigheid van de dagen; handelsdagen tot het stapmaximum. Dollars per jaar zijn uitleg,
> geen criterium. Vastgelegd in `.claude/skills/payout-throughput/SKILL.md`.

## Live settings — de werkende config (A-75, vervangt A-43)

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
A-77 voor de near-miss-bescherming.

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

### Per-account set (1 okt, stand Tradovate 30 sep na sluiting — vervangt 26 sep)

16 PA's (013, 018, 022–035; 030–033 nieuw, 034/035 vers) + 3 × 250K-eval (267–269, vers).
Alle 50K-evals van vorige week zijn weg. Regels A-78/A-81; schema `fleet_startschema_2026-10-02_v2.pdf` (doel vooraan; gemengde vloot: fase A/B 250/100/500, fase C 150/50/300 × qty; live config uit alerts 2 okt).
30 sep: elke account −$400 tot −$1.600 (één SL-dag).

| Account | Balans | Ruimte | Qty | Pine act/gb/cap | TV target | TV DLL | Status |
|---|---:|---:|---:|---|---:|---:|---|
| PA013 | 54.927 | 4.827 | **1** | 250 / 100 / 500 | $500 | geen | #2 $2.000 aanvraagbaar (zonder buffer) zodra 5 kwal.dagen vol; qty 2 bij 55.100 |
| PA018 | 55.444 | 5.344 | 2 | 500 / 200 / 1.000 | $1.000 | $600 | #1 geblokkeerd tot 58.348 (best-day 2.504) |
| PA022 | 52.797 | 2.697 | 1 | 250 / 100 / 500 | $500 | geen | +1.303 tot max #1 |
| PA023 (4.0) | 50.374 | 274 | 1 | 250 / 100 / 500 | $500 | $200 | TV DLL staat nog op 1.000; 1 verliesdag tot liq |
| PA024 (4.0) | 48.931 | 443 | 1 | 250 / 100 / 500 | $500 | $200 | TV DLL staat nog op 1.000 |
| PA025 | 48.414 | 698 | 1 | 250 / 100 / 500 | $500 | $200 | |
| PA026 | 50.615 | 1.469 | 1 | 250 / 100 / 500 | $500 | geen | |
| PA027 | 49.737 | 1.591 | 1 | 250 / 100 / 500 | $500 | geen | |
| PA028 | 48.848 | 1.076 | 1 | 250 / 100 / 500 | $500 | $300 | |
| PA029 | 48.777 | 1.242 | 1 | 250 / 100 / 500 | $500 | $400 | |
| PA030–033 | 49.2–49.8k | 1.35–1.9k | 1 | 250 / 100 / 500 | $500 | geen | nieuw |
| PA034, PA035 | 50.000 | 2.500 | 1 | 250 / 100 / 500 | $500 | geen | vers |
| 267–269 | 250K eval | 6.500 | 5 NQ | geen guards | — | — | keuze Ferry: meerdere trades (p 2–16%, A-77) |

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

## A-81 — Diversificatie getoetst aan het doel (2 okt 2026)

Meetlatten: breach-kans en gelijkmatigheid eerst, dan dagen tot het stapmaximum. Stroom: Pine-jaar
c92d9 (TP 85, 250/100/500, qty 1), guards op trade-closes, rolling starts om de 3 dagen.

| variant (qty 1) | vers: breach / #1 na / payouts-jr | winstdagen | gelockt $3k: breach / #1 na |
|---|---|---:|---|
| 250/100/500 · alle sessies | 8% / 102 d / 7.120 | 66% | 8% / 42 d |
| 200/75/400 · alle | 8% / 105 d / 6.334 | 68% | — |
| **150/50/300 · alle** | 8% / 112 d / 5.537 | **74%** | **1% / 36 d** |
| 250/100/500 · alleen Globex | **33%** / 75 d / 4.341 | 59% | 13% / 32 d |
| 250/100/500 · entries tot 12:00 | 34% / 71 d | 62% | — |
| qty 2 · 500/200/1.000 · alleen Globex | — | — | 53% ($3k) / 32% ($5k) |

**Conclusies.** (1) **Sessie-split afgewezen voor dit doel.** Alleen-Globex verlaagt de
drawdown in dollars maar verhoogt de breach-kans (vers 8% → 33%, gelockt 8% → 13%, qty 2 tot
53%): minder winst per dag houdt het account langer bij de floor, en op evals/verse PA's is
snelheid naar de lock zelf continuïteit. De correlatie 0,00 uit A-80 is echt, maar helpt het
account niet. (2) **Strakkere caps zijn de enige diversificatie die het doel dient**: 150/50/300
per contract geeft dezelfde verse breach-kans, 74% winstdagen, en op gelockte accounts met
kleine ruimte 1% breach en een snellere #1 (36 tegen 42 dagen), voor ~10% langzamer op verse
accounts. Giveback 50 is op trade-closes niet te onderscheiden van 100; de Pine-intraday-trail
kan anders knippen → export nodig. (3) **Strategie-aanpassingen**: niets gevalideerds verbetert
continuïteit (TP 70, BE, trail allemaal slechter op het jaar); alleen via Pine-exports. (4) Echte
diversificatie (tweede instrument) staat geparkeerd (bord, D-54/38/39).

**Gevraagd aan Ferry:** Pine-exports op het jaar, qty 1, TP 85, trail uit: 150/50/300 en
200/75/400; daarna besluit over een gemengde vloot (bijv. gelockte accounts 150/50/300 × qty).

## A-80 — Live config uit de alerts (2 okt) ≠ advies; fase op ruimte, size op saldo (2 okt 2026)

**Alerts-log 2 okt (`5d1d1`), laatste alert per account:** 013/018 qty 2 met 300/110/900;
022/026/027/032 qty 1 250/100/500; 023 250/130/750; 024 250/100/750; 025/028/029/033/035
300/110/900; 030/031 320/170/1.000; 034 qty 2 320/260/1.000. Evals: 267 op 15 NQ, 268/269 op
12 NQ, 270–273 (50K) op 5 NQ, allemaal phase **Research (none)** → geen halt na pass/breach.

**Toets van die sets** (basis-stroom TP 85, 8 pariteitsmaanden, minuutniveau, per contract):
250/100/500 → 5.230 (61% winstdagen, maxDD 2.659); 250/100/750 → 4.854; 250/130/750 → 3.600;
300/110/900 → 2.815 (maxDD 4.104); 320/170/1.000 → 1.875; 300/110/900 op qty 2 (= 150/55/450
per ct) → 2.650; geen guards → 2.016. Advies: alle PA-charts op 250 / 100 / 500 × qty.

**Fase-logica (verzoek Ferry):** fase uit ruimte tot liq, size uit saldo. A kwetsbaar: ruimte
< 1.300 → qty 1, DLL ⅓ ruimte. B opbouw: ruimte ≥ 1.300, niet gelockt → qty 1, geen DLL
(A-79-optie: qty 2 bij winst ≥ 1.000 én ruimte ≥ 2.000). C gelockt: size op saldo — 55.000 → 2,
57.800 → 3, 58.500 → 4. Payout-poorten los daarvan. In het fleet-doc van 2 okt staat per account
fase, saldo, live config, advies en het verschil.

**Intra-trade trailing live (PMT-payload `trail=1`, 2 okt):** 013, 018, 025, 028, 029, 033, 035
draaien Enable Trailing On met trigger 6,1 pt = 61t en buffer 2,6 pt = 26t (de zeven 300/110/900-
charts). 1–2 okt: vijf trail-exits per account op MFE 63–76t, gesloten op +21 tot +46t, waar de
charts zonder trail op vier van die vijf de TP (+84t) boekten (8 TP tegen 4 TP). A-78: trail 40/60
kostte op het jaar alles (−$414 tegen +$9.342); 61/26 is strakker. **Advies: Enable Trailing Off
op alle zeven.** Break-even staat nergens aan; evals zonder trail/BE.

**Pine-jaar-bevestiging 2 okt (exports 8f3b5 / 8bc3d / f2c7a, 1-10-2025 → 2-10-2026, qty 1, TP 82 / SL 100):**
250/100/500 zonder trail → **$8.087**, 65% winstdagen, maxDD 4.651, verse-breach 8%, payouts
$8.167/jr. 320/100/900 zonder trail → $7.648, 59%, maxDD 5.854, **verse-breach 44%**, $4.489/jr
(gelockt $5k: 2%, $7.736). 300/110/900 **met trail 61/26** (de live set van 013/018/025/028/029/
033/035) → **−$1.207**, 1.689 trail-exits à +$37, maxDD 11.009, breach 58%. Conclusie staat:
alle PA-charts op 250/100/500 × qty, trailing uit. (TP 82 in deze run; TP 85 blijft de referentie.)

**Diversificatie via verschillende day-caps (argument Ferry 2/10) — gemeten op het Pine-jaar:**
correlatie dag-P&L 250/100/500 ~ 320/100/900 = 0,92; alle 91 verliesdagen van de ene set zijn
ook verliesdagen van de andere, gemiddeld verlies identiek (−347 / −346); alleen de winstdagen
verschillen. Vloot van 16 × qty 1: 16 × 250/100/500 → $129k/jr, std $5.385/dag, maxDD $74k;
8 × A + 8 × B → $126k, std 5.481, maxDD 84k; de live-mix (4 A, 5 B, 7 trail) → $62k, maxDD 103k.
**Cap-diversiteit diversifieert niet, hij kost alleen edge.** Wat wél decorreleert binnen de
strategie: de sessie. Globex-deel ~ US-deel dag-P&L correlatie **0,00** (jaar c92d9: Globex
$7.714, US $1.628 per ct). Vloot 8 × alleen-Globex + 8 × alle sessies: $136k (−9%), std 4.472
(−16%), maxDD 64k (−13%); 16 × alleen-Globex: $123k, maxDD 56k. Dat is de enige verdeelsleutel
in deze strategie die de verliesdagen uit elkaar trekt; bevestiging via Pine-export met US- en
IB-venster uit nog nodig (sessiefilter wijzigt entries).

**250K-eval pass-kans per qty (Monte Carlo A-77, winrate 33/42/50%):** 5 NQ 2/6/16 · 8 NQ 3/6/11 ·
12 NQ 4/8/13 · 15 NQ 10/16/23 · 26 NQ 20/25/31%. 15 NQ: één SL = einde, tolerantie 87t, 2 TP's.

## A-79 — Sneller vooruit op verse 50K: dynamische qty-regel (1 okt 2026, voorstel)

**Vraag Ferry 1/10:** accounts boeken geen of trage vooruitgang. **Diagnose:** structureel. De
qty-1-set doet op het Pine-jaar $36 per account-dag; eerste payout (winst ≥ 4.100 + 8 dagen +
5 kwal.dagen) ligt daarmee op ~100 handelsdagen, en de week 21–30 sep was op elke account
negatief (US-sessie). Accounts met ruimte < $1.300 (023, 024, 025, 028, 029) zitten bovendien
aan een DLL die hun herstel knipt; die kunnen niet sneller, alleen overleven of niet.

**Simulatie (Pine-jaar c92d9/a67c4, verse 50K, rolling starts om de 3 dagen, floor incl. pad):**

| beleid | breach | haalt #1 | #1 na | payouts/jr (geen buffer) | met buffer 2.000 |
|---|---:|---:|---:|---:|---:|
| A-78: qty 1, qty 2 na lock én ruimte ≥ 5.000 | 8% | 86% | 104 d | $6.715 | $5.328 (126 d) |
| qty 2 altijd | 76% | 30% | 20 d | $2.797 | |
| **qty 1 tot winst ≥ 1.000, dan 2 zolang ruimte ≥ 2.000, anders terug naar 1** | **10%** | 84% | 96 d | **$11.534** | $8.460 (102 d) |
| qty 2 zolang ruimte ≥ 2.000, anders 1 | 13% | 80% | 93 d | $10.587 | $7.928 |
| qty 1 tot lock, dan 2 ongeacht ruimte | 27% | 73% | 78 d | $9.084 | |

**Voorstel.** (1) Dynamische regel: vers qty 1; vanaf winst ≥ $1.000 qty 2 (500/200/1.000, DLL
600) zolang ruimte ≥ $2.000; zakt de ruimte eronder → terug naar qty 1 (geen DLL als ruimte ≥
1.300). Dat is +72% payouts per account-jaar voor 2 punt extra breach; de eerste payout komt
nauwelijks eerder, de volgende wel. Vervangt de $55.000-drempel voor qty 2 op verse accounts;
gelockte accounts houden A-78. (2) Buffer van $2.000 kost op dit jaar $1,4–3k per account-jaar
en 20+ dagen op #1; de bescherming na een payout is in deze sim niet zichtbaar. Keuze Ferry.
(3) Intraday 4.0 (023: ruimte 274, 024: 443) à $100/maand: kans op #1 vanaf hier verwaarloosbaar;
laten lopen tot breach zonder reset of opzeggen — keuze Ferry.

## A-78 — Exit- en dagguard-varianten (30 sep 2026; replay ongeschikt voor exits, TP 85 blijft, DLL pas vanaf qty 2)

**Data.** Ferry's "3y MGC tickdata" = 1-minuut-OHLC MGC1! 26-09-2023 → 25-09-2026 (1,05 mln
bars). Entries uit de exports `89aa5` (jaar) en `d8ac1` (65 d) op de bars nagespeeld met
alternatieve exits (script `replay.py`, scratchpad). Pariteit: 65 d rauw 53,1% / $5.730 per
contract vs export 53,4% / $6.564 (verschil = commissie/slippage-conventie en same-bar
conservatief: stop vóór TP). **Nov-2025 t/m feb-2026 valt uit** — de bars staan daar op een
ander contract dan de chart van de export (entryprijs 6–9 punten buiten de bar); 8 maanden
over (sep–okt 2025, apr–sep 2026, 152 dagen, 1.720 entries). Same-bar-regels conservatief
(BE/trail geraakt als de bar door het niveau sluit). Sequencing benaderd: entry overgeslagen
als de vorige nagespeelde trade nog open is.

**Exit-varianten, netto per contract (jaar-8-mnd / 65 d), basis TP 85 / SL 100 = 2.016 / 4.367:**

| variant | jaar | 65 d | PF | opmerking |
|---|---:|---:|---|---|
| TP 70 | 4.156 (+106%) | 6.154 (+41%) | 1,06 / 1,16 | winrate 61–62%, robuust op beide vensters |
| BE 80t → +1 (Ferry's idee) | 2.569 (+27%) | 4.914 (+13%) | 1,04 / 1,12 | near-miss-redding bestaat, is klein |
| BE 75t → +40 | 3.268 (+62%) | 5.032 (+15%) | | |
| trail act 40t / buffer 60t | 5.240 (+160%) | 6.608 (+51%) | 1,12 / 1,25 | max DD −44% / −47% |
| **TP 70 + trail 40/60** | **5.827 (+189%)** | **6.907 (+58%)** | 1,13 / 1,27 | winstdagen 56% / 71% |
| trail 30/60 | 5.857 | 3.920 (−10%) | | niet robuust |
| SL 80 / SL 120 / TP 100 / TP 122 | slechter of gelijk | | | |

**Dagguards op minuutniveau (echte intraday-trail incl. open P&L), per contract, 152 d:**
basis 2.016 → 5.653 met 250/25/–/400 (giveback 25!) en 5.232 met de live set 250/100/500/400;
TP70+trail40/60: 5.827 → 7.021 met 250/50/500/150. Activatie 250/ct bevestigd; giveback
25–50 doet het op minuutniveau beter dan 100; cap 500 neutraal; DLL 150–400.

**Qty × strakke $-guards, Apex 50K vers (rolling starts om de 6 dagen, intraday floor incl.
open winst, ladder met 8-dagen/kwal/consistency, geen buffer):** qty 1–2 geschaald: basis
qty 2 met $250/$200/$500/$300 → 0% breach, ≈ $10,7k payouts/jaar; trail40/60 qty 2 met
$500/$100/$1.000/$300 → 0%, ≈ $21,8k. **Qty 4 met vaste strakke guards** (per ct 80/25/125/150
= $320/$100/$500/$600): TP70 → 0% breach, ≈ $22k/jaar; basis → 23%, ≈ $16k. Qty 6–8: breach
≥ 55% bij vrijwel elke set (uitzondering TP70+trail op qty 6, $300/$150/$750/$900: 18%).
**De DLL is de knop bij hoge qty**: 125/50/250 per ct met DLL 300/ct (= $1.200 op qty 4) →
95% breach; dezelfde set met DLL 150/ct (= $600) → 36%. Absolute payout-cijfers zijn ruis
(22 starts, 0,6 jaar); de volgorde niet.

**Voorstel (niet live).** Pine-exports ter bevestiging op 90 d + jaar, verder identiek aan
d8ac1: (a) TP 70; (b) TP 85 + Enable Trailing On, Trail Activation MFE 40, Trail Buffer 60;
(c) TP 70 + trail 40/60. Daarna dagguards: activatie 250/ct, giveback 50/ct, cap 500/ct,
DLL 150–300/ct; en de qty-4-variant $320/$100/$500/$600 als aparte test. Trail-definitie in
de replay: na MFE ≥ 40t staat de stop op hoogste high sinds activatie − 60t, per bar
bijgewerkt; controleer of de Pine-trail hetzelfde doet vóór je de cijfers vergelijkt.

**A-78 — Pine-bevestiging 30 sep (jaar 29-09-2025 → 30-09-2026, exports 286e1/13684/b0e76/0f1d0).**
(1) **Trail 40/60 ingetrokken.** In de Pine kost hij geld: TP85+trail −$414/ct, TP70+trail
+$4.367 tegen +$7.381 zonder trail. 1.871 resp. 1.440 TRAIL-exits met gemiddeld −$4/−$10, plus
~700 extra her-entries na de vroege exits. De +160% uit de replay was een sequencing-artefact
(vaste entry-set; de Pine neemt na een trail-exit nieuwe signalen die de replay niet ziet).
Replay-uitkomsten voor trail/BE zijn daarmee ongeldig; TP-varianten wel bruikbaar (zelfde
entries, exits alleen later/eerder op dezelfde trade).
(2) **TP 70 bevestigd** met de live dagguards 250/100/500 op qty 1: **+$7.381/ct/jaar**, 64%
winstdagen, 60% trade-winrate, 4.156 trades, worst day −1.149/ct, maxDD 4.871/ct. Exacte delta
t.o.v. TP 85 met dezelfde guards ontbreekt nog (export aangevraagd).
(3) **Qty 4 met vaste guards 320/100/600 + TP 70** (export 0f1d0): $30.663/jaar = $7.666/ct,
86% winstdagen, best day $828, maar worst day −$4.035 (geen DLL) → verse 50K breacht 85%.
Met Tradovate-DLL $800 (trade-close-sim): $23.360/jaar, 77% winstdagen, worst −$949, maxDD
$2.845, verse-breach ≈ 43%, payouts ≈ $9k/jaar, #1 na ~39 dagen. Ter vergelijking geschaald
qty 2 (500/200/1.000, DLL 800): $15.589/jaar, breach ≈ 54%, payouts ≈ $8,3k; qty 1 DLL 400:
$7.794, breach ≈ 40%. Op dit jaar breacht een verse 50K in 40–85% van de starts, welke set
ook; de fixed-$-conclusie van A-75 ("vaste guards wurgen per-contract") geldt niet met TP 70
+ activatie 80t/ct. Kandidaat voor gelockte accounts met ≥ $3.000 ruimte (013/018): qty 4,
Pine 320/100/600, TV target $600, TV DLL $800.
**A-78 — correctie 30 sep (exports c92d9 = TP 85 baseline, 973b3 = qty 4 met Pine-DLL).**
(1) **TP 85 blijft.** Zelfde jaar, zelfde guards 250/100/500, qty 1: TP 85 **$9.342/ct**
(3.627 trades, 56% winrate, 66% winstdagen, worst −1.255, maxDD 4.547) tegen TP 70 $7.381
(4.156 trades). TP 85 wint in 9 van 13 maanden. De TP-70-claim uit de replay (+106%) was net
als de trail een sequencing-artefact: eerdere exits geven nieuwe entries die de replay niet
ziet. **Conclusie over de methode: de bar-replay is ongeschikt voor elke exit-wijziging
(TP, SL, BE, trail); alleen Pine-exports tellen.** Replay alleen nog voor dagguards op een
gegeven trade-stroom.
(2) **DLL op qty 1 kost op dit jaar geld en verhoogt de breach-kans**: qty 1 zonder DLL 8%
verse-breach / $7.376 payouts/jr (#1 na ~100 dagen); met DLL 400 42% / $2.860. Reden: 52
dagen ≤ −400 waarvan veel herstellen; de day-trail houdt de worst day op −1.255, binnen de
$2.500. **Regel wordt: geen Tradovate-DLL op qty 1 zolang de day-trail aan staat; DLL vanaf
qty 2 (worst day anders −2.510 > trailing).** Qty 2 geschaald (500/200/1.000) met DLL 600:
$15.966/jr, breach 56%, payouts $6.981, #1 na 25 dagen — verse 50K op qty 2 is op dit jaar
een muntworp; bevestigt qty 1 tot de lock.
(3) **Qty 4 vaste guards 320/100/600 + TP 70 met Pine-risk-gate DLL 800** (973b3): $18.109/jr,
76% winstdagen, worst −949, maxDD 3.061, breach 53%, payouts $4.520. Past in de ruimte van
013/018 (maxDD 3k); TP-85-tegenhanger nog niet getest (export aangevraagd). Geschaald TP 85
qty 4 DLL 800: $28.398 maar maxDD 8.359 → past niet in $5k ruimte.
**A-78 — slot 30 sep (exports 793f1 = qty 4 TP 85 vaste guards, a67c4 = qty 2 TP 85 geschaald + Pine-DLL 600).**
(4) **De vaste qty-4-set is TP-specifiek.** Met TP 85 stort hij in: $8.379/jr (2.095/ct) tegen
$18.109 met TP 70. Mechanisme: activatie $320 < één TP op qty 4 ($340), dus de day-trail armt
na één winnaar en de eerste terugval van $100 sluit de dag; met TP 70 ($280) zijn twee
winnaars nodig. De "fixed-$ wurgt"-bevinding van A-75 is dus een verhouding activatie/TP,
geen qty-effect. Geen vaste-guard-set voor TP 85 zonder nieuwe test (activatie ≥ 1,2 TP).
(5) **Geschaald qty 2 TP 85 (500/200/1.000, Pine-DLL 600)**: $13.869/jr, 58% winstdagen, worst
−689, maxDD 5.673, 53 gate-exits. Verse 50K: 77% breach (niet doen). **Gelockt met $5.000
ruimte: 2% breach, volle ladder 6/6 binnen het jaar, #1 na ~60 dagen.** Met $3.000 ruimte 26%.
Qty 4 TP 70 vast op $3k/$5k ruimte: 2%/0%, eveneens volle ladder — gelijkwaardig, maar vraagt
TP 70 (config-wijziging, OOS-klok). Qty 1 TP 85 gelockt: 0–6%, $7,6–8k/jr, #1 na ~100 dagen.
**Ruimte-eis in de ladder wordt de maxDD van de geschaalde set, niet 3 DLL-dagen:** qty 2 ≈
$5.700 (2% breach bij $5k), qty 3 ≈ $7.700, qty 4 ≈ $8.400 (trade-close-sim op c92d9). Post-lock
is ruimte = balans − 50.100, dus qty 2 vanaf ≈ $55.000, qty 3 vanaf ≈ $57.800, qty 4 vanaf
≈ $58.500 — samen met de consistency-drempels (55.000 / 56.700) is dit de bindende reeks.

**Besluit A-78 (30 sep).** TP 85 / SL 100 blijft; geen BE, geen trail. Verse 50K: qty 1, day-trail
250/100/500, **geen Tradovate-DLL**. Gelockt: qty 2 met 500/200/1.000 en DLL 600 zodra ruimte
≥ $5.000 (balans ≥ 55.000); qty 3 bij ≥ 57.800; qty 4 bij ≥ 58.500 met DLL 4 × SL/ct. Replay
alleen nog voor dagguards op een gegeven stroom; exit-wijzigingen uitsluitend via Pine-exports.
## A-77 — Eval near-miss: intraday trailing vs TP 122t (24 sep 2026, mechanisme bevestigd; trailing-stop = voorstel)

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

## A-76 — Day-trail en DLL herijkt op export d8ac1 (23 sep 2026)

**Bewijs.** TES-MGC-C export `d8ac1` (24 jun–23 sep, qty 4, TP R-multiple 1 = 100t,
exit mode Off, gate Off = rauwe stroom): 1.063 trades, 65 dagen, $26.258, 63%
winstdagen, best-day $4.293, worst −$3.772, max DD op dagsommen $5.107. Guards
gesimuleerd op trade-closes (per contract, ×4 op deze run):

| Variant per contract | Totaal/ct | Winstdagen | Best-day/ct | Worst/ct | Max DD/ct |
|---|---:|---:|---:|---:|---:|
| rauw | 6.564 | 63% | 1.073 | −943 | 1.277 |
| 125 / 50 / 250 (= de ingevulde 500/200/1.000 op qty 4) | 4.668 | 78% | 337 | −943 | 1.277 |
| **250 / 100 / 500** (A-75) | 6.554 | 69% | 594 | −943 | 1.277 |
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

## A-75 — Werkende live-config vastgelegd + schaalregel guards (18 sep 2026)

**Nummering (besluit Ferry 28-09):** het register van deze chat draagt het voorvoegsel
`A-` (A-43, A-75, A-76, A-77 …); nummers blijven staan, alleen het voorvoegsel is nieuw.
`D-`-nummers geeft alleen de Scrum Master uit (`docs/SPRINT.md`). Reikt een A-besluit
buiten deze chat, dan wordt het gemeld in `docs/inbox.md` en krijgt het daar een D-nummer;
de twee verwijzen naar elkaar. Eerdere afgeleverde documenten (fleet-doc 28-09) noemen
nog "A-76/A-77"; lees dat als A-76/A-77.

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

## A-43 — Buffer-gedreven per-account sizing + hard Tradovate-limits (28 aug 2026)

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
