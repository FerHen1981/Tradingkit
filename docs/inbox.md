# Inbox — cross-chat verzoeken (zie werkafspraken §2/§4)

Formaat per item: **van → aan** · datum · status. De eigenaar van de doelmap voert
uit en zet status op `done` met de commit-hash. Niemand bouwt buiten de eigen map.

---

## OPEN

### 1. Geverifieerde commissie per contract uit Cash_History
**Backtest Setup → Middleware App** · 2026-08-19 · status: OPEN

Schuldpunt uit de werkafspraken §6: commissie staat op drie waarden (Pine 0.67/1.55,
backtest 0.52/1.75). `backtest/config.py CONTRACTS` is de single source, maar de
*juiste* getallen komen uit de broker-waarheid — en die is van Middleware
(Tradovate `Cash_History` → `cash_ledger.py`, net gewired in `b317575`).

**Verzoek:** lever per verhandeld contract (NQ/MNQ, ES/MES, GC/MGC, …) de werkelijke
round-turn commissie + fees per venue (Apex/Tradovate, MFFU, FTMO/MT5) uit de ledger.
Eén tabelletje hier als antwoord is genoeg.

**Waarom het urgent is voor het lab:** de commissie beslist mee welke kandidaten de
funnel overleven. Hoogfrequente kandidaten (10-17k trades/jaar op 1m) kantelen van
winstgevend naar verliesgevend tussen $0.52 en $1.75 per side — zolang dit niet klopt
zijn PF-oordelen op die groep onbetrouwbaar.

**Afhandeling daarna:** Backtest Setup werkt `CONTRACTS` bij (de bron), meldt het
hier; Pine Dev draait `tools/gen_pine_firms.py`-achtige sync voor de Pine-kant.

### 2. funded.py leest Apex-regels nog niet uit data/propfirms.json
**Backtest Setup → Backtest Setup (eigen schuld, hier gelogd voor zichtbaarheid)**
· 2026-08-19 · status: OPEN

`backtest/funded.py` heeft `APEX_DD`, payout-ladder en consistency hardcoded;
per §3 hoort dat via `backtest/firms.py` uit `data/propfirms.json` te komen
(firms.py leest die al). Backtest Setup lost dit in eigen map op; geen actie van
anderen nodig. Let op bij Middleware/Pine: tot die tijd kunnen funded-simulaties
in het lab afwijken van de registry als propfirms.json wijzigt.

### 3. ATR-kalibratie voor de MR·FVG engine (Fase 1 un-overfit)
**Pine Dev → Backtest Setup** · 2026-08-19 · status: OPEN

Pine `MEX_EL_TESORO` v7.9.1 stelt `Distance Unit` open met een `ATR`-optie: op
`unitMode = ATR` worden FVG-band, stop, TP en buffers ATR(14)-veelvouden, zodat één
getallenset op elke asset klopt (de un-overfit primitief uit de vastgelegde scope).
Default blijft `Ticks`, dus live is onveranderd.

**Verzoek uit `backtest/`:** (a) reken de huidige MGC-tick-tuning om naar ATR(14)-
veelvouden op 1m — FVG 9–18t, stop 100t, max 130t, TP R-mult 2.5; (b) sweep die
veelvouden op **MGC + ES + NQ** en lever de set die over de drie assets standhoudt.
Doel: bewijzen dat één ATR-set generiek werkt vóór Pine Dev hem als default vastzet.

**Afhandeling daarna:** Backtest Setup levert de multiples hier; Pine Dev zet ze in
de engine en stuurt het bevroren bestand voor de compile-test.

---

### 4. Viewer-rol (units-only) voor `viewer.py` + productie van public-stats.json
**Web → Middleware App** · 2026-08-19 · status: OPEN

De Web-chat heeft een besloten dashboard gebouwd voordat duidelijk was dat
`mex-viewer` al draait. Dat was een duplicaat op **dezelfde host én poort**
(`app.mex-traders.com` → `127.0.0.1:8080`). De service is geschrapt; alleen het
deel dat `viewer.py` nog niet heeft, is blijven staan als module.

**Wat er klaarligt:** `web/handover/mex_units/` — omrekening naar ticks, pips en
R, plus een rolgrens waarbij een `viewer` een payload krijgt waarin geen
bedrag voorkomt. Niet verborgen of op nul, maar afwezig: elke rol bouwt zijn
eigen payload in plaats van dat er één volledig antwoord wordt afgeknipt.
17 tests, die de viewer-payload op veldnaam én op waarde nalopen. Geen
datatoegang in de module; hij krijgt gewone dicts binnen.

Specs komen uit `backtest/config.py CONTRACTS` (§3) — de module houdt bewust
geen eigen kopie en faalt hard als die import niet lukt.

**Verzoek 1 — de viewer-rol.** Neem de module over in `middleware/app/` en hang
er in `viewer.py` een derde toegangsniveau aan, naast owner-wachtwoord en het
read-only token: een gast die alleen units ziet. Voeden vanuit de
gezaghebbende bronnen — trades via `fills_pairing.py`, balansen via
`cash_ledger.py`.

**Verzoek 2 — de publieke momentopname.** `www.mex-traders.com/resultaten` leest
`web/sites/mex/src/data/public-stats.json`. Dat bestand bestaat nu alleen als
voorbeelddata (`"sample": true`, waardoor elke pagina die het rendert een
zichtbare placeholder-melding toont). Er is een taak nodig die het periodiek
schrijft uit dezelfde bronnen, met `roles.for_public()` en
`roles.assert_no_currency()` als laatste controle vóór wegschrijven. De site
doet nooit een API-call — hij leest een bestand — dus er hoeft geen poort open
naar de handelsdata en de publicatie mag bewust vertraagd worden.

**Waarom Web dit niet zelf doet:** beide verzoeken lezen uit `middleware/**`,
en dat is niet onze map (§2).

**Let op bij overname:** `units.py` importeert `backtest.config`. Draait de
middleware met een eigen werkmap, dan moet de repo-root op `sys.path`. Details
in `web/handover/mex_units/README.md`.

**Losse observatie, geen verzoek:** `viewer.py` heeft eigen styling. De
huisstijl uit het merkpakket ligt als tokens in
`web/packages/brand/src/styles/tokens.css`. Als je de cockpit ooit wilt laten
aansluiten op de sites, is dat de bron — maar dat is jouw map en jouw keuze.

## DONE

(nog leeg)
