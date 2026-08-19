"""Parsing + pairing tests for the routed-log live journal, using the real card formats."""
import json
import datetime as dt

from app.routed_journal import (
    parse_routed_lines, pair_events, to_record, _short, _acct_token,
)
from app.notion_journal import trade_key, scalar_properties, slippage_entry_ticks
from app.fills_pairing import session_date


def _discord(ts, title, desc):
    body = json.dumps({"username": "MEX", "embeds": [{"title": title, "description": desc}]})
    return json.dumps({"ts": ts, "kind": "discord", "account": "", "result": "x", "body": body})


def _pmt(ts, account):
    body = json.dumps({"symbol": "MGC1!", "data": "buy",
                       "multiple_accounts": [{"account_id": account, "quantity_multiplier": 1}]})
    return json.dumps({"ts": ts, "kind": "pmt", "account": account, "result": "sent", "body": body})


def test_short_code():
    assert _short("PAAPEX2700250000015") == "PA015"
    assert _short("APEX27002500000209") == "AP209"


def test_acct_token():
    assert _acct_token("PA015-0k-260813 | 5ct @ 4403.1 | SL 4413.1 | TP 4378.1") == "PA015"


def test_parse_and_pair_full_trade():
    lines = [
        _pmt("2026-08-13T04:00:00Z", "PAAPEX2700250000015"),
        _discord("2026-08-13T04:00:01Z", "📉 MGC1! SHORT LIMIT",
                 "Entry 4403.5 | Stop 4413.5 | TP 4378.5 | Qty 5 | Contraction"),
        _discord("2026-08-13T04:00:05Z", "📥 MGC1! FILL SHORT",
                 "PA015-0k-260813 | 5ct @ 4403.1 | SL 4413.1 | TP 4378.1"),
        _discord("2026-08-13T05:10:00Z", "📤 MGC1! EXIT 🟢",
                 "PA015-0k-260813 | short closed @ 4397.7 | TRAIL | PnL +$263.3 | MFE 79t · MAE 3t"),
    ]
    events, amap = parse_routed_lines(lines)
    assert amap["PA015"] == "PAAPEX2700250000015"
    trades = pair_events(events, amap)
    assert len(trades) == 1
    t = trades[0]
    assert t.closed
    assert t.account == "PAAPEX2700250000015"
    assert t.direction == "SELL"
    assert t.entry_price == 4403.1 and t.exit_price == 4397.7
    assert t.qty == 5
    assert t.pnl == 263.3
    assert t.signal_price == 4403.5     # from the LIMIT card → enables slippage
    assert t.mfe == 79 and t.mae == 3 and t.reason == "TRAIL"


def test_negative_pnl_and_sl_reason():
    lines = [
        _pmt("2026-08-13T04:00:00Z", "APEX27002500000214"),
        _discord("2026-08-13T04:00:05Z", "📥 NQ1! FILL SHORT",
                 "AP214-0k-260813 | 5ct @ 30184.00 | SL 30201.50 | TP 30153.50"),
        _discord("2026-08-13T04:30:00Z", "📤 NQ1! EXIT 🔴",
                 "AP214-0k-260813 | short closed @ 30216.25 | SL | PnL -$1790.5 | MFE 36t · MAE 22t"),
    ]
    events, amap = parse_routed_lines(lines)
    t = pair_events(events, amap)[0]
    assert t.pnl == -1790.5
    assert t.reason == "SL"
    rec = to_record(t)
    assert rec.status == "Closed (SL)"
    assert rec.gross_pnl == -1790.5


def test_open_trade_is_written_before_close():
    lines = [
        _pmt("2026-08-13T04:00:00Z", "PAAPEX2700250000013"),
        _discord("2026-08-13T04:00:05Z", "📥 MGC1! FILL LONG",
                 "PA013-0k-260813 | 6ct @ 4403.1 | SL 4393.1 | TP 4428.1"),
    ]
    events, amap = parse_routed_lines(lines)
    trades = pair_events(events, amap)
    assert len(trades) == 1 and not trades[0].closed
    rec = to_record(trades[0])
    assert rec.status == "Open"
    # key is entry-based so it stays stable once the exit later arrives
    k1 = trade_key(rec)
    trades[0].exit_ts = dt.datetime(2026, 8, 13, 5, tzinfo=dt.timezone.utc)
    trades[0].exit_price = 4410.0
    trades[0].pnl = 120.0
    assert trade_key(to_record(trades[0])) == k1


