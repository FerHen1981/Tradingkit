"""Regression tests for the fill-driven Trade Journal mapping (app/notion_journal.py).

Cases are taken verbatim from real exported Trade Journal rows, so the deterministic
mappings (idempotency key, tick math, slippage, notes) stay pinned to the real data.
Run directly (`python tests/test_notion_journal.py`) or via pytest.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.notion_journal import (  # noqa: E402
    TradeRecord, trade_key, result_ticks, slippage_entry_ticks, duration_min, build_notes,
)

_TZ = dt.timezone(dt.timedelta(hours=-4))  # GMT-4 (ET summer), as in the export


def _es_el_leon():
    return TradeRecord(
        account_id="APEX27002500000205", buy_fill_id="599992280060", sell_fill_id="599992280086",
        direction="BUY", contract="ESU6", symbol="ES1!", position_size=1,
        entry_price=7593.50, exit_price=7596.25, gross_pnl=137.50, commissions=3.10,
        open_dt=dt.datetime(2026, 8, 3, 6, 20, tzinfo=_TZ),
        close_dt=dt.datetime(2026, 8, 3, 6, 31, tzinfo=_TZ),
        framework="🦁 ΞL LΞON — ES", planned_sl=7568.50, planned_tp=7631.00,
    )


def _mgc_el_tesoro():
    return TradeRecord(
        account_id="PAAPEX2700250000018", buy_fill_id="601570370032", sell_fill_id="601570370062",
        direction="BUY", contract="MGCZ6", symbol="MGC1!", position_size=8,
        entry_price=4110.70, exit_price=4114.70, gross_pnl=320.0, commissions=10.72,
        open_dt=dt.datetime(2026, 8, 4, 2, 51, tzinfo=_TZ),
        close_dt=dt.datetime(2026, 8, 4, 3, 23, tzinfo=_TZ),
        framework="💎 ΞL TΞSORO — MGC Funded", planned_tp=4135.7,
    )


def test_trade_key_matches_export():
    assert trade_key(_es_el_leon()) == "205_599992280060_599992280086"
    assert trade_key(_mgc_el_tesoro()) == "018_601570370032_601570370062"


def test_result_ticks():
    assert result_ticks(_es_el_leon()) == 11.0        # (7596.25-7593.50)/0.25
    assert result_ticks(_mgc_el_tesoro()) == 40.0     # (4114.70-4110.70)/0.10
    loss = _mgc_el_tesoro()
    loss.exit_price = 4110.60                          # 1 tick below entry
    assert result_ticks(loss) == -1.0


def test_slippage_entry_ticks():
    t = _es_el_leon()
    t.signal_price = 7593.00                           # filled 2 ticks worse than signal
    assert slippage_entry_ticks(t) == 2.0
    assert slippage_entry_ticks(_es_el_leon()) is None  # no signal price -> None


def test_duration_and_notes():
    assert duration_min(_es_el_leon()) == 11.0
    assert build_notes(_es_el_leon()) == "acct=APEX27002500000205; plannedSL=7568.5; plannedTP=7631"
    assert build_notes(_mgc_el_tesoro()) == "acct=PAAPEX2700250000018; plannedTP=4135.7"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
