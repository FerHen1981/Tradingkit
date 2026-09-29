# Pine-surface inventaris — 13 live scripts (D-100)

_Read-only scan van `pine/*.pine`. Gegenereerd door `tools/pine_inventory.py`._

**Scripts (13):** EL_BANDIDO_MYM_HF_EOD, EL_LEON_MYM_CON_EOD_Q2, EL_LEON_MYM_CON_INTRA_Q2, EL_LEON_MYM_PROD_EOD, EL_MATADOR_MES_PROD_EOD, EL_PATRON_MGC_AGG_EOD, EL_REY_MNQ_PROD_EOD, EL_REY_MNQ_PROD_INTRA, EL_TESORO_MGC_CON_EOD, EL_TORO_ES_FAST_INTRA, EL_TORO_GC_SNIPER_EOD, EL_TORO_NQ_HF_INTRA, EL_TORO_NQ_SNIPER_INTRA

## Samenvatting — is de gebruikte taal een kleine, opsombare set?

| Categorie | Distinct features | In ALLE scripts (core) | Totaal calls |
|---|---|---|---|
| `ta.*` | 13 | 12 | 240 |
| `request.*` | 1 | 0 | 2 |
| `str.*` | 8 | 7 | 2701 |
| `math.*` | 8 | 8 | 1712 |
| `array.*` | 16 | 16 | 2032 |
| `input.*` | 5 | 5 | 2161 |
| `strategy.*` | 19 | 19 | 1322 |
| `timeframe.*` | 1 | 1 | 13 |
| `syminfo.*` | 5 | 3 | 1038 |
| `color.*` | 15 | 15 | 1169 |
| `barstate.*` | 4 | 4 | 286 |
| `dayofweek.*` | 7 | 7 | 91 |
| `drawing/output` | 8 | 8 | 641 |
| `constructs` | 9 | 9 | 12711 |
| `built-in vars` | 14 | 14 | 7158 |
| `user functions` | 39 | 38 | 498 |
| `chart.*` | 1 | 1 | 39 |

## Conclusie voor D-101 — weken, niet maanden (voor de reken-kern)

De hypothese van spoor B klopt: de **reken-kern** die de 13 scripts delen is een kleine,
opsombare verzameling.

- **`ta.*` = 13 functies, 12 in álle scripts** (`highest`, `lowest`, `barssince`, `ema`,
  `atr`, `hma`, `pivothigh`, `pivotlow`, `sma`, `stdev`, `vwap`, `vwma`). De dertiende,
  **`ta.requestVolumeDelta`, staat in slechts 2 scripts** (PATRON + TESORO) — precies de
  twee met de niet-canonieke TradingView-delta uit de fleet-doc. Elk van deze twaalf heeft
  al een equivalent in `backtest/indicators.py` (D-100 leunt hierop).
- **`request.*` = 1** (`request.security`, 2×, alleen voor de volume-delta). Vrijwel geen
  multi-timeframe/multi-symbol afhankelijkheid — de grote onbekende bij een herimplementatie
  is dus afwezig.
- **39 user-functions, 38 gedeeld** over alle 13: de familie is één codebase met per script
  alleen andere input-waarden. Dit is de kern van de herimplementatie en hij is eindig.

**Wat de grote getallen NIET zijn:** `str.*` (~2700), `color.*`, `drawing/output`,
`table.*`, en het leeuwendeel van de `constructs`-telling zijn **dashboard-, JSON- en
tekenwerk** — een headless (Python/.NET) engine reproduceert dat niet, hij reproduceert de
signaal- en account-logica. De `ternary ?:` en `[N] history-ref` tellingen zijn bewust
benaderend (regex per regel) en dienen alleen als grofmazig signaal, niet als exacte maat.

**Gevolg voor D-66/D-63/D-54/D-57:** met één gedeelde reken-kern (deze ~13 ta-functies +
de gedeelde user-functions) is er straks één implementatie en dus geen CVD-pariteit meer te
bewaken tussen bron en mirror — D-66 gaat op in D-100 en de keten D-63 → D-54 → D-57 vervalt,
zoals de startprompt stelt.

Herhaalbaar: `python3 tools/pine_inventory.py`. Dit bestand is een gedateerde momentopname
(append-only); een latere run krijgt een nieuwe datum.

---

## `ta.*`

| feature | scripts | totaal |
|---|---|---|
| `ta.highest` | 13/13 | 39 |
| `ta.lowest` | 13/13 | 39 |
| `ta.barssince` | 13/13 | 30 |
| `ta.ema` | 13/13 | 26 |
| `ta.atr` | 13/13 | 13 |
| `ta.hma` | 13/13 | 13 |
| `ta.pivothigh` | 13/13 | 13 |
| `ta.pivotlow` | 13/13 | 13 |
| `ta.sma` | 13/13 | 13 |
| `ta.stdev` | 13/13 | 13 |
| `ta.vwap` | 13/13 | 13 |
| `ta.vwma` | 13/13 | 13 |
| `ta.requestVolumeDelta` | 2/13 | 2 |

