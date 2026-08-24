# MES Scratch Research — Final Proposal

## Engine assumptions
- MES 1-minute, 2023-08-24 through 2026-08-21.
- Research restarted from scratch after invalidating prior same-bar-fill-biased results.
- No same-fill-bar strategy exit.
- Ambiguous later bar: stop before target.
- Valid 0.25 tick rounding.
- 1 tick adverse slippage baseline; +1 and +2 additional ticks used as stress.
- Rithmic MES commission: $1.02 round-turn per MES.
- Force-flat 16:55–18:00 ET.
- PA/daily accounting uses 18:00 ET trading-day boundary.
- Delta OFF for the production baseline because historical native delta coverage is incomplete.
- No isolated hour/day optimization.

## Structural result
Three independent edge families survived. The broadest plateau is larger FVG with medium expiry. The most useful PA families were:
- B075: FVG 8–20 ticks, SL 140 ticks, 0.75R, expiry 24 bars.
- B125: FVG 8–22 ticks, SL 120 ticks, 1.25R, expiry 24 bars.
- Higher-R 3R/3.5R families remained profitable under slippage stress but monetized poorly in the PA lifecycle because of wide stops/long holds.

## Proposed Production
- 4 MES
- FVG 8–20 ticks
- SL 140 ticks
- 0.75R
- Limit expiry 24 bars
- Delta OFF
- VWAP veto OFF
- BE OFF
- Trade trail OFF
- All structural hours except mandatory 16:55–18:00 ET flat window
- Daily management OFF
- Apex 50K EOD PA

Research metrics:
- 2,044 trades
- PF 1.170
- PF with 2-tick exit slippage 1.146
- PF with 3-tick exit slippage 1.122
- 2023/24, 2025 and 2026 all positive
- Long and short both positive
- Rolling-8 positive ~59.9%
- PA lifecycle: ~$32.85k banked, 18 payouts, 11 breaches over full sample
- ~30 days to P1 average; ~51 days average later interval
- ~$3,005 banked per 100 account-slot days

## Proposed Harvest
- 5 MES
- FVG 8–22 ticks
- SL 120 ticks
- 1.25R
- Limit expiry 24 bars
- Delta OFF
- VWAP veto OFF
- BE OFF
- Trade trail OFF
- Daily trail/cap: activation $500, giveback $150, cap $1,000
- Apex 50K EOD PA

Research metrics:
- 1,153 trades after daily management
- PF ~1.208
- Underlying base family PF 1.136; 2-tick stress 1.114; 3-tick stress 1.093
- 2023/24, 2025 and 2026 all positive
- Rolling-8 positive ~64.7%
- PA lifecycle: ~$46.38k banked, 30 payouts, 27 breaches over full sample
- ~17.6 days to P1 average; ~20.5 days later payout interval
- ~$4,243 banked per 100 account-slot days

## Interpretation
- Production is preferred for controlled fleet deployment and lower churn.
- Harvest is preferred when account replacement is cheap/abundant and time-for-money is the priority.
- Intraday PA was not selected as the default because conservative MFE-first threshold replay caused materially more breaches.
- ES is not selected for these final sizes: 4–5 MES is below one ES equivalent, so switching to 1 ES would roughly double exposure. MES sizing precision is more valuable than the ES commission saving here.
- Native Delta sign agreement is interesting for some higher-R families in 2026 but is not production-ready because older data lacks adequate native delta coverage.

## Required Pine validation
Before live PA use, Pine should be validated against the scratch engine on one fixed period:
- near-parity trade count;
- similar win rate / PF;
- correct 18:00 session day;
- correct $0.51 per-side MES commission;
- no same-bar fill lookahead;
- correct force-flat;
- correct limit expiry and tick rounding.
