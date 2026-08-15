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
