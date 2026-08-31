# EL TESORO — MNQ Research Summary

## Data audit
- Dataset: MNQ 3y 1m tick_cvd.csv
- Coverage: 24 Aug 2023 through 21 Aug 2026
- 1,058,466 one-minute bars
- Price range observed: 14,136.50–30,975.50
- Bar volume populated throughout
- Native bid/ask Delta is not usable across the whole sample: 0% non-zero in 2023/2024, ~54.5% in 2025, ~99.6% in 2026
- Primary research therefore uses Pine-parity CVD from OHLCV. Native tick delta is diagnostic only.

## Structural findings
MNQ is materially different from MGC. Small FVGs dominate.

### All-session structural families
- FVG 3–7, CVD6, SL160, 2.5R, VWAP veto ON: ~968 trades, PF ~1.31; every major time segment positive.
- FVG 2–6, CVD7, SL160–200: fewer trades and higher quality.
- FVG 3–7 / CVD8: quality improves but throughput drops strongly.

## Market regime findings
Liquidity Core = London 02:00–05:00 ET + US morning 07:00–12:00 ET + Globex reopen 18:00–19:00 ET.

- Middle family improves from PF ~1.32 all-hours to ~1.57 in Liquidity Core.
- Quality family improves to ~1.65 in Liquidity Core.
- Lunch 12:00–14:00 ET is weak for middle/quality.
- Cash open / OR is strong for the high-throughput family but has a small trade sample in the stricter families.
- Regime filters remain market-structure filters, not optimized individual hours.

## Exit-management findings
Unlike MGC, MNQ benefits from a late trade trail.

### Harvest candidate
- FVG 1–5
- CVD6
- SL160 ticks
- TP 2.0R
- BE OFF
- Trade trail ~120 / 16
- Liquidity Core
- ~578 trades
- PF ~1.45
- all three time segments positive

### Balanced / Production candidate
- FVG 2–6
- CVD7
- SL200 ticks
- TP 1.25R
- BE OFF
- Trade trail ~100 / 40
- Liquidity Core
- ~254 trades
- PF ~1.70–1.74
- all three time segments positive

### Quality candidate
- FVG 2–8
- CVD8
- SL200 ticks
- TP 1.25R
- BE OFF
- Trade trail ~160 / 16
- Liquidity Core
- ~167 trades
- PF ~1.78

## Rolling 8 trading-day consistency (1 MNQ, before PA daily/account overlays)
- Harvest: ~62.8% positive rolling-8 windows; median +$51.40; worst -$451.70
- Balanced: ~60.9%; median +$36.70; worst -$310.80
- Quality: ~47.5%; median $0 due sparse trading; worst -$240.40

## Contract size / PA findings — first lifecycle pass
Current Apex 50K Level 1 allows 20 micros and has a $1,000 DLL. This makes the clean nominal stop-risk zones approximately:
- Harvest SL160: up to ~12 MNQ before gross stop risk exceeds ~$1,000
- Balanced/Quality SL200: up to ~10 MNQ before gross stop risk reaches ~$1,000

### Harvest lifecycle highlights
- 9 MNQ Intraday: strongest initial time-for-money result in the simplified lifecycle pass; ~23 payouts / ~9 breaches over the 3-year historical stream; first payout among successful account sequences ~20 days average.
- 8–10 MNQ is the preferred clean research zone.
- EOD has lower churn but lower banked dollars per slot-day than the best Intraday variants.

### Production / Quality sizing
- Balanced/Quality around 7–9 MNQ has materially lower raw stop exposure and lower churn than high-size variants.
- Exact final size must be revalidated with the Pine account engine and TradingView fills.

## Daily management
The first bar-level sweep suggests MNQ is not identical to MGC:
- no daily cap remains competitive on raw expectancy;
- daily profit protection around activation 400–500, giveback 100–150, cap 750–1,000 can improve PF / reduce DD for the Harvest family but costs some total net profit;
- payout lifecycle, not raw strategy P&L, should decide the final daily settings.

## Native tick-delta diagnostic
Only on the period where native Delta is actually populated:
- Harvest PF improves from ~1.38 to ~1.53 when requiring native delta direction agreement (1 bar).
- Balanced PF improves further as native streak is strengthened; native streak 3 showed PF ~2.06 in the shorter native-data sample.
- Quality shows the same direction, but sample size becomes small.

This is diagnostic evidence, not yet a production rule, because native delta is unavailable in the first ~2 years of the dataset.

## Current recommendation before Pine validation
### MNQ Production / Balanced research preset
- Qty research zone: 7–9 MNQ
- FVG 2–6 ticks
- CVD streak 7
- VWAP side veto ON
- SL 200 ticks
- TP 1.25R
- BE OFF
- Trade trail 100 / 40
- Liquidity Core

### MNQ Harvest research preset
- Qty research zone: 8–10 MNQ
- FVG 1–5 ticks
- CVD streak 6
- VWAP side veto ON
- SL 160 ticks
- TP 2.0R
- BE OFF
- Trade trail 120 / 16
- Liquidity Core

## Required validation before blind PA deployment
1. Build full Pine variants without removing execution/alerts/account logic.
2. TradingView backtest must match simulator trade count and direction/entry sequence reasonably closely.
3. Calibrate exact VWAP session anchor and bar-magnifier/intrabar sequencing.
4. Run exact EOD and Intraday PA account lifecycle in Pine.
5. Only then choose final qty and daily activation/giveback/cap.
6. Later compare MNQ daily P&L and breach dates against MGC to measure actual diversification benefit.
