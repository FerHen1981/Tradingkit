"""Pipeline v7 — spine, fleet transcription, stage 0 and stage 1."""
import numpy as np
import pandas as pd
import pytest

from backtest.pipeline import fleet
from backtest.pipeline.audit import audit
from backtest.pipeline.parity import compare
from backtest.pipeline.stages import BY_KEY, GROUND_RULES, STAGES


def test_twelve_stages_with_two_hard_gates():
    assert [s.n for s in STAGES] == list(range(12))
    assert [s.key for s in STAGES if s.hard] == ["parity", "tv_validation"]
    assert len(GROUND_RULES) == 12
    assert BY_KEY["parity"].n == 1


def test_fleet_matches_released_pine_inputs():
    """Spot-check the transcription against MEX_FLEET_PACKAGE_2026-08-23."""
    assert len(fleet.names()) == 9
    c = fleet.engine_config("EL_TESORO_MGC_CON_EOD")
    assert (c.contract.symbol, c.contract_size) == ("MGC", 7.0)
    assert (c.gap_min_ticks, c.gap_max_ticks, c.cvd_trend_count) == (11.0, 16.0, 6)
    assert (c.fixed_stop_ticks, c.r_multiple, c.expiry_bars) == (140.0, 2.25, 12)
    m = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    assert (m.gap_min_ticks, m.gap_max_ticks, m.cvd_trend_count) == (10.0, 22.0, 6)
    assert (m.fixed_stop_ticks, m.r_multiple) == (120.0, 1.75)


def test_fleet_is_uniform_where_the_scripts_are():
    """Every released script has CVD+FVG on, BE/trail off, R-multiple, fixed stop."""
    for n in fleet.names():
        c = fleet.engine_config(n)
        assert c.use_cvd_filter and c.use_cvd_streak and c.use_gap_filter
        assert not c.use_breakeven and not c.use_trail
        assert c.tp_mode == "R-multiple" and c.stop_swing is False
        assert c.cvd_source == "proxy"          # ground rule 4
        assert c.day_trail_model.startswith("Activation")


def _frame(n=600, bad=False):
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 0.05, n))
    high = close + 0.1
    low = close - 0.1
    open_ = close.copy() if not bad else close + 5.0      # bad: open outside [low, high]
    idx = pd.date_range("2026-01-05", periods=n, freq="min", tz="America/New_York")
    df = pd.DataFrame({"et": idx, "Open": open_, "High": high, "Low": low, "Close": close,
                       "Volume": 1.0, "Delta": rng.integers(-5, 5, n).astype(float)})
    from backtest.data import _derive
    return _derive(df)


def test_stage0_reports_shape_and_passes_clean_data():
    r = audit(_frame(), "GC")
    assert r["bars"] == 600 and r["ohlc_violations"] == 0
    assert "New_York" in r["timezone"]
    assert not [f for f in r["findings"] if f["severity"] == "high"]


def test_stage0_flags_broken_ohlc():
    r = audit(_frame(bad=True), "GC")
    assert r["ohlc_violations"] > 0
    assert any(f["severity"] == "high" for f in r["findings"])


def test_stage0_flags_a_dead_delta_column():
    """A Delta column of zeros would silently gate every trade (this is D-09)."""
    df = _frame()
    df["Delta"] = 0.0
    r = audit(df, "GC")
    assert any("Delta column is effectively empty" in f["message"] for f in r["findings"])


class _Exp:
    """Minimal stand-in for a parsed TradingView export."""
    def __init__(self, trades):
        self._t = trades

    def stats(self):
        nets = [t["net"] for t in self._t]
        wins = [x for x in nets if x > 0]
        gl = -sum(x for x in nets if x <= 0)
        return {"trades": len(nets), "net": sum(nets),
                "win_rate_pct": round(100 * len(wins) / len(nets), 1),
                "profit_factor": round(sum(wins) / gl, 2) if gl else float("inf"),
                "longs": sum(1 for t in self._t if t["dir"] > 0),
                "shorts": sum(1 for t in self._t if t["dir"] < 0)}


def _export(n=100, pf_net=(200, -100)):
    t = []
    for i in range(n):
        win = i % 2 == 0
        t.append({"net": pf_net[0] if win else pf_net[1], "dir": 1 if i % 3 else -1})
    return _Exp(t)


