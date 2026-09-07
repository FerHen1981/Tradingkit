# MNQ Scratch Research — corrected engine / reconstructed CVD

## Engine
- 1-minute MNQ, full 2023-08-24 through 2026-08-21 sample.
- MES/MNQ tick: 0.25; MNQ tick value $0.50.
- Rithmic MNQ commission: $1.02 round turn per MNQ.
- No strategy exit on limit-fill bar.
- Later ambiguous OHLC bar: stop before target.
- Valid tick rounding.
- 1 tick adverse exit slippage baseline, 2 and 3 ticks stress.
- 16:55-18:00 ET mandatory flat/maintenance only; no isolated hour/day optimization.
- 18:00 ET trading-day boundary for PA/daily accounting.
- Reconstructed OHLCV CVD proxy used as a first-class axis.

## Structural findings
- Robust edge remains concentrated in small FVGs.
- Quality plateau moved clearly to CVD7-8 under the corrected engine.
- CVD8 produced the strongest median robustness; CVD7 retained more throughput.
- CVD5 is a high-throughput family but is much more cost/churn sensitive.

## Quality candidate
- FVG 2-8 ticks
- SL 200 ticks
- 1.25R
- limit expiry 6 bars
- CVD8 proxy
- 448 trades
- PF ~1.373
- PF with 2-tick slippage ~1.360
- PF with 3-tick slippage ~1.347
- all historical segments positive
- LONG and SHORT positive

### Production sizing candidate
- 6 MNQ
- Apex 50K EOD model
- daily management OFF initially for Pine parity
- alternative after parity: hard daily cap $1,000

EOD lifecycle, 6 MNQ:
- OFF: ~$38.5k banked, 20 payouts, 13 breaches
- CAP1000: ~$41.8k banked, 23 payouts, 11 breaches
- CAP750: ~$36.7k banked, 20 payouts, 8 breaches

Quality C8 is the preferred Production research family because it remains robust under severe slippage stress and has materially lower churn than throughput variants.

## Balanced / faster candidate
- FVG 1-4 ticks
- SL 120 ticks
- 3.0R
- expiry 12 bars
- CVD7 proxy
- ~834 trades
- PF ~1.256
- 3-tick stress PF ~1.228
- all historical segments positive

At 11 MNQ EOD:
- OFF: ~$39.0k banked, 20 payouts, 14 breaches
- CAP1250: ~$59.4k banked, 30 payouts, 36 breaches

This is a faster monetization candidate but has clearly higher churn once daily caps are used aggressively.

## Throughput CVD5 diagnostic
- FVG 1-6
- SL140
- 2R
- expiry12
- CVD5
- ~2,951 trades
- PF ~1.119
- 3-tick stress PF ~1.094

This family can generate very high payout throughput with caps but breaches/churn are much higher. It is not the default Production candidate.

## Current recommendation
1. Validate Quality C8 in Pine first, daily management OFF.
2. Require trade-count / WR / PF / long-short parity before optimizing daily cap.
3. If parity holds, compare 6 MNQ OFF vs CAP750 vs CAP1000 in TradingView.
4. Only then validate Balanced CVD7 as a Harvest/time-for-money alternative.
