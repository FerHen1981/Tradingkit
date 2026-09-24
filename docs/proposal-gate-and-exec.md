# Voorstel · positie-gate met richting

Status: **voorstel — niets gebouwd.** Ter beoordeling door de scrum master.
Eigenaar uitvoering: Pine Dev (`pine/**`). Raakt het live executiepad.
Basis: `docs/execution-contract.md` (geverifieerd tegen v6.8.14..v7.9.1).

## Waarom

Na de bevestigingen van de eigenaar (19-08) blijven er precies twee dingen over:

1. **Defect — de gate kent geen richting.** `gateOK = isFlat or posRiskOff`. Zodra een
   positie risk-off is, staat de gate voor *beide* richtingen open. Een tegengesteld
   signaal doet dan `strategy.entry` de andere kant op, en dat **reverseert** de open
   positie. **Apex staat twee tegengestelde open orders niet toe**, dus dit is niet
   alleen ongewenst gedrag maar een firm-risico. Dit gedrag zit er sinds v6.8.14 in.
**Niet in dit voorstel:** `calc_on_order_fills=true` **blijft aan** — besluit eigenaar 19-08-2026.
Pine Dev had een revert voorgesteld op een verkeerde lezing van een eerder antwoord; daar was geen
akkoord voor. De regel blijft ongemoeid. Vastgelegd in de backlog als besluit, niet als werk.

## Voorstel A · richting-gate (3 regels, één nieuwe hulpvariabele)

Regel die we willen, letterlijk:

| Situatie | Toegestaan |
|---|---|
| Flat | long én short |
| In positie, niet risk-off | niets |
| In positie, risk-off | **alleen dezelfde richting als de open positie** |
| Positie gesloten | weer beide (= flat) |

Nieuwe hulpvariabele naast `isFlat`/`posRiskOff`, vóór regel 1119:

```pine
// Richting van de open positie: 1 long, -1 short, 0 flat. De gate mag na risk-off alleen
// hetzelfde teken toelaten — een tegengesteld signaal zou strategy.entry laten reverseren,
// en twee tegengestelde open orders staat Apex niet toe.
int  posDir     = strategy.position_size > 0 ? 1 : strategy.position_size < 0 ? -1 : 0
bool gateAnyDir = isFlat                       // flat: beide richtingen
bool gateSameDir = not isFlat and posRiskOff   // risk-off: alleen posDir
f_gateFor(int _dir) => gateAnyDir or (gateSameDir and _dir == posDir)
```

Dan op de drie plekken:

| Regel | Nu | Wordt |
|---|---|---|
| 1119 | `bool gateMemOK = (isFlat or posRiskOff) and canTrade` | `bool gateMemOK = (gateAnyDir or gateSameDir) and canTrade` — de *memory* mag blijven scannen; de richtingstoets valt bij de order |
| 1141 | `bool consumed0 = (long0 or short0) and (isFlat or posRiskOff)` | `bool consumed0 = (long0 and f_gateFor(1)) or (short0 and f_gateFor(-1))` |
| 1312 | `gateOK = isFlat or posRiskOff` | vervalt; regel 1358 toetst per richting |
| 1358 | `if (longSignal or shortSignal) and gateOK and …` | `if ((longSignal and f_gateFor(1)) or (shortSignal and f_gateFor(-1))) and …` |

Blockers-tekst (regel 1346) wordt specifieker: `"In position, "` → `"In position (opposite), "`
wanneer de richting de blokkade is, zodat het dashboard laat zien *waarom*.

**Wat dit NIET doet:** het staat geen stacking toe. `pyramiding` blijft 1, dus een
same-direction signaal na risk-off wordt door TradingView genegeerd — de gate is dan open,
maar er komt geen tweede order. Willen we bijladen na risk-off, dan is dat een aparte
beslissing (pyramiding + qty-ladder) en géén onderdeel van dit voorstel.

## Voorstel B · chart-asset in plaats van MGC-hardcode

Laatste harde asset-aannames in het script:
- `f_pol()`-tabel: elke preset draagt `"MGC"` als familie; `polInstrOK` blokkeert handel als
  `syminfo.root` niet matcht. Op elke andere asset slaat de policy dicht.
- `mwStrategy = "GC"` — de strategie-sleutel naar de middleware.

Voorstel: de presetfamilie wordt `"ANY"` (het account bepaalt de asset, niet het script), en
`mwStrategy` valt terug op `syminfo.root` als het veld leeg is. Rekenkundig is de engine al
asset-onafhankelijk (`syminfo.mintick`/`pointvalue` overal), dus dit is de laatste stap.

## Testplan (vóór live)

1. Compileren in de Pine-editor; script opnieuw aan de chart toevoegen.
2. **Gate-bewijs op de chart:** een risk-off positie afwachten en verifiëren dat een
   tegengesteld signaal in de blockers-rij verschijnt als "In position (opposite)" en dat
   `strategy.position_size` niet omklapt.
3. **DRY_RUN op de receiver aan**, dan het receiver-log lezen: bij een tegengesteld signaal
   mag er géén `buy`/`sell` langskomen, alleen de blocked-melding.
4. Backtest v7.9.2 vs v7.3 op dezelfde periode: het verschil moet verklaarbaar zijn uit voorstel A
   en niets anders.

## Impact

| | |
|---|---|
| Raakt live executie | **ja** — gate beslist of er een order uitgaat |
| Nieuwe inputs | geen |
| Verwijderde inputs | geen |
| Registry/propfirms | ongewijzigd (blijft via codegen) |
| Andere mappen | geen — volledig binnen `pine/**` |
| Terugdraaibaar | ja, één commit |
