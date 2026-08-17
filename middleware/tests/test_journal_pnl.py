"""Day P&L tally derived from the Tradovate perf snapshots (feeds the exit notification)."""
from app.journal import Journal


def _j(tmp_path) -> Journal:
    return Journal(str(tmp_path / "j.db"))


def _snap(ts, account, realized, open_pnl=0.0):
    return {"ts": ts, "account": account, "account_id": 1, "realized": realized,
            "open_pnl": open_pnl, "total_val": 0.0, "raw": {}}


def test_day_pnl_is_the_move_since_the_day_boundary(tmp_path):
    j = _j(tmp_path)
    j.write_perf([_snap(100, "APEX-1", 500.0), _snap(100, "APEX-2", -200.0)])   # opening marks
    j.write_perf([_snap(200, "APEX-1", 750.0, 30.0), _snap(200, "APEX-2", -150.0, -10.0)])
    out = j.day_pnl(since_ts=50)
    assert out["realized"] == 300.0        # +250 and +50 on cumulative marks, not the raw totals
    assert out["open_pnl"] == 20.0
    assert out["accounts"] == 2


def test_day_pnl_ignores_snapshots_from_before_the_boundary(tmp_path):
    j = _j(tmp_path)
    j.write_perf([_snap(10, "APEX-1", 9_000.0)])        # yesterday's cumulative total
    j.write_perf([_snap(100, "APEX-1", 9_000.0), _snap(200, "APEX-1", 9_120.0)])
    assert j.day_pnl(since_ts=50)["realized"] == 120.0


def test_day_pnl_is_empty_without_a_poller(tmp_path):
    assert _j(tmp_path).day_pnl(since_ts=0) == {
        "realized": None, "open_pnl": None, "accounts": 0, "since_ts": 0}
