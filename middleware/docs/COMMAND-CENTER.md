# CIO Command Center — haalbaarheids- & fit-analyse

De visie (het "CIO Multi-Portfolio Trading Command Center") tegen onze **werkelijke
datastroom** gelegd: wat kan **nu**, wat kan **later mits we een databron toevoegen**, en wat
is **voorlopig geblokkeerd**. Dit is geen bouwplan — het is de eerlijke kaart die bepaalt in
welke volgorde het bouwplan zin heeft.

> Kernconclusie: de visie splitst schoon in **twee helften**. De **analyse-helft**
> (performance, attributie, expectancy, MAE/MFE, strategie/instrument/tijd, drawdown uit
> realized, executie/slippage) kunnen we grotendeels **nu** bouwen — we hebben de per-trade
> data al. De **kapitaal- & live-risico-helft** (economisch kapitaal, saldi, DD/survival-
> buffers, marge, unrealized P&L, payouts/fees, evaluatie/funded-economics) hangt op **data
> die we nog niet hebben**: live saldi, kasstromen, en marktprijzen.

---

## 1. Waar het allemaal op draait: welke data hebben we?

**Data die we NU al per trade produceren** (routed-log + Fills-CSV → Notion):

account · prop firm (Apex) · fase (funded/eval) · strategie (El___/framework) · asset ·
instrument (symbool/contract) · richting · entry/exit-tijd · entry/exit-prijs · qty ·
**gross P&L** · commissie (CSV) · **initiële risk = |entry−SL|×pointvalue×qty** (SL zit in de
FILL-kaart!) · **R-multiple = P&L / initiële risk** · **MAE/MFE (ticks)** · holdingtijd ·
sessie/uur/weekdag (uit tijd) · exit-reden (SL/TP/TRAIL) · **signaalprijs → entry-slippage** ·
regelstatus (RISK OFF / BLOCKED-kaarten).

**Data die we NIET hebben** (en die de tweede helft blokkeert):

- **Account-saldo / equity / high-water-mark / marge** — geen Tradovate-API, geen saldo-feed.
- **Kasstromen**: eval-fees, activation-fees, payouts, reset-kosten, stortingen/opnames.
- **Live marktprijs** voor open posities → geen unrealized P&L, geen live exposure.
- **Markt-/volatiliteitsregime** en een economische kalender (CPI/FOMC/NFP) als databron.
- **Setup-tagging, screenshots, notities** per trade (nu niet gestructureerd vastgelegd).

Belangrijke nuance: voor de **MT5/FTMO-kant draait al MetaAPI** in de stack — dáár zijn saldi
en fills wél via API beschikbaar. Voor de **futures (Apex/Tradovate)** kan saldo alleen
*gereconstrueerd* worden (startsaldo + cumulatieve realized ± kasstromen) — een benadering,
expliciet te markeren, nooit als harde NAV.

---

## 2. Kan NU — de analyse-helft (data-ready)

Deze secties kunnen we bouwen op de data die er al is; geen nieuwe bron nodig.

| Visie-sectie | Waarom het nu kan |
|---|---|
| §17 Portfolio Performance (gross/net/realized, MTD/QTD/YTD, PF, expectancy, avg R, max/avg DD) | alles uit de trade-historie; DD uit de **realized**-equitycurve per account/strategie |
| §18 Performance Attribution (firm/account/strategie/asset/instrument/richting/sessie/tijd) | trades zijn multidimensionaal filterbaar → cross-filter + drilldown |
| §19–20 Strategy Command Center + §31 MAE/MFE (+ **MFE-capture %**) | MFE/MAE zitten in de EXIT-kaart; R-multiple afleidbaar |
| §20 Strategy Health (rolling expectancy/PF/winrate/DD, percentiel-t.o.v.-eigen-historie) | puur uit trade-reeks; "14e percentiel"-inzichten zijn rekenwerk |
| §21 Strategy × Account / × Firm / × Asset / × Instrument-matrices | groeperen van bestaande velden |
| §22–23 Asset & Instrument Analytics (per NQ/ES/GC…, long/short, sessie) | idem |
| §28 Drawdown Intelligence (op **realized**-basis, incl. percentiel) | realized-equitycurve per niveau |
| §29 Trade Database met ORDER/EXECUTION/POSITION/TRADE | fills = executions (CSV), gepaarde trades = trade-niveau |
| §30 Execution — **entry**-slippage + commissie-kosten-% | signaalprijs vs fill; commissie uit CSV (exit-slippage = deels, zie §4) |
| §32 Expectancy Engine ($ en R, per elke dimensie, **met sample size**) | volledig rekenbaar |
| §33 Time Analytics (weekdag×uur heatmaps, metric-switch) | uit timestamps (we hebben zelfs al een `/heatmap`-skill) |
| §39 Performance Calendar (dag/week/maand, klik → dag-review) | realized per dag (Recap bestaat al) |
| §42–43 Universal Drilldown + Comparison Mode | contextbehoud over de bestaande dimensies |
| §5–6 Global header + filterbar, §13 Account Matrix, §55 navigatie | UI bovenop dezelfde `/api/state`-laag |

**Randvoorwaarde die we goedkoop kunnen toevoegen:** *setup* en *market regime* als
**handmatige/afgeleide tag** per trade (kolom in de Trade Journal) — dan werken §21/§34 ook.

---

## 3. LATER — mits we één databron toevoegen: de **Account Ledger**

Dit is de **hoeksteen** van de hele tweede helft. Eén nieuwe, door onszelf te bouwen bron:

