# Input-herstructurering v2 — mijn interpretatie + openstaande vragen

> Pine Dev · 25-08 · **spec in wording.** Ferry leverde de doelstructuur; dit is hoe ik
> die lees. Nog niets gebouwd. Alle labels en tooltips worden **Engels**.

## De doelstructuur (14 groepen, in deze paneelvolgorde)

| # | Groep | Inhoud |
|---|---|---|
| 0 | — | Tradovate Account ID |
| 1 | — | Reference Timezone |
| 2 | Trading Boundary | dag-grens **+ RTH/ETH** |
| 3 | Time Gate | Market Regime \| Liquidity Core \| Custom · Force Flat 16:55–18:00 default aan |
| 4 | TRADE — Position Sizing | Distance Unit, ATR, Sizing Mode, Fixed Qty, Risk per Trade, Allow Fractional, Max Qty Cap |
| 5 | TRADE — Entry & Stop | Entry Mode, Limit Expiry, Stop Mode, Max Stop Distance, Fixed Stop |
| 6 | TRADE — Management | TP Mode, R-Multiple, TP Units, BE toggle/trigger/offset, Trail toggle/activation/buffer, FVG valid |
| 7 | ACCOUNT — Management | Day Cap Mode, Day Trail Model (= Activation + giveback), Activation, Giveback, Daily Hard Cap, Daily Level Scaling (= Fixed USD) |
| 8 | ACCOUNT — Guard | Drawdown Model, Phase, Trailing DD, Daily Loss Limit, Consistency, Min Payout, Min Profit, Live Sync, Use Model Preset → Program, MAE Guard + Base/After-safety-net/Margin, Lock Cost Buffer |
| 9 | SIGNAL — Filters | CVD toggle + Engine (Proxy/TradingView) + Lower TF + Streak, FVG toggle + Min/Max + Validation window, VWAP · **NIEUW: BBWP, EMA+Length, Volume Profile (POC), Discount/Premium, MFI, Long/Short** |
| 10 | SIGNAL — Alerts | Routing toggles, PMT Token, PineConnector ID/symbol/risk, Middleware Token, Strategy Name (= script title), Alert-when: payout cap, signal blocked, config on first bar |
| 11 | VISUALS — Strategy | Dashboard toggle/location/theme/text size/layout + toggles voor signals, TP/SL levels (incl. fills), order levels, unfilled orders, trade labels, PnL/MFE/MAE, DLL/cap/payout/breach/trail-events |
| 12 | VISUALS — Indicators | FVG (filled/unfilled/both), FVG (all/in range), filters valid, time gate open, trade gate open |
| 13 | DEVELOPER — Settings | Entry start toggle + datum/tijd, stop toggle + datum/tijd, Test Balance, Test Model (Preset/Custom) |

**Leidend principe van Ferry:** *staat het er niet tussen, dan hoeft het er niet in* — qua
input en mogelijk ook qua functionaliteit.

## Het werk valt in drie soorten, en ze hebben niet hetzelfde risico

**A. Herordenen en hernoemen** — nul gedragsrisico. Groepen, volgorde, Engelse labels.

**B. Weghalen** — nul gedragsrisico zolang elke verwijderde input zijn huidige default als
constante terugkrijgt (de regel uit `CLEANUP_PROPOSAL.md`). Hier vallen de 14 dode
schakelaars en de 79 uur-/dagvinkjes onder.

**C. Nieuw bouwen** — **wél gedragsrisico, en het botst met "bestaande logica onaangetast".**
Hieronder vallen: RTH/ETH, zes nieuwe regime-vensters, en de zes nieuwe signaalfilters
(BBWP, EMA, POC, Discount/Premium, MFI, Long/Short). Een veto dat trades tegenhoudt
verandert per definitie de signalen, en daarmee vervalt elke bevroren meting.

> **Mijn voorstel voor C:** bouwen als **inert** — aanwezig, zichtbaar, default **uit**, en
> in die stand aantoonbaar zonder effect (dezelfde export voor/na). Activeren is dan een
> aparte onderzoeksronde per filter, via de pijplijn. Zo krijg je de knoppen nu, zonder dat
> de vloot zijn bewijs verliest.

