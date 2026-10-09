# mex_units — units en de rolgrens

**Dit is de canonieke kopie** (D-132, 08-10). De module is in `web/handover/`
gebouwd omdat `middleware/**` niet van de Web-chat is, en bij de overname (D-17)
hierheen gekomen. De handover-map is opgeruimd; `public_stats.py`,
`dashboard_state.py` en `viewer.py` importeren uitsluitend dit pad.

## Wat het is

Twee dingen, allebei zonder datatoegang:

- **`units.py`** — rekent een bedrag op een markt om naar de eenheid van die
  markt: ticks voor futures, pips voor spot FX. Tick-size en pointvalue komen
  uit `backtest/config.py CONTRACTS`; die staan hier niet nog eens (§3). Wat
  hier wél staat is presentatie — de Nederlandse naam en de eenheid per markt.
- **`roles.py`** — aggregeert trades tot een fleet-beeld en bouwt daar per rol
  een payload van. Hier zitten ook de twee publicatiepoorten en
  `for_public_evals()`.

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

## Twee poorten, twee verschillende risico's

`assert_no_currency()` is een tweede slot op dezelfde deur: het weigert een
publieke momentopname zodra er een sleutelnaam in staat die naar geld ruikt.

`assert_no_eval_metrics()` bewaakt iets anders — niet of er geld in zit, maar of
eval-cijfers vermengd raken met de gewone fleet-payload. Tellers per status
(`passed`, `breached`, `50k_eq`) horen in `for_public_evals()`, dat ze
normaliseert naar 50k-equivalent en langs dezelfde geldpoort naar buiten stuurt.

Die twee dekken samen Ferry's regel van 07-10: **een aantal mag evals meenemen,
een bedrag nooit.** `assert_no_currency` doet de bedragen-helft,
`assert_no_eval_metrics` de scheiding. Ze zijn bewust niet één poort — een
vermengde teller is geen geldlek en een geldlek is geen vermenging, en één
foutmelding voor beide maakt niet duidelijk wat je moet repareren.

⚠️ **Bekend gat in `FORBIDDEN_KEY_PARTS`, gemeld 08-10** (zie `docs/inbox.md`):
negen veldnamen die `docs/schema-config.md` als bedrag definieert glippen er
doorheen, waaronder `verified_amount` (D-93) en `amount` (payouts). Gemeten met
`assert_no_currency({"verified_amount": 1})` — die werpt niets.

## Hoe je het aansluit

De module weet niet waar trades vandaan komen — dat is met opzet. Voer hem
gewone dicts, uit de gezaghebbende bronnen (§3):

```python
from app.mex_units import roles, units

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
cd middleware && python3 -m pytest tests/test_mex_units_roles.py -q
```

23 tests — let op dat je ze vanuit `middleware/` draait, want ze importeren
`app.mex_units`. De belangrijkste bouwen een fleet die gegarandeerd geld bevat en
controleren de viewer-payload op twee manieren: op veldnaam én op waarde. Alle
bedragen in de fixture hebben centen en gepubliceerde unit-aantallen zijn hele
getallen, dus een match is altijd een echt lek en nooit toeval.

## Let op

`units.py` importeert `backtest.config`. Draait de middleware met een eigen
werkmap, dan moet de repo-root op `sys.path` staan. De import faalt bewust hard
in plaats van terug te vallen op een ingebakken tabel — dat laatste zou de
registry stilzwijgend laten verouderen.
