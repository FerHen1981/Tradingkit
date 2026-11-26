# MYM Scratch Research — Final Proposal

## Method
MYM was researched from scratch using the corrected multi-market engine:
- no same-fill-bar strategy exit;
- stop-first on ambiguous later OHLC bars;
- valid tick rounding;
- 1 tick adverse slippage baseline plus 2/3-tick stress;
- MYM tick size = 1 index point;
- MYM tick value = $0.50/tick;
- micro commission convention = $1.02 round-turn;
- canonical reconstructed OHLCV CVD proxy;
- no isolated hour/day optimization;
- all structural sessions except mandatory 16:55–18:00 ET flat/maintenance window;
- 18:00 ET session-day for PA lifecycle.

## Structural families

### Production / Quality
- FVG 12–20 ticks
- SL 480 ticks
- TP 1.25R
- limit expiry 24 bars
- CVD6
- BE OFF
- trade trail OFF
- no discretionary regime filter

1 MYM structural metrics:
- ~449–451 trades
- PF ~1.41
- 2-tick stress PF ~1.40
- 3-tick stress PF ~1.38
- all historical segments positive
- LONG and SHORT both positive

Recommended sizing:
- 3 MYM
- gross nominal stop = 480 * $0.50 * 3 = $720 before costs/slippage
- EOD PA preferred as the baseline validation model
- Daily management OFF for first Pine parity test

Lifecycle, 3 MYM, EOD, daily OFF:
- ~451 trades
- PF ~1.417
- rolling-8 positive ~68.45%
- ~$20.8k banked
- 12 payouts
- 7 breaches
- ~$1.91k banked / 100 account-slot days
- P1 average ~69 days

Daily cap $750 raises PF slightly but does not improve lifecycle economics enough to justify extra complexity for Production.

### Balanced alternative
- FVG 10–24
- SL480
- 1.25R
- expiry24
- CVD5
- 3 MYM
- daily OFF or cap1000

This monetizes faster than Quality but with more breaches.
EOD daily OFF: ~$22.5k banked, 13 payouts, 10 breaches.
EOD cap1000: ~$24.7k banked, 15 payouts, 13 breaches.

### Harvest
- FVG 4–8
- SL160
- 1.5R
- expiry18
- CVD3
- 5 MYM
- hard daily cap $1,000
- BE OFF / trail OFF
- EOD baseline

Lifecycle:
- ~2,070 trades after daily cap
- PF ~1.171
- rolling-8 positive ~61.5%
- ~$42.6k banked
- 28 payouts
- 67 breaches
- ~$3.89k banked / 100 slot-days
- P1 average ~13.7 days

This is a true high-churn Harvest model and should only be used when PA replacement is inexpensive and abundant.

## High-R finding
A high-R family exists around:
- FVG6–18
- SL260
- 4.5R
- expiry24
- CVD8

It remains profitable under slippage stress, but PA economics are weaker because large intratrade excursions interact poorly with intraday trailing drawdown. It is retained as a research branch, not the default.

## EOD vs Intraday
Unlike MNQ, MYM can show material EOD-vs-Intraday differences, especially for high-R/wide-excursion families. Therefore the PA model must remain a separate lifecycle axis; strategy PF alone is insufficient.

## Pine validation gate
Validate Production first:
- 3 MYM
- FVG12–20
- CVD6 proxy ON
- SL480 ticks
- 1.25R
- expiry24
- BE/trail OFF
- daily OFF
- all sessions except force-flat
- $0.51 per side commission
- 1 tick slippage
- EOD PA preset

Do not optimize further until Pine and the scratch engine have near-parity in trade count, WR/PF, payoff and LONG/SHORT behavior.
