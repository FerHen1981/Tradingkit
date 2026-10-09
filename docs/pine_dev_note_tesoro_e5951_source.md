# Bron-script voor El Tesoro backtest e5951 (Ferry, 19-08-2026)

Kopieer dit blok naar Pine Dev-chat.

---

## Waarom deze note

Ferry heeft gevraagd naar het exacte Tesoro-script dat de backtest-export
`T_SORO_COMEX_MINI_MGC1_20260819_e5951.xlsx` (3.651 trades over 12 mnd,
netto -$89.556 baseline) heeft geproduceerd. Hieronder de mapping van
backtest-datum → commit in `pine/MEX_EL_TESORO.pine`.

## Meest waarschijnlijke bron

**Commit `0c5951c` — TESORO v7.9.2 + D-08 commission-fix**
- Datum: 2026-08-19 14:05 UTC
- Bron: https://github.com/FerHen1981/Tradingkit/blob/0c5951c/pine/MEX_EL_TESORO.pine
- Checkout: `git checkout 0c5951c -- pine/MEX_EL_TESORO.pine`

**Waarom deze:** de backtest-properties tonen commission `$0,52` per contract.
Dat getal is precies op 19-08 om 14:05 UTC door commit `0c5951c` (D-08) in het
script gezet. Backtest-range eindigt op 19-08 19:34 ET (= ~23:34 UTC), dus
gedraaid ná deze commit.

## Alternatieven (voor het geval commission handmatig ingesteld was)

| Datum UTC | Commit | Versie | Wat er verandert |
|---|---|---|---|
| 2026-08-19 10:59 | `7264b40` | v7.9.2 | position-gate direction |
| 2026-08-18 20:23 | `6db2402` | v7.9.1 | ATR distance unit |
| 2026-08-18 19:14 | `0dd6e0e` | v7.9.0 | asset profile, één engine per instrument |
| 2026-08-18 18:22 | `42cce3e` | v7.8.2 | Max Stop 100 → 130 |

## Backtest-instellingen (uit Properties-sheet, ter verificatie)

Als de checkout klopt moeten deze settings default of instelbaar zijn:

- Fixed Qty = 6
- Entry Mode = Limit @ 50% FVG
- Stop Mode = Fixed (legacy), 100 units
- Max Stop Distance = 130 units
- Take-Profit Mode = R-multiple 1,55
- Enable Break-even = On
- Enable Trailing = On, Activation 48, Buffer 24
- Min FVG Size = 9, Max FVG Size = 15
- Confirmation window = 2 bars
- Drawdown Model = Intraday
- Trailing Drawdown = $2.500
- Firm program = apex_50k_legacy_pa
- VWAP side veto = On
- Use Delta Filter = Off
- Commission = $0,52 per contract per zijde

## Note over de v1_0_0-vloot (D-42)

Deze v7.9.x-lijn wordt vervangen door de `v1_0_0`-scripts uit
`MEX_FLEET_PACKAGE_2026-08-23`. Het script hierboven blijft alleen relevant
voor:
- Nachecken hoe de e5951-backtest tot stand kwam
- Vergelijkingsbasis wanneer de nieuwe `TES-MGC-C` (v1_0_0) een validatie-export
  krijgt en Ferry wil weten "hoeveel beter/anders draait de nieuwe versie"

Voor nieuw werk: bouw op `v1_0_0`, niet op v7.9.x.

---

*Einde note.*
