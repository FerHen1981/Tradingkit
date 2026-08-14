"""Command-center asset rollup — pairs local Fills into per-asset edge, deduped."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.dashboard_state import _load_asset_rollup  # noqa: E402

_HDR = "_id,_orderId,_timestamp,_action,_qty,_price,Account,Contract,Product,_tickSize,commission\n"


def _write(dirpath, name, rows):
    with open(os.path.join(dirpath, name), "w", encoding="utf-8") as f:
        f.write(_HDR)
        for r in rows:
            f.write(r + "\n")


# one GC trade: buy 1 MGC @4110.70, sell @4114.70 → gross 40.00, comm 1.34, net 38.66, 40 ticks
_GC = [
    "1,10,2026-08-04T06:51:00+00:00,0,1,4110.70,PAAPEX2700250000018,MGCZ6,MGC,0.10,0.67",
    "2,11,2026-08-04T07:23:00+00:00,1,1,4114.70,PAAPEX2700250000018,MGCZ6,MGC,0.10,0.67",
]
# one ES trade: buy 1 MES @7593.50, sell @7596.25 → gross 13.75, comm 0, net 13.75, 11 ticks
_ES = [
    "3,12,2026-08-03T10:20:00+00:00,0,1,7593.50,APEX27002500000205,MESU6,MES,0.25,0",
    "4,13,2026-08-03T10:31:00+00:00,1,1,7596.25,APEX27002500000205,MESU6,MES,0.25,0",
]


def test_asset_rollup_and_dedup():
    d = tempfile.mkdtemp()
    _write(d, "20260804_018_Fills.csv", _GC)
    _write(d, "20260804_018_Fills (1).csv", _GC)      # overlapping export → must count once
    _write(d, "20260803_205_Fills.csv", _ES)
    assets, totals = _load_asset_rollup(d, skip=[])
    by = {a["sym"]: a for a in assets}

    assert by["GC"]["n"] == 1                          # deduped, not 2
    assert by["GC"]["net"] == 38.66
    assert by["GC"]["ticks"] == 40
    assert by["GC"]["wins"] == 1 and by["GC"]["robust"] is True

    assert by["ES"]["n"] == 1
    assert by["ES"]["net"] == 13.75
    assert by["ES"]["ticks"] == 11
    assert by["ES"]["robust"] is True

    assert totals["n"] == 2
    assert totals["net"] == 52.41


def test_skip_filters_account():
    d = tempfile.mkdtemp()
    _write(d, "20260804_018_Fills.csv", _GC)
    _write(d, "20260803_205_Fills.csv", _ES)
    assets, totals = _load_asset_rollup(d, skip=["205"])   # drop the ES account
    syms = {a["sym"] for a in assets}
    assert syms == {"GC"} and totals["n"] == 1
