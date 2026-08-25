# MGC-bucket op de GC-twin — is echte data nodig, en wat kost de twin aan zekerheid? (D-56)

> **Vraag (D-56):** is MGC-1-minuutdata te krijgen en tegen welke moeite? Zo niet,
> leg dan expliciet vast dat de MGC-bucket op de GC-twin beoordeeld blijft en wat dat
> aan zekerheid kost. **Uitkomst: de twin is bruikbaarder dan het lijkt voor de
> oordelen die we feitelijk maakten (allemaal afwijzingen), maar niet voor een
> positief funderingsoordeel.**

## 1. Zijn GC en MGC eigenlijk "een twin"? — ja, op de assen die tellen
Uit `backtest/config.py CONTRACTS`:

| | mintick | pointvalue | tickvalue | commissie/side |
|---|---|---|---|---|
| **GC** (100 oz) | 0.10 | $100 | **$10/tick** | $1,75 |
| **MGC** (10 oz) | 0.10 | $10 | **$1/tick** | $0,52 |

- **Zelfde onderliggende (goud), zelfde prijsraster (mintick 0.10).** GC is letterlijk
  10× MGC: dezelfde prijsreeks in $/oz, dezelfde tick-increments. De prijs-*actie*
  (rendementen, volatiliteit in ticks, gap-structuur op 1m) is daarmee vrijwel identiek.
- **De $-rekenkant klopt al voor MGC.** De engine rekent P&L als `ticks × tickvalue`,
  en de sweep draaide de **MGC-contractspec** ($1/tick), niet GC's $10. Dus de payout-,
  DLL- en drawdown-cijfers zijn MGC-correct, óók al liepen ze over GC-prijsbars.
- **De commissie klopt ook al.** De MGC-engines draaiden ~0,51–0,52 = de MGC-waarde.
  De kostenbug uit **D-63** (0,51 i.p.v. 0,37) raakt de **index-micros** (MNQ/MES/MYM),
  **niet** de MGC-bucket. Voor MGC is de kostenaanname dus juist.
- **CVD is faithful.** De canonieke CVD is de OHLCV-polariteitsproxy (grondregel 4),
  berekend uit OHLC — dat is bijna identiek tussen GC en MGC. Alleen bij *native* Delta
  zou MGC's eigen volume meetellen, en dat is niet het default-pad.

## 2. Wat vangt de twin dan NIET? — precies één ding: fill-realisme
De enige as waarop GC en MGC materieel verschillen is **liquiditeit / marktdiepte**.
GC heeft een dieper orderboek dan MGC. Gevolg voor de simulatie:

- De slippage is in de pijplijn een **vaste aanname** (1 tick basis, 2–3 in stress —
  grondregel), niet uit de tape gelezen. Op GC-bars én op MGC-bars gebruikt de engine
  diezelfde aanname, dus de twin *flatteert* de fills niet automatisch.
- **Maar** een echte MGC-tape zou een **ruimere** stress-slippage rechtvaardigen dan
  GC's diepe boek — dunnere book, meer beweging per lot, meer gap-risico in dunne
  sessies. De twin laat je dus met een *te milde* aanname wegkomen.

**Richting van de bias: de twin is licht optimistisch op executie.** Dat is de enige
noemenswaardige zekerheidskost.

## 3. Wat kost dat aan zekerheid — per soort oordeel
- **Een AFWIJZING op de twin is conservatief-veilig.** Echte MGC (dunner, slechtere
  fills) valt hooguit slechter uit. PATRON's afwijzing (trap 2 **geen edge**, −$2,76/tr,
  PF 0,96; trap 9 cherry-pick) staat daarmee met hoog vertrouwen — de mechaniek verdient
  op de *gunstige* twin al niets. Zelfde logica voor TESORO/BANDIDO die niet funderen op
  1 contract: op echte MGC funderen ze zeker niet plots wél.
- **Een POSITIEF funderingsoordeel op de twin zou optimistisch zijn** en vraagt echte
  MGC-data. **Maar dat oordeel bestaat niet** — elke MGC-uitkomst in de sweep is een
  afwijzing. **Conclusie: de optimisme-bias van de twin loopt de veilige kant op voor
  alles wat we feitelijk beweerd hebben.**
- **Wat je met de twin NIET mag:** een afwijzing terugdraaien ("PATRON leeft toch") of
  een MGC-engine funded verklaren. Dáárvoor, en alleen daarvoor, is echte MGC nodig.

## 4. Is echte MGC-1m te krijgen, en tegen welke moeite? — laag
MGC (COMEX Micro Gold) is een liquide, standaard vendor-product. Ferry heeft de
export-keten al gebruikt voor de **index-micros** (`MES/MNQ/MYM 3y 1m tick_cvd`,
~1,05M bars elk, via de Quantower/ATAS-route in `lab/normalize.py`). **MGC is dezelfde
export van hetzelfde platform** — geen nieuwe feed, geen aankoop, mits zijn databron
COMEX-metalen dekt (de meeste futures-feeds bundelen CME-index én COMEX-metaal). Kortom:
**lage tot nul marginale moeite als de feed MGC dekt; anders een eenmalige vendor-vraag.**

## Aanbeveling
1. **Exporteer echte MGC-1m** langs dezelfde weg als de andere micros — dat sluit het
   voorbehoud netjes en is goedkoop. Formaat: zie `docs/data_export.md` / de bestaande
   micro-exports.
2. **Tot dat er is:** de MGC-bucket blíjft op de GC-twin, en dat is **verdedigbaar voor
   de huidige verdicts** (allemaal afwijzingen; de bias loopt de veilige kant op).
   Leg in elke MGC-uitspraak vast: *"gemeten op de GC-twin; geldig als afwijzing, niet
   als funderingsbewijs."*
3. **Beslissing voor Ferry** (data-acquisitie is zijn call): dekt je huidige feed MGC?
   Zo ja, één export erbij. Zo nee, is een MGC-1m-bron de moeite waard, of accepteren we
   de twin-afwijzing als definitief voor PATRON/TESORO/BANDIDO? → uitgezet in `inbox.md`.

## Herkomst
`config.py CONTRACTS` (specs) · `FLEET_sweep_20260825.md` (de MGC-verdicts) ·
`DECISIONS.md` 25-08 (PATRON-afval, D-63 kostenbug op index-micros) · D-52-triage.
