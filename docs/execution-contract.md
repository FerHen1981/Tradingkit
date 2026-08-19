# Executiepad Pine → receiver → PMT/Tradovate

Feitelijke inventarisatie van `pine/MEX_EL_TESORO.pine` v7.9.1 tegen de git-historie
(v6.8.14 t/m v7.9.1) en `middleware/dotnet-receiver/Program.cs` (branch
`claude/legacy-accounts-scripts-analysis-ui0j6m`). Eigenaar van dit document: Pine Dev.
Alles hieronder is nagetrokken in de code, niet uit herinnering.

## 1. Wat Pine verstuurt

Twee kanalen, en maar één daarvan executeert.

### A. `f_sendExec()` → `alert()` met PMT-JSON — DIT executeert
8 aanroepplekken, identiek in élke versie sinds v6.8.14:

| # | Waar | actie | Betekenis |
|---|---|---|---|
| 1 | cap-lock (payout veiliggesteld) | `close` | alles dicht |
| 2 | long entry | `buy` | LMT of MKT + bracket |
| 3 | short entry | `sell` | LMT of MKT + bracket |
| 4 | pending vervangen door nieuw signaal | `close` | bedoeld als *cancel* |
| 5 | pending expiry / flat-window / day-halt | `close` | bedoeld als *cancel* |
| 6-8 | day-halt, account-halt, flat-window | `close` | alles dicht |

Payload (`f_pmtJSON`): `data` (buy/sell/close), `quantity`, `price`, `dollar_sl`,
`dollar_tp`, `trail`, `trail_stop`, `trail_trigger`, `trail_freq`, `breakeven`,
`order_type` (LMT/MKT), `reverse_order_close: true`, `pyramid: false`,
`multiple_accounts[0].account_id`.

### B. `alert_message=` op `strategy.entry`/`strategy.exit` — executeert NIET
CSV via `f_orderMsg()`. De receiver ziet geen PMT-JSON en behandelt dit als journaal.
Let op: de **per-bar** stop-updates (`strategy.exit` in het BE/trail-blok, regel 1549/1572)
hebben géén `alert_message` — alleen de exit bij fill (1440/1442) heeft die.

## 2. Wat de receiver doet
`POST /signal/{token}` → JSON parsen → **alleen** payloads met `data` + `multiple_accounts`
gaan naar PMT. Account uit `multiple_accounts[0].account_id` kiest Tradovate vs Rithmic
(`MEX_PMT_RITHMIC_ACCOUNTS`). Kill-switch en DRY_RUN zitten hier. Overige payloads:
Discord / journaal / opslag.

## 3. Gap-analyse tegen de gewenste werking

| Gewenst | Nu in code | Status |
|---|---|---|
| Pending overrulen bij nieuw signaal (close + new) | plek 4, `f_sendExec("close")` | ✅ werkt |
| Pending **cancellen** bij expiry (12 bars) via PMT | plek 5 stuurt `data:"close"` | ✅ werkt — **eigenaar bevestigd 19-08: PMT annuleert een werkende order op een `close`-bericht, zoals in eerdere versies.** Geen aparte cancel-actie nodig |
| In positie én niet risk-off → géén nieuwe signalen | `gateOK = isFlat or posRiskOff` | ✅ werkt |
| Na risk-off → gate open **alleen in dezelfde richting** | `gateOK` kent geen richting; een tegengesteld signaal doet `strategy.entry` in de andere richting = **reversal** van de open positie | ❌ **defect** |
| Positie naar BE → PMT verplaatst de stop | bracket-velden uit de entry-payload | ✅ werkt — **eigenaar bevestigd 19-08: de JSON-embed doet dit en doet het nog steeds.** Geen losse alert nodig |
| Trailing verplaatst de stop | idem, `trail`/`trail_trigger`/`trail_stop` | ✅ werkt (zelfde bevestiging) |

