"""Capability-gate tests (D-101 increment 2).

The gate is the interpreter's refusal surface: it accepts exactly the D-100 namespaced
surface and HARD-FAILS on anything else — a new ta.* function, a new namespace, a typo.
The two things that matter: (1) all 13 live scripts pass (the manifest really is what the
fleet uses), and (2) the unknown is refused, never waved through.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backtest.pineinterp import check_supported, UnsupportedPineError, SUPPORTED_TA

PINE_DIR = Path(__file__).resolve().parent.parent.parent / "pine"
SCRIPTS = sorted(PINE_DIR.glob("*.pine"))


@pytest.mark.skipif(not SCRIPTS, reason="pine/*.pine not present")
@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name.replace("MEX_", "").replace("_v1_0_0.pine", ""))
def test_every_live_script_is_within_the_supported_subset(path):
    rep = check_supported(path.read_text(encoding="utf-8"), name=path.name)
    assert rep["ta_used"], "a fleet script should use some ta.* functions"
    assert set(rep["ta_used"]) <= SUPPORTED_TA


@pytest.mark.skipif(not SCRIPTS, reason="pine/*.pine not present")
def test_the_fleet_uses_exactly_the_d100_ta_surface():
    """Across all 13, the ta.* functions are the enumerated D-100 set — nothing new crept
    in. If this fails, a script gained a ta function the interpreter has not been taught."""
    used = set()
    for p in SCRIPTS:
        used |= set(check_supported(p.read_text(encoding="utf-8"), name=p.name)["ta_used"])
    assert used <= SUPPORTED_TA
    # requestVolumeDelta lives only in the two non-canonical-CVD scripts
    rvd = [p.name for p in SCRIPTS
           if "requestVolumeDelta" in check_supported(p.read_text(), name=p.name)["ta_used"]]
    assert len(rvd) == 2 and all("PATRON" in n or "TESORO" in n for n in rvd)


def test_hard_fails_on_unknown_ta_function():
    with pytest.raises(UnsupportedPineError, match=r"ta\.supertrend"):
        check_supported("x = ta.supertrend(close, 10, 3)", "synthetic")


def test_hard_fails_on_unknown_namespace():
    with pytest.raises(UnsupportedPineError, match="polyline"):
        check_supported("p = polyline.new()", "synthetic")


def test_reports_every_offender_not_just_the_first():
    with pytest.raises(UnsupportedPineError) as ei:
        check_supported("a = ta.cci(close, 20)\nb = matrix.get(m, 0, 0)", "synthetic")
    msg = str(ei.value)
    assert "ta.cci" in msg and "matrix" in msg


def test_supported_calls_pass_cleanly():
    rep = check_supported("e = ta.ema(close, 20)\nh = math.max(1, 2)\n"
                          "d = str.tostring(e)\nc = color.new(color.red, 0)", "ok")
    assert "ema" in rep["ta_used"] and "math" in rep["namespaces_used"]


def test_string_and_comment_contents_are_not_scanned():
    """A ta.* named only inside a string or comment must not trip the gate — the scan is
    on tokens, and the lexer has already dropped comments and opaque-ified strings."""
    src = '// ta.supertrend in a comment\nmsg = "call ta.madeup() here"\ne = ta.ema(close, 9)'
    rep = check_supported(src, "ok")
    assert rep["ta_used"] == ["ema"]
