# Time-of-day × day-of-week analysis + the EOD drawdown model

## EOD vs Intraday trailing drawdown — the biggest funding lever found

The four scripts are one engine; El Toro/Dorado use `ddModel="Intraday"`,
El Matador/Patron use `ddModel="EOD"`. Intraday ratchets the trailing DD on the
*unrealised* peak (punishing you for giving back open profit); EOD ratchets only
on the daily closing balance. Eval funnel (fresh eval every 5 sessions, 20-session
horizon), NQ 1m, 3y:

| config | drawdown model | pass-rate |
|---|---|---:|
| El Toro | Intraday | 29.1% |
| El Toro TUNED (+RTH) | Intraday | 34.4% |
| **El Matador** | **EOD** | 35.8% |
| **El Matador + RTH** | **EOD** | **41.1%** |

**El Matador (EOD) + RTH hours funds ~41% of evals vs El Toro's 29%** — the single
biggest improvement to the funding objective. Presets `EL_MATADOR`, `EL_PATRON`
added.

## Heatmap (ET hour × weekday, El Toro raw signal, 2,628 trades, 3y)

Interactive version: switch metric (expectancy / PF / win% / net / count / hold).
Diverging color centred on break-even.

**By ET hour — expectancy $/trade (in-sample):**
- Strong positive: **00 (+432, PF 1.71), 23 (+321, PF 1.51), 04 (+200), 11 (+184),
  14 (+183)**.
- Strong negative: **20 (−357), 06 (−339), 22 (−332), 03 (−294), 10 (−277)**.
- The RTH block 09–15 is **mixed**, not uniformly good — only 11 & 14 carry it;
  09, 10, 12, 13, 15 are negative. So "trade RTH" is too coarse; the real edge is
  a handful of hours.

**By weekday:** all net-negative on raw signal (negative underlying edge), but
Tue/Wed least bad, Thu/Fri worst.

## Caveat — do not hard-code these hours yet

This is one in-sample 3-year window. Selecting hours by in-sample expectancy is
textbook overfitting. An hour-filtered config must be **walk-forward validated**
(tune the hour mask on 2y, confirm on 1y) before it goes into a preset or the Pine
time-gate. Next step: build a validated "best-hours" mask and re-run the funnel
IS/OOS.