## `request.*`

| feature | scripts | totaal |
|---|---|---|
| `request.security_lower_tf` | 2/13 | 2 |

## `str.*`

| feature | scripts | totaal |
|---|---|---|
| `str.tostring` | 13/13 | 2333 |
| `str.format_time` | 13/13 | 117 |
| `str.length` | 13/13 | 113 |
| `str.substring` | 13/13 | 52 |
| `str.format` | 13/13 | 39 |
| `str.upper` | 13/13 | 26 |
| `str.match` | 13/13 | 13 |
| `str.replace` | 4/13 | 8 |

## `math.*`

| feature | scripts | totaal |
|---|---|---|
| `math.max` | 13/13 | 607 |
| `math.abs` | 13/13 | 546 |
| `math.min` | 13/13 | 351 |
| `math.round` | 13/13 | 104 |
| `math.avg` | 13/13 | 52 |
| `math.floor` | 13/13 | 26 |
| `math.ceil` | 13/13 | 13 |
| `math.sum` | 13/13 | 13 |

## `array.*`

| feature | scripts | totaal |
|---|---|---|
| `array.get` | 13/13 | 442 |
| `array.push` | 13/13 | 312 |
| `array.size` | 13/13 | 273 |
| `array.new` | 13/13 | 182 |
| `array.remove` | 13/13 | 182 |
| `array.shift` | 13/13 | 182 |
| `array.new_float` | 13/13 | 117 |
| `array.set` | 13/13 | 117 |
| `array.clear` | 13/13 | 65 |
| `array.from` | 13/13 | 65 |
| `array.fill` | 13/13 | 26 |
| `array.sum` | 13/13 | 17 |
| `array.indexof` | 13/13 | 13 |
| `array.max` | 13/13 | 13 |
| `array.new_bool` | 13/13 | 13 |
| `array.new_int` | 13/13 | 13 |

## `input.*`

| feature | scripts | totaal |
|---|---|---|
| `input.bool` | 13/13 | 1128 |
| `input.float` | 13/13 | 454 |
| `input.string` | 13/13 | 366 |
| `input.int` | 13/13 | 178 |
| `input.time` | 13/13 | 35 |

## `strategy.*`

| feature | scripts | totaal |
|---|---|---|
| `strategy.closedtrades` | 13/13 | 364 |
| `strategy.netprofit` | 13/13 | 221 |
| `strategy.openprofit` | 13/13 | 126 |
| `strategy.exit` | 13/13 | 104 |
| `strategy.position_size` | 13/13 | 91 |
| `strategy.cancel` | 13/13 | 78 |
| `strategy.close_all` | 13/13 | 65 |
| `strategy.entry` | 13/13 | 52 |
| `strategy.opentrades` | 13/13 | 39 |
| `strategy.grossloss` | 13/13 | 26 |
| `strategy.long` | 13/13 | 26 |
| `strategy.short` | 13/13 | 26 |
| `strategy.wintrades` | 13/13 | 26 |
| `strategy.commission` | 13/13 | 13 |
| `strategy.equity` | 13/13 | 13 |
| `strategy.fixed` | 13/13 | 13 |
| `strategy.grossprofit` | 13/13 | 13 |
| `strategy.losstrades` | 13/13 | 13 |
| `strategy.position_avg_price` | 13/13 | 13 |

## `timeframe.*`

| feature | scripts | totaal |
|---|---|---|
| `timeframe.change` | 13/13 | 13 |

## `syminfo.*`

| feature | scripts | totaal |
|---|---|---|
| `syminfo.ticker` | 13/13 | 502 |
| `syminfo.mintick` | 13/13 | 407 |
| `syminfo.pointvalue` | 13/13 | 117 |
| `syminfo.root` | 4/13 | 8 |
| `syminfo.type` | 2/13 | 4 |

## `color.*`

| feature | scripts | totaal |
|---|---|---|
| `color.new` | 13/13 | 680 |
| `color.red` | 13/13 | 82 |
| `color.gray` | 13/13 | 78 |
| `color.white` | 13/13 | 56 |
| `color.green` | 13/13 | 52 |
| `color.orange` | 13/13 | 52 |
| `color.rgb` | 13/13 | 39 |
| `color.maroon` | 13/13 | 26 |
| `color.teal` | 13/13 | 26 |
| `color.b` | 13/13 | 13 |
| `color.blue` | 13/13 | 13 |
| `color.g` | 13/13 | 13 |
| `color.olive` | 13/13 | 13 |
| `color.purple` | 13/13 | 13 |
| `color.r` | 13/13 | 13 |

