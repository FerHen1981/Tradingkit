# Wat er op TradingView draait

_Eigenaar: Pine Dev · D-103, spoor C ("alleen versies")._
_Dit is een conventie plus een tabel, geen bouwwerk. Handmatig plakken blijft zoals het is._

## Waarom dit bestand bestaat

De repo weet welke versie er in `pine/` staat. Niemand weet welke versie er **op de chart**
staat — dat is een handmatige plakactie en die laat geen spoor na. Als een script zich anders
gedraagt dan de repo doet vermoeden, is de eerste vraag altijd "welke versie hangt er eigenlijk
op die chart?", en het antwoord kostte tot nu toe een rondje zoeken in de scriptinstellingen.

Twee kolommen dus: wat de repo draagt (dat vul ik) en wat er op TradingView hangt (dat bevestigt
Ferry na het plakken). Lopen ze uit elkaar, dan is dat zichtbaar in plaats van vermoed.

## Conventie

1. **Versienummer leeft in het script.** `var string currentVersion = "vX.Y.Z"`, direct boven
   `strategy()`. Dat is de enige waarheid; de bestandsnaam zegt niets.
2. **Elke gedragswijziging bumpt het nummer** en krijgt een regel in het historieblok bovenin
   het script. Weergave of commentaar alleen: patch. Gedrag: minor. Nieuwe motor: major.
3. **Na het plakken vult Ferry de rechterkolom** — versie + datum. Eén regel, geen proza.
4. **Loopt de kolom achter, dan is dat het antwoord**, niet een reden om te gokken.

De versie is ook live af te lezen zonder dit bestand: hij staat in de scripttitel op de chart
(`MΞX EL MATADOR · MES PROD EOD · v3.13.1`) en in de CONFIG-kaart in Discord (`ver=v3.13.1`).

## Stand

| Script | Shorttitle | In de repo | Sinds | Op TradingView | Geplakt op |
|---|---|---|---|---|---|
| MEX_EL_REY_MNQ_PROD_EOD | `REY-MNQ-P` | v3.13.1 | 03-11 | **compileerfix** — `acctStartMissing` las `acctStarted` vóór zijn declaratie (CE10272), dus v3.12.0 én v3.13.0 compileerden niet; de lint heeft nu ook een gebruik-voor-declaratie-check | nee — het script liep nog nergens |
| v3.13.0 | 03-11 | **compile-patch** — de `Account start`-default was de niet-const `timestamp`-vorm (CE10123), v3.12.0 compileerde nergens; de lint heeft nu een const-defval-check · **tabel B op EL TESORO** (All sessions · FVG 8/23 · confirm 4 · Delta uit · TP Fixed 85 · giveback-2 50@04:00 · dagstop 5 · `apex_50k_legacy_pa`), de andere twaalf ongewijzigd · **visuals**: FVGNaN in het entry-label opgelost en het tijdvenster is niet langer hetzelfde grijs als een getest FVG-vak | **ja, hele vloot** |
| v3.12.0 | 03-11 | **§2A van de v3.12.0-instructie** — de payout-poort zet `pmtBlock` niet meer (payout-gereedheid is een kaart, orders gaan door) · nieuwe input **`Account start`** zodat de balans vanaf de echte accountstart telt in plaats van vanaf `validFrom`; default in de toekomst en een niet-ingevulde chart handelt niet · PAYOUT-kaart meldt "script-balans, niet Apex" · **§2B eerste deel:** de day-exit-guards zijn **per contract** (defaults 150/50/300, dus qty 3 → 450/150/900) op de negen PA-scripts, met een waarschuwing op de chart als een chart nog opgeslagen totalen draagt | **ja, hele vloot** |
| v3.11.0 | 08-10 | **D-154** vier dagstops in groep 7, **alle vier default uit**: max verliezen op rij · max winsten op rij · eerste verlies boven +X · giveback-2 vanaf een uur. Voeden `dayHalted`, dus de bestaande HALT-machinerie blijft ongewijzigd; `dexStop=` staat in de CONFIG-regel | **ja, hele vloot** — nieuwe inputs, ook met alles uit |
| v3.10.0 | 08-10 | **D-148** vast payout-maximum per accountgrootte en **geen** maximum vanaf payout 6 (`f_firmLadder` draagt beide registry-vormen; geen maximum = `na`, niet 0) · **D-139** een onbekende `accountPhase` blokkeert entries in plaats van alle poorten te openen, met een rood label op de chart | **ja, hele vloot** — akkoord Ferry 08-10 |
| v3.9.0 | 06-10 | **D-126** de payout-ladder komt uit de registry (`f_ladderCap` → `f_firmLadder`) · **D-125** `pmtBlock` hangt op `payoutReady` i.p.v. op de cap alleen — deadlock weg · **D-124** `useWaitForCap` is een input, default `true` · **poort** `gen_pine_firms.py` faalt nu als een `f_firm*` geen call-site heeft, en vond meteen `f_firmMinPayout` | **ja, hele vloot** — één reset voor alle drie, want ze raken dezelfde poort |
| v3.8.0 | 29-09 | **D-110 stap 2** — `dllHit` is weg; één dagrem over. `acctDLL` blijft als weergave (D-96). Een halt op de firmawaarde heet voortaan "Daily Loss" | **nee** — de rem is niet losser geworden, alleen de dubbele weg; de klok staat sinds v3.6.0 op nul |
| v3.7.0 | 29-09 | **D-110 stap 1b** — de firmalimiet doet mee IN de eigen rem: `min(SL × stops × qty, firm_dll)`. Daarmee halteert de eigen rem per definitie op of vóór de firmalimiet en is `dllHit` strikt overbodig — dat opent stap 2. De derde term (ruimte × fractie) blijft een middleware-signaal | **nee** — de klok staat sinds v3.6.0 al op nul en deze versie zet hem niet opnieuw (besluit Ferry 29-09) |
| v3.13.1 | 03-11 | — | — |
| MEX_EL_REY_MNQ_PROD_INTRA | `REY-NQ-PI` | v3.13.1 | 03-11 | — | — |
| MEX_EL_MATADOR_MES_PROD_EOD | `MAT-MES-P` | v3.13.1 | 03-11 | — | — |
| MEX_EL_TESORO_MGC_CON_EOD | `TES-MGC-C` | v3.13.1 | 03-11 | — | — |
| MEX_EL_PATRON_MGC_AGG_EOD | `PAT-MGC-A` | v3.13.1 | 03-11 | — | — |
| MEX_EL_LEON_MYM_PROD_EOD | `LEO-MYM-P` | v3.13.1 | 03-11 | — | — |
| MEX_EL_LEON_MYM_CON_EOD_Q2 | `LEO-YM-CE` | v3.13.1 | 03-11 | — | — |
| MEX_EL_LEON_MYM_CON_INTRA_Q2 | `LEO-YM-CI` | v3.13.1 | 03-11 | — | — |
| MEX_EL_BANDIDO_MYM_HF_EOD | `BAN-MYM-H` | v3.13.1 | 03-11 | — | — |
| MEX_EL_TORO_NQ_SNIPER_INTRA | `TOR-NQ-SN` | v3.13.1 | 03-11 | — | — |
| MEX_EL_TORO_NQ_HF_INTRA | `TOR-NQ-HF` | v3.13.1 | 03-11 | — | — |
| MEX_EL_TORO_ES_FAST_INTRA | `TOR-ES-FI` | v3.13.1 | 03-11 | — | — |
| MEX_EL_TORO_GC_SNIPER_EOD | `TOR-GC-SN` | v3.13.1 | 03-11 | — | — |

