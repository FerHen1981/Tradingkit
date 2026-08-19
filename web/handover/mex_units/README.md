# mex_units — units en de rolgrens

**Bedoeld voor overname door Middleware App.** Deze map ligt in `web/` omdat
`middleware/**` niet van de Web-chat is (werkafspraken §2); de code hoort
uiteindelijk in `middleware/app/`. Zie het verzoek in `docs/inbox.md`.

## Wat het is

Twee dingen, allebei zonder datatoegang:

- **`units.py`** — rekent een bedrag op een markt om naar de eenheid van die
  markt: ticks voor futures, pips voor spot FX. Tick-size en pointvalue komen
  uit `backtest/config.py CONTRACTS`; die staan hier niet nog eens (§3). Wat
  hier wél staat is presentatie — de Nederlandse naam en de eenheid per markt.
- **`roles.py`** — aggregeert trades tot een fleet-beeld en bouwt daar per rol
  een payload van.

## Waarom het niet gewoon een filter is

De belofte aan een `viewer` is dat er geen bedrag in zijn antwoord voorkomt.
Niet verborgen, niet op nul — afwezig. Daarom bouwt elke rol zijn eigen payload
in plaats van dat er één "volledig" antwoord wordt afgeknipt. Een filter lekt
elk veld dat iemand later toevoegt en vergeet te noteren; een aparte builder
kan dat niet.

| Rol | Krijgt |
|---|---|
| `owner` | alles, inclusief bedragen en rekeningnamen |
| `partner` | zelfde cijfers, andere labeling |
| `viewer` | **alleen units** — ticks, R, percentages, en rekeningen als aantal per fase |

Een onbekende rol valt terug op `viewer`, zodat een typefout in een
gebruikersbestand toegang versmalt in plaats van verbreedt.

`assert_no_currency()` is een tweede slot op dezelfde deur: het weigert een
publieke momentopname zodra er een sleutelnaam in staat die naar geld ruikt.

## Hoe je het aansluit

De module weet niet waar trades vandaan komen — dat is met opzet. Voer hem
gewone dicts, uit de gezaghebbende bronnen (§3):

```python
from mex_units import roles, units

fleet = roles.build(trades, accounts)   # trades uit fills_pairing.py
payload = roles.serialise(fleet, user_role)
```

Elke trade-dict mag deze sleutels hebben; ontbrekende sleutels worden
overgeslagen in plaats van geraden:

`ts`, `symbol`, `realized_usd`, `realized_r`, `fill_qty`, `slippage_ticks`,
`hold_s`.

Voor rekeningen: `account`, `realized`, `open_pnl`, `total_val` — balansen
horen uit `cash_ledger.py` te komen, niet uit een eigen query.

## Tests

```bash
python3 -m pytest web/handover/mex_units/tests -q
```

17 tests. De belangrijkste bouwen een fleet die gegarandeerd geld bevat en
controleren de viewer-payload op twee manieren: op veldnaam én op waarde. Alle
bedragen in de fixture hebben centen en gepubliceerde unit-aantallen zijn hele
getallen, dus een match is altijd een echt lek en nooit toeval.

## Let op bij overname

`units.py` importeert `backtest.config`. Draait de middleware met een eigen
werkmap, dan moet de repo-root op `sys.path` staan. De import faalt bewust hard
in plaats van terug te vallen op een ingebakken tabel — dat laatste zou de
registry stilzwijgend laten verouderen.
