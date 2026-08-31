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
    assert by["MGC"]["n"] == 1 and by["MGC"]["net"] == 38.66 and by["MGC"]["ticks"] == 40
    assert by["MGC"]["micro"] is True and by["MGC"]["robust"] is True   # MGC = micro, funded edge
    assert by["MES"]["net"] == 13.75 and by["MES"]["ticks"] == 11 and by["MES"]["micro"] is True
    assert ag["totals"]["n"] == 2 and ag["totals"]["net"] == 52.41
    assert by["MGC"]["comm"] == 1.34 and ag["totals"]["comm"] == 1.34   # 0.67 + 0.67
    assert ag["acct_net"]["PAAPEX2700250000018"] == 38.66
    assert ag["acct_net"]["APEX27002500000205"] == 13.75


def test_aggregate_fees_and_excursions():
    today = dt.datetime.now(ds._ET).date()
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 100.0, "ticks": 10, "close": today, "comm": 5.0, "mfe": 40, "mae": 3},
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 50.0, "ticks": 5, "close": today, "comm": 3.0, "mfe": 20, "mae": 7},
    ]
    gc = ds._aggregate(trades, "all")["assets"][0]
    assert gc["comm"] == 8.0 and gc["mfe"] == 30.0 and gc["mae"] == 5.0    # avg excursions


def test_skip_filters_account():
    d = tempfile.mkdtemp()
    _write(d, "20260804_018_Fills.csv", _GC)
    _write(d, "20260803_205_Fills.csv", _ES)
    trades = ds._load_trades(d, skip=["205"])          # drop the ES account
    ag = ds._aggregate(trades, "all")
    assert {a["sym"] for a in ag["assets"]} == {"MGC"} and ag["totals"]["n"] == 1


def test_window_start_boundaries():
    d = dt.date(2026, 8, 14)                            # a Friday, Q3
    assert ds._window_start("day", d) == d
    assert ds._window_start("week", d) == dt.date(2026, 8, 10)   # Monday
    assert ds._window_start("month", d) == dt.date(2026, 8, 1)
    assert ds._window_start("quarter", d) == dt.date(2026, 7, 1)  # Q3 starts Jul
    assert ds._window_start("rolling", d) == dt.date(2026, 7, 15)  # 30 days back
    assert ds._window_start("all", d) is None


def test_aggregate_window_filters_by_close():
    from app.fills_pairing import session_date
    session_today = session_date(dt.datetime.now(dt.timezone.utc))  # CME session date (18:00 ET roll)
    old = session_today - dt.timedelta(days=90)
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 100.0, "ticks": 10, "close": session_today},
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 50.0, "ticks": 5, "close": old},
    ]
    assert ds._aggregate(trades, "all")["totals"]["net"] == 150.0
    assert ds._aggregate(trades, "day")["totals"]["net"] == 100.0     # only current session's
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
        assert st["fleet"]["realized_net"] == 0.0        # ledger (no accounts without a token)
        assert st["fleet"]["window_net"] == 52.41        # trade-log total
        assert st["fleet"]["trades"] == 2
        assert {a["sym"] for a in st["assets"]} == {"MGC", "MES"}
        assert st["status"]["trades_total"] == 2 and st["status"]["notion_ok"] is False
        assert st["status"]["data_through"] == "2026-08-04"   # latest close in the fixtures
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_day_window_uses_current_session():
    """After 18:00 ET the session rolls — 'day' is the CURRENT session, not the last one with
    trades.  If no trades exist for the current session, the totals are zero."""
    from app.fills_pairing import session_date
    session_today = session_date(dt.datetime.now(dt.timezone.utc))
    yesterday = session_today - dt.timedelta(days=1)
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "MGC", "net": 80.0, "ticks": 0, "close": session_today},
        {"acct": "PAAPEX2700250000018", "sym": "MGC", "net": 10.0, "ticks": 0, "close": yesterday},
    ]
    # only the current session's trades
    assert ds._aggregate(trades, "day")["totals"]["net"] == 80.0
    # if only old trades exist, day = 0 (not the "last day with trades")
    old_only = [t for t in trades if t["close"] != session_today]
    assert ds._aggregate(old_only, "day")["totals"]["net"] == 0


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
    assert trades[0]["sym"] == "MGC" and trades[0]["net"] == 38.66


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


