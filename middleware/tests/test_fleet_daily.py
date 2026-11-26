"""D-163 — Fleet-daily aggregator. Alleen pure functies hier; de Notion-writer
loopt tegen een externe API en wordt handmatig DRY-getest op de VPS."""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.cash_ledger import parse_cash_history
from app.fleet_daily import build_mutation_rows, build_rows, load_ledgers


HDR = "Account,Transaction ID,Timestamp,Date,Delta,Amount,Cash Change Type,Currency,Contract\n"


def _write(rows: list[str]) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write(HDR)
        for r in rows:
            f.write(r + "\n")
    return path


def test_daily_breakdown_splits_gross_from_commission():
    # Twee trading-dagen, elke dag één Trade Paired + één Commission. De dagrij
    # moet bruto, commissie, netto, aantal trades correct dragen.
    path = _write([
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PA13,2,08/04 00:57,2026-08-04,"1,000.00","51,000.00", Trade Paired,USD,MGCZ6',
        'PA13,3,08/04 00:57,2026-08-04,-3.10,"50,996.90", Commission,USD,MGCZ6',
        'PA13,4,08/05 14:30,2026-08-05,-250.00,"50,746.90", Trade Paired,USD,MGCZ6',
        'PA13,5,08/05 14:30,2026-08-05,-3.10,"50,743.80", Commission,USD,MGCZ6',
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    rows = L["PA13"].daily_rows()
    assert len(rows) == 2
    r1 = next(r for r in rows if r["date"] == "2026-08-04")
    assert r1["gross_pnl"] == 1000.0 and r1["commissions"] == 3.10
    assert r1["net_pnl"] == 996.90 and r1["trade_count"] == 1
    r2 = next(r for r in rows if r["date"] == "2026-08-05")
    assert r2["gross_pnl"] == -250.0 and r2["commissions"] == 3.10
    assert r2["net_pnl"] == -253.10 and r2["trade_count"] == 1


def test_mutations_carry_payout_and_funding():
    path = _write([
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PA13,2,08/20,2026-08-20,"-2,000.00","48,000.00", Payout,USD,',
        'PA13,3,09/01,2026-09-01,"50,000.00","98,000.00", Fund Transaction,USD,',   # reset of top-up
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    led = L["PA13"]
    # Mutations lijst draagt alle drie: initial fund + payout + reset.
    types = [m["type"] for m in led.mutations]
    assert types.count("Fund Transaction") == 2
    assert types.count("Payout") == 1
    # Payout bedrag is negatief (geld eruit), en de totalen matchen.
    pay = next(m for m in led.mutations if m["type"] == "Payout")
    assert pay["delta"] == -2000.0 and pay["date"] == "2026-08-20"
    # Funding-mutaties tellen niet mee in daily_realized (trading-only).
    assert led.daily_realized == {}
    assert led.daily_rows() == []


def test_data_fee_lands_in_mutations_but_also_in_netto():
    # Een data fee is een trading-dag-kostenpost (telt in netto mee), maar hoort niet
    # in bruto en niet in commissies. Hij verschijnt ook als mutation zodat de
    # Dagstand hem als aparte post kan boeken.
    path = _write([
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PA13,2,08/04,2026-08-04,"500.00","50,500.00", Trade Paired,USD,MGCZ6',
        'PA13,3,08/04,2026-08-04,-3.10,"50,496.90", Commission,USD,MGCZ6',
        'PA13,4,08/04,2026-08-04,-105.00,"50,391.90", Data Fee,USD,',
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    led = L["PA13"]
    rows = led.daily_rows()
    assert len(rows) == 1
    r = rows[0]
    assert r["gross_pnl"] == 500.0            # alleen Trade Paired
    assert r["commissions"] == 3.10           # alleen Commission
    assert r["net_pnl"] == 391.90             # 500 − 3.10 − 105 (data fee)
    # Data fee ook als mutation (naast de initial fund).
    assert any(m["type"] == "Data Fee" for m in led.mutations)


def test_build_rows_drops_future_dates():
    # Export met een datafout die een rij in de toekomst zet: die stilzwijgend
    # overslaan, nooit verzonnen P&L publiceren.
    path = _write([
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PA13,2,08/04,2026-08-04,"1,000.00","51,000.00", Trade Paired,USD,MGCZ6',
        'PA13,3,09/99,2099-09-09,"9,999.00","60,999.00", Trade Paired,USD,MGCZ6',
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    rows = build_rows(L, today=dt.date(2026, 8, 10))
    dates = {r["date"] for r in rows}
    assert dates == {"2026-08-04"}


def test_load_ledgers_latest_snapshot_wins_across_overlapping_exports(tmp_path):
    # Twee exports voor hetzelfde account: de méést complete (meeste events) wint.
    older = tmp_path / "20260810_PA13_Cash_History.csv"
    older.write_text(HDR +
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,\n'
        'PA13,2,08/04,2026-08-04,"1,000.00","51,000.00", Trade Paired,USD,MGCZ6\n')
    newer = tmp_path / "20260818_PA13_Cash_History.csv"
    newer.write_text(HDR +
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,\n'
        'PA13,2,08/04,2026-08-04,"1,000.00","51,000.00", Trade Paired,USD,MGCZ6\n'
        'PA13,3,08/18,2026-08-18,-3.10,"50,996.90", Commission,USD,MGCZ6\n'
        'PA13,4,08/18,2026-08-18,"4,871.48","55,868.38", Trade Paired,USD,MGCZ6\n')
    L = load_ledgers(str(tmp_path))
    assert set(L) == {"PA13"}
    assert L["PA13"].balance == 55868.38
    rows = L["PA13"].daily_rows()
    dates = {r["date"] for r in rows}
    assert dates == {"2026-08-04", "2026-08-18"}


def test_skip_account_filter_works():
    path = _write([
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'DEMO,2,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
    ])
    # Dir met één bestand; `load_ledgers` leest alle *Cash_History*.csv.
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "x_Cash_History.csv")
        shutil.move(path, dest)
        L = load_ledgers(td, skip=["DEMO"])
    assert set(L) == {"PA13"}


def test_mutation_rows_are_sorted_and_future_dropped():
    path = _write([
        'PA13,1,07/15,2026-07-16,"50,000.00","50,000.00", Fund Transaction,USD,',
        'PA13,2,09/01,2099-01-01,"-500.00","49,500.00", Payout,USD,',   # future
        'PA13,3,08/20,2026-08-20,"-2,000.00","47,500.00", Payout,USD,',
    ])
    L = parse_cash_history(path)
    os.unlink(path)
    muts = build_mutation_rows(L, today=dt.date(2026, 8, 25))
    dates = [m["date"] for m in muts]
    # Alleen 07-16 en 08-20 overleven; op datum gesorteerd.
    assert dates == ["2026-07-16", "2026-08-20"]
    assert all(m["kind"] == "mutation" for m in muts)
