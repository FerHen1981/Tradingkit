"""Export normalizer tests — Quantower/ATAS quirks -> canonical schema (stdlib)."""
import csv
import os
import tempfile

import pytest

from backtest.lab.normalize import to_canonical

# Mimics the real export: BOM, separate UTC col, decimal-comma quoted prices,
# duplicate "Cumulative delta..._Close" columns, a trailing empty column.
_EXPORT = (
    "﻿DateTime,UTC,Open,High,Low,Close,Ticks(from bar),Volume(from bar),"
    "Cumulative delta (By volume)_Close,Cumulative delta (By volume)_Close,"
    "Trades,Volume,Buy (Ask) volume,Sell (Bid) volume,Delta,\n"
    "4-12-2011 19:00:00,-04:00,2309,2317,2309,2317,103,195,,,0,0,0,0,0,\n"
    '5-12-2011 09:30:00,-05:00,"2316,25","2319,75","2316,25",2318,55,72,,,0,0,10,5,5,\n'
)


def _run():
    d = tempfile.mkdtemp()
    src, dst = os.path.join(d, "raw.csv"), os.path.join(d, "canon.csv")
    open(src, "w", encoding="utf-8").write(_EXPORT)
    to_canonical(src, dst)
    with open(dst, newline="") as f:
        return list(csv.reader(f))


def test_header_is_canonical():
    rows = _run()
    assert rows[0] == ["DateTime", "Open", "High", "Low", "Close", "Volume",
                       "Delta", "BuyVolume", "SellVolume", "CVD_close"]


def test_datetime_merged_with_offset():
    rows = _run()
    assert rows[1][0] == "4-12-2011 19:00:00 -04:00"
    assert rows[2][0] == "5-12-2011 09:30:00 -05:00"


def test_decimal_comma_converted():
    rows = _run()
    # row 2 had "2316,25" -> 2316.25 ; bar-volume 72 ; delta 5
    assert rows[2][1] == "2316.25" and rows[2][2] == "2319.75"
    assert rows[2][5] == "72" and rows[2][6] == "5"


def test_volume_uses_bar_volume():
    rows = _run()
    # canonical Volume comes from Volume(from bar) (195/72), not the order-flow Volume (0)
    assert rows[1][5] == "195"


def test_missing_required_rejected():
    d = tempfile.mkdtemp()
    src, dst = os.path.join(d, "bad.csv"), os.path.join(d, "out.csv")
    open(src, "w").write("DateTime,UTC,Open,High,Low,Close\n1,-04:00,1,2,3,4\n")  # no Volume/Delta
    with pytest.raises(ValueError, match="missing a source column"):
        to_canonical(src, dst)


def _write(path, header, *rows):
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    return path


def test_export_without_a_delta_column_still_ingests(tmp_path):
    """The canonical CVD is the OHLCV polarity proxy (ground rule 4), so a source
    that ships no order-flow column must not be rejected. Delta is written as 0."""
    from backtest.lab.normalize import to_canonical
    src = _write(tmp_path / "MES.csv",
                 ["DateTime", "UTC", "Open", "High", "Low", "Close", "Volume"],
                 ["24-08-2025 18:00:00", "-04:00", "6400,25", "6401,00", "6400,00", "6400,75", "812"])
    out, n = to_canonical(src, tmp_path / "canonical.csv")
    assert n == 1
    lines = open(out).read().strip().splitlines()
    assert lines[0].split(",") == ["DateTime", "Open", "High", "Low", "Close", "Volume", "Delta"]
    assert lines[1].endswith(",0"), lines[1]
    assert lines[1].startswith("24-08-2025 18:00:00 -04:00,6400.25")


def test_a_real_delta_column_is_still_carried_through(tmp_path):
    """The counter-example: making Delta optional may not silently zero a source
    that does ship it."""
    from backtest.lab.normalize import to_canonical
    src = _write(tmp_path / "MES.csv",
                 ["DateTime", "UTC", "Open", "High", "Low", "Close", "Volume", "Delta"],
                 ["24-08-2025 18:00:00", "-04:00", "6400,25", "6401,00", "6400,00", "6400,75",
                  "812", "-137"])
    out, _ = to_canonical(src, tmp_path / "canonical.csv")
    assert open(out).read().strip().splitlines()[1].endswith(",-137")


def test_a_missing_price_column_is_still_refused(tmp_path):
    """Delta became optional; OHLCV did not."""
    import pytest
    from backtest.lab.normalize import to_canonical
    src = _write(tmp_path / "MES.csv",
                 ["DateTime", "UTC", "Open", "High", "Low", "Volume"],
                 ["24-08-2025 18:00:00", "-04:00", "1", "2", "0", "5"])
    with pytest.raises(ValueError, match="Close"):
        to_canonical(src, tmp_path / "canonical.csv")