**(a) Account-snapshots** (§47): per account periodiek balance · equity · HWM · DD-niveau ·
resterende buffer · marge. **(b) Kasstromen** (§48): payout · opname · storting · fee · reset ·
activation · handmatige correctie — strikt gescheiden van trading-P&L.

Bronnen voor die ledger, in oplopende moeite:
- **FX/FTMO-accounts:** via **MetaAPI** — saldi/equity/HWM automatisch. ✅ echt live mogelijk.
- **Futures/Apex-accounts:** startsaldo + cumulatieve realized ± kasstromen → *gereconstrueerd*
  saldo (benadering, gemarkeerd). Payouts/fees moeten **ingevoerd** worden (Notion-DB of import).
- **Fees/payouts/evals:** een kleine ledger die jij bijhoudt (of importeert uit firm-portals).

Zodra die ledger er is, komt in bereik:

| Visie-sectie | Ontgrendeld door de ledger |
|---|---|
| §8/§58 **Economisch kapitaal vs notional** (fees geïnvesteerd, payouts, net economic P&L) | kasstromen + notional-config |
| §11–12 Account Command Center + **Health Score** + **Survival Buffer** | saldo + firm-regels (firms.py) → live buffers |
| §10 **Prop Firm Rule Engine** (DD/DLL/consistency/payout-drempels, configureerbaar) | `backtest/firms.py` bestaat al als data — koppelen aan live saldo |
| §14 Prop Firm Economics (**ROI op prop-fees**) | fees vs payouts |
| §15 Evaluation Analytics (funnel, conversie, kosten per passed account) | eval-status + fees |
| §16 Funded Analytics (**account-longevity/survival** — cruciaal inzicht) | account-levensduur + payouts |
| §26–27 Risk Command Center + **Risk Budgeting** (regel-risico, buffers, budgetten) | buffers uit saldo; budgetten zijn config |
| §36 Prop Firm Concentration | notional/payout/kapitaal per firm |

**Risk-to-stop (open risico) kan al deels nu:** we kennen open posities + hun SL → initiële
risk in $ is rekenbaar zónder saldo. Wat wél saldo vergt is DD-**buffer** en unrealized P&L.

---

## 4. Voorlopig GEBLOKKEERD — vergt een capaciteit die we (nog) niet hebben

Niet "onmogelijk", maar geblokkeerd tot er een extra feed/pad is:

| Visie-sectie | Blokkade | Mogelijke workaround |
|---|---|---|
| Live **unrealized P&L** & §24 Exposure (delta/notional live) | geen live prijs-feed | risk-to-stop tonen i.p.v. unrealized; prijs-feed later |
| **Close/flatten vanaf web** (§ owner-controle) | geen order-API (Tradovate) | halt/kill kan al; MetaAPI kan de MT5-kant wél sluiten |
| §34 **Markt-/vol-regime** automatisch | geen markt-data/kalender-bron | eerst handmatige regime-tag; later data-feed |
| §25 **Correlatie & concentratie** (prijs-gebaseerd) | geen prijsreeksen per instrument | later; concentratie-op-open-risk kan wel ruw |
| §37 **Stress Testing** met echte sensitiviteiten | vergt posities×prijzen×buffers | pas zinvol na ledger + prijs-feed |
| §17 **Sharpe/Sortino/Calmar** "zuiver" | denominator-probleem (§17/§58) | tonen mét expliciete kapitaalbasis, of pas na ledger |
| §30 **exit**-slippage | geen "bedoelde" exit bij TRAIL-exits | alleen bij TP/SL-exits betrouwbaar |

---

## 5. Eerlijke scope-inschatting

Dit is de **volledige institutionele "faces"-laag** uit ARCHITECTURE.md, fors uitgebreid — een
maandenlang traject, geen sprint. De huidige **cockpit is de kiem** van §11/§13/§18 (read-only).
De verstandige route bouwt vóórt op onze momentum i.p.v. alles tegelijk:

1. **Nu doorbouwen op de analyse-helft** (§2) — hoog rendement, data is er, past op de
   bestaande `/api/state`-laag en de Notion Trade Journal. Denk: global filters + attributie +
   strategy/instrument/time-analytics + expectancy/R + Account Matrix.
2. **De Account Ledger opzetten** (§3) — dé hoeksteen. Begin met MetaAPI voor de FX-saldi en
   een kleine fees/payouts-ledger; futures-saldo gereconstrueerd + gemarkeerd. Dit ontgrendelt
   economisch kapitaal, buffers, health, prop-economics, evaluatie/funded-analytics.
3. **Prop Firm Rule Engine live** — `firms.py` koppelen aan de ledger → survival-buffers,
   consistency, payout-eligibility per account.
4. **Pas daarna** de prijs-/regime-afhankelijke delen (exposure, correlatie, stress, unrealized).

Dit spoort met de fasering in de visie (§59), maar realistisch gemaakt: **Foundation +
CIO-MVP + Analytics** zijn grotendeels data-ready; **Prop Intelligence + Portfolio
Intelligence** hangen aan de ledger en (deels) een prijs-feed.

---

## 6. De ene beslissing die de tweede helft bepaalt

**Waar komen de kasstromen en saldi vandaan?** Concreet:
- Houd je fees / payouts / resets / eval-status ergens bij (LifeOS, spreadsheet, firm-portal)?
- Zo ja → we bouwen daar een import/mapping op en de economics-helft komt snel in bereik.
- Zo nee → we zetten een kleine **Account Ledger-DB** op (Notion of Postgres) die jij per
  payout/fee bijwerkt; MetaAPI vult de FX-saldi automatisch.

Zodra dat helder is, is de rest een kwestie van gefaseerd bouwen — de kaart hierboven zegt per
onderdeel of het "nu", "na de ledger", of "na een prijs-feed" is.
