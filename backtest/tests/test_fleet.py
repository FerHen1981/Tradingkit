"""Fleet register — the promoted/validated strategy list."""
import os

from backtest.lab import fleet


def test_seed_has_the_eight_fleet_strategies(tmp_path):
    os.environ["LAB_DIR"] = str(tmp_path)
    f = fleet.load_fleet()
    names = {r["name"] for r in f}
    assert names == {"EL_TORO", "EL_MATADOR", "EL_DORADO", "EL_PATRON",
                     "EL_LEON", "EL_REY", "EL_MINERO", "EL_TESORO"}
    by = {r["name"]: r for r in f}
    assert by["EL_REY"]["asset"] == "ES" and by["EL_REY"]["status"] == "funded"
    assert by["EL_MINERO"]["asset"] == "GC" and by["EL_MINERO"]["status"] == "eval"


def test_promote_upserts_and_stamps(tmp_path):
    os.environ["LAB_DIR"] = str(tmp_path)
    fleet.load_fleet()
    f = fleet.promote({"id": "spec:custom_a.yaml", "name": "custom_a",
                       "asset": "NQ", "status": "eval", "kpis": {"profit_factor": 1.3}})
    row = [r for r in f if r["id"] == "spec:custom_a.yaml"][0]
    assert row["promoted_at"] and row["seed"] is False
    # re-promoting the same id updates in place, not duplicates
    f2 = fleet.promote({"id": "spec:custom_a.yaml", "name": "custom_a", "status": "funded"})
    assert len([r for r in f2 if r["id"] == "spec:custom_a.yaml"]) == 1
    assert [r for r in f2 if r["id"] == "spec:custom_a.yaml"][0]["status"] == "funded"


def test_demote_removes(tmp_path):
    os.environ["LAB_DIR"] = str(tmp_path)
    fleet.load_fleet()
    f = fleet.demote("preset:EL_TORO")
    assert not any(r["id"] == "preset:EL_TORO" for r in f)
