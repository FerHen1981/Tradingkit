# Live state

Read this first in every chat. Update it last. If it is stale, nothing below it
can be trusted.

_Last updated: 2026-10-04 (Analyses & Data chat)_

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

### Per-account set (5 okt, stand Tradovate 2 okt na sluiting — vervangt 1 okt)

14 PA's (013, 018, 022, 025–035) + evals 275, 276 (50K, vers) en 277 (300K, vers). Weg sinds 30 sep:
PA023, PA024 (Intraday 4.0) en de evals 267–273. Per account op maat (A-84/A-85); schema `fleet_startschema_2026-10-05_v2.pdf` met maandag-checklist.
1–2 okt: PA013 ontving payout #2 ($2.000) en verloor ≈ $800 (qty 2, 300/110/900 + trail) → ruimte 2.026, volgende is #3 $2.500 bij 55.100;
PA018 −$1.419 → ruimte 3.925 → qty 1; PA022 onder safety net; PA025 nog $130 ruimte.

| Account | Fase | Balans | Ruimte | Qty | Pine act/gb/cap | TV target | TV DLL | Status |
|---|---|---:|---:|---:|---|---:|---:|---|
| PA013 | C | 52.126 | 2.026 | 1 | 150 / 50 / 300 | $300 | geen | trail uit; #1 10/9 en #2 ($2.000) begin okt ontvangen; #3 $2.500 bij 55.100 |
| PA018 | C | 54.025 | 3.925 | 1 (was 2) | 150 / 50 / 300 | $300 | geen | trail uit; #1 geblokkeerd tot 58.348 (+4.322). Kans binnen 5 dagen op elke size ≤ 12% bij gelijke breach-kans; qty 1: 11–13% in 40 d / 0–2% breach; qty 2 500/200/1.000 DLL 600: 29% / 10%; qty 3: 52% / 21%; qty 5: 57% / 42% (rolling windows Pine-jaar) |
| PA022 | C | 52.072 | 1.972 | 1 | 150 / 50 / 300 | $300 | geen | +2.028 tot #1 |
| PA025 | A | 47.847 | 130 | 1 | 250 / 100 / 500 | $500 | — | één SL = einde; lot of uit (keuze Ferry) |
| PA026 | A | 50.401 | 1.254 | 1 | 250 / 100 / 500 | $500 | $400 | |
| PA027 | B | 49.522 | 1.377 | 1 | 250 / 100 / 500 | $500 | geen | |
| PA028 | A | 48.316 | 543 | 1 | 250 / 100 / 500 | $500 | $200 | trail uit |
| PA029 | A | 48.243 | 708 | 1 | 250 / 100 / 500 | $500 | $200 | trail uit |
| PA030, 031 | B | 49.2k | 1.31k | 1 | 250 / 100 / 500 | $500 | geen | was 320/170/1.000 |
| PA032 | B | 49.262 | 1.413 | 1 | 250 / 100 / 500 | $500 | geen | |
| PA033 | A | 48.652 | 814 | 1 | 250 / 100 / 500 | $500 | $200 | trail uit |
| PA034 | B | 50.095 | 2.473 | 1 (was 2) | 250 / 100 / 500 | $500 | geen | |
| PA035 | B | 49.875 | 2.177 | 1 | 250 / 100 / 500 | $500 | geen | trail uit |
| 275, 276 | 50K eval | 50.000 | 2.500 | 5 NQ | geen guards, Apex Eval | — | — | lottery p ≈ 1/3 |
| 277 | 300K eval | 300.000 | 7.500 | 35 NQ | geen guards, Apex Eval, goal 20.000 | — | — | one-shot p ≈ 1/4,75 (handoff) |

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

## A-90 — Schalen op drawdown-ruimte, niet op saldo: wat de ruimte wél en niet kan (7 okt 2026)

**Vraag Ferry 7/10:** de fase/qty-logica hangt aan het saldo; moet dat niet aan de ruimte tot de auto-liq hangen, en kan er
een stap tussen vers ($2.500) en de lock ($52.600)? **Mechanisch:** vóór de lock trailt de floor de piek, dus de ruimte is
op elke nieuwe piek precies $2.500 en daartussen minder — hij groeit nooit. Een "tussenstap op ruimte" bestaat vóór de lock
dus alleen in de vorm *"groter sizen zodra je (bijna) op de piek staat"*; ná de lock is de ruimte = saldo − 50.100 en groeit
hij wél, en daar is het schaalmodel al ruimte-gebaseerd (A-84: 2 bij ≥ 3.000, 3 bij ≥ 4.500).

