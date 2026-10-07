#!/usr/bin/env python3
"""Validate a 1-minute dataset before it enters the research pipeline.

The gate this enforces: **CVD is never disabled.** A file whose ``Delta`` column
is absent, empty or all-zero cannot be used, because the engine would silently
turn the delta filter into a pass-through (``indicators.py:162-173``) and
backtest a different strategy than the one running live.

Rather than a blunt pass/fail, the important output is the **CVD boundary**: the
point in history from which real per-bar delta actually exists. Feeds usually
serve deep OHLCV and shallow order-flow, so a 15-year file is often a 4-year
research window wearing a 15-year coat.

Usage
-----
    python3 tools/validate_dataset.py NQ_1m.csv --symbol NQ
    python3 tools/validate_dataset.py NQ_1m.csv --symbol NQ --to-parquet out/
    python3 tools/validate_dataset.py NQ_1m.csv --symbol NQ --write-manifest

Exit code is 0 on PASS (possibly with a restricted window), 1 on REJECT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "data" / "manifest.json"

# Quantower and friends spell these several ways. Map lowercased/stripped
# header -> canonical name.
ALIASES = {
    "datetime": "DateTime", "date time": "DateTime", "timestamp": "DateTime",
    "time": "DateTime", "date": "Date",
    "open": "Open", "high": "High", "low": "Low", "close": "Close",
    "last": "Close",
    "volume": "Volume", "vol": "Volume", "total volume": "Volume",
    "buyvolume": "BuyVolume", "buy volume": "BuyVolume", "ask volume": "BuyVolume",
    "askvolume": "BuyVolume", "bought": "BuyVolume",
    "sellvolume": "SellVolume", "sell volume": "SellVolume", "bid volume": "SellVolume",
    "bidvolume": "SellVolume", "sold": "SellVolume",
    "delta": "Delta", "volume delta": "Delta", "cumulative delta": "CVD_close",
    "cvd": "CVD_close", "cvd_close": "CVD_close", "cvd close": "CVD_close",
}

# A month counts as CVD-valid when at least this share of its traded bars
# carries a non-zero delta. Real order flow is noisy; a genuinely quiet minute
# with delta exactly 0 does happen, but not for 20% of a month.
MIN_NONZERO_SHARE = 0.80


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def emit(self) -> None:
        for m in self.notes:
            print(f"  ·  {m}")
        for m in self.warnings:
            print(f"  ⚠  {m}")
        for m in self.errors:
            print(f"  ✗  {m}")


def read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(path)
    return pd.read_csv(path, sep=None, engine="python")


def normalise_columns(df: pd.DataFrame, rep: Report) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    for col in df.columns:
        key = str(col).strip().lower().replace("_", " ").replace("  ", " ")
        canon = ALIASES.get(key) or ALIASES.get(key.replace(" ", ""))
        if canon:
            mapping[col] = canon
    renamed = df.rename(columns=mapping)
    matched = {v for k, v in mapping.items() if k != v}
    if matched:
        rep.note(f"header aliases matched: {', '.join(sorted(matched))}")
    unknown = [c for c in renamed.columns if c not in set(ALIASES.values())]
    if unknown:
        rep.note(f"columns ignored: {', '.join(map(str, unknown[:8]))}")

    # A split Date + Time export needs joining before parsing.
    if "Date" in renamed.columns and "DateTime" in renamed.columns:
        renamed["DateTime"] = (renamed["Date"].astype(str).str.strip() + " "
                               + renamed["DateTime"].astype(str).str.strip())
        renamed = renamed.drop(columns=["Date"])
        rep.note("joined split Date + Time columns into DateTime")
    return renamed


def _to_datetime(values: pd.Series) -> pd.Series:
    """Parse timestamps that may or may not carry an offset. A multi-year export
    spans DST, so the offsets themselves are mixed (-05:00 / -04:00) — pandas
    refuses that unless we normalise to UTC first."""
    try:
        return pd.to_datetime(values, errors="coerce", format="mixed")
    except ValueError as exc:
        if "Mixed timezones" not in str(exc):
            raise
        return pd.to_datetime(values, errors="coerce", format="mixed", utc=True)


def parse_time(df: pd.DataFrame, rep: Report) -> pd.DataFrame | None:
    ts = _to_datetime(df["DateTime"])
    if ts.isna().all():
        rep.error("no DateTime value could be parsed")
        return None
    bad = int(ts.isna().sum())
    if bad:
        rep.warn(f"{bad} unparseable DateTime rows dropped")
        df = df.loc[ts.notna()].copy()
        ts = ts.loc[ts.notna()]
    if ts.dt.tz is None:
        rep.warn("timestamps are timezone-naive — assuming America/New_York. "
                 "Re-export with UTC or an explicit offset to remove the guess "
                 "(DST transitions are silently wrong otherwise).")
        ts = ts.dt.tz_localize("America/New_York", ambiguous="NaT",
                               nonexistent="shift_forward")
        keep = ts.notna()
        if (~keep).any():
            rep.warn(f"{int((~keep).sum())} rows fell in a DST fold and were dropped")
            df, ts = df.loc[keep].copy(), ts.loc[keep]
    df = df.copy()
    df["et"] = ts.dt.tz_convert("America/New_York")
    return df.sort_values("et").reset_index(drop=True)


def check_structure(df: pd.DataFrame, rep: Report) -> None:
    dup = int(df["et"].duplicated().sum())
    if dup:
        rep.warn(f"{dup} duplicate timestamps ({dup / len(df):.2%}) — will be "
                 "de-duplicated on load, but check the export for overlap")

    step = df["et"].diff().dt.total_seconds().dropna()
    if len(step):
        one_min = float((step == 60).mean())
        rep.note(f"{one_min:.1%} of gaps are exactly 60s")
        if one_min < 0.5:
            rep.error(f"only {one_min:.1%} of bars are 1 minute apart — this does "
                      "not look like a 1-minute export")
        # Weekends and the daily maintenance break are legitimate; a multi-day
        # hole in the middle of a week is not.
        big = step[step > 3 * 24 * 3600]
        if len(big):
            rep.warn(f"{len(big)} gaps longer than 3 days (largest "
                     f"{big.max() / 86400:.1f} days) — holidays, or missing history?")

    hours = df["et"].dt.hour.nunique()
    if hours < 20:
        rep.warn(f"only {hours} distinct ET hours present — this looks like an "
                 "RTH-only session template. The engine models the full ~23h CME "
                 "session (18:00 ET roll, 16:55-18:00 flat).")

    for col in ("Open", "High", "Low", "Close"):
        if col not in df.columns:
            rep.error(f"missing required column {col}")
    if {"Open", "High", "Low", "Close"} <= set(df.columns):
        bad = int(((df["High"] < df["Low"])
                   | (df["High"] < df[["Open", "Close"]].max(axis=1))
                   | (df["Low"] > df[["Open", "Close"]].min(axis=1))).sum())
        if bad:
            rep.error(f"{bad} bars have inconsistent OHLC")


def check_delta_consistency(df: pd.DataFrame, rep: Report) -> None:
    have = set(df.columns)
    if {"BuyVolume", "SellVolume"} <= have:
        if "Delta" not in have:
            df["Delta"] = df["BuyVolume"] - df["SellVolume"]
            rep.note("Delta derived from BuyVolume - SellVolume")
        else:
            diff = (df["Delta"] - (df["BuyVolume"] - df["SellVolume"])).abs()
            mism = int((diff > 1e-6).sum())
            if mism:
                rep.warn(f"{mism} bars where Delta != BuyVolume - SellVolume "
                         f"({mism / len(df):.2%})")
        if "Volume" in have:
            diff = (df["Volume"] - (df["BuyVolume"] + df["SellVolume"])).abs()
            mism = int((diff > 1e-6).sum())
            if mism:
                rep.warn(f"{mism} bars where Volume != BuyVolume + SellVolume "
                         f"({mism / len(df):.2%}) — some feeds leave unclassified "
                         "trades out of the split")
    if "Delta" in df.columns and "Volume" in df.columns:
        over = int((df["Delta"].abs() > df["Volume"] + 1e-6).sum())
        if over:
            rep.error(f"{over} bars where |Delta| > Volume — impossible, the "
                      "columns are misaligned or scaled differently")


def cvd_coverage(df: pd.DataFrame, rep: Report) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Per-month share of traded bars carrying a non-zero delta, and the first
    month from which coverage holds continuously to the end of the file."""
    traded = df["Volume"] > 0 if "Volume" in df.columns else pd.Series(True, index=df.index)
    ok = df["Delta"].notna() & (df["Delta"] != 0) & traded
    month = df["et"].dt.tz_localize(None).dt.to_period("M")

    cov = pd.DataFrame({
        "bars": month.groupby(month).size(),
        "traded": traded.groupby(month).sum(),
        "delta_ok": ok.groupby(month).sum(),
    })
    cov["share"] = (cov["delta_ok"] / cov["traded"].replace(0, pd.NA)).astype(float)

    valid = cov["share"] >= MIN_NONZERO_SHARE
    # Walk back from the end: the usable window is the longest unbroken tail.
    first = None
    for period in reversed(cov.index):
        if not bool(valid.loc[period]):
            break
        first = period
    return cov, (first.to_timestamp() if first is not None else None)