def test_discord_without_pmt_is_not_a_real_trade():
    """PA019 bug: alerts with PMT disabled in Pine still fire Discord cards.
    Without a PMT record the viewer must NOT show them as real trades."""
    lines = [
        # PA015 has a PMT record → real trade
        _pmt("2026-08-19T04:00:00Z", "PAAPEX2700250000015"),
        _discord("2026-08-19T04:00:05Z", "📥 MGC1! FILL SHORT",
                 "PA015-0k-260819 | 5ct @ 4403.1 | SL 4413.1 | TP 4378.1"),
        # PA019 has NO PMT record → phantom, should be filtered out
        _discord("2026-08-19T04:00:05Z", "📥 MGC1! FILL LONG",
                 "PA019-0k-260819 | 3ct @ 4405.0 | SL 4395.0 | TP 4430.0"),
        _discord("2026-08-19T04:30:00Z", "📤 MGC1! EXIT 🟢",
                 "PA019-0k-260819 | long closed @ 4420.0 | TP | PnL +$150.0 | MFE 50t · MAE 5t"),
    ]
    events, amap = parse_routed_lines(lines)
    assert "PA015" in amap
    assert "PA019" not in amap   # no PMT record for this account
    trades = pair_events(events, amap)
    # Only PA015 should appear — PA019 is a phantom
    assert len(trades) == 1
    assert trades[0].account == "PAAPEX2700250000015"


def test_record_maps_to_notion_props():
    lines = [
        _pmt("2026-08-13T04:00:00Z", "PAAPEX2700250000018"),
        _discord("2026-08-13T04:00:01Z", "📉 MGC1! SHORT LIMIT", "Entry 4400.5 | Stop 4410 | TP 4375 | Qty 6"),
        _discord("2026-08-13T04:00:05Z", "📥 MGC1! FILL SHORT", "PA018-0k-260813 | 6ct @ 4400.2 | SL 4410.2 | TP 4375.2"),
        _discord("2026-08-13T05:00:00Z", "📤 MGC1! EXIT 🟢", "PA018-0k-260813 | short closed @ 4393.0 | TRAIL | PnL +$423.96 | MFE 97t · MAE 29t"),
    ]
    events, amap = parse_routed_lines(lines)
    rec = to_record(pair_events(events, amap)[0])
    props = scalar_properties(rec)
    assert props["Direction"]["select"]["name"] == "SELL"
    assert props["Gross PnL"]["number"] == 423.96
    assert props["Entry Price ($)"]["number"] == 4400.2
    # entry slippage: (short) intended 4400.5 vs fill 4400.2 → filled 0.3 worse-or-better in ticks
    assert slippage_entry_ticks(rec) is not None
    assert "MFE=97t" in props["Notes"]["rich_text"][0]["text"]["content"]


def test_session_date_rolls_at_18_et():
    """The CME session day rolls at 18:00 ET. A trade at 17:59 ET on Aug 19 belongs to
    session 2026-08-19; a trade at 18:01 ET on Aug 19 belongs to session 2026-08-20.
    The viewer LIVE tab uses this to decide what counts as 'Realized today'."""
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    # 17:59 ET on Aug 19 → session date 2026-08-19
    before_roll = dt.datetime(2026, 8, 19, 17, 59, tzinfo=ET)
    assert session_date(before_roll) == dt.date(2026, 8, 19)
    # 18:01 ET on Aug 19 → session date 2026-08-20 (new session started)
    after_roll = dt.datetime(2026, 8, 19, 18, 1, tzinfo=ET)
    assert session_date(after_roll) == dt.date(2026, 8, 20)
    # The viewer must not show the 17:59 trade as "today" after 18:01
    assert session_date(before_roll) != session_date(after_roll)
