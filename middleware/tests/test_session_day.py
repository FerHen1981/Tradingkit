"""The trading day rolls at 18:00 ET, not at midnight (D-03 step 1).

The firm counts trading days, profitable days and the consistency ratio per SESSION. A
session opens 18:00 ET and carries the next calendar date, so bucketing on the calendar day
puts every trade between 18:00 and 24:00 ET on the wrong day — quietly shifting the day
counters and the best-day ratio the payout gate runs on.

Tradovate labels each fill with that session itself (`_tradeDate`); we take the broker's
label where it exists and derive it only for sources that have none (the routed-log).
"""
import datetime as dt
import os
import tempfile
from zoneinfo import ZoneInfo

from app.fills_pairing import SESSION_ROLL_ET, pair_fills, parse_fills_csv, session_date

ET = ZoneInfo("America/New_York")

_HDR = ("_id,_orderId,_contractId,_timestamp,_tradeDate,_action,_qty,_price,_active,_accountId,"
        "Fill ID,Order ID,Timestamp,Date,Account,B/S,Quantity,Price,_priceFormat,_priceFormatType,"
        "_tickSize,Contract,Product,Product Description,commission\n")


def _row(fid, ts_utc, trade_date, action, qty, price):
    return (f"{fid},{fid},1,{ts_utc},{trade_date},{action},{qty},{price},true,1,"
            f"{fid},{fid},x,x,PAAPEX2700250000013,{'Buy' if action == 0 else 'Sell'},{qty},{price},"
            f"-1,0,0.1,MGCZ6,MGC,E-Micro Gold,0.67\n")


def _write(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write(_HDR + "".join(rows))
    return path


def test_session_rolls_at_18_et():
    """17:00-18:00 ET is the maintenance break, so the boundary sits inside a dead hour."""
    assert SESSION_ROLL_ET == 18
    day = lambda h: session_date(dt.datetime(2026, 8, 17, h, 30, tzinfo=ET))  # noqa: E731
    assert day(9) == dt.date(2026, 8, 17)      # mid-session
    assert day(16) == dt.date(2026, 8, 17)     # before the close
    assert day(17) == dt.date(2026, 8, 17)     # inside the break, still today's session
    assert day(18) == dt.date(2026, 8, 18)     # new session opens → tomorrow's date
    assert day(23) == dt.date(2026, 8, 18)     # evening trade belongs to the next session


def test_broker_trade_date_wins_over_the_calendar_day():
    # 22:37Z = 18:37 ET on 08-17 → Tradovate labels it session 08-18
    path = _write([
        _row("1", "2026-08-17T22:37:30.000Z", "2026-08-18", 1, 5, 4470.6),
        _row("2", "2026-08-17T23:06:54.000Z", "2026-08-18", 0, 5, 4470.1),
    ])
    fills = parse_fills_csv(path)
    os.unlink(path)
    assert fills[0].trade_date == dt.date(2026, 8, 18)
    assert fills[0].ts.astimezone(ET).date() == dt.date(2026, 8, 17)   # calendar day differs
    trade = pair_fills(fills)[0]
    assert trade.session_date == dt.date(2026, 8, 18)


def test_derived_when_the_broker_gives_no_label():
    """Routed-log style: no _tradeDate → fall back to the 18:00 ET roll, same bucket."""
    path = _write([
        _row("1", "2026-08-17T22:37:30.000Z", "", 1, 5, 4470.6),
        _row("2", "2026-08-17T23:06:54.000Z", "", 0, 5, 4470.1),
    ])
    fills = parse_fills_csv(path)
    os.unlink(path)
    assert fills[0].trade_date is None
    assert pair_fills(fills)[0].session_date == dt.date(2026, 8, 18)


def test_day_session_is_unaffected():
    """A trade opened and closed inside the day session keeps its calendar date."""
    path = _write([
        _row("1", "2026-08-18T14:00:00.000Z", "2026-08-18", 0, 2, 4450.0),   # 10:00 ET
        _row("2", "2026-08-18T15:00:00.000Z", "2026-08-18", 1, 2, 4452.0),   # 11:00 ET
    ])
    fills = parse_fills_csv(path)
    os.unlink(path)
    t = pair_fills(fills)[0]
    assert t.session_date == dt.date(2026, 8, 18) == t.exit_ts.astimezone(ET).date()