## Operationele consequentie die je vooraf moet weten

Een herstructurering van deze omvang **reset de opgeslagen instellingen op elke chart**.
TradingView koppelt bewaarde waarden aan de volgorde en identiteit van de inputs; die
veranderen allebei. Gevolg: na het plakken staat elk script op zijn defaults en moet je
per chart opnieuw instellen, en **elke alert die op die scripts hangt opnieuw aanmaken**.

Je hebt gisteren net alle alerts opnieuw gemaakt. Het is dus verstandig dit in één keer te
doen en daarna niet meer aan de inputvolgorde te komen.

## Besluiten Ferry 25-08 — de vragen zijn beantwoord

| # | Besluit |
|---|---|
| C | Nieuwe filters **werkend bouwen maar default OFF**. Ze grijpen alleen in als ze aangevinkt zijn, dus de bevroren config blijft ongemoeid. |
| 1 | idem — werkend, uit |
| 2 | Vensters hieronder voorgesteld; **de tijden moeten in de input-labels zichtbaar zijn** |
| 3 | Uurraster blijft als handmatig blackout-gereedschap. **17:00 blijft staan** voor toekomstige markten |
| 4 | RTH/ETH raakt **alleen de sessie/dag-grens**, niet de entries. Entry-filtering als notitie voor later |
| 5 | **Developer** = het huidige "Research (none)". **Custom** = accountregels handmatig, firm preset genegeerd |
| 6 | Ging over **Bot Name**, niet over de middleware-sleutel: Bot Name neemt de titel uit de scriptheader over |
| 7 | Roll/OpEx/news **weg** · MEX Policy preset **weg** · **Skip Monday weg** (oude aanname, de statistiek bepaalt dat zelf) · **Eval-tracking weg** (Custom dekt het, en het is onduidelijk wat het doet) |
| 8 | Daily risk-gate hoort onder **ACCOUNT — Guard** |
| 9/10 | **EL REY eerst**, daarna de rest |

### Meegenomen: de openstaande wijziging uit inbox 20

Dit is de reden dat de scripts sowieso aangepast moesten worden, en hij gaat mee in deze ronde:

1. **De daily risk-gate uit D-45** (DLL + trail op sessie-P&L, venster, reset op de CME-roll)
   zit alleen in `pine/MEX_EL_TESORO.pine`. Komt nu in alle scripts, onder ACCOUNT — Guard.
2. **De registry-koppeling uit v7.9.5.** `f_firmRules` levert `_fkDD` / `_fkMax` / `_fkDLL`
   maar niemand leest ze, dus `dllHit` rekent op de handmatige `acctDLL` en een
   Intraday-programma wordt als EOD gerekend. Wordt `ddModelEff` / `acctTrailEff` /
   `acctDllEff`, precies zoals in TESORO v7.9.5.

### En één defect dat besluit 6 meteen dicht

**Alle negen v1_0_0-scripts dragen `botName = "MΞX ΞL TΞSORO"`.** Elke Discord-kaart van
PATRON, REY, LEON, MATADOR en BANDIDO komt dus binnen onder de naam TESORO — zichtbaar in de
alertlog van 24-08, waar `PAT-MGC-A` meldingen stuurde als TESORO. Bot Name uit de header
halen lost dat in één keer op voor de hele vloot.

## Voorstel Market Regime — negen vensters, tijden in ET

De **eerste drie bestaan al en blijven exact zoals ze zijn**, want `Liquidity Core` is
gedefinieerd als precies die drie en voedt de live time-gate. Daar mag niets aan schuiven.

| Venster | ET | Grondslag |
|---|---|---|
| Globex reopen | **18:00 – 19:00** | heropening na settlement *(bestaat)* |
| London | **02:00 – 05:00** | Londen open t/m Europese ochtend *(bestaat)* |
| US | **07:00 – 12:00** | pre-cash t/m late ochtend *(bestaat)* |
| Asia | **19:00 – 02:00** | Tokio-sessie, loopt over middernacht |
| Initial Balance | **09:30 – 10:30** | eerste uur na de cash open |
| NY AM | **09:30 – 11:30** | ochtendtrend |
| Lunch | **11:30 – 13:00** | liquiditeitsdip |
| NY PM | **13:00 – 15:00** | middagsessie |
| Power Hour | **15:00 – 16:00** | slotuur richting settlement |

