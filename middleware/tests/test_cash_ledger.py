"""Cash_History ledger parser tests."""
import os
import tempfile

from app.cash_ledger import parse_cash_history, _money


def test_money_formats():
    assert _money("50,000.00") == 50000.0
    assert _money("-3.10") == -3.10
    assert _money("$(210.00)") == -210.0
    assert _money("") == 0.0


def _write(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write("Account,Transaction ID,Timestamp,Date,Delta,Amount,Cash Change Type,Currency,Contract\n")
        for r in rows:
            f.write(r + "\n")
    return path


def test_aggregate_balance_and_types():
    path = _write([
        'PAAPEX2700250000013,1,07/15 18:27,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PAAPEX2700250000013,2,07/22 00:57,2026-07-22,-3.10,"49,996.90", Commission,USD,NQU6',
        'PAAPEX2700250000013,3,07/22 00:57,2026-07-22,-210.00,"49,786.90", Trade Paired,USD,NQU6',
        'PAAPEX2700250000013,4,08/01 00:00,2026-08-01,"1,000.00","50,786.90", Trade Paired,USD,MGCZ6',
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    led = L["PAAPEX2700250000013"]
    assert led.balance == 50786.90          # last running Amount
    assert led.funding == 50000.0
    assert led.commissions == 3.10          # positive cost
    assert led.trade_pnl == 790.0           # -210 + 1000
    assert led.payouts == 0.0


def test_payout_detected():
    path = _write([
        'PAAPEX2700250000013,1,x,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PAAPEX2700250000013,2,x,2026-08-20,"-2,000.00","48,000.00", Payout,USD,',
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    assert L["PAAPEX2700250000013"].payouts == -2000.0