**Historische correctie.** BE/trail-updates naar PMT hebben in gééns van de repo-versies
bestaan — v6.8.14 t/m v7.9.1 hebben exact dezelfde 8 `f_sendExec`-plekken. Het ontwerp is
**bracket-based**: `trail_trigger`/`trail_stop`/`breakeven` gaan één keer mee met de entry en
**PMT trailt de Tradovate-stop server-side** (zo staat het ook in commit `5d33e4b`). Het
"werkte" dus via PMT, niet via losse alerts. Of dat voldoende is hangt af van of PMT die
velden honoreert — dat is een receiver/PMT-verificatie, geen Pine-bug.

`gateOpenOnRiskOff` uit v7.3 was een constante `true`; verwijderen in v7.5 was
gedragsneutraal. **Geen regressie**, ondanks dat het op een verlies lijkt.

## 4. Wat er sinds v7.3 wél op het executiepad veranderde

| Wijziging | Versie | Effect |
|---|---|---|
| `calc_on_order_fills=true` | v7.6 | **Groot,** maar **bewust behouden** (besluit eigenaar 19-08). Strategie herrekent op elke fill; dit is het "On order fills" dat in de export-vergelijking de trefkans 81% → 74,6% bracht. Het is het eerlijker uitvoeringsmodel — niet terugdraaien |
| `use_bar_magnifier=true` | v7.6 | alleen backtest-realisme |
| `maxStopSize` default 100 → 130 | v7.8.2 | selecteert bredere setups; raakt welke trades vuren |
| Firm-keys + dagentellers uit registry | v7.7-7.9 | voedt `payoutEligible` → `pmtBlock` → **blokkeert entries** bij wait-for-cap |
| `minQualDayUSD` input verwijderd (nu registry) | v7.8.0 | payout-teller, indirect via `pmtBlock` |
| Titel/`shorttitle` MGC eruit | v7.9.1 | geen |
| `unitMode`/`atrLen` inputs | v7.9.1 | geen (default Ticks = ongewijzigd) |

Propfirm-regels raken dus **wel** de executie, via `pmtBlock`.

## 5. Voorstel: wie beheert welke logica

| Logica | Voorstel | Waarom |
|---|---|---|
| Signaaldetectie (FVG, VWAP, CVD, regime) | **Pine** | heeft de bars |
| Trade-management-intentie (stop/BE/trail/TP-niveaus berekenen) | **Pine** | volgt uit de bars |
| Bracket-uitvoering (stop daadwerkelijk laten meelopen) | **PMT** (server-side) | staat het dichtst bij de order; geen alert-afhankelijkheid |
| **Working-order state** (leeft de limit nog? cancel) | **.NET receiver** | Pine kent alleen wat het *denkt*; de receiver ziet PMT's antwoord |
| Positie-gate (richting, risk-off) | **Pine** | hangt aan de bar-logica, moet vóór de order |
| Account-regels (consistency, dagen, ladder, DD) | **registry → middleware** | reeds zo; Pine leest via codegen |
| Size / day-cap / DLL | **Playbook (middleware)** | rekent uit actuals |

Kern van het voorstel: **Pine stuurt intenties, de receiver voert uit en houdt de
broker-state.** Concreet betekent dat één nieuwe actie in het contract — een echte
`cancel` naast `close` — omdat "sluit positie" en "annuleer werkende order" bij de broker
twee verschillende dingen zijn en Pine ze nu op dezelfde manier verstuurt.

## 6. Beantwoord door de eigenaar (19-08-2026)

1. **`close` ís de cancel.** PMT annuleert een werkende order op een `close`-bericht, zoals
   eerdere versies al deden. Het expiry-pad is dus correct — geen `cancel`-actie in het contract.
2. **De bracket werkt.** `trail`/`trail_trigger`/`trail_stop`/`breakeven` uit de JSON-embed
   worden door PMT server-side uitgevoerd, toen en nu. Geen `move_stop`-intentie nodig.
3. **De richting-gate moet gefixt.** Apex staat niet toe dat er twee tegengestelde orders
   openstaan. Dit is het enige echte defect.
4. **`calc_on_order_fills` blijft aan.** Pine Dev las een eerder antwoord verkeerd en stelde een
   revert voor; de eigenaar heeft dat 19-08 afgewezen. De regel blijft staan.

Netto blijft er één defect over. Zie `docs/proposal-gate-and-exec.md`.
