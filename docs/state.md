# Live state

Read this first in every chat. Update it last. If it is stale, nothing below it
can be trusted.

_Last updated: 2026-08-11 (Analyses & Data chat)_

## Live settings

| Account | Firm | Phase | Strategy | Asset | Volume | Since | Dataset behind it |
|---|---|---|---|---|---|---|---|
| _TBD_ | | | | | | | |

> Not yet filled. Until this table is real, "this week looks like last week" is a
> feeling, not a finding.

## Datasets

Tracked in `data/manifest.json` (not yet created). No analysis may cite a dataset
that is not registered there.

| Symbol | Range | CVD valid from | Rows | Source | Status |
|---|---|---|---|---|---|
| NQ | 2023-06-18 → 2026-06-17 | **unknown** | ~1.1M | TradingView 1m export | in use, CVD depth unverified |

## In-sample / out-of-sample

Defined on the **CVD-valid window**, not the calendar.

- **In-sample**: everything up to ~2024.
- **Walk-forward**: `funnel.py` restarts a fresh eval at many points — this is
  the working OOS for the eval question.
- **Sealed holdout**: most recent 12 months. Untouched until a config is frozen.
  One look, one verdict.
- **Note**: the 2023-2026 window is already *burnt* — the roll/OpEx factory was
  tuned on it (`CLAUDE.md`: "validated, 3y OOS"). It is in-sample by use.

## Open decisions (blocking)

1. **How far back does real per-bar `Delta` actually go?** TradingView derives
   volume-delta from lower-timeframe data with plan-limited history. Probe one
   symbol to the limit before exporting 15 years of anything. This boundary sets
   the entire research window.
2. **Data hosting.** ~500 MB CSV per symbol per 15y → ~10 GB total: too large for
   git (100 MB/file hard limit) and for LFS free tier. Proposed: Parquet+zstd
   (~1 GB total) published as GitHub Release assets, fetched per analysis.
   Requires a small Parquet reader in `backtest/data.py`.
3. **Micros**: proposal is to *not* export them. Same price series as full-size;
   only the multiplier differs and that already lives in `config.py` `CONTRACTS`.
   CVD should be read from the liquid full-size contract regardless.
4. **QQQ**: not a future, different session and volume semantics, not tradable on
   a futures prop account. Proposal: drop, or context-only.
5. **BTC**: CME futures start Dec 2017 (max ~8.5y). Contract spec in
   `config.py:42` is marked **verify** (BTC=5 vs MBT micro).
6. **FX futures multipliers** (`6E/6B/6J/6A/6S/6C`) are marked **verify** in
   `config.py:44-49`.

## Not started

- `data-contract` skill (dataset registration + CVD gate)
- `eval-throughput` skill (Goal A metrics)
- `payout-throughput` skill (Goal B metrics)
- `recap` skill (fixed weekly format)
- El Presidente dashboards (two URLs, one per goal)
