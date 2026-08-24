"""The fleet mirror must equal the released .pine sources, input for input.

`backtest/pipeline/fleet.py` is a hand transcription of `pine/v1_0_0/*.pine`.
A silent drift there would poison stage 1 for the whole fleet: the harness would
report parity against a config that no released script actually runs. So the
transcription is not trusted — it is re-derived from the sources on every test
run and compared field by field.

Skips (does not fail) when the Pine sources are absent, so the backtest suite
still runs in a checkout without `pine/**`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backtest.pipeline import fleet

PINE_DIR = Path(__file__).resolve().parents[2] / "pine" / "v1_0_0"

# Pine input title -> (getter on Config, kind). None getter = compared against _SPEC.
FIELDS = [
    ("Fixed Qty",                                 lambda c: c.contract_size,            float),
    ("Min FVG Size (units)",                      lambda c: c.gap_min_ticks,            float),
    ("Max FVG Size (units)",                      lambda c: c.gap_max_ticks,            float),
    ("Count",                                     lambda c: c.cvd_trend_count,          float),
    ("Fixed Stop (units, legacy mode)",           lambda c: c.fixed_stop_ticks,         float),
    ("Max Stop Distance (units) — else no trade", lambda c: c.max_stop_ticks,           float),
    ("R-Multiple (R-multiple mode)",              lambda c: c.r_multiple,               float),
    ("Limit Order Expiry (bars)",                 lambda c: c.expiry_bars,              float),
    ("Day-trail activation ($)",                  lambda c: c.day_trail_activation_usd, float),
    ("Day-trail giveback ($)",                    lambda c: c.day_trail_giveback_usd,   float),
    ("Day-cap hard target ($)",                   lambda c: c.day_cap_usd,              float),
    ("Pivot Strength (bars links/rechts)",        lambda c: c.pivot_k,                  float),
    ("Stop Buffer beyond swing (units)",          lambda c: c.swing_buf_ticks,          float),
    ("Day-profit exit mode",                      lambda c: c.day_exit_mode,            str),
    ("Day-trail model",                           lambda c: c.day_trail_model,          str),
    ("Take-Profit Mode",                          lambda c: c.tp_mode,                  str),
    ("Account Phase",                             lambda c: c.phase,                    str),
    ("Use Delta Filter",                          lambda c: c.use_cvd_filter,           bool),
    ("Use FVG Size Range Filter",                 lambda c: c.use_gap_filter,           bool),
    ("Enable Break-even",                         lambda c: c.use_breakeven,            bool),
    ("Enable Trailing",                           lambda c: c.use_trail,                bool),
    ("FVG fill check (gap invalid once mid is touched)", lambda c: c.use_fill_check,    bool),
]

_INPUT = re.compile(
    r'input\.(?:int|float|bool|string)\(\s*([^,()]+?)\s*,\s*(?:title\s*=\s*)?"([^"]+)"')


def _pine_inputs(path: Path) -> dict[str, str]:
    txt = path.read_text(encoding="utf-8", errors="replace")
    return {m.group(2): m.group(1).strip() for m in _INPUT.finditer(txt)}


def _coerce(raw: str, kind):
    if kind is bool:
        return raw == "true"
    if kind is float:
        return float(raw)
    return raw.strip('"')


def _engine_name(path: Path) -> str:
    return path.name.replace("MEX_", "").replace("_v1_0_0.pine", "")


def _sources() -> list[Path]:
    return sorted(PINE_DIR.glob("*.pine")) if PINE_DIR.is_dir() else []


needs_pine = pytest.mark.skipif(not _sources(), reason="pine/v1_0_0 niet aanwezig")


@needs_pine
def test_every_released_script_has_a_mirror():
    assert {_engine_name(p) for p in _sources()} == set(fleet.names())


@needs_pine
@pytest.mark.parametrize("path", _sources(), ids=_engine_name)
def test_mirror_matches_source(path):
    name = _engine_name(path)
    ins, cfg = _pine_inputs(path), fleet.engine_config(name)
    diffs = []
    for title, get, kind in FIELDS:
        if title not in ins:
            diffs.append(f"{title}: ontbreekt in de .pine")
            continue
        pine, ours = _coerce(ins[title], kind), get(cfg)
        if kind is float:
            ours = float(ours)
        if pine != ours:
            # A documented source defect is allowed to differ, nothing else.
            if title == "Day-profit exit mode" and name in fleet.PINE_DEFECTS:
                continue
            diffs.append(f"{title}: pine={pine!r} mirror={ours!r}")
    assert not diffs, f"{name} wijkt af van de bron:\n  " + "\n  ".join(diffs)


@needs_pine
@pytest.mark.parametrize("path", _sources(), ids=_engine_name)
def test_string_inputs_have_a_valid_default(path):
    """A Pine v6 input.string whose defval is outside its own options list does
    not compile. Any script that trips this is unbuildable as shipped and must be
    listed in PINE_DEFECTS, so no engine can quietly claim stage-1 parity."""
    txt = path.read_text(encoding="utf-8", errors="replace")
    broken = []
    for m in re.finditer(r'input\.string\(\s*"([^"]*)"\s*,\s*"([^"]+)"[^\n]*?options=\[([^\]]*)\]', txt):
        default, title, opts = m.group(1), m.group(2), m.group(3)
        allowed = re.findall(r'"([^"]*)"', opts)
        if default not in allowed:
            broken.append(f"{title}: default {default!r} niet in {allowed}")
    if broken:
        assert _engine_name(path) in fleet.PINE_DEFECTS, (
            f"{path.name} heeft een niet-compilerende input.string en staat niet in "
            f"PINE_DEFECTS:\n  " + "\n  ".join(broken))


@needs_pine
@pytest.mark.parametrize("path", _sources(), ids=_engine_name)
def test_drawdown_model_comes_from_the_firm_program(path):
    """All nine scripts ship with the firm preset ON, so the loose "Drawdown
    Model" input is overwritten at runtime (D-20). The mirror must therefore
    follow the firm program, not the input — reading the input would put every
    engine on Intraday and silently mis-model the seven EOD ones."""
    name = _engine_name(path)
    ins = _pine_inputs(path)
    assert _coerce(ins["Use firm preset (fills account rules below)"], bool) is True, (
        f"{name}: firm preset staat UIT — dan is de losse input wel leidend en "
        f"klopt de afleiding in fleet.drawdown_model() niet meer")
    program = _coerce(ins["Firm program"], str)
    assert program == fleet.firm_program(name), (
        f"{name}: firm program pine={program!r} mirror={fleet.firm_program(name)!r}")
    cfg = fleet.engine_config(name)
    assert cfg.dd_model == fleet.drawdown_model(program), name
    assert cfg.dd_model == ("Intraday" if "intraday" in program else "EOD"), (
        f"{name}: {program} zou {cfg.dd_model} moeten geven")


@needs_pine
def test_the_registry_actually_defines_every_firm_program_used():
    """fleet.drawdown_model() falls back to a key-name guess when the registry
    lacks the program. That fallback must never be what we actually rely on."""
    from backtest.firms import raw_programs
    known = {p.get("key") for p in raw_programs()}
    used = {fleet.firm_program(n) for n in fleet.names()}
    assert used <= known, f"niet in data/propfirms.json: {sorted(used - known)}"


@needs_pine
@pytest.mark.parametrize("path", _sources(), ids=_engine_name)
def test_session_window_matches_the_source(path):
    """Day and hour toggles are trading filters, not cosmetics: inheriting
    Config's Mon-Fri default silently drops every Sunday-Globex entry, and that
    showed up as a 10.7% trade-count gap on MATADOR's first parity run."""
    name, ins = _engine_name(path), _pine_inputs(path)
    cfg = fleet.engine_config(name)

    days = {"Sun": 6, "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
    want = {wd for label, wd in days.items()
            if _coerce(ins[label], bool)}
    assert set(cfg.trade_days) == want, (
        f"{name}: pine handelt {sorted(want)}, mirror {sorted(cfg.trade_days)}")
    assert _coerce(ins["Sat (crypto)"], bool) is False, f"{name}: zaterdag staat aan"
    assert fleet.trades_sunday(name) == (6 in want)

    off = {int(h) for h in (f"{i:02d}" for i in range(24))
           if h in ins and not _coerce(ins[h], bool)}
    assert set(range(24)) - set(cfg.enabled_hours) == off, (
        f"{name}: pine zet uren {sorted(off)} uit, mirror "
        f"{sorted(set(range(24)) - set(cfg.enabled_hours))}")

    assert _coerce(ins["Force Flat Window"], bool) == cfg.use_auto_flat, name


@needs_pine
def test_not_every_engine_trades_sunday():
    """A guard that the transcription is real and not a blanket value: PATRON and
    TESORO (both MGC) sit out the Sunday open, the other seven do not."""
    sundays = {n: fleet.trades_sunday(n) for n in fleet.names()}
    assert any(sundays.values()) and not all(sundays.values()), sundays
    assert sundays["EL_PATRON_MGC_AGG_EOD"] is False
    assert sundays["EL_TESORO_MGC_CON_EOD"] is False
    assert sundays["EL_MATADOR_MES_PROD_EOD"] is True


@needs_pine
def test_regime_and_market_match_the_source():
    for path in _sources():
        name = _engine_name(path)
        ins = _pine_inputs(path)
        assert _coerce(ins["Market regime"], str) == fleet._SPEC[name][12], name
        assert fleet.market(name) in path.name, name


@needs_pine
@pytest.mark.parametrize("path", _sources(), ids=_engine_name)
def test_our_fvg_detection_equals_the_pine_formula(path, tmp_path):
    """The measurement that settled where MATADOR's parity gap comes from.

    All 35 unexplained missed signals had no FVG of that direction in our window.
    That is only evidence about the DATA if our detection is provably identical
    to Pine's — otherwise it is evidence about our code. So the Pine expression
    is transcribed literally here and compared bar for bar."""
    import numpy as np

    from backtest import indicators as im
    from backtest.pipeline import fleet

    name = _engine_name(path)
    cfg = fleet.engine_config(name)
    rng = np.random.default_rng(19)
    n = 8_000
    px = 6000 + np.cumsum(rng.normal(0, 6.0, n))
    high = px + np.abs(rng.normal(0, 9.0, n))
    low = px - np.abs(rng.normal(0, 9.0, n))
    tick = cfg.contract.mintick
    high = np.round(high / tick) * tick
    low = np.round(low / tick) * tick
    close = np.clip(px, low, high)
    open_ = np.clip(px + rng.normal(0, 2.0, n), low, high)

    import pandas as pd

    from backtest import data as dm
    idx = pd.date_range("2025-09-02", periods=n, freq="1min", tz="America/New_York")
    raw = pd.DataFrame({"DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"),
                        "Open": open_, "High": high, "Low": low, "Close": close,
                        "Volume": np.full(n, 100.0), "Delta": np.zeros(n)})
    csv = tmp_path / "fvg.csv"
    raw.to_csv(csv, index=False)
    df = dm.load(str(csv), cache=False)
    high, low = df["High"].to_numpy(), df["Low"].to_numpy()
    ind = im.compute(df, cfg)

    # literal transcription of the Pine source (fvgDirection / top / bottom)
    d = np.zeros(n, int)
    top = np.full(n, np.nan)
    bot = np.full(n, np.nan)
    for i in range(2, n):
        if low[i - 2] >= high[i]:
            d[i], top[i], bot[i] = -1, low[i - 2], high[i]
        elif low[i] >= high[i - 2]:
            d[i], top[i], bot[i] = 1, low[i], high[i - 2]
    size = np.abs(top - bot)
    ok = (~np.isnan(size) & (size >= cfg.gap_min_ticks * tick)
          & (size <= cfg.gap_max_ticks * tick) & (size > 0))

    assert np.array_equal(np.asarray(ind["fvg_dir"]), d), f"{name}: richting wijkt af"
    assert np.allclose(np.nan_to_num(np.asarray(ind["fvg_size"]), nan=-1),
                       np.nan_to_num(size, nan=-1)), f"{name}: grootte wijkt af"
    assert np.array_equal(np.asarray(ind["fvg_pass"]), ok), f"{name}: band-pass wijkt af"
    assert ok.sum() > 20, "te weinig gaps — de vergelijking bewijst niets"
