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


def test_load_cash_ledgers_latest_snapshot_wins(tmp_path):
    """Two overlapping Cash_History exports for one account → the more complete (more events)
    snapshot wins, so overlapping exports never double-count."""
    from app.dashboard_state import _load_cash_ledgers
    hdr = "Account,Transaction ID,Timestamp,Date,Delta,Amount,Cash Change Type,Currency,Contract\n"
    older = tmp_path / "20260810_PAAPEX2700250000013_Cash_History.csv"
    older.write_text(hdr +
                     'PAAPEX2700250000013,1,x,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,\n'
                     'PAAPEX2700250000013,2,x,2026-08-04,"1,000.00","51,000.00", Trade Paired,USD,MGCZ6\n')
    newer = tmp_path / "20260818_PAAPEX2700250000013_Cash_History.csv"
    newer.write_text(hdr +
                     'PAAPEX2700250000013,1,x,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,\n'
                     'PAAPEX2700250000013,2,x,2026-08-04,"1,000.00","51,000.00", Trade Paired,USD,MGCZ6\n'
                     'PAAPEX2700250000013,3,x,2026-08-18,-3.10,"50,996.90", Commission,USD,MGCZ6\n'
                     'PAAPEX2700250000013,4,x,2026-08-18,"4,871.48","55,868.38", Trade Paired,USD,MGCZ6\n')
    led = _load_cash_ledgers(str(tmp_path), skip=[])
    assert set(led) == {"PAAPEX2700250000013"}
    assert led["PAAPEX2700250000013"].balance == 55868.38     # newer (4 events) wins over older (2)
    assert led["PAAPEX2700250000013"].commissions == 3.10
    # skip filter drops the account entirely
    assert _load_cash_ledgers(str(tmp_path), skip=["013"]) == {}
    # no files → empty (overlay is a no-op)
    assert _load_cash_ledgers(str(tmp_path / "nope"), skip=[]) == {}


def test_daily_realized_and_payout_count():
    """Per-day net (Trade Paired + Commission, NOT funding/payouts) and payout count/sum."""
    path = _write([
        'PAAPEX2700250000013,1,x,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PAAPEX2700250000013,2,x,2026-08-17,"200.00","50,200.00", Trade Paired,USD,MGCZ6',
        'PAAPEX2700250000013,3,x,2026-08-17,-3.10,"50,196.90", Commission,USD,MGCZ6',
        'PAAPEX2700250000013,4,x,2026-08-18,"400.00","50,596.90", Trade Paired,USD,MGCZ6',
        'PAAPEX2700250000013,5,x,2026-08-20,"-2,000.00","48,596.90", Payout,USD,',
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    led = L["PAAPEX2700250000013"]
    assert led.daily["2026-08-17"] == 196.90    # 200 - 3.10 (funding excluded)
    assert led.daily["2026-08-18"] == 400.00
    assert "2026-07-16" not in led.daily        # funding is not a trading day
    assert led.n_payouts == 1 and led.payouts == -2000.0
