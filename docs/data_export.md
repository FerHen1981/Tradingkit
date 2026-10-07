# Dataset export spec — Quantower → research pipeline

The one rule that governs everything here: **CVD is never disabled.** A file
without a real per-bar `Delta` is not a smaller dataset, it is a *different
strategy* (`indicators.py:162-173` turns the filter into a pass-through). So the
export must carry real order-flow, and the validator must be able to prove it.

Run `tools/validate_dataset.py` on every file **before** uploading. It is cheap;
re-exporting 15 years because a column was wrong is not.

---

## 0. First, the pilot

Do **one** symbol end-to-end before exporting anything else. NQ or ES, as far
back as your feed allows. That single file answers the only question that
actually sets the research window: *how far back does real Delta exist?*

Everything else waits for that answer.

---

## 1. Which data connection

Quantower itself does not hold history — your **connection** does, and tick-level
history is what real Delta is computed from. Depth differs enormously per vendor
(Rithmic and CQG are typically shallow on historical ticks; IQFeed, dxFeed and
Barchart go much deeper).

**Tell me which connection you export from.** If a vendor only serves minute
bars for older periods, Quantower cannot reconstruct Delta there — it will hand
back zeros, which look like data and are not.

## 2. Load volume-analysis data

Bid/ask volume is a separate load in Quantower from plain OHLCV. Make sure the
volume-analysis (footprint) data is actually loaded for the full requested range
before exporting — not just for the visible window. If it silently loads only
the recent part, the older bars come out with `Delta = 0`.

The validator is built to catch exactly this, but catching it after a 15-year
export is a wasted evening.

## 3. Export settings

| Setting | Value | Why |
|---|---|---|
| Timeframe | **1 minute** | Sufficient base — see §6 |
| Session template | **full CME session (~23h)**, not RTH | The engine models the 18:00 ET roll and the 16:55-18:00 flat |
| Timezone | **UTC**, or ET with explicit offset | Ambiguous local time breaks DST; the loader wants an offset |
| Contract | see §5 | |
| Range | as far back as the feed goes — **do not trim** | I need to see where Delta dies |

**Do not delete the zero-delta region.** That boundary is the finding.

## 4. Columns

Minimum viable:

```
DateTime, Open, High, Low, Close, Volume, Delta
```

Preferred (adds cross-checks and lets the validator verify Delta rather than
trust it):

```
DateTime, Open, High, Low, Close, Volume, BuyVolume, SellVolume, Delta, CVD_close
```

- `Delta` = per-bar buy-volume minus sell-volume, from real trade classification.
- `CVD_close` is derivable (`cumsum(Delta)` per session) — include it if it comes
  free, skip it if it costs an extra step.
- Quantower's own header names (`Buy Volume`, `Ask Volume`, `Date`+`Time` split,
  etc.) are fine — the validator normalises common variants and tells you what it
  matched.

## 5. Continuous contracts — say which kind

For a multi-year file you need a continuous series, and **how it is stitched
changes the results**:

- **Back-adjusted**: historical prices shifted so roll gaps vanish. Clean equity
  curves, but historical price levels are fictional and old absolute prices drift
  far from what traded.
- **Raw / spliced**: real prices, but each roll leaves a gap — and this strategy
  reads 3-bar fair-value gaps. A roll gap can manufacture a signal that never
  existed.

Neither is free. Tell me which one you exported; if Quantower lets you export the
**roll dates**, include them and I will mask the roll bars instead of guessing.

## 6. Why 1-minute is enough

`data.py:resample()` aggregates 1m to any N-minute bar, session-aligned and
gap-safe, and it **sums** `Delta`, `BuyVolume` and `SellVolume`. Volume delta is
additive, so a 5-minute delta is exactly the sum of its five 1-minute deltas —
nothing is lost by storing 1m and building the rest.

The one thing 1m cannot reconstruct is **intrabar ordering**: when a bar's range
spans both stop and target, we cannot know which came first. The engine currently
assumes the stop (`README.md`, pessimistic fill model). If you can also export a
**short recent window at tick or 1-second resolution** (a few months is plenty),
we can measure how much that assumption costs instead of eating it blind.

## 7. Contract specs — getting BTC and the FX futures out of "verify"

`config.py:41-49` marks BTC and `6E/6B/6J/6A/6S/6C` as unverified, so their dollar
figures are currently guesses. Quantower's **Symbol Info** panel shows tick size
and tick value per symbol directly — that is the authoritative source and takes a
minute per symbol.

Send me, per symbol: **tick size**, **tick value ($)**, **contract multiplier**,
and whether it is the full-size or micro contract. Cross-check against what your
broker/prop firm actually fills, since that is what determines real P&L.

## 8. File format, hosting & transfer

Export CSV from Quantower, then convert — the validator does it in the same pass:

```
python tools\validate_dataset.py NQ_export.csv --symbol NQ --to-parquet exports\
```

**Parquet + zstd** is roughly 4-10× smaller than CSV depending on how noisy the
volume columns are (4.1× on a synthetic worst case; real price series do better).
A ~500 MB CSV should land between 50 and 125 MB.

Naming: `<SYMBOL>_1m_<FIRST>_<LAST>.parquet`, e.g. `NQ_1m_2019-01_2026-08.parquet`.

### Where it goes: PC → bucket → server

Not PC → server. The bucket is the canonical copy; the PC uploads once and the
server pulls. That way nothing depends on the PC being awake, and a rebuilt server
re-syncs itself.

```
  Quantower (PC)  ──upload──▶  object storage  ──sync──▶  VPS  ──▶  analyses
                               (canonical)                 (cache)
```

**Cloudflare R2** is the recommended bucket: 10 GB free, zero egress fees, and it
speaks the S3 API so `rclone` works out of the box.

Upload from Windows (once `rclone config` has an `r2` remote):

```
rclone copy exports\ r2:tradingkit-corpus\1m\ --progress
```

Pull on the VPS:

```
rclone sync r2:tradingkit-corpus/1m /opt/tradingkit/data --progress
```

If you would rather not run `rclone` on the PC, R2's web UI accepts drag-and-drop
for the pilot file — the CLI only starts paying off at corpus scale.

### Getting a file to me

I need a URL that plain `curl` can fetch. Two workable routes:

1. **R2 presigned URL** (preferred) — time-limited, no public exposure:
   `rclone link r2:tradingkit-corpus/1m/NQ_1m_....parquet` and paste me the link.
2. **GitHub Release asset** on this repo — easy drag-and-drop in the browser
   (Releases → Draft a new release → tag `data-v1` → attach → publish), but on a
   **private** repo the asset download needs a token, so tell me if that route is
   chosen and we check access before you upload 14 files.

⚠ **Do not make exchange data publicly downloadable.** CME data via a broker feed
comes with redistribution terms; a public bucket is redistribution. Presigned,
expiring links are the right shape.

### Direct PC → server, if you ever want it

Windows 10+ ships OpenSSH, so from PowerShell:

```
scp exports\*.parquet mex@<vps-host>:/opt/tradingkit/data/
```

Fine for a one-off, but it makes the transfer depend on the PC being on, which is
the thing we are trying to get rid of.

## 9. What to skip

- **Micros** (MNQ/MES/MGC/…) — same price series as full-size; only the multiplier
  differs and that lives in `config.py` `CONTRACTS`. Read CVD from the liquid
  full-size contract even when trading micros.
- **QQQ as a strategy dataset** — not a future, RTH-only volume, different tape,
  not tradable on a futures prop account. Worth having as a *context* series for
  correlation work (see `docs/state.md`), not as something to backtest.
