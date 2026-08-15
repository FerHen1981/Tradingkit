"""Command-center state — asset rollup (deduped), timeframe windows, assembly."""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import dashboard_state as ds  # noqa: E402

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


def test_trades_dedup_and_pnl():
    d = tempfile.mkdtemp()
    _write(d, "20260804_018_Fills.csv", _GC)
    _write(d, "20260804_018_Fills (1).csv", _GC)      # overlapping export → count once
    _write(d, "20260803_205_Fills.csv", _ES)
    trades = ds._load_trades(d, skip=[])
    assert len(trades) == 2                            # deduped, not 3
    ag = ds._aggregate(trades, "all")
    by = {a["sym"]: a for a in ag["assets"]}
    assert by["GC"]["n"] == 1 and by["GC"]["net"] == 38.66 and by["GC"]["ticks"] == 40
    assert by["GC"]["robust"] is True
    assert by["ES"]["net"] == 13.75 and by["ES"]["ticks"] == 11
    assert ag["totals"]["n"] == 2 and ag["totals"]["net"] == 52.41
    assert ag["acct_net"]["PAAPEX2700250000018"] == 38.66
    assert ag["acct_net"]["APEX27002500000205"] == 13.75


def test_skip_filters_account():
    d = tempfile.mkdtemp()
    _write(d, "20260804_018_Fills.csv", _GC)
    _write(d, "20260803_205_Fills.csv", _ES)
    trades = ds._load_trades(d, skip=["205"])          # drop the ES account
    ag = ds._aggregate(trades, "all")
    assert {a["sym"] for a in ag["assets"]} == {"GC"} and ag["totals"]["n"] == 1


def test_window_start_boundaries():
    d = dt.date(2026, 8, 14)                            # a Friday, Q3
    assert ds._window_start("day", d) == d
    assert ds._window_start("week", d) == dt.date(2026, 8, 10)   # Monday
    assert ds._window_start("month", d) == dt.date(2026, 8, 1)
    assert ds._window_start("quarter", d) == dt.date(2026, 7, 1)  # Q3 starts Jul
    assert ds._window_start("rolling", d) == dt.date(2026, 7, 15)  # 30 days back
    assert ds._window_start("all", d) is None


def test_aggregate_window_filters_by_close():
    today = dt.datetime.now(ds._ET).date()
    old = today - dt.timedelta(days=90)
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 100.0, "ticks": 10, "close": today},
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 50.0, "ticks": 5, "close": old},
    ]
    assert ds._aggregate(trades, "all")["totals"]["net"] == 150.0
    assert ds._aggregate(trades, "day")["totals"]["net"] == 100.0     # only today's
    assert ds._aggregate(trades, "rolling")["totals"]["net"] == 100.0  # 90d ago excluded


def test_command_state_assembles_without_token():
    d = tempfile.mkdtemp()
    _write(d, "20260804_018_Fills.csv", _GC)
    _write(d, "20260803_205_Fills.csv", _ES)
    old = dict(os.environ)
    try:
        os.environ["EXPORTS_DIR"] = d
        os.environ["DASH_TTL_S"] = "0"                  # bypass cache
        os.environ["DASH_SKIP"] = ""
        os.environ.pop("NOTION_TOKEN", None)
        st = ds.command_state("all")
        assert st["window"] == "all" and st["accounts"] == []
        assert st["fleet"]["trades"] == 2 and st["fleet"]["realized_net"] == 52.41
        assert {a["sym"] for a in st["assets"]} == {"GC", "ES"}
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_seed_property_mapping():
    from app.seed_accounts import to_property, SEEDS
    assert to_property("DD Floor $", 50100.0) == {"number": 50100.0}
    assert to_property("Prop Firm", "Apex Trader Funding") == {"select": {"name": "Apex Trader Funding"}}
    assert to_property("Status", "Funded Account") == {"select": {"name": "Funded Account"}}
    # 209 is deliberately excluded from seeding (incomplete export)
    assert not any("209" in a for a in SEEDS)
    assert SEEDS["PAAPEX2700250000015"]["DD Floor $"] == 49897.60


def test_global_pairing_across_files():
    """A position opened in one export snapshot and closed in another must pair as ONE trade.
    Per-file pairing would see an orphan open in A and an orphan close in B → 0 trades."""
    d = tempfile.mkdtemp()
    _write(d, "20260804a_Fills.csv", [_GC[0]])   # only the BUY (open)
    _write(d, "20260804b_Fills.csv", [_GC[1]])   # only the SELL (close), later snapshot
    trades = ds._load_trades(d, skip=[])
    assert len(trades) == 1                        # globally paired, not lost
    assert trades[0]["sym"] == "GC" and trades[0]["net"] == 38.66


def test_aggregate_stage_filter():
    today = dt.datetime.now(ds._ET).date()
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 100.0, "ticks": 10, "close": today},
        {"acct": "APEX27002500000205", "sym": "ES", "net": 40.0, "ticks": 4, "close": today},
    ]
    assert ds._aggregate(trades, "all", "all")["totals"]["net"] == 140.0
    assert ds._aggregate(trades, "all", "funded")["totals"]["net"] == 100.0   # PA only
    assert ds._aggregate(trades, "all", "eval")["totals"]["net"] == 40.0      # APEX only


def test_seed_additions_and_archive():
    from app.seed_accounts import SEEDS, ARCHIVE
    assert "APEX27002500000212" in SEEDS and SEEDS["APEX27002500000212"]["Account Size"] == 250000
    for acct in ("APEX27002500000215", "APEX27002500000216", "APEX27002500000217",
                 "APEX27002500000218", "APEX27002500000219", "APEX27002500000220",
                 "APEX27002500000221", "APEX27002500000222"):
        assert acct in SEEDS
    assert SEEDS["APEX27002500000218"]["DD Amount $"] == 2000      # intraday-trail $2k
    assert SEEDS["APEX27002500000213"]["DD Floor $"] == 50192.25   # breached floor
    assert "APEX27002500000207" in ARCHIVE