def print_coverage(cov: pd.DataFrame) -> None:
    by_year = cov.groupby(cov.index.year).agg(
        bars=("bars", "sum"), traded=("traded", "sum"), delta_ok=("delta_ok", "sum"))
    by_year["share"] = by_year["delta_ok"] / by_year["traded"].replace(0, pd.NA)
    print("\n  CVD coverage by year (share of traded bars with non-zero delta)")
    print("  ────────────────────────────────────────────────────────────────")
    for year, row in by_year.iterrows():
        share = float(row["share"]) if pd.notna(row["share"]) else 0.0
        bar = "█" * int(round(share * 40))
        flag = "" if share >= MIN_NONZERO_SHARE else "   ← unusable"
        print(f"  {year}  {share:6.1%}  {bar:<40}{flag}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(entry: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"datasets": []}
    data["datasets"] = [d for d in data["datasets"]
                        if not (d["symbol"] == entry["symbol"]
                                and d["file"] == entry["file"])]
    data["datasets"].append(entry)
    data["datasets"].sort(key=lambda d: (d["symbol"], d["file"]))
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\n  manifest updated: {MANIFEST.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--symbol", required=True, help="contract key, e.g. NQ ES GC 6E")
    ap.add_argument("--source", default="quantower", help="feed/vendor, for the manifest")
    ap.add_argument("--contract", default="unknown",
                    choices=["back-adjusted", "raw-spliced", "single", "unknown"],
                    help="how the continuous series was stitched")
    ap.add_argument("--to-parquet", type=Path, metavar="DIR",
                    help="also write a zstd parquet copy here")
    ap.add_argument("--write-manifest", action="store_true")
    args = ap.parse_args()

    print(f"\n▌ {args.path.name}  →  symbol {args.symbol}\n")
    rep = Report()

    df = read_any(args.path)
    print(f"  {len(df):,} rows, {len(df.columns)} columns")
    df = normalise_columns(df, rep)

    if "DateTime" not in df.columns:
        rep.error("no DateTime column found — export a timestamp, or a Date + Time pair")
        rep.emit()
        return 1

    parsed = parse_time(df, rep)
    if parsed is None:
        rep.emit()
        return 1
    df = parsed

    check_structure(df, rep)

    if "Delta" not in df.columns and not {"BuyVolume", "SellVolume"} <= set(df.columns):
        rep.error("no Delta (and no BuyVolume/SellVolume to derive it from). "
                  "CVD is never disabled — this file cannot be used. Re-export "
                  "with volume-analysis data loaded, or propose an alternative "
                  "source for approval.")
        rep.emit()
        return 1

    check_delta_consistency(df, rep)
    cov, cvd_from = cvd_coverage(df, rep)

    rep.emit()
    print_coverage(cov)

    first, last = df["et"].iloc[0], df["et"].iloc[-1]
    print(f"\n  range          {first:%Y-%m-%d} → {last:%Y-%m-%d}")

    if cvd_from is None:
        print("\n  ✗ REJECT — no period reaches "
              f"{MIN_NONZERO_SHARE:.0%} delta coverage. The order-flow data never "
              "loaded. Do not run analyses on this file.")
        return 1

    if rep.errors:
        print(f"\n  ✗ REJECT — {len(rep.errors)} structural error(s) above. The file "
              "is internally inconsistent; fix the export before any analysis runs "
              "on it.")
        return 1

    usable = df[df["et"] >= cvd_from.tz_localize("America/New_York")]
    share_kept = len(usable) / len(df)
    print(f"  CVD valid from {cvd_from:%Y-%m}  "
          f"({len(usable):,} bars, {share_kept:.0%} of the file)")

    if share_kept < 0.98:
        verdict_window = f"{cvd_from:%Y-%m}"
        print(f"\n  ⚠ PASS — but only from {cvd_from:%Y-%m}. Everything before that "
              "carries no order flow and must not enter a backtest; it is context "
              "only. The research window is the CVD-valid part, not the file.")
    else:
        print("\n  ✓ PASS — full file carries order flow.")

    if args.to_parquet:
        args.to_parquet.mkdir(parents=True, exist_ok=True)
        out = args.to_parquet / (f"{args.symbol}_1m_{first:%Y-%m}_{last:%Y-%m}.parquet")
        df.to_parquet(out, compression="zstd", index=False)
        ratio = args.path.stat().st_size / max(out.stat().st_size, 1)
        print(f"  parquet        {out.name}  "
              f"({out.stat().st_size / 1e6:.0f} MB, {ratio:.1f}× smaller)")

    if args.write_manifest:
        write_manifest({
            "symbol": args.symbol,
            "file": args.path.name,
            "source": args.source,
            "contract": args.contract,
            "rows": int(len(df)),
            "first": f"{first:%Y-%m-%d}",
            "last": f"{last:%Y-%m-%d}",
            "cvd_valid_from": f"{cvd_from:%Y-%m-%d}",
            "cvd_window_share": round(share_kept, 4),
            "sha256": sha256(args.path),
        })

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
