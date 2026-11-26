# EL TESORO — MES Research Summary

## Research basis
- Dataset: MES 3y 1m tick_cvd.csv
- Period: 2023-08-24 through 2026-08-21
- Bars: 1,058,100
- Main CVD: Pine-parity reconstructed from OHLCV across full history
- Native tick delta: diagnostic only; first non-zero data appears 2025-12-21
- No isolated hour/day optimization
- Market regime: Liquidity Core = London 02:00–05:00 ET + US morning 07:00–12:00 ET + Globex reopen 18:00–19:00 ET
- TradingView-like pending limit sequencing and pessimistic stop-before-target handling

## Structural findings
1. MES is fundamentally different from MGC and MNQ.
2. The dominant structural edge is a short-horizon exit:
   - SL around 20 ticks
   - target around 0.5R
3. FVG 10–18 with low CVD threshold is the highest-quality core.
4. FVG 8–18 with low CVD threshold increases throughput.
5. VWAP veto does not improve the main families; default candidate is OFF.
6. BE/trade trailing add no value in the short-target family because target is normally reached before those mechanisms can activate.
7. Cash open / OR60 are particularly strong regimes; Liquidity Core improves PF modestly while reducing drawdown.

## Production candidate
- 18 MES
- FVG 10–18 ticks
- CVD streak 3
- VWAP veto OFF
- SL 20 ticks
- TP 0.5R
- BE OFF
- Trade trail OFF
- Liquidity Core
- Daily profit: activation $500 / giveback $150 / cap $750

Strategy:
- 1,146 trades
- Net ≈ $86,668
- PF ≈ 2.07
- Rolling-8 positive ≈ 92.68%
- Median rolling-8 ≈ +$1,333
- Worst rolling-8 ≈ -$1,478
- All three historical segments positive

PA lifecycle:
- EOD: ≈ $61,698 banked, 32 payouts, 0 breaches, ≈ $5,645 per 100 calendar slot-days
- Intraday: ≈ $68,989 banked, 33 payouts, 1 breach, ≈ $6,312 per 100 slot-days
- Mean P1 ≈ 42 days

Lower-risk Production alternative:
- 15 MES
- Same signal/exit logic
- Daily 400 / 150 / 600
- PF ≈ 2.06
- 0 breaches in both EOD and Intraday lifecycle reconstructions
- Lower banked $/slot-day

## Harvest candidate
- 17 MES
- FVG 8–18 ticks
- CVD streak 1
- VWAP veto OFF
- SL 20 ticks
- TP 0.5R
- BE OFF
- Trade trail OFF
- Liquidity Core
- Daily profit management OFF

Strategy:
- 2,677 trades
- Net ≈ $139,911
- PF ≈ 1.64
- Rolling-8 positive ≈ 87.06%
- Median rolling-8 ≈ +$1,380
- Worst rolling-8 ≈ -$2,126
- All three historical segments positive

PA lifecycle:
- Intraday: ≈ $101,179 banked, 49 payouts, 4 breaches, ≈ $9,257 per 100 slot-days
- EOD: ≈ $89,780 banked, 46 payouts, 2 breaches, ≈ $8,214 per 100 slot-days
- Mean P1 Intraday ≈ 24.8 days
- Mean payout interval ≈ 19.6 days

Maximum-throughput alternative:
- 20 MES
- Same Harvest logic
- Similar $/slot-day, more breaches and larger tail exposure
- 17 MES is preferred as the central Harvest candidate

## Interpretation
MES may be the strongest diversification candidate tested after MGC:
- much higher signal frequency;
- strong intrinsic PF in Production;
- very high positive rolling-8 rate;
- payout lifecycle is strong;
- strategy structure is materially different from MGC/MNQ.

Before blind deployment:
1. Build full Pine Production and Harvest variants.
2. Validate trade count and PF in TradingView.
3. Verify the tight 20-tick SL / 0.5R structure is not materially degraded by TradingView intrabar fills/slippage.
4. Compare MES daily-loss/breach dates with MGC/MNQ to quantify actual fleet diversification.