def test_routed_trades_after_date():
    import json
    d = tempfile.mkdtemp()
    fill = {"title": "FILL LONG MGC1!", "description": "PA018-0k-260814 | 8ct @ 4110.7 | SL 4100.0 | TP 4135.0"}
    exit_ = {"title": "EXIT MGC1!", "description": "PA018-0k-260814 | long closed @ 4114.7 | TRAIL | PnL +$320.0 | MFE 40t · MAE 3t"}
    lines = [
        # De order die deze fill autoriseert: zonder geaccepteerde PMT-order telt een kaart
        # niet als executie (poort 24-08).
        json.dumps({"kind": "pmt", "ts": "2026-08-14T14:49:00+00:00",
                    "account": "PAAPEX2700250000018", "result": "sent 200 (poging 1)",
                    "body": json.dumps({"symbol": "MGC1!", "data": "buy", "quantity": "8"})}),
        json.dumps({"kind": "discord", "ts": "2026-08-14T14:50:00+00:00", "body": json.dumps({"embeds": [fill]})}),
        json.dumps({"kind": "discord", "ts": "2026-08-14T15:20:00+00:00", "body": json.dumps({"embeds": [exit_]})}),
    ]
    with open(os.path.join(d, "routed_20260814.jsonl"), "w") as f:
        f.write("\n".join(lines) + "\n")
    r = ds._load_routed_trades(d, [], dt.date(2026, 8, 13))       # Aug-14 close is after Aug-13
    assert len(r) == 1 and r[0]["sym"] == "MGC" and r[0]["net"] == 320.0 and r[0]["ticks"] == 40
    assert r[0]["mfe"] == 40 and r[0]["mae"] == 3 and r[0]["comm"] == 0.0   # excursions from the log
    assert ds._load_routed_trades(d, [], dt.date(2026, 8, 14)) == []   # not after Aug-14


def test_heatmap_aggregation():
    today = dt.datetime.now(ds._ET).date()
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 100.0, "ticks": 10, "close": today, "hour": 9, "dow": 0},
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": -30.0, "ticks": -3, "close": today, "hour": 9, "dow": 0},
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 50.0, "ticks": 5, "close": today, "hour": 14, "dow": 2},
    ]
    hm = {(c["dow"], c["hour"]): c for c in ds._aggregate(trades, "all")["heatmap"]["all"]}
    assert hm[(0, 9)]["net"] == 70.0 and hm[(0, 9)]["n"] == 2      # 100 − 30, Monday 09h
    assert hm[(2, 14)]["net"] == 50.0 and hm[(2, 14)]["n"] == 1    # Wednesday 14h


def test_dimension_breakdowns():
    today = dt.datetime.now(ds._ET).date()
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "MGC", "strat": "El Tesoro — MGC", "net": 100.0, "ticks": 0, "close": today, "hour": 9, "dow": 0},
        {"acct": "APEX27002500000205", "sym": "MES", "strat": "El Rey — MES", "net": 40.0, "ticks": 0, "close": today, "hour": 9, "dow": 0},
    ]
    ag = ds._aggregate(trades, "all")
    assert set(ag["heatmap"].keys()) == {"all", "asset", "strat", "acct"}     # heatmap now filterable
    assert "MGC" in ag["heatmap"]["asset"] and "El Tesoro — MGC" in ag["heatmap"]["strat"]
    assert "El Rey — MES" in ag["calendar"]["strat_day"]                       # calendar splits strategy
    assert ag["strat_stats"]["El Tesoro — MGC"]["net"] == 100.0               # per-strategy stats


def test_pearson():
    assert ds._pearson([1, 2, 3], [2, 4, 6]) == 1.0        # perfectly positive
    assert ds._pearson([1, 2, 3], [3, 2, 1]) == -1.0       # perfectly negative
    assert ds._pearson([1, 1, 1], [1, 2, 3]) is None       # flat series → undefined
    assert ds._pearson([1], [1]) is None                   # n < 2


def test_correlation_matrix():
    d1, d2 = dt.date(2026, 8, 1), dt.date(2026, 8, 2)
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 100.0, "ticks": 0, "close": d1},
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": -50.0, "ticks": 0, "close": d2},
        {"acct": "APEX27002500000205", "sym": "ES", "net": 50.0, "ticks": 0, "close": d1},
        {"acct": "APEX27002500000205", "sym": "ES", "net": -25.0, "ticks": 0, "close": d2},
    ]
    corr = ds._aggregate(trades, "all")["correlation"]
    labels, m = corr["labels"], corr["matrix"]
    i, j = labels.index("GC"), labels.index("ES")
    assert m[i][j] == 1.0 and m[i][i] == 1.0 and corr["days"] == 2   # move together → +1