## `barstate.*`

| feature | scripts | totaal |
|---|---|---|
| `barstate.isconfirmed` | 13/13 | 208 |
| `barstate.islast` | 13/13 | 30 |
| `barstate.isfirst` | 13/13 | 26 |
| `barstate.isrealtime` | 13/13 | 22 |

## `dayofweek.*`

| feature | scripts | totaal |
|---|---|---|
| `dayofweek.friday` | 13/13 | 13 |
| `dayofweek.monday` | 13/13 | 13 |
| `dayofweek.saturday` | 13/13 | 13 |
| `dayofweek.sunday` | 13/13 | 13 |
| `dayofweek.thursday` | 13/13 | 13 |
| `dayofweek.tuesday` | 13/13 | 13 |
| `dayofweek.wednesday` | 13/13 | 13 |

## `drawing/output`

| feature | scripts | totaal |
|---|---|---|
| `alert(` | 13/13 | 182 |
| `plot` | 13/13 | 143 |
| `label.new` | 13/13 | 108 |
| `box.new` | 13/13 | 65 |
| `fill` | 13/13 | 52 |
| `plotshape` | 13/13 | 52 |
| `bgcolor` | 13/13 | 26 |
| `table.new` | 13/13 | 13 |

## `constructs`

| feature | scripts | totaal |
|---|---|---|
| `if` | 13/13 | 3605 |
| `ternary ?:` | 13/13 | 3551 |
| `var` | 13/13 | 2023 |
| `[N] history-ref` | 13/13 | 1070 |
| `else` | 13/13 | 1070 |
| `=> (func/lambda)` | 13/13 | 901 |
| `for` | 13/13 | 322 |
| `while` | 13/13 | 104 |
| `switch` | 13/13 | 65 |

## `built-in vars`

| feature | scripts | totaal |
|---|---|---|
| `na` | 13/13 | 2501 |
| `close` | 13/13 | 1044 |
| `nz` | 13/13 | 840 |
| `time` | 13/13 | 546 |
| `bar_index` | 13/13 | 433 |
| `syminfo.mintick` | 13/13 | 407 |
| `open` | 13/13 | 383 |
| `high` | 13/13 | 381 |
| `low` | 13/13 | 334 |
| `syminfo.pointvalue` | 13/13 | 117 |
| `volume` | 13/13 | 68 |
| `timenow` | 13/13 | 65 |
| `last_bar_index` | 13/13 | 26 |
| `ohlc4` | 13/13 | 13 |

## `user functions`

| feature | scripts | totaal |
|---|---|---|
| `f_arrow()` | 13/13 | 13 |
| `f_autoAcctName()` | 13/13 | 13 |
| `f_bbwp()` | 13/13 | 13 |
| `f_bbwpMa()` | 13/13 | 13 |
| `f_calDayId()` | 13/13 | 13 |
| `f_calcQty()` | 13/13 | 13 |
| `f_capDrawings()` | 13/13 | 13 |
| `f_contractSpec()` | 13/13 | 13 |
| `f_distPrice()` | 13/13 | 13 |
| `f_evalTail()` | 13/13 | 13 |
| `f_evtLabel()` | 13/13 | 13 |
| `f_firmDays()` | 13/13 | 13 |
| `f_firmLadder()` | 13/13 | 13 |
| `f_firmMinPayout()` | 13/13 | 13 |
| `f_firmRules()` | 13/13 | 13 |
| `f_getHour()` | 13/13 | 13 |
| `f_getMinute()` | 13/13 | 13 |
| `f_gwName()` | 13/13 | 13 |
| `f_inRangeMOD()` | 13/13 | 13 |
| `f_isTradingDay()` | 13/13 | 13 |
| `f_journal()` | 13/13 | 13 |
| `f_ladderCap()` | 13/13 | 13 |
| `f_markUnfilled()` | 13/13 | 13 |
| `f_minuteOfDay()` | 13/13 | 13 |
| `f_msgHead()` | 13/13 | 13 |
| `f_orderMsg()` | 13/13 | 13 |
| `f_pcSym()` | 13/13 | 13 |
| `f_persistentBlockers()` | 13/13 | 13 |
| `f_pmtJSON()` | 13/13 | 13 |
| `f_profileAdd()` | 13/13 | 13 |
| `f_sendDiscord()` | 13/13 | 13 |
| `f_sendExec()` | 13/13 | 13 |
| `f_signalBlockers()` | 13/13 | 13 |
| `f_toMOD()` | 13/13 | 13 |
| `f_tpFixDist()` | 13/13 | 13 |
| `f_trailOn()` | 13/13 | 13 |
| `f_valCol()` | 13/13 | 13 |
| `f_volSlice()` | 13/13 | 13 |
| `f_pol()` | 4/13 | 4 |

