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
    ("Drawdown Model",                            lambda c: c.dd_model,                 str),
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
def test_regime_and_market_match_the_source():
    for path in _sources():
        name = _engine_name(path)
        ins = _pine_inputs(path)
        assert _coerce(ins["Market regime"], str) == fleet._SPEC[name][12], name
        assert fleet.market(name) in path.name, name
