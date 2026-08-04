# Timeframe scan — does 2m…30m beat 1m?

Question: resample the NQ 1m data to 2/3/…/15/20/30-minute bars and check whether
a higher timeframe funds accounts (El Toro pass-rate) or banks more per blown PA
(El Dorado banked ÷ breaches) than 1m.

Method: `data.resample()` (session-aligned to 18:00 ET). Distance inputs are in
ticks and tuned for 1m, so each timeframe's tick inputs are scaled by **√N**
(volatility scales ~√time) to give every timeframe a fair shot. Tuned presets
(`EL_TORO_TUNED`, `EL_DORADO_TUNED`). Full 3-year sample.

## Results

| TF | El Toro pass% | El Dorado PF | banked | breaches | $/breach | trades |
|---:|---:|---:|---:|---:|---:|---:|
| **1m** | **34.4%** | 0.89 | $9,000 | 28 | $321 | **1,130** |
| 2m | 28.5% | 0.82 | $3,000 | 16 | $188 | 542 |
| 3m | 23.2% | 0.84 | $1,500 | 12 | $125 | 339 |
| 4m | 21.2% | 0.96 | $0 | 5 | — | 207 |
| 5m | 23.8% | 0.95 | $10,500 | 8 | $1,312 | 191 |
| 6m | 12.6% | 0.47 | $0 | 8 | — | 100 |
| 7m | 15.2% | 0.84 | $0 | 2 | — | 77 |
| 8m | 17.9% | 0.89 | $0 | 2 | — | 43 |
| 9m | 16.6% | 1.03 | $3,000 | 4 | $750 | 67 |
| 10m | 17.9% | 0.53 | $0 | 1 | — | 25 |
| 12m | 21.2% | 1.03 | $0 | 2 | — | 31 |
| 15m | 12.6% | 0.18 | $0 | 0 | — | 6 |
| 20m | 11.3% | 4.57 | $0 | 0 | — | 4 |
| 30m | 7.9% | 0.01 | $0 | 0 | — | 3 |

## Conclusions

1. **El Toro: 1m wins decisively.** Pass-rate falls almost monotonically with
   timeframe (34% → 8%). The eval is a variance play — it needs many fast
   attempts to hit +$3,000 before the trailing DD; coarser bars mean fewer
   trades and fewer chances. Stay on 1m.

2. **El Dorado: 1m is the only trustworthy row.** Trade count collapses roughly
   as 1/N (1,130 → single digits). The eye-catching higher-TF numbers are
   **small-sample noise**: 20m shows PF 4.57 on *4 trades*, 30m PF 0.01 on *3*.
   Even the best-looking mid-TF rows (5m: $1,312/breach; 9m: PF 1.03) rest on
   191 and 67 trades over three years — far too thin to trade.

3. **Structural reason.** N-minute bars have ~1/N as many 3-bar FVG windows, so
   signal density drops with N regardless of tuning. This stack (FVG + delta +
   VWAP + time-gate) is inherently a high-frequency 1-minute intraday method;
   coarsening the bars removes its edge rather than improving it.

**Bottom line: keep both scripts on 1m.** No higher timeframe robustly improved
the payout/funding objective; the apparent exceptions are sample-size artefacts.

## Caveat / what could still be worth a look

`5m` was the one mid-timeframe with a non-trivial trade count (191) *and* a
positive-ish profile (PF 0.95, $10.5k banked / 8 breaches). Probably noise, but
it is the only candidate worth a dedicated **per-5m re-optimisation + walk-forward**
(rather than √N-scaled 1m params) before dismissing. Everything ≥6m is too thin.
