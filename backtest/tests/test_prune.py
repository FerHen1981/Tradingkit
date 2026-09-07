"""Lab prune tool — removes runs and keeps index.json consistent with disk."""
import json
import os

from backtest.lab import prune, paths


def _seed(tmp, runs, ghost=True):
    os.environ["LAB_DIR"] = str(tmp)
    res = tmp / "results"
    res.mkdir(parents=True, exist_ok=True)
    for rid, m in runs.items():
        d = res / rid
        d.mkdir()
        m = {**m, "run_id": rid}
        (d / "run.json").write_text(json.dumps(m))
    idx = [{"run_id": rid} for rid in runs]
    if ghost:
        idx.append({"run_id": "GHOST_gone"})          # entry with no folder
    (tmp / "index.json").write_text(json.dumps(idx))


def test_reindex_drops_orphans(tmp_path):
    _seed(tmp_path, {"A_x": {"kind": "spec"}, "B_y": {"kind": "preset"}})
    n = prune._rebuild_index()
    assert n == 2
    ids = {e["run_id"] for e in json.loads(paths.index_path().read_text())}
    assert ids == {"A_x", "B_y"}                       # ghost pruned


def test_match_filter_selects_only_matching(tmp_path):
    _seed(tmp_path, {"NQ_v1_demo": {"kind": "spec"}, "NQ_v2_demo": {"kind": "spec"},
                     "ES_real": {"kind": "preset"}}, ghost=False)
    victims = [p for p in prune._run_dirs() if "NQ_v" in p.name]
    assert len(victims) == 2 and all("NQ_v" in p.name for p in victims)
    # the real run is untouched by the filter
    assert any(p.name == "ES_real" for p in prune._run_dirs())


def test_heavy_fields_excluded_from_index(tmp_path):
    _seed(tmp_path, {"R1": {"kind": "spec", "desc": {"big": 1},
                            "edge_by_regime": {"x": 1}, "kpis": {"pf": 1.2}}}, ghost=False)
    prune._rebuild_index()
    row = json.loads(paths.index_path().read_text())[0]
    assert "desc" not in row and "edge_by_regime" not in row   # heavy fields kept out
    assert row["kpis"] == {"pf": 1.2}                          # light fields kept