**Simulatie** (Pine-jaarstromen, verse 50K, rolling starts, qty per dag gekozen uit ruimte/lock/winst; vers 50K
hit60/br60 · hit90/br90 · mediaan dagen #1 · P(lock ≤ 90 d) / mediaan dagen tot lock):

| regel | TP 85 (live) | TP 120 |
|---|---|---|
| A · 1 tot lock; na lock 2 bij ≥ 3k, 3 bij ≥ 4,5k (huidig) | 24,6 / 5,7 · 37,7 / 5,7 · 49 d · 58% / 41 d | 48,0 / 16,3 · 65,9 / 16,3 · 40 d · 79% / 29 d |
| C · 2 altijd (referentie) | 30,3 / **64,8** · 19 d | 42,3 / 57,7 · 15 d |
| D · vers 2 bij ruimte ≥ 2.000 | 27,9 / 35,2 · 26 d · 48% / 16 d | 55,3 / 24,4 · 33 d · 75% / 20 d |
| E · vers 2 alleen bij ruimte ≥ 2.400 (op de piek) | 26,2 / 13,1 · 41 d · 60% / 34 d | 52,8 / 18,7 · 37 d · 76% / 24 d |
| F · vers 2 zodra winst ≥ 1.500 én ruimte ≥ 2.000 (laatste stuk naar de lock) | 27,0 / 9,8 · 39,3 / 13,1 · 47 d · 55% / 38 d | 54,5 / 18,7 · 67,5 / 18,7 · 36 d · 80% / 27 d |
| H · na lock al 2 bij ≥ 2.600, 3 bij ≥ 4k | 27,0 / **25,4** · 47 d | 52,0 / **13,8** · 42 d · 80% / 29 d |

**Lezing.** (1) Ferry's intuïtie klopt: de ruimte is de maat, niet het saldo — en het model van A-84 rekent al zo; alleen
het fase-etiket (A < 1.300 · B · C gelockt) is een ruimte-klasse, geen saldo-klasse. (2) **Vóór de lock is er geen veilige
tussenstap.** Elke vorm van qty 2 vóór de lock verdubbelt minstens de breach-kans (6 → 10–35%) voor 1–10 dagen winst op de
mediaan; de minst slechte is F (qty 2 pas in het laatste stuk, winst ≥ 1.500 én op/bij de piek): +1,6 pt hit, +4–7 pt
breach. Onder "continuïteit eerst" niet aan te raden; wie de snelheid wil, neemt F en accepteert het. (3) **Ná de lock
hangt de juiste instapdrempel voor qty 2 af van de TP:** op TP 85 is 2.600 te vroeg (breach 6 → 25%), 3.000 is de grens;
op TP 120 mag het direct na de lock (16 → 14% breach, hit +4 pt). (4) Na een payout zakt de ruimte met het bedrag →
direct afschalen (doctrine blijft). (5) De ruimte-klasse A (< 1.300, één SL-reeks van het einde) blijft qty 1 met DLL;
de DLL helpt op TP 85 (breach 35 → 21% in D vs G) en schaadt op TP 120 — consistent met A-83: alleen waar één dag kan doden.

**Stand 7 okt op de ruimte-regel (A, live TP 85):** 018 (gelockt, 4.762) → qty 3 · 013 (gelockt, 2.559) en 022 (gelockt,
2.485) → 1, qty 2 pas bij 53.100 · 034/035 (vers, 2.395) → 1 · 026/027/030/031/032 (vers, 1.565–1.765) → 1 · 028/029/033
(799–1.071) → 1 + DLL 300. Evals: 276, 278, 280, 282 gepasst → verse PA's op qty 1; 281 gebreacht (47.194 < 47.500);
279 (250K) heeft nog $244 ruimte → één verlies is het einde, laten lopen of resetten (keuze Ferry); 277 = 300K PA (A-88).

## A-89 — Vroeg stoppen is goed; de winst zit in strakker trailen ná 04:00 ET (7 okt 2026)

**Vraag Ferry 7/10:** accounts stoppen al vóór 04:00 ET op +135/ct — optimaal, of valt er later op de dag nog iets te
halen, of in de cap-instellingen? **Sessieprofiel per contract** (laatste jaar; engine TP 120 raw / Pine TP 85 met
guards): Globex 18–02 ET draagt +$27 / +$24 per dag, London 02–07 −$13 / +$5, US-pre −$0 / −$1, RTH +$5 / +$9. **Staat de
dag om 04:00 op ≥ +100, dan is de rest van de dag gemiddeld −$84 tot −$97** (55–58% kans op teruggave, 26–42% kans op
meer dan −150 teruggave). Staat hij tussen 0 en 100: rest +$37 / +$113. Staat hij negatief: rest +$19 / +$81. Dus:
een vroege plus vasthouden is goed, een vroege min laten doorlopen ook (A-83). Uurcijfers (6:00 en 12–13 ET negatief)
zijn geen beleid — uurniveau is OOS-ruis (CLAUDE.md); sessies wel.

**Beleidsvarianten op de doel-meetlat** (post-hoc op trade-closes, qty 1, vers 50K hit60/br60 — 3 jaar · laatste jaar):

| beleid | TP 85: 3 j | TP 85: jaar | TP 120: 3 j | TP 120: jaar |
|---|---|---|---|---|
| 250/100/500 (live) | 8,5 / 13,9 | 18 / 24 | 17,6 / 10,7 | 53 / 15 |
| 150/50/300 | 4,5 / 10,4 | 8 / 13 | 16,5 / 8,0 | 50 / 7 |
| **250/100/500, ná 04:00 giveback 50** | 7,7 / **8,0** | 20 / **6** | 17,9 / 9,9 | 53 / 13 |
| 250/100/500, stop 04:00 als ≥ +100 | 7,7 / 8,0 | **24 / 6** | 19,2 / 13,3 | **61 / 6** |
| 250/100/500, stop 07:00 als ≥ +100 | 7,5 / 12,8 | 23 / 21 | 18,9 / 8,0 | 58 / 8 |

**Lezing.** (1) De guards die de dag vroeg sluiten doen precies het goede; "later nog iets bijdragen" is op een
plus-dag negatief verwacht. (2) De verbetering zit niet in een andere cap maar in **tijdafhankelijk trailen**: na
04:00 ET de giveback naar 50 (of de dag sluiten zodra hij ≥ +100 staat) halveert de breach-kans op het jaar bij gelijke
of hogere hit-kans; over drie jaar is het effect kleiner maar in dezelfde richting. (3) Dit bestaat niet als Pine-input
(één giveback per dag) en niet in Tradovate; het is een Pine Dev-verzoek (giveback-2 vanaf tijdstip) of een
middleware-regel (D-02-gate: na 04:00 ET geen nieuwe entries zodra dag-P&L ≥ +100 × qty). Gemeld in inbox 07-10.
Waarom de accounts vandaag exact op +135 stopten is zonder alerts-log niet te zeggen (op 250/100/500 is +135 niet
gearmed); log gevraagd.

## A-88 — Onderzoeksronde El Tesoro & El Toro op elf 1-minuutdatasets (4 okt 2026)

**Opzet.** Python-engine uit `backtest/` (pessimistisch fillmodel) op MGC, GC, NQ, MNQ, ES, MES, MYM,
MCL, 6E, 6B, 6J (okt 2023 → okt 2026). Twee profielen per markt — Tesoro (TP < SL) en Toro (TP > SL) —
met parameters geschaald op de mediane 1-minuut true range in ticks (MGC 21 · GC 20 · NQ 34 · MNQ 35 ·
ES 6 · MES 6 · MYM 9 · MCL 6 · 6E 2 · 6B 1 · 6J 1). Trappen: A entry-grid (136 sets) · B exit-grid (TP ×
SL) op de top-4 · C dagguards × qty · D ATR-relatief. Finalisten met de volledige engine (intraday
day-trail + Apex-overlay; exacte eval-funnel met floor op open P&L). Meetlat = het doel (A-84):
P(payout #1 binnen 60/90 d) en P(breach), winstdagen, per kwartaal en per jaar. Rapport:
`onderzoeksronde_2026-10-04_tesoro_toro.pdf`; scripts `research.py`, `goalmetrics.py`, `confirm.py` (scratchpad).

**Pariteit (trap 1).** El Tesoro live-config op MGC vs Pine-jaar `c92d9`: 3.566 vs 3.627 trades, 92%
gepaarde instapmomenten, winrate 55,0 vs 55,5, PF 1,02 vs 1,06, winstdagen 64 vs 66, exit-mix 78/69/13
vs 79/69/12 → **poort dicht**. Engine is ≈ $1,5/trade pessimistischer (stop-first). El Toro op NQ: 73 van
74 live-trades op dezelfde minuut geplaatst; exits niet toetsbaar (logs afgekapt) → **export gevraagd**.
Live Pine "Delta engine = Research OHLCV proxy" = de engine-definitie.

**El Tesoro funded (MGC, qty 1, 250/100/500, 375 verse starts, 3 jaar):**

| set (8–23 · c4 · e12 · CVD uit) | trades | net/ct | wd | hit60 / br60 | hit90 / br90 | mediaan | slechtste kwartaal |
|---|---:|---:|---:|---|---|---:|---|
| TP 85 / SL 100 — live | 5.904 | 12.546 | 58,0 | 8,5 / 14,1 | 23,5 / 22,9 | 68 d | −2.775 |
| **TP 120 / SL 100** | 4.684 | 15.455 | 57,8 | **15,7 / 11,5** | 26,9 / 17,3 | 54 d | −4.545 |
| TP 120 · guards 150/50/300 | 3.489 | 14.867 | **66,3** | 8,8 / **5,6** | 20,5 / 14,4 | 64 d | −3.139 |
| TP 100 / SL 100 | 5.214 | 13.924 | 57,6 | 11,2 / 19,2 | 20,3 / 28,8 | 56 d | −2.627 |

Per jaar: 2023/24 alles vlak (range 3–7 ticks, te weinig FVG's ≥ 8); 2024/25 live beter (hit90 14,6 vs
10,6); 2025/26 TP 120 veel beter (hit60 46 vs 18, breach 18 vs 25). Entries doen weinig (live set in de
kop; 6–46 + CVD 3 proxy +40% hits bij TP 85). VWAP-veto uit = −$10k/ct. ATR-relatieve parameters (72
varianten) slechter. Guards × qty bevestigen A-79/A-84 (qty 2 alleen gelockt of met DLL 300/ct).

**Andere markten, Tesoro-profiel (geschaald):** GC-data −27% net vs MGC-data op dezelfde config (twin-
voorbehoud werkt beide kanten op); NQ/MNQ: geen payout op qty 1, 58–88% breach op qty ≥ 2 → af;
ES/MES −$16k…−$23k/ct → af; MYM −$10k → af; MCL −$2k…−$4k, 4 van 12 kwartalen met ≥ 30 handelsdagen → af;
6E/6B/6J: range 1–2 ticks, tick-grid zinloos; 180 ATR-varianten per markt allemaal negatief (beste 6E −$16k, 6B −$5,7k, 6J −$12k per contract, 0% hits) → af. **El Tesoro is een MGC-engine.**

**Eval (exacte funnel, 377 starts, 3 jaar NQ):**

| variant | qty · TP | 50K pass | per jaar | 300K pass |
|---|---|---:|---|---:|
| El Toro live (4–12 · c2 · e9 · CVD 3) | 5 · 122 | 35,5% | 30,5 · 37,0 · 38,3 | 15,9% (35 NQ) |
| **El Toro FVG 19–27 · c4 · e9 · CVD 3** | 5 · 122 | **39,3%** | 35,6 · 43,7 · 40,0 | 21,8% (30 NQ · TP 138) |
| 300K: FVG 19–20 · c4 · e12 · CVD uit | 30 · 138 | 34,5% | — | **24,1%** (IS 24,3 · OOS 25,0; buren 19,6–24,1) |
| live + trailing stop 42/36 + SL 40 (A-87) | 35 · 122 | — | — | 16,4% → geen hefboom |
| El Tesoro MGC one-hit | 37 MGC · 85 | 39,5% | — | — |
| El Tesoro MGC meerdere trades | 3 MGC · 85 | 29,4% (+20% time-out) | — | — |

Sizing is geen hefboom (6·102 / 4·152 / 3·202 → 39,5–41,1%). ES/MES 17–19%, MYM/MCL/6E/6B/6J 0–2% → af. Toro-exits
als funded-engine (MNQ) → 50% winstdagen, negatief → El Toro blijft eval-only.

**Aanbevelingen (alle onder voorbehoud van een Pine-export vóór live; elke wijziging reset de OOS-klok):**
(1) Funded MGC: **TP 120** bij ongewijzigde entries, guards 250/100/500 × qty; 150/50/300 voor gelockte
accounts met kleine ruimte. (2) Eval 50K NQ: **FVG 19–27, confirm 4, expiry 9, CVD 3**, 5 NQ, TP 122.
(3) Eval 300K: **30 NQ, TP 138**, brede FVG-band (19–27 of 13–37), confirm 4. (4) Alternatief eval 50K:
El Tesoro op MGC met 37 contracten (39,5%). (5) Niet: ES/MES, MYM, MCL, Tesoro op NQ, ATR-parameters,
trailing stop op de 300K. Gevraagd aan Ferry: Pine-jaarexports TP 120 (MGC) en El Toro FVG 19–27 (NQ),
beide naast de huidige sets op hetzelfde venster.

**Aanvulling 5 okt — pariteit El Toro dicht (export `6ae27`).** Ferry leverde de gevraagde export: TOR-NQ-HF,
FVG 19–27, confirm 4, expiry 9, Delta-filter On (native `requestVolumeDelta`, LTF 1) streak 3, TP 122 / SL 90,
5 NQ, Research, 5 okt 2025 → 5 okt 2026. Vergelijking met de engine op dezelfde config en hetzelfde venster
(CVD-proxy): **1.931 vs 1.901 trades (+1,6%), 96% / 98% gepaarde instapmomenten, winrate 42,7 vs 43,2, PF
0,98 vs 1,01, exits SL 1.090/TP 808 vs 1.063/816, maandelijkse aantallen gelijk** → poort dicht. Netto wijkt
af ($−48,7k vs +$23,6k op 5 ct ≈ 1,5 tick per trade): het pessimistische fillmodel (stop-first + 1 tick) weegt
op NQ zwaarder dan op MGC; rangordes blijven bruikbaar, dollars niet. Twee bijvangsten: (1) de Pine draaide
de **native** delta en de engine de **OHLCV-proxy**, en toch 96% pairing — op dit script maakt de delta-bron
geen materieel verschil (raakt D-66/SM-05); CVD uit zou 3.151 trades geven, dus de filter zelf doet wél iets.
(2) Rechtstreeks uit de export: P(TP ∧ MAE < 100t) = **42,9%** op het jaar (bovengrens zonder tussentijdse
retrace); de exacte engine-funnel zegt 40,0% voor deze set tegen 38,3% voor de live set op hetzelfde jaar.
Daarmee is aanbeveling (2) van A-88 — FVG 19–27 / confirm 4 / expiry 9 op de 50K-evals — door een Pine-export
gedekt. Nog open: de MGC-export met TP 120 (aanbeveling 1) en, voor de 300K, een export met TP 138.

**Aanvulling 5 okt, tweede export `e609f` (live-entries 4–12 / confirm 2 / expiry 9, Delta-filter UIT, TP 122 / SL 90,
5 NQ, zelfde jaar).** Engine vs Pine: 5.808 vs 5.641 trades (+3%), 95% / 98% gepaard, winrate 43,2 vs 43,4, PF 1,00 vs
1,02, maandaantallen gelijk → tweede bevestiging van de poort. Uit de exports zelf: P(TP ∧ MAE < 100t) = 43,2% (live-
entries zonder delta) vs 42,9% (19–27 met delta) — op de loterij-meetlat gelijk. Exacte funnel op dít jaar (119 starts,
foutmarge ≈ ±4,5 pt): live-entries CVD uit 39,5% · live-entries CVD aan 38,7% · 19–27 c4 CVD aan 40,3% → **op één jaar
niet te onderscheiden**; het voordeel van 19–27 (3 jaar: 39,3 vs 35,5%, elk jaar 2–6 pt) is klein en komt uit de
twee eerdere jaren. Wat wél overeind blijft op dit jaar: **300K 30 NQ · TP 138 · 19–27 = 23,5% tegen 16,0%** voor de
live set op 35 NQ. Opvallend: zonder delta-filter nette de Pine +$149k op 5 ct over het jaar tegen +$23,6k met 19–27 —
de delta-filter kost op NQ meer winst dan hij breaches spaart, maar voor een one-hit-eval telt alleen de eerste trade.

**Aanvulling 5 okt — MGC-export TP 120 (`9dc3f`) sluit aanbeveling (1).** Ferry's export: TP 120 / SL 100, 8–23 c4 e12,
Delta uit, day-trail **300/100/600** (de qty-2-schaal, niet 250/100/500), qty 1, Developer, 5 okt 2025 → 5 okt 2026, 3.196
trades. Engine op dezelfde config: 3.062 vs 3.141 trades (tot 25/9), winrate 47,2 beide, exits gelijk, 90–92% gepaard →
poort dicht. **Pine tegen Pine, zelfde jaar, per contract** (TP 85 = `c92d9` met 250/100/500):

| | trades | win | net/ct | wd | worst dag | maxDD | vers 50K hit60 / br60 | hit90 / br90 | mediaan | gelockt $3k hit40 / br40 |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|
| TP 85 (Pine 250/100/500) | 3.589 | 55,4 | 8.251 | 65% | −1.255 | 4.547 | 25 / 6 | 37 / 6 | 50 d | 69 / 5 |
| TP 120 (Pine 300/100/600) | 3.196 | 47,2 | 10.279 | 61% | −1.493 | 8.243 | 47 / 16 | 63 / 16 | 41 d | 76 / 11 |
| TP 120 + 250/100/500 (post-hoc) | | | | 63% | | | 45 / 16 | 70 / 16 | 48 d | 80 / 11 |
| **TP 120 + 150/50/300 (post-hoc)** | | | | **73%** | | | **64 / 14** | **76 / 14** | 49 d | **82 / 7** |

Kwartalen TP 120: 2025Q4 −4.431 (TP 85: −2.032), 2026Q1 +6.446, Q2 +2.001, Q3 +6.899. **Lezing:** TP 120 verdubbelt
tot verdrievoudigt de kans op payout #1 en wint op gelockte accounts, tegen een hogere breach-kans (14–16% i.p.v. 6%) en
een dieper slecht kwartaal; met 150/50/300 is hij op alle assen behalve breach beter dan de live set. Spoort met de
engine over 3 jaar (A-88), met dezelfde kanttekening dat 2024/25 andersom uitviel. Per account (A-84): TP 120 +
150/50/300 waar de ruimte ≥ ~$1.500 is; TP 85 alleen waar één SL het einde is. **Elke omzetting reset de OOS-klok.**
Ferry levert geen NQ-export met TP 138: de 300K-eval is op de one-hit-set gefund (account 277 → PA).
**Verse 300K PA (277) op de Pine-jaarstromen** (aangenomen: trailing 7.500, lock bij +7.600, payout #1 $3.500, 30%,
8 dagen / 5 × ≥ $50 — Apex-300K-regels nog te bevestigen; guards per contract × qty): TP 120 + 150/50/300 → qty 3:
hit60 71% / breach 14%, mediaan 45 d, slechtste dag −4.480; qty 4: 76% / 16%, 34 d, −5.973; qty 5: 79% / 15%, 27 d,
−7.466 (= de hele trailing in één dag → alleen met DLL). TP 85 qty 3: 23–26% / 6%. **Voorstel:** TP 120, qty 3 met
450/150/900 tot de lock, daarna qty 4 (600/200/1.200); geen DLL op qty ≤ 4, wel op 5. Zelfde script-lijn als de
50K's (fase-scripts A-86), alleen qty en guards anders.

**Aanvulling 7 okt — 250K-eval (vraag Ferry).** Exacte funnel, 3 jaar NQ, 377 starts, trailing 6.500 / goal 15.000,
max 27 contracten, one-hit (TP × qty × $5 − commissie ≥ 15.000):

| entries | qty · TP | floor | pass 3 j | per jaar 23/24 · 24/25 · 25/26 |
|---|---|---:|---:|---|
| live (4–12 · c2 · e9 · CVD 3) | 27 · 122 | 48t | 17,8% | 11,0 · 24,4 · 18,3 |
| live | 25 · 122 | 52t | 19,6% | — |
| **FVG 19–27 · c4 · e9 · CVD 3** | 27 · 122 | 48t | 25,2% | 26,3 · 23,5 · 25,8 |
| FVG 19–27 | 25 · 122 | 52t | 25,7% | 27,1 · 23,5 · 26,7 |
| **FVG 19–27** | **22 · 138** | 59t | **27,1%** | **25,4 · 27,7 · 27,5** |
| FVG 19–27 | 20 · 152 | 65t | 27,3% | — (marge $138) |

SL 45 i.p.v. 90 kost 1–2 punt (sluit trades die binnen de floor zouden overleven) → SL 90 laten staan, de floor
regeert. **Advies 250K: El Toro, FVG 19–27 / confirm 4 / expiry 9 / CVD 3, 22 NQ, TP 138, SL 90, phase Apex Eval,
trailing 6.500, goal 15.000** → ~1 op 3,7 tegen ~1 op 5,6 op de live set. Zelfde mechanisme als de 300K (A-88):
grotere gaps en een iets ruimere floor.

## A-87 — 300K-eval op El Toro HF: één TP blijft de beste route, de trailing stop is de enige hefboom (4 okt 2026)

**Data.** 75 unieke live NQ-trades uit de vier alerts-logs (2 sep–2 okt, dedupe over accounts, MFE/MAE
per exit): 24 TP (32%), 51 SL. MFE/MAE komen uit de Pine op barbasis (SL-trades tonen mediaan MAE 75 bij
een stop van 90), dus de echte excursies zijn groter en elk cijfer hieronder is eerder te gunstig.
**Structuur.** 300K: target 20.000, trailing 7.500, max 35 contracten. Target ÷ trailing = 2,67 (50K: 1,2).
Op 35 NQ ligt de Apex-floor 42,9 ticks onder de beste open stand; de SL van 90 bestaat daar feitelijk niet.

| variant | P(pass) | basis |
|---|---|---|
| **35 NQ, één TP 122 (huidig)** | **13–19%** | 14 van 24 TP-trades hebben MAE < 43; 19% negeert tussentijdse retrace, 13% rekent 31% retrace (handoff) |
| 35 NQ, TP 116–118 | idem | één extra trade in 75 haalt 116; verschil is ruis; netto bij 116 = $20.192 (marge $192) |
| 33–34 NQ | 20% bovengrens | floor 44–45t; 33 NQ TP 122 netto $20.028 — te dun |
| El Toro meerdere trades, 8–30 NQ | 0–8% | live-reeks heeft −23t verwachting per trade; elke extra trade is een extra kans om te verliezen |
| El Toro TP 100 / SL 60 / SL 45 op 12–17 NQ | 0–3% | kortere SL raakt vaker (MAE), lagere TP wint te weinig |
| El Tesoro MGC 6–15 ct, geen guards | 5–12% pass / 88–95% breach | Pine-jaar, trailing 7.500 op trade-close-piek |
| 35 NQ + Pine trailing stop act 42t / buffer 36t + SL 40t | 14–34% → **16% (correctie 4 okt, exacte engine-funnel over 3 jaar NQ: 16,4% tegen 15,9% zonder trail)** | 24 van 51 SL-trades hadden MFE ≥ 42 en worden ≈ +6t i.p.v. account dood, maar de volgende pogingen op hetzelfde account falen bijna even vaak; de optimistische bovengrens van 34% was te hoog |

**Correctie 4 okt (A-88, onderzoeksronde op de 3-jaars NQ-data met de Python-engine, exacte intraday-floor):** 35 NQ één TP = **15,9%** pass over 377 verse starts; met trail 42/36 + SL 40 **16,4%**. De trail is dus geen hefboom van betekenis; de 300K blijft een loterij van ~1 op 6. Het onderstaande is de oorspronkelijke lezing op de 75 live-trades.

**Lezing.** (1) Op 35 NQ is de trailing stop geen afweging meer maar de enige hefboom: zonder trail is
elke trade met MFE ≥ 43 die omkeert het einde van het account; mét trail (buffer 36 < floor 43, 7 ticks
voor slippage op 35 contracten) wordt dat een kleine winst en blijft de poging open. Wat je verliest zijn
TP-trades die na 42t eerst 36t terugvallen en daarna alsnog de 122 halen — die eindigen nu op +6t in
plaats van pass; het aandeel is zonder pad-data niet te meten (vandaar 14–34%). (2) Zet de Pine-SL op 40t
zodat engine en Apex hetzelfde zien; een SL-hit op 40t (−$7.000) laat $500 over en is praktisch ook het
einde. (3) Lagere size met meer trades verliest op de 300K altijd: de live-winrate van 32% bij 122/90 is
negatief, en El Tesoro op MGC breacht 9 van de 10. (4) Verwachte pogingen per funded 300K: 3 (optimistisch)
tot 7 (pessimistisch) met trail, 5–8 zonder. **Script:** `MEX_EL_TORO_NQ_HF_INTRA_v1_0_0` heeft `Enable
Trailing`, `Trail Activation MFE`, `Trail Buffer`, `Fixed Stop`, `Eval Profit Goal` en `Trailing Drawdown`
als inputs — geen Pine-wijziging nodig. Zelfde conclusie als A-77 voor de 50K (act 95 / buf 10), nu
gekwantificeerd. **Test vóór live** blijft: El Toro-export TP 122 / SL 40 / trail 42-36 naast de huidige,
tel TP-exits en trail-exits.

## A-86 — BT_90_days (6 jul–2 okt) + fase-varianten van het Pine-script (3 okt 2026)

**Exports (v3.2.2, TP 85 / SL 100, BE Off, trailing stop Off, Trail + cap, risk-gate Off, 65 dagen,
guards als vaste dollars, dus níet × qty):**

| set | qty | trades | net | net/ct | winstdagen | best / worst dag | maxDD |
|---|---:|---:|---:|---:|---:|---|---:|
| 250/200/1.000 (`89de0`, `d70a8`) | 1 | 908 | 6.532 / 6.613 | 6.532 | 75% | +848 / −834 | 979 |
| 320/270/1.000 (`af520`) | 1 | 1.063 | 5.468 | 5.468 | 66% | +848 / −834 | 1.009 |
| 250/200/1.000 (`1bd17`) | 2 | 582 | 8.199 | 4.100 | 80% | +1.021 / −1.668 | 1.957 |
| 250/200/1.000 (`4bfd2`) | 3 | 410 | 7.715 | 2.572 | 85% | +1.055 / −2.523 | 2.956 |
| 250/200/1.000 (`ca714`) | 4 | 317 | 11.313 | 2.828 | 88% | +1.059 / −2.547 | 2.547 |
| 320/270/1.000 (`7bcca`) | 4 | 394 | 10.741 | 2.685 | 83% | +1.059 / −2.547 | 3.126 |

**Account-simulatie op deze stromen (rolling starts, horizon 40 d, haal-% / breach-% / mediaan dagen
tot de volgende trede):**

| export | qty | vers 50K (#1 $1.500) | gelockt, winst 3.100 (#1) | gelockt, winst 5.000 (#2) |
|---|---:|---|---|---|
| `89de0` | 1 | 55 / 0 / 28 | 89 / 0 / 8 | 100 / 0 / 8 |
| `1bd17` | 2 | **65 / 0 / 20** | 96 / 0 / 8 | 100 / 0 / 8 |
| `4bfd2` | 3 | 38 / **60** / 20 | 95 / 5 / 8 | 100 / 0 / 8 |
| `ca714` | 4 | 41 / **50** / 14 | 91 / 9 / 8 | 100 / 0 / 8 |

**Lezing op het doel.** (1) Een vaste cap van $1.000 op hogere qty geeft veel groene dagen (88% op
qty 4) omdat de cap de winstkant knipt, maar de verlieskant blijft 100t × qty per trade: de slechtste
dag blijft −2.5k op qty 3/4 en dat is op een vers 50K-account een breach (60% / 50% in 40 dagen).
Op gelockte accounts met ≥ $3k ruimte is diezelfde set wél bruikbaar (5–9% breach, 8 dagen tot de
trede). Dit bevestigt A-83: de DLL hoort alleen waar één dag kan doden, en op qty ≥ 3 vers hoort hij
er dus bij of de qty omlaag. (2) **Qty 2 met vaste 250/200/1.000 is in dit venster de beste verse
set** (65% haal in 40 d, 0% breach, mediaan 20 d) — beter dan qty 1 (55%, 28 d). Dat spoort met A-79.
(3) Giveback 200 (vast) versus 100 per contract: in dit venster geen verschil van betekenis op qty 1
(6.532 vs A-85 250/100/500 op 30 d); het verschil zit in de cap. (4) **Caveat: 6 jul–2 okt is één
positief regime**; de 0%-breaches zijn venstergebonden. Het jaar (A-81) geeft 8% vers op qty 1.
Daarom het voorstel hieronder voor 90-daagse batches over drie jaar.

**90-daagse batches over de 3-jaarsdata.** Niet met de Python-replay: die is alleen geldig voor
dagguards op bestaande entries (A-78), en er bestaan geen Pine-entries voor 2023–2025. Twee routes:
(a) in TradingView het `validFrom`/`validUntil`-venster per kwartaal zetten (12 kwartalen × 2–3
sets, Deep Backtesting) en exporteren; wij zetten ze dan in één tabel per kwartaal (haal/breach/
mediaan); (b) Backtest Setup draait de Python-engine op dezelfde kwartalen — via de SM, hun map.
Route (a) kan vandaag; (b) is de duurzame.

**Fase-varianten van het script (geleverd, buiten de repo — `pine/**` is van Pine Dev).** Zes kopieën
van EL TESORO v3.2.2 → v3.3.0, zelfde engine, alleen defaults en naam/shorttitle/`mwStrategy`:

| script | shorttitle | fase | qty | day-trail act/gb/cap | risk-gate |
|---|---|---|---:|---|---|
| EL PATRON | `PAT-MGC-A` | A — ruimte < $1.300 | 1 | 150 / 50 / 300 | On, DLL 300 |
| EL TESORO | `TES-MGC-B` | B — vers / ruimte ≥ $1.300 | 1 | 250 / 100 / 500 | Off |
| EL DORADO | `DOR-MGC-B2` | B2 — vers, ruimte ≥ $2.000 (A-79) | 2 | 300 / 100 / 600 | On, DLL 600 |
| EL MATADOR | `MAT-MGC-C2` | C2 — gelockt, ruimte ≥ $2.000 | 2 | 300 / 100 / 600 | On, DLL 600 |
| EL REY | `REY-MGC-C3` | C3 — gelockt, ruimte ≥ $3.000 | 3 | 450 / 150 / 900 | On, DLL 900 |
| EL LEON | `LEO-MGC-C4` | C4 — gelockt, ruimte ≥ $4.000 | 4 | 600 / 200 / 1.200 | On, DLL 1.200 |

Gemeenschappelijke defaults gelijk aan de live config (A-75): All sessions, TP Fixed 85 / SL 100,
BE Off, trailing stop Off, Trail + cap met Activation + giveback, FVG 8–23, confirm 4, streak 5,
Delta filter Off, phase Developer, firm preset Off, consistency 30, kwalificatiedag $50, payout-buffer
0, risk-gate alleen DLL (`rgTriggerT` 0). Afwijkingen van v3.2.2-defaults die zijn rechtgezet:
R-multiple 2,25 → Fixed 85; Liquidity Core → All sessions; qty 4 → per fase; Funded → Developer;
50%/$250 → 30%/$50; CVD-filter aan → uit (live-stand; botst met CLAUDE.md "CVD never disabled",
besluit bij SM/Pine Dev); streak 6 → 5; FVG 11–16 → 8–23; confirm 0 → 4; firm preset aan → uit.
Wissel van fase = ander script op het chart; de guards van A-76 schalen per contract, de vaste-cap-
variant van dit BT_90-pakket is via de inputs te zetten. Bestand: `MEX_fase_varianten_v3_3_0.zip`.
Gemeld aan de SM in `docs/inbox.md` (3 okt).

**Aanvulling 4 okt — eval-variant (zevende script, `TOR-MGC-E`).** El Tesoro op een 50K-eval, Pine-jaar
8bc3d, trailing 2.500 op de trade-close-piek (de echte Apex-floor volgt de open piek en is strenger),
goal 3.000, pass/breach binnen 60 d: qty 1 42/33 (mediaan 40 d) · qty 2 41/59 (15 d) · qty 3 34/66
(5 d) · qty 4 30/70 (3 d) · qty 5 32/68 (3 d); qty 5 met vaste cap 1.000 44/56 (4 d). Day-guards
helpen op een eval niet (geen consistency-regel) behalve die ene cap-variant, één jaar, dus geen
besluit. Eval-defaults: qty 3, Day-profit exit Off, risk-gate Off, phase Eval, firm preset
`apex_50k_legacy_eval` (250K: qty 8 + `apex_250k_legacy_eval`; 300K heeft geen preset, goal staat
hard op 3.000 → Developer of preset vragen bij Pine Dev). Op NQ blijft TOR-NQ-HF de one-TP-lottery
(p ≈ 1/3, A-77).

## A-85 — Fleet-doc 5 okt v2: per account op maat, uit fills + dashboard + varianten (3 okt 2026)

**Feiten 3/10.** Apex-dashboard: alle 14 PA's zijn Legacy 50K Tradovate met dezelfde regels (safety
net $52.600, 8 dagen, 5 × ≥ $50, consistency 30%) — de eerdere melding van 50%/$250-accounts is
ingetrokken. PA013 payouts: #1 $1.500 (10 sep), #2 $2.000 (1 okt). Fills 27/9–3/10 (14 accounts,
FIFO, sluiten op de dashboard-balansen): elke account negatief; **1 okt −$800 per contract op elke
account** (013 qty 3 −2.309, 018 qty 4 −2.773, 022 qty 2 −1.312) — fills tonen op 013/018 een
hogere qty dan de alerts (2): PMT-multiplier controleren.
**Ferry's varianten (exports 3 okt):** laatste 2–3 weken negatief op elke set: 250/100/500 −537,
150/50/300 −1.443, 320/150/750 −364 per ct; 30 d (24 aug–2 okt): 250/200/1.000 +2.536 (73%
winstdagen, maxDD 979), qty 4 vast 320/270/1.000 +1.119/ct (83% winstdagen, worst −2.547).
Niet op het jaar getest; kandidaten zodra de jaar-exports er zijn.
**Model (`tailor.py`, stand 3 okt, score haal-40d − ½ breach-40d):** 022 → qty 2 · 300/100/600 ·
DLL 600 (73% / 19%, mediaan 19 d); 018 → qty 4 · 600/200/1.200 · DLL 1.200 (73% / 19%, 20 d) of
qty 3 · 450/150/900 · DLL 900 (66% / 11%, 26 d); 013 (→ #3 $2.500, cyclusdag 1) → qty 2 ·
300/100/600 · DLL 600 (66% / 17%, 28 d); 034 → qty 2 · 300/100/600 · DLL 600 (42% / 26%); 035
idem (28% / 43%); 026/027/030/031/032 (ruimte ≈ 1.300) → qty 1 · 150/50/300 · DLL 300 (0% in 40 d,
11–13% in 60 d, breach 25–35%); 025/028/029/033 (ruimte < 820) → geen set met waarde (breach
88–100% in 60 d). Caveat: in het huidige verliesregime verliest 150/50/300 het meest (knipt de
goede dagen, de slechte blijven); het model kiest hem op jaarniveau voor kwalificatiedagen en
breach-kans. Doc: `fleet_startschema_2026-10-05_v2.pdf` (vervangt 5 okt v1) met maandag-checklist.

## A-84 — Van generiek naar per account: settings op cashflow (3 okt 2026)

**Besluit Ferry 3/10:** per account bepalen welke qty en act/gb/cap (en of een DLL) het snelst
naar het eerstvolgende stapmaximum leiden, op basis van ruimte tot liq, best-day sinds laatste
payout, de regels van dat account (consistency 30% óf 50%, kwalificatiedag $50 óf $250) en de
payout-stand. Koers op cashflow, niet per definitie op accountbehoud; verschillende settings per
account zijn een bijkomende spreiding. Feiten verwerkt: 013 staat ná payout #2 ($2.000, begin
okt), dus volgende is #3 $2.500; consistency en kwal.minimum verschillen per account (lijst per
account nog aan te leveren; default 30% / $50).

