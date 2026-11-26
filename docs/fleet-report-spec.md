# Fleet-rapport — outputspecificatie

_Eigenaar: Scrum Master. Opgesteld 28-09-2026 uit Ferry's `fleet_startschema_2026-09-28`._
_Dit is de **acceptatietest** voor **D-96** (de vijf vooruitblikken) en **D-97** (schaaladvies):_
_de webapp is af wanneer hij deze tabellen zelf produceert uit actuals + registry._

> ⛔ **Bewust geen bedragen in dit bestand.** Het fleet-doc bevat balansen per account; die
> horen niet in de repo. Hier staan alleen de kolommen en de formules. De formules zijn
> **geverifieerd tegen de cijfers in het doc van 28-09** — per formule staat erbij op welk
> account dat gebeurd is.

---

## 1. Waarom dit document bestaat

Ferry onderhoudt dit rapport nu met de hand, elke keer opnieuw. Antwoord 6 van de herijking:
*"dat beter en sneller als dat in de webapp bijgehouden wordt op basis van de actuals."*
Dit bestand zegt precies **wat** de webapp dan moet produceren, zodat fase 5 en 6 niet
hoeven te raden.

**Bron van de regels is `data/propfirms.json`** — élke drempel hieronder is een
registry-waarde, geen constante in code. Waar de registry een regel niet draagt, faalt de
berekening hard (D-96). Dat is de reden dat **D-104** een voorwaarde is.

---

## 2. Tabel A — stand per account

Kolommen: `Account · Product · Balans · Liq-niveau · Ruimte · Winst · Lock · Payout-status`

| Veld | Formule | Bron |
|---|---|---|
| Balans | startbalans + cumulatieve netto P&L − uitbetaalde payouts | T3 (fills, D-92) + payout-log |
| Liq-niveau | vóór lock: `start − trailing_drawdown` · ná lock: `start + lock_offset` | registry |
| **Ruimte** | `balans − liq-niveau` | afgeleid |
| **Winst** | `balans − startbalans` | afgeleid |
| Lock | gelockt zodra `balans ≥ lock_threshold`; anders het resterende bedrag | registry |
| Payout-status | zie tabel C | registry + tellers |

