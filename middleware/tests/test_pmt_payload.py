"""PMT payload — the middleware must place the SAME trailing / break-even bracket the
Pine f_pmtJSON did, or PMT never moves the Tradovate stop (stops stay put)."""
from app.brokers.pmt import build_payload
from app.models import Signal


def _acct():
    return {"token": "TK", "account_id": "PAAPEX2700250000021", "quantity_multiplier": 1}


def test_payload_carries_trailing_and_breakeven():
    # values mirror the live PMT export for MGC (trail 2.4 / trigger 4.8 / freq 0.2 / BE 2)
    sig = Signal(secret="x", strategy="GC", event="ENTRY", action="sell", symbol="MGC1!",
                 price=4452.95, order_type="LMT", dollar_sl=10, dollar_tp=25, qty=5,
                 trail=1, trail_stop=2.4, trail_trigger=4.8, trail_freq=0.2, breakeven=2)
    p = build_payload(sig, _acct())
    assert p["trail"] == 1
    assert p["trail_stop"] == 2.4 and p["trail_trigger"] == 4.8 and p["trail_freq"] == 0.2
    assert p["breakeven"] == 2
    # PMT trails the stop server-side from these; the middleware never sends a stop-update
    assert p["update_sl"] is False and p["update_tp"] is False


def test_backward_compatible_without_trail_fields():
    # an old-shape signal (no trail fields) still validates and defaults to a fixed stop
    sig = Signal(secret="x", strategy="GC", action="sell", symbol="MGC1!",
                 dollar_sl=10, dollar_tp=25, qty=5)
    p = build_payload(sig, _acct())
    assert p["trail"] == 0 and p["breakeven"] == 0
    assert p["trail_stop"] == 0 and p["trail_trigger"] == 0 and p["trail_freq"] == 0