Twee dingen om te weten:

- **US overlapt bewust met Initial Balance, NY AM en Lunch.** De vensters worden ge-OR'd, dus
  overlap is onschadelijk; het geeft je een grof blok naast fijnere. Wil je dat niet, dan
  knip ik US terug naar 07:00–09:30 — maar dan **verandert `Liquidity Core` van betekenis**
  en vervalt de vergelijkbaarheid met alles wat daarop gemeten is.
- **Asia loopt over middernacht** (19:00–02:00), dus die test anders dan de andere acht. Dat
  is code, geen keuze, maar het is de plek waar zo'n venster stuk kan gaan.

## Openstaande vragen (beantwoord 25-08 — hierboven)

1. **De zes nieuwe filters** (BBWP, EMA, POC, Discount/Premium, MFI, Long/Short): inert
   bouwen zoals hierboven, of meteen werkend? *Voorstel: inert.*
2. **Market Regime** — ik heb drie vensters met tijden (London 02:00–05:00, US 07:00–12:00,
   Globex reopen 18:00–19:00 ET). Jij noemt er negen. Geef je de exacte ET-tijden voor Asia,
   Lunch, Power Hour, NY AM, NY PM en Initial Balance, of zal ik ze voorstellen volgens
   marktconventie en jij corrigeert?
3. **Custom = Days & Hours "zonder 1700"** — lees ik als: het uurraster blijft bestaan als
   *handmatig blackout-gereedschap*, niet als optimalisatievlak, en uur 17 laat je weg omdat
   Force Flat dat al dekt. Klopt dat?
4. **RTH/ETH** — bepaalt dat de **dag-grens** (waar sessie-P&L en de dagteller resetten), of
   filtert het **entries**, of allebei?
5. **Phase (Funded, Eval, Custom, Developer)** — is Developer het huidige "Research (none)"?
   En wat doet **Custom**: alle accountregels handmatig, dus firm preset genegeerd?
6. **Strategy Name = script title** — de middleware mapt accounts op deze sleutel
   (`accounts.yaml`). Automatisch afleiden verandert hem van `GC` naar de scripttitel en
   **breekt die mapping** tenzij Middleware meegaat. Akkoord dat ik dit eerst als verzoek
   naar Middleware App stuur in plaats van het eenzijdig te wijzigen?
7. **Vier blokken staan niet in je lijst maar doen wél iets.** Wat wil je ermee?
   - **Roll/OpEx/news factory** (`GROUP_EVT`, 8 inputs, master default uit) — *voorstel: weg.*
   - **MEX Policy preset / Fleet Matrix** (`polPreset`) — overlapt met jouw "Use Model
     Preset → Program". *Voorstel: weg, want de firm preset dekt het.*
   - **Skip Monday open** (default aan, blokkeert ma 00:00–02:00 ET) — *voorstel: behouden
     onder Time Gate; het is een echte liquiditeitsregel.*
   - **Eval-tracking, CAP-LOCK en de payout-ladder** — deels gedekt door Min Payout /
     Consistency. *Voorstel: behouden, maar zonder eigen inputs waar de registry al beslist.*
8. **De daily risk-gate uit D-45** (DLL + trail op sessie-P&L, met venster) staat niet in je
   lijst. ACCOUNT — Management noemt Day Cap en Day Trail, maar niet de DLL-gate. Hoort die
   erin, en zo ja onder groep 7 of 8?
9. **Bereik** — geldt de herstructurering voor alle dertien scripts, of eerst de negen
   v1_0_0 en de vier TORO's later?
10. **Uitvoering** — eerst alleen MATADOR, export vóór/ná trade-voor-trade vergelijken, en
    pas daarna de rest in één ronde? *Voorstel: ja.*
