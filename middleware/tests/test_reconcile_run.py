"""D-03: the reconciliation runs on the sources that actually exist.

The engine never wrote a row because `intended` came from the sqlite journal (filled only by
the dead main.py) and `actual` from the Tradovate read-API (not available for these accounts),
with no timer to trigger it. This runner points the same pure functions at the routed-log and
the Fills export instead.
"""
import json
import os
import tempfile

from app.reconcile_run import fills_from_exports, intents_from_routed


def _routed(tmp, lines):
    p = os.path.join(tmp, "routed_20260818.jsonl")
    with open(p, "w") as f:
        for o in lines:
            f.write(json.dumps(o) + "\n")
    return p


def _pmt(action, symbol="MGC1!", qty=5, price=4450.0, acct="PAAPEX2700250000013"):
    return json.dumps({
        "symbol": symbol, "data": action, "quantity": str(qty), "price": str(price),
        "dollar_sl": 10, "dollar_tp": 25,
        "multiple_accounts": [{"account_id": acct, "quantity_multiplier": 1}],
    })


def test_intents_come_from_the_routed_log():
    with tempfile.TemporaryDirectory() as tmp:
        _routed(tmp, [
            {"kind": "pmt", "account": "PAAPEX2700250000013", "ts": 1000.0,
             "body": _pmt("sell"), "result": "sent 200"},
            {"kind": "pmt", "account": "PAAPEX2700250000013", "ts": 1100.0,
             "body": _pmt("buy", price=4460.0), "result": "sent 200"},
        ])
        got = intents_from_routed(tmp, since_ts=0)
    assert [g["side"] for g in got] == ["sell", "buy"]
    assert got[0]["symbol"] == "MGC1!" and got[0]["qty"] == 5.0 and got[0]["price"] == 4450.0
    assert got[0]["account"] == "PAAPEX2700250000013"
    assert got[0]["dollar_sl"] == 10 and got[0]["forward_result"] == "sent 200"


def test_close_is_not_an_intent_and_discord_lines_are_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        _routed(tmp, [
            {"kind": "pmt", "account": "A", "ts": 1000.0, "body": _pmt("close"), "result": "sent 200"},
            {"kind": "discord", "ts": 1001.0, "body": '{"embeds":[{"title":"x"}]}', "result": "sent 204"},
            {"kind": "journal", "ts": 1002.0, "body": "csv,row", "result": "stored"},
            {"kind": "pmt", "account": "A", "ts": 1003.0, "body": "not json", "result": "sent 200"},
        ])
        assert intents_from_routed(tmp, since_ts=0) == []


def test_since_filters_older_intents():
    with tempfile.TemporaryDirectory() as tmp:
        _routed(tmp, [
            {"kind": "pmt", "account": "A", "ts": 500.0, "body": _pmt("sell"), "result": "sent 200"},
            {"kind": "pmt", "account": "A", "ts": 2000.0, "body": _pmt("buy"), "result": "sent 200"},
        ])
        got = intents_from_routed(tmp, since_ts=1000.0)
    assert len(got) == 1 and got[0]["side"] == "buy"


def test_iso_timestamps_are_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        _routed(tmp, [{"kind": "pmt", "account": "A", "ts": "2026-08-18T22:05:01Z",
                       "body": _pmt("buy"), "result": "sent 200"}])
        got = intents_from_routed(tmp, since_ts=0)
    assert len(got) == 1 and got[0]["ts"] > 0


def test_fills_are_deduped_across_overlapping_exports():
    hdr = ("_id,_orderId,_contractId,_timestamp,_tradeDate,_action,_qty,_price,_active,_accountId,"
           "Fill ID,Order ID,Timestamp,Date,Account,B/S,Quantity,Price,_priceFormat,"
           "_priceFormatType,_tickSize,Contract,Product,Product Description,commission\n")
    row = ("9,9,1,2026-08-18T14:00:00.000Z,2026-08-18,0,2,4450.0,true,1,9,9,x,x,"
           "PAAPEX2700250000013,Buy,2,4450.0,-1,0,0.1,MGCZ6,MGC,E-Micro Gold,0.67\n")
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("a_Fills.csv", "b_Fills.csv"):          # same fill in two snapshots
            with open(os.path.join(tmp, name), "w") as f:
                f.write(hdr + row)
        got = fills_from_exports(tmp, since_ts=0)
        assert len(got) == 1 and got[0].venue == "tradovate" and got[0].side == "buy"
        assert got[0].symbol == "MGC" and got[0].qty == 2.0
        # skip-list drops the account entirely
        assert fills_from_exports(tmp, since_ts=0, skip=["013"]) == []