**Methode (`tailor.py`, scratchpad):** per account alle 24 sets (qty 1–4 × 150/50/300, 250/100/500,
320/100/900 per ct × DLL geen/3 SL) op rolling windows van het Pine-jaar (8bc3d, TP 82);
meet P(stapmaximum gehaald binnen 20/40/60 d) en P(breach); score = haal-40d − 0,5 × breach-40d.
Fresh floor trailt de piek; gelockt floor vast op −ruimte; poorten 8 dagen, 5 kwal.dagen op het
account-minimum, consistency op het account-%.

**Uitkomst stand 2 okt (default 30%/$50), beste set en haal/breach binnen 40 d:**
013 (gelockt, ruimte 2.026, → #3 $2.500): qty 2 · 300/100/600 · DLL 600 → 66%/17%, mediaan 28 d.
018 (ruimte 3.925, best 2.504): qty 4 · 600/200/1.200 · DLL 1.200 → 73%/19%, 20 d; qty 3 ·
450/150/900 · DLL 900 → 66%/11%, 26 d. 022 (ruimte 1.972): qty 2 · 300/100/600 · DLL 600 →
73%/19%, 19 d. 034 (vers, ruimte 2.473): qty 2 · 300/100/600 · DLL 600 → 42%/26%, 38 d (qty 1:
0% in 40 d, 5% breach). 035 (2.177): qty 2 idem → 28%/43%; qty 1 → 0%/5%. 026/027/030/031/032
(ruimte 1.250–1.400, onder start): qty 1 · 150/50/300 · DLL 300 → 0% in 40 d, 11–13% in 60 d,
breach 25–40%. 025/028/029/033 (ruimte < 820): breach 88–100% binnen 60 d bij elke set — geen
cashflow-waarde meer; laten lopen als lot of afstoten. **Patroon:** waar één dag kan doden
kiest de score tóch een DLL (A-83 bevestigd); strakke caps (150/50/300 × qty) winnen op haal-kans
omdat kwalificatiedagen sneller vol zijn; ruime caps (320/100/900) zijn sneller maar breachen meer.
Nog niet verwerkt: per account 50%-consistency en $250-kwal.minimum (voorbeeld op 022: zelfde
set, haal-kans gelijk) — lijst van Ferry nodig.

## A-83 — Waarde van de DLL en van de cap, getoetst aan het doel (3 okt 2026)

**Stelling Ferry:** een DLL vertraagt alleen (stoppen op verlies haalt het herstel weg); een cap
heeft wél waarde voor consistency boven een bedrag x. **Meting** (Pine-jaar c92d9, 250/100/500 × qty,
zelfde trades, met/zonder Tradovate-DLL op trade-closes, rolling starts):

| situatie | zonder DLL: breach / payouts-jr | met DLL 300–400/ct: breach / payouts-jr |
|---|---|---|
| vers 50K, qty 1 | **8% / 7.462** | 33–43% / 2.837–3.839 |
| vers 50K, qty 2 | 76% / 4.078 | 56–61% / 6.084–6.813 |
| gelockt $3k, qty 1 | 8% / 11.791 | **0% / 9.262–10.401** |
| gelockt $3k, qty 2 | **11% / 20.290** | 44–48% / 11.677–12.737 |
| gelockt $5k, qty 2 | 8% / 21.213 | 1–19% / 17.419–21.235 |
| gelockt $5k, qty 3 | **10% / 20.711** | 43–44% / 14.639–15.403 |

**Conclusie.** Ferry heeft gelijk op de hoofdregel: de DLL knipt herstel-dagen weg (52 dagen ≤ −400
op het jaar, de meeste herstellen) en verlaagt daarmee zowel het tempo als — door de lagere
cumulatieve stand — meestal ook de overleving. **Een DLL heeft alleen waarde waar één dag de
account kan doden:** fase A (ruimte < de slechtste dag van de set, $1.255 op qty 1) en verse
accounts op qty 2 (slechtste dag −2.510 > trailing 2.500). Overal elders: geen Tradovate-DLL.
Bij gelockt qty 1 met kleine ruimte is DLL 300 een lichte continuïteitswinst (8% → 0%) voor 12%
minder payouts — keuze per account. **De cap** heeft geen dollarwaarde (cap uit = cap 500, A-76)
maar wél consistency-waarde: hij houdt de best-day onder 30% van de winst bij aanvraag. Regel:
cap per dag ≤ 0,3 × verwachte winst bij de eerstvolgende aanvraag; 500/ct volstaat tot qty 2,
en een account met een al hoge best-day (018: $2.504) mag tot die waarde. De day-trail
(activatie/giveback) is wat de winstdagen van 51% naar 66% brengt; dat is de continuïteitsknop,
niet de DLL. **Besluit A-83:** Tradovate-DLL alleen in fase A en op verse qty-2-accounts;
fase-B/C-accounts zonder DLL; cap 500/ct (fase C 300/ct), of hoger tot de consistency-grens.

## A-82 — Volledige analyse alerts-log 1–2 okt (`3ed21`, 3 okt 2026)

**Stand van de config op vrijdagavond:** niets omgezet. Laatste entry-payload 2 okt 19:40 UTC:
trail=1 op 013, 018, 025, 028, 029, 033, 035; guards nog 300/110/900 (die zeven), 320/170/1.000
(030/031), 320/260/1.000 qty 2 (034), 250/100/500 (022/026/027/032). Evals 268–274 phase
Research (none). 4 webhook-timeouts = Discord-embeds, geen PMT-orders.

**Live-resultaat 1–2 okt per set (per contract, dezelfde trades):**

| set | accounts | exits | TP / SL / trail | P&L per ct (2 dagen) |
|---|---|---:|---|---:|
| 250/100/500, geen trail | 022, 026, 027, 032 | 12–17 | 7–8 TP / 4 SL | **+150 tot +330** (022 −515 door 1/10) |
| 300/110/900 + trail 61/26 | 013, 018, 025, 028, 029, 033, 035 | 24 | 5 TP / 12 SL / 6 trail | **−620 tot −780** |
| 320/170/1.000, geen trail | 030, 031 | 20 | 11 TP / 9 SL | −16 |
| 320/260/1.000 qty 2 | 034 | 9 | 5 TP / 3 SL | +106 |

De trail-charts namen drie keer zoveel SL's (12 tegen 4): elke trail-exit op +21 tot +46t gaf
een her-entry die in de US-sessie verloor. Verschil met de 250/100/500-charts: ≈ $900 per
contract in twee dagen. 030/031 lieten de dag open tot in de middag en gaven de ochtend terug.
Uur-profiel MGC (alle accounts, per ct): 00h +1.343, 03h +1.476, 11h +1.469 tegen 06h −1.967,
12h −959, 14h −2.978. 191 Day-trail-halts, 184 geblokkeerde signalen na een halt (de guards
werken zoals bedoeld).

**Evals 1–2 okt:** 268 (12 NQ) +1.486 (TP, SL); 269 (12 NQ) −11.354 (2 SL, dood); 270 (5 NQ)
−4.731 (2 SL, dood); 273 −2.440; 274 (5 NQ) **4 SL's = −9.762 op een account dat na de eerste
al dood was** — phase Research (none) stopt niet; 271 +469. Zeven 50K/250K-evals weg in twee
dagen; alleen 275/276/277 over.

**Advies voor het doel (continuïteit, dan tijd tot stapmaximum):** (1) maandag vóór 18:00 ET
de checklist uit `fleet_startschema_2026-10-05.pdf`: trail uit op de zeven, fase C op
150/50/300, fase B/A op 250/100/500, 034 naar qty 1; (2) evals op phase Apex Eval met trailing en
goal, zodat een dode account geen orders meer stuurt; (3) US-middag blijft de verliespost maar
geen sessieschakelaar (A-81: verhoogt breach); sample-check 16 okt; (4) PA025 ($130 ruimte):
beslissen; (5) geen verdere config-wijzigingen tot de Pine-exports 150/50/300 en 200/75/400 er
zijn.

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