⚠️ **`Winst` is niet hetzelfde als de som van de fills** zodra er een payout is uitbetaald:
een payout verlaagt de balans maar komt niet in de fills voor. Dat verschil is op 28-09
gemeten op PA013 (fills september −$1.903 onder de doc-winst, waarvan $1.500 de op 10-09
ontvangen payout #1 is en de rest historie van vóór het exportvenster). **De payout-registratie
is dus een aparte invoer naast T3 en mag niet vergeten worden.**

**Rood-markering:** ruimte onder `3 × DLL bij qty 1` — in het doc verwoord als *"minder dan
3 DLL-dagen"*.

---

## 3. Tabel B — startschema per account

Kolommen: `Account · Qty · Pine act/gb/cap · TV target · TV DLL · Volgende stap · Toelichting`

| Veld | Formule |
|---|---|
| DLL | `sl_per_contract × dll_sl_multiple × qty` — in het doc: 4 × SL per contract |
| Ruimte nodig | `3 × DLL` (drie DLL-dagen) |
| Volgende stap | de balans waarbij `ruimte ≥ 3 × DLL(qty+1)`, dus opschalen kan |

🔴 **De harde grens die het doc expliciet maakt:** de DLL mag *"nooit meer dan ⅓ van de
ruimte"* zijn. Dat is een tweede begrenzing naast de ladder en hij bijt eerder — op PA022
is dat in het doc met zoveel woorden genoteerd. **Beide regels moeten in de berekening,
en de strengste wint.**

---

## 4. Tabel C — payout-poorten

Een payout is aanvraagbaar wanneer **alle** onderstaande poorten open staan. De webapp toont
per account **welke poort dicht is**, niet alleen of er wel of niet uitbetaald kan worden —
dat is precies wat Ferry nu met de hand uitzoekt.

| Poort | Formule | Geverifieerd op |
|---|---|---|
| **1. Drempel** | `balans ≥ safety_net + payout_bedrag` | PA022: het doc noteert het resterende bedrag tot precies die drempel |
| **2. Buffer** | met bufferbeleid: `balans − payout ≥ safety_net + buffer` | §6 van het doc, buffer is beleid en dus een instelling |
| **3. Cyclus** | `handelsdagen sinds vorige payout ≥ cyclus_lengte` | PA013 staat op 8/8 |
| **4. Kwalificatiedagen** | `aantal dagen met netto ≥ min_qual_day ≥ min_qual_days` | PA013 staat op 3/5 |
| **5. Consistency** | `best_day / consistency_pct ≤ totale winst`, dus vereiste winst = `best_day / consistency_pct` | ✅ **drie keer onafhankelijk geverifieerd**: PA018 en PA026 op 30% (legacy), PA023 op 50% (Intraday 4.0) — de percentages klopten allebei exact met het doc |

> 🔴 **Poort 5 laat zien waarom de registry per programma moet kloppen en niet per firma.**
> Legacy 50K rekent met 30%, Intraday 4.0 met 50%. Eén verkeerd percentage geeft een
> plausibel ogende en onjuiste payout-datum. Dit is hetzelfde faalpatroon als de stille
> drawdown-fallback in D-68 — en de reden dat D-96 hard faalt op een ontbrekende regel.

---

## 5. Tabel D — payout-projectie

Kolommen: `Account · Product · #1 … #6 (datum · bedrag) · Totaal`

De projectie is deterministisch: netto per contract per handelsdag × qty volgens de ladder,
payout zodra het stapmaximum boven de buffer beschikbaar is.

🔴 **Wat de webapp anders moet doen dan het handmatige doc.** Het doc rekent met *"$187
netto per contract per handelsdag (live 1–14 sep)"*. Eigen meting op de fills van 28-09:

| Venster | Netto per account-dag | Netto per contract-dag |
|---|---|---|
| 01→14 sep | positief, ruim | positief, ruim |
| 15→25 sep | **negatief** | **negatief** |
| hele venster | positief | ongeveer een zevende van de doc-basis |

De projectie is niet fout gerekend — de **basis** is de beste twee weken. **Eis aan de
webapp: de gebruikte basis is zichtbaar en instelbaar** (welk venster, hoeveel dagen), en
naast de projectie staat wat dezelfde berekening op het volledige venster geeft. Een
projectie zonder zichtbare basis is een aanname met een getal eromheen.

---

## 6. Tabel E — de schaal-ladder · invoer voor D-97

Per programma en per qty: `DLL · ruimte nodig (3 DLL-dagen) · lock-drempel · plafond vóór
payout #1 · qty na lock`.

De doctrine die het doc hanteert en die D-97 moet reproduceren én toetsen:

- **Afschalen doe je direct, niet bij de aanvraag** — na een payout (de winst daalt met het
  bedrag) en na een DLL-dag.
- **Een cap-dag op de oude qty in de week vóór de aanvraag is de dag die de consistency
  breekt.** Dat is de niet-voor-de-hand-liggende regel en precies waar een adviesmotor
  waarde toevoegt.
- Opschalen pas wanneer de ruimte drie DLL-dagen op de nieuwe qty draagt.

⚠️ **D-97 kopieert deze doctrine niet, hij toetst hem** — Ferry's antwoord 15 vraagt
letterlijk *op welk niveau* een daily halt hoort en *wanneer* op- en afschalen. Dat zijn
meetbare vragen op de eigen historie. Komt de meting op iets anders uit dan de doctrine,
dan is dat de uitkomst en niet een fout.

---

## 7. Wat hier NIET in hoort

- Bedragen, balansen en accountnummers — die blijven buiten de repo.
- De eval-pijplijn (§5 van het doc) en de handoff-analyse (§8). Die hangen aan de
  vlootrangorde en die bestaat niet; zie D-98, deel 6b.
- Strategiekeuze per account. Zelfde reden.