def test_calendar_aggregation():
    d1, d2 = dt.date(2026, 8, 3), dt.date(2026, 8, 4)
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": 100.0, "ticks": 0, "close": d1},
        {"acct": "PAAPEX2700250000018", "sym": "GC", "net": -40.0, "ticks": 0, "close": d2},
        {"acct": "APEX27002500000205", "sym": "ES", "net": 25.0, "ticks": 0, "close": d1},
    ]
    cal = ds._aggregate(trades, "all")["calendar"]
    byd = {x["d"]: x for x in cal["by_day"]}
    assert byd["2026-08-03"]["net"] == 125.0 and byd["2026-08-03"]["n"] == 2   # fleet total
    assert byd["2026-08-04"]["net"] == -40.0
    assert cal["asset_day"]["GC"]["2026-08-03"] == {"net": 100.0, "n": 1}      # by asset (net + count)
    assert cal["acct_day"]["018"]["2026-08-04"] == {"net": -40.0, "n": 1}      # by account
    assert cal["acct_day"]["205"]["2026-08-03"] == {"net": 25.0, "n": 1}


def test_stats_metrics():
    rows = [{"net": 100.0, "mae": 5}, {"net": 50.0, "mae": 3}, {"net": -40.0, "mae": 10}]
    s = ds._stats(rows)
    assert s["n"] == 3 and s["wins"] == 2 and s["win_pct"] == 66.7
    assert s["gross_win"] == 150.0 and s["gross_loss"] == 40.0 and s["pf"] == 3.75
    assert s["expectancy"] == 36.67 and s["avg_win"] == 75.0 and s["avg_loss"] == 40.0
    assert s["heat"] == 6.0                                # avg MAE (5+3+10)/3


def test_product_taxonomy_micro_vs_full():
    assert ds._prod("MGC")[0] == "MGC" and ds._prod("MGC")[2] is True and ds._prod("MGC")[4] is True
    assert ds._prod("GC")[0] == "GC" and ds._prod("GC")[2] is False and ds._prod("GC")[4] is False
    assert ds._prod("MES")[2] is True and ds._prod("ES")[2] is False


def test_equity_curve_and_projection():
    d1, d2, d3 = dt.date(2026, 8, 3), dt.date(2026, 8, 4), dt.date(2026, 8, 5)
    trades = [
        {"acct": "PAAPEX2700250000018", "sym": "MGC", "net": 100.0, "ticks": 0, "close": d1},
        {"acct": "PAAPEX2700250000018", "sym": "MGC", "net": -40.0, "ticks": 0, "close": d2},
        {"acct": "PAAPEX2700250000018", "sym": "MGC", "net": 60.0, "ticks": 0, "close": d3},
    ]
    eq = ds._aggregate(trades, "all")["equity"]
    assert [c["cum"] for c in eq["curve"]] == [100.0, 60.0, 120.0]   # running cumulative
    assert eq["curve"][1]["dd"] == -40.0 and eq["max_dd"] == -40.0    # drawdown from peak 100
    assert eq["exp_day"] == 40.0                                      # mean daily net
    assert len(eq["proj"]) == 15 and eq["proj"][0]["k"] == 1
    assert eq["proj"][0]["hi"] >= eq["proj"][0]["mid"] >= eq["proj"][0]["lo"]


def test_attention_feed_ranking():
    accts = [
        {"id": "211", "firm": "Apex", "health": "Breached", "bufpct": -30.0, "buffer": -761, "payout": {"stage": "Eval"}},
        {"id": "016", "firm": "Apex", "health": "Watch", "bufpct": 45.0, "buffer": 1900,
         "payout": {"stage": "Funded", "consistency_pct": 33, "eligible": False}},
        {"id": "013", "firm": "Apex", "health": "Healthy", "bufpct": 214.0, "buffer": 5370,
         "payout": {"stage": "Funded", "consistency_pct": 12, "eligible": True, "withdrawable": 2870}},
        {"id": "214", "firm": "Apex", "health": "Healthy", "bufpct": 100.0, "buffer": 2500,
         "payout": {"stage": "Eval", "target": 3000, "profit": 2600, "eligible": False}},
    ]
    items, counts = ds._attention(accts)
    assert items[0]["sev"] == "critical" and items[0]["account"] == "211"   # breach ranks first
    titles = {(i["account"], i["title"]) for i in items}
    assert ("016", "Watch buffer") in titles and ("016", "Consistency risk") in titles
    assert ("013", "Payout ready") in titles
    assert ("214", "Near eval target") in titles                            # 2600 ≥ 0.8·3000
    assert counts["critical"] == 1 and counts["warning"] >= 1
