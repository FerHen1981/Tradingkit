# MES Scratch Research — Final Proposal with Reconstructed CVD

## Method
MES was restarted from scratch after invalidating the earlier same-bar-fill-biased research.
The corrected engine uses:
- no strategy exit on the limit-fill bar;
- stop-first handling if SL and TP are both touched on a later OHLC bar;
- valid 0.25 tick rounding;
- 1 tick adverse exit slippage baseline, plus 2- and 3-tick stress;
- explicit MES round-turn commission;
- force-flat/maintenance handling;
- 18:00 ET trading-day boundary for daily/PA accounting;
- reconstructed OHLCV CVD proxy as a first-class axis;
- no isolated hour/day cherry-picking.

## Canonical CVD proxy
Per 1-minute bar:
- close > open => +1
- close < open => -1
- doji => compare close with previous close
- unresolved doji => carry previous polarity
CVD N = N consecutive proxy-direction bars aligned with the FVG trade direction.

## Structural result
The broad CVD search identified a strong CVD4–6 plateau.
After 3-tick adverse exit-slippage stress:
- CVD4 median PF ~1.15
- CVD5 median PF ~1.18
- CVD6 median PF ~1.28
CVD6 was both the strongest and broadest quality zone.

## Production proposal
Signal/exit:
- FVG 10–22 ticks
- SL 120 ticks
- TP 1.75R
- pending limit expiry 6 bars
- reconstructed CVD streak 6
- VWAP veto OFF
- BE OFF
- trade trail OFF
- no discretionary session filter
- mandatory force-flat only

Sizing/account:
- 6 MES
- EOD 50K PA model
- daily management: OFF initially for Pine parity
- optional second validation: day activation 750 / giveback 100 / cap 1250

Why 6 MES:
- nominal gross full stop = 120 * $1.25 * 6 = $900 before costs;
- 7 MES would be ~$1,050 gross and crosses the modeled $1,000 Level-1 DLL.

Structural metrics, 1 MES:
- ~268 trades
- PF ~1.666
- PF 2-tick stress ~1.637
- PF 3-tick stress ~1.608
- all historical segments positive
- LONG and SHORT positive

With 6 MES, EOD lifecycle:
- daily OFF: ~$25.9k banked, 12 payouts, 3 breaches
- day 750/100/1250: ~$24.1k banked, 13 payouts, 2 breaches
The OFF version is simpler and should be Pine-validated first.

## Harvest proposal
Signal/exit:
- FVG 8–22 ticks
- SL 120 ticks
- TP 1.00R
- pending limit expiry 12 bars
- reconstructed CVD streak 4
- VWAP veto OFF
- BE OFF
- trade trail OFF
- no discretionary session filter

Sizing/account:
- 5 MES
- EOD 50K PA model
- hard daily cap $1,000

Why 5 MES:
- nominal gross full stop = 120 * $1.25 * 5 = $750 before costs;
- materially lower tail risk than 7–8 MES while retaining good payout throughput.

Metrics:
- underlying structural PF ~1.259
- rolling-8 positive roughly mid-60% zone in the lifecycle tests
- with 5 MES + cap $1,000:
  - ~$47.2k banked
  - 25 payouts
  - 17 breaches
  - ~$4.32k banked per 100 account-slot days
  - P1 average ~36.5 days
  - later payout interval ~27.2 days

## Alternative faster Harvest
6 MES with cap $1,000 or $1,250 increases throughput but also account churn. It is not the default recommendation.

## Trade management
- Quality CVD6: a small BE improvement in PF exists, but total net falls and complexity rises.
- Balanced/Throughput: BE/trailing do not add durable value.
- Defaults remain BE OFF and trade trail OFF.

## MES vs ES
The final recommended sizes are 5–6 MES, only 0.5–0.6 ES equivalent.
Switching to 1 ES would materially increase exposure rather than merely reduce costs.
Therefore MES remains the preferred execution instrument for these defaults.

## Required Pine validation gate
Production first:
- near-parity trade count
- similar WR/PF
- exact FVG range and CVD proxy
- expiry 6
- SL120 / 1.75R
- no same-fill-bar future leakage
- correct 18:00 session accounting
- correct commission/slippage semantics

Only after Production parity is proven should Harvest be validated and then moved to PA lifecycle/portfolio testing.
