"""Normalize a broker/platform CSV export into the canonical Lab schema.

Canonical output columns:
    DateTime (with tz offset attached), Open, High, Low, Close, Volume, Delta
    (+ optional BuyVolume, SellVolume, CVD_close)

Handles the gotchas seen in Quantower/ATAS exports:
  * a UTF-8 BOM on the header
  * decimal-COMMA numbers ("2316,25" -> 2316.25)
  * a SEPARATE tz-offset column (DateTime + UTC -> "DD-MM-YYYY HH:MM:SS -04:00",
    the offset-attached format backtest.data.load expects)
  * duplicate headers (first occurrence wins) and a trailing empty column

Streaming (stdlib csv) so a multi-million-row file normalizes with flat memory.
"""
from __future__ import annotations

import csv
from pathlib import Path

_DT = "DateTime"
_TZ = "UTC"

# canonical name -> acceptable source names (first present wins)
_REQUIRED = {
    "Open":   ["Open"],
    "High":   ["High"],
    "Low":    ["Low"],
    "Close":  ["Close"],
    "Volume": ["Volume(from bar)", "Volume"],   # bar volume preferred (always populated)
}
# Written when present, filled with 0 when not. Delta lives here rather than in
# _REQUIRED because the canonical CVD is the deterministic OHLCV polarity proxy
# (pipeline v7, ground rule 4) — native Delta is an explicit experiment, never a
# dependency. Half our existing datasets carry Delta ≡ 0 anyway (D-09), so
# refusing an export that simply lacks the column bought nothing and blocked
# every source that does not ship order-flow.
_FILLED = {
    "Delta":  ["Delta"],
}
_OPTIONAL = {
    "BuyVolume":  ["Buy (Ask) volume"],
    "SellVolume": ["Sell (Bid) volume"],
    "CVD_close":  ["Cumulative delta (By volume)_Close"],
}


def _first_index(idx: dict[str, int], names: list[str]):
    for n in names:
        if n in idx:
            return idx[n]
    return None


class _Counting:
    """Line iterator that tracks how many characters passed through — cheap,
    accurate-enough progress for a multi-GB ASCII CSV without touching tell()."""
    def __init__(self, f):
        self.f, self.chars = f, 0

    def __iter__(self):
        return self

    def __next__(self):
        line = next(self.f)
        self.chars += len(line)
        return line


def to_canonical(src: str | Path, dst: str | Path,
                 datetime_col: str = _DT, tz_col: str = _TZ,
                 progress=None) -> tuple[str, int]:
    """Rewrite `src` into the canonical schema at `dst`. Returns (dst, rows).
    `progress(chars_done, total_bytes)` is called every ~200k rows so a 1GB
    export shows movement instead of minutes of silence."""
    src, dst = Path(src), Path(dst)
    total = src.stat().st_size
    with open(src, newline="", encoding="utf-8-sig") as fin:
        counted = _Counting(fin)
        r = csv.reader(counted)
        header = next(r)
        idx: dict[str, int] = {}
        for i, name in enumerate(header):
            idx.setdefault(name.strip(), i)          # first occurrence wins

        if datetime_col not in idx:
            raise ValueError(f"export has no {datetime_col!r} column (have {header[:6]}...)")
        dt_i = idx[datetime_col]
        tz_i = idx.get(tz_col)

        req_i = {}
        for canon, srcs in _REQUIRED.items():
            j = _first_index(idx, srcs)
            if j is None:
                raise ValueError(f"export missing a source column for {canon!r} "
                                 f"(tried {srcs})")
            req_i[canon] = j
        fill_i = {canon: _first_index(idx, srcs) for canon, srcs in _FILLED.items()}
        opt_i = {canon: _first_index(idx, srcs) for canon, srcs in _OPTIONAL.items()}
        opt_i = {c: j for c, j in opt_i.items() if j is not None}

        out_cols = ["DateTime", *_REQUIRED.keys(), *_FILLED.keys(), *opt_i.keys()]
        dst.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with open(dst, "w", newline="", encoding="utf-8") as fout:
            w = csv.writer(fout)
            w.writerow(out_cols)
            for row in r:
                if not row or len(row) <= dt_i:
                    continue
                dt = row[dt_i].strip()
                if tz_i is not None and len(row) > tz_i:
                    dt = f"{dt} {row[tz_i].strip()}"
                out = [dt]
                for canon in _REQUIRED:
                    out.append(_num(row, req_i[canon]))
                for canon, j in fill_i.items():
                    out.append(_num(row, j) if j is not None else "0")
                for canon in opt_i:
                    out.append(_num(row, opt_i[canon]))
                w.writerow(out)
                n += 1
                if progress and n % 200_000 == 0:
                    progress(counted.chars, total)
    if progress:
        progress(total, total)
    return str(dst), n


def _num(row: list[str], i: int) -> str:
    """Cell value with decimal-comma -> decimal-point; blank stays blank."""
    if i is None or i >= len(row):
        return ""
    v = row[i].strip()
    return v.replace(",", ".") if v else ""


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Normalize a platform CSV export to the Lab schema.")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--datetime-col", default=_DT)
    ap.add_argument("--tz-col", default=_TZ)
    a = ap.parse_args()
    dst, n = to_canonical(a.src, a.dst, datetime_col=a.datetime_col, tz_col=a.tz_col)
    print(f"normalized {n:,} rows -> {dst}")


if __name__ == "__main__":
    _main()
