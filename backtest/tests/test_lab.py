"""Data-room catalog + run-registry tests (stdlib only — no pandas needed)."""
import importlib
import json
import os
import tempfile
from datetime import datetime, timezone

import pytest


def _reload_lab(lab_dir):
    """Point $LAB_DIR at a temp dir and reload the lab modules that read it."""
    os.environ["LAB_DIR"] = lab_dir
    import backtest.lab.paths as paths
    import backtest.lab.runs as runs
    import backtest.lab.datasets as datasets
    importlib.reload(paths); importlib.reload(runs); importlib.reload(datasets)
    return paths, runs, datasets


_CSV = (
    "DateTime,Open,High,Low,Close,Volume,Delta,CVD_close,BuyVolume,SellVolume\n"
    "18-06-2023 18:00:00 -04:00,100,101,99,100,10,5,5,7,2\n"
    "18-06-2023 18:01:00 -04:00,100,102,100,101,12,3,8,8,5\n"
    "18-06-2023 18:02:00 -04:00,101,103,100,102,9,-2,6,4,6\n"
)


# --- catalog --------------------------------------------------------------- #
def test_catalog_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        _, _, datasets = _reload_lab(tmp)
        p = os.path.join(tmp, "NQ_1m.csv")
        open(p, "w").write(_CSV)
        m = datasets.catalog(p, symbol="NQ", timeframe="1m")
        assert m["symbol"] == "NQ" and m["rows"] == 3
        assert m["has_orderflow"] is True and m["has_cvd"] is True
        assert m["first_dt"].startswith("18-06-2023 18:00")
        assert m["last_dt"].startswith("18-06-2023 18:02")
        assert len(m["sha256"]) == 64


def test_catalog_missing_column_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        _, _, datasets = _reload_lab(tmp)
        p = os.path.join(tmp, "bad.csv")
        open(p, "w").write("DateTime,Open,High,Low,Close\n1,2,3,4,5\n")  # no Volume/Delta
        with pytest.raises(ValueError, match="missing required columns"):
            datasets.catalog(p)


def test_write_catalog_drops_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        paths, _, datasets = _reload_lab(tmp)
        p = os.path.join(tmp, "NQ_1m.csv")
        open(p, "w").write(_CSV)
        mpath = datasets.write_catalog(p, symbol="NQ")
        assert os.path.exists(mpath)
        assert json.loads(open(mpath).read())["symbol"] == "NQ"


# --- run_id / registry ----------------------------------------------------- #
def test_run_id_is_recognizable():
    _, runs, _ = _reload_lab(tempfile.mkdtemp())
    when = datetime(2026, 8, 15, tzinfo=timezone.utc)
    rid = runs.make_run_id("NQ", "El_Toro_v7_PAonly", "15m", "eval", "a1b2c3", when)
    assert rid == "NQ_El-Toro-v7-PAonly_15m_eval_20260815_a1b2c3"


def test_fingerprint_deterministic_and_order_independent():
    _, runs, _ = _reload_lab(tempfile.mkdtemp())
    a = runs.fingerprint({"tf": "15m", "asset": "NQ", "groups": {"fvg": {"gap_min_ticks": 9}}})
    b = runs.fingerprint({"asset": "NQ", "groups": {"fvg": {"gap_min_ticks": 9}}, "tf": "15m"})
    c = runs.fingerprint({"tf": "5m", "asset": "NQ", "groups": {"fvg": {"gap_min_ticks": 9}}})
    assert a == b and a != c and len(a) == 6


def test_record_run_writes_and_indexes():
    with tempfile.TemporaryDirectory() as tmp:
        paths, runs, _ = _reload_lab(tmp)
        meta = {"run_id": "NQ_S_15m_classic_20260815_abc123", "asset": "NQ",
                "strategy": "S", "timeframe": "15m", "lens": "classic",
                "kpis": {"pf": 1.4}, "groups": {"fvg": {}}}
        d = runs.record_run(meta, {"kpis.json": json.dumps({"pf": 1.4})})
        assert os.path.exists(os.path.join(d, "run.json"))
        assert os.path.exists(os.path.join(d, "kpis.json"))
        idx = runs.load_index()
        assert len(idx) == 1 and idx[0]["run_id"] == meta["run_id"]
        assert "groups" not in idx[0]          # heavy fields kept out of the index


def test_record_run_upserts_same_id():
    with tempfile.TemporaryDirectory() as tmp:
        _, runs, _ = _reload_lab(tmp)
        meta = {"run_id": "R1", "kpis": {"pf": 1.0}}
        runs.record_run(meta)
        runs.record_run({"run_id": "R1", "kpis": {"pf": 2.0}})
        idx = runs.load_index()
        assert len(idx) == 1 and idx[0]["kpis"]["pf"] == 2.0