**De rechterkolom staat bewust leeg.** Ik weet niet wat er op de charts hangt en dat verzin ik
niet. Vul hem bij de eerstvolgende plakronde; een streepje betekent "niet bevestigd", niet
"oud".

## Versiehistorie van de vloot

| Versie | Datum | Wat er veranderde | Zet de OOS-klok op nul |
|---|---|---|---|
| v3.6.0 | 29-09 | **D-110 stap 1** — Ferry's eigen dagrem staat AAN met de formule `100 × 4 × qty`, als drie inputs plus een override. De firm-rem (`dllHit`) blijft bewust staan; stap 2 wacht per script op `pine/tools/owner_dll_check.py` | **ja, hele vloot** — een rem die aan gaat is een config-wijziging, geen plumbing |
| v3.5.0 | 29-09 | **D-108** nul betekent geen limiet (`dllHit` eist `acctDLL > 0`, `consistencyPct <= 0` is geen regel) + firmablokken hergegenereerd · **D-107** één `f_sendExec("close")` per bar en de vier halt-paden sturen de **werkelijke** positie in plaats van `t_qty` | ⚠️ **deels — beslissing SM/Ferry.** D-107 is plumbing: `strategy.close_all()` is niet aangeraakt, de backtest is bit-voor-bit gelijk. D-108 is dat **niet** voor de evaluaties: die verliezen de halt op −$1.000 |
| v3.4.0 | 07-09 | Eén handelsvenster per script: `validFrom` + `validUntil`, vier verspreide datum-inputs eruit (item 31 / D-71) | ja, hele vloot |
| v3.3.0 | 26-08 | CONFIG-kaart op beide kanalen · payout-dagtellers uit de registry · TORO Discord-naam en config-inhoud | ja |
| v3.2.0 | 26-08 | Overhaul uitgerold naar alle dertien: drie-laags tabel, ARMED-kaart, getekende tijdvensters, trade-annotaties op eigen venster | ja |
| v2.3.2 | 25-08 | `breakeven_offset` in `f_pmtJSON` (D-44) | nee, plumbing |

Volledige toelichting per versie staat in het historieblok bovenin elk script.