def test_stage1_passes_when_the_simulator_matches():
    exp = _export()
    s = exp.stats()
    sim = {"trades": s["trades"], "profit_factor": s["profit_factor"],
           "win_rate_pct": s["win_rate_pct"], "longs": s["longs"], "shorts": s["shorts"]}
    assert compare(sim, exp)["pass"]


def test_stage1_fails_on_a_materially_different_trade_count():
    exp = _export(100)
    s = exp.stats()
    sim = {"trades": 40, "profit_factor": s["profit_factor"],
           "win_rate_pct": s["win_rate_pct"], "longs": s["longs"], "shorts": s["shorts"]}
    out = compare(sim, exp)
    assert not out["pass"]
    assert not [c for c in out["checks"] if c["name"] == "trade count"][0]["ok"]
    assert "NOT at parity" in out["verdict"]


# --- price-series substitution (mini stands in for its micro) -------------------

def test_every_fleet_market_has_a_known_twin():
    from backtest.pipeline import fleet
    for n in fleet.names():
        own, twin = fleet.acceptable_symbols(n)
        assert twin, f"{n}: markt {own} heeft geen twin — trap 1 verliest die route"
        assert fleet.TWIN[twin] == own, "twin-map is niet symmetrisch"


def test_twin_shares_tick_size_but_not_point_value():
    """The whole substitution rests on this: same ticks (so identical FVG bands,
    stops and R-targets) but a different dollar multiplier."""
    from backtest.config import CONTRACTS
    from backtest.pipeline import fleet
    for micro, mini in fleet.TWIN.items():
        a, b = CONTRACTS.get(micro), CONTRACTS.get(mini)
        if not a or not b:
            continue
        assert a.mintick == b.mintick, f"{micro}/{mini}: tick size verschilt"
        assert a.pointvalue != b.pointvalue, f"{micro}/{mini}: geen twin maar hetzelfde contract"


def test_a_micro_and_its_mini_produce_the_same_trade_sequence(tmp_path):
    """The measured claim behind fleet.TWIN. Point value scales the dollars; it
    must not move the trade count, win rate or long/short split — those are the
    checks stage 1 gates on."""
    import dataclasses

    import numpy as np
    import pandas as pd

    from backtest import data as dm, indicators as im
    from backtest.config import contract
    from backtest.engine import Engine
    from backtest.metrics import kpis
    from backtest.pipeline import fleet

    # volatile enough that FVGs land inside MATADOR's 10-22 tick band; a quiet
    # random walk produces zero trades and would make this test vacuous.
    rng = np.random.default_rng(7)
    n, sigma = 60_000, 4.0
    px = 6000 + np.cumsum(rng.normal(0, sigma, n))
    idx = pd.date_range("2025-09-02 00:00", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({
        "Open": px, "Close": px + rng.normal(0, sigma * 0.7, n),
        "High": px + np.abs(rng.normal(0, sigma * 2, n)),
        "Low": px - np.abs(rng.normal(0, sigma * 2, n)),
        "Volume": rng.integers(50, 900, n).astype(float),
        "Delta": np.zeros(n),
    })
    raw["High"] = raw[["High", "Open", "Close"]].max(axis=1)
    raw["Low"] = raw[["Low", "Open", "Close"]].min(axis=1)
    raw.insert(0, "DateTime", idx.strftime("%d-%m-%Y %H:%M:%S %z"))
    csv = tmp_path / "twin.csv"
    raw.to_csv(csv, index=False)
    df = dm.load(str(csv), cache=False)

    base = fleet.engine_config("EL_MATADOR_MES_PROD_EOD")
    out = {}
    for sym in ("MES", "ES"):
        cfg = dataclasses.replace(base, contract=contract(sym))
        out[sym] = kpis(Engine(cfg, df, im.compute(df, cfg), research_mode=True).run())

    assert out["MES"]["trades"] >= 10, "te weinig trades — de test bewijst dan niets"
    for key in ("trades", "win_rate_pct", "longs", "shorts"):
        assert out["MES"][key] == out["ES"][key], (
            f"{key} verschilt tussen micro en mini: "
            f"{out['MES'][key]} vs {out['ES'][key]}")
