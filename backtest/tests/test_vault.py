"""Vault ingest — the deterministic (definition) half of self-learning.

Pins the two things that must be right: (1) the Pine parser pulls title + default
+ bounds + options, and (2) the scanner splits indicators into KNOWN (mapped to a
registry group or recognised primitive) and UNKNOWN (adopted). The fleet's own
EL_REY_MNQ_PROD_EOD used ta.vwma/ta.hma — those are now RECOGNISED (vwma is the
BBWP basis option, hma the MFI smoother, both wired as filters in Fase 6), so the
fixture also carries two genuinely-unwired calls (ta.cci/ta.tsi) to keep the
adoption path under test.
"""
from __future__ import annotations

import json

import pytest

from backtest.lab import vault


_PINE = '''
//@version=6
var string GROUP_FVG  = "5 · SIGNAL — FVG"
var string GROUP_CVD  = "6 · SIGNAL — Volume delta"
qty     = input.float(6, "Fixed Qty", minval=0, step=1, group=GROUP_UNIT)
mode    = input.string("Day-cap (hard target)", "Day-profit exit mode", options=["Off","Day-cap (hard target)","Trail + cap"])
useX    = input.bool(true, "Enable X")
band    = input.int(12, "Min FVG Size (units)", minval=1, maxval=40, step=1)
h       = ta.hma(close, 20)
v       = ta.vwma(close, 14)
a       = ta.atr(14)
c       = ta.cci(close, 20)
t       = ta.tsi(close, 25, 13)
'''


@pytest.fixture(autouse=True)
def _lab(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DIR", str(tmp_path))


# --- parser -------------------------------------------------------------------

def test_parse_pulls_title_default_and_bounds():
    inp = {i["title"]: i for i in vault.parse_pine_inputs(_PINE)}
    assert inp["Fixed Qty"]["default"] == 6 and inp["Fixed Qty"]["min"] == 0
    assert inp["Min FVG Size (units)"]["min"] == 1 and inp["Min FVG Size (units)"]["max"] == 40
    assert inp["Enable X"]["default"] is True and inp["Enable X"]["type"] == "bool"


def test_parse_reads_options_incl_parens_in_default():
    inp = {i["title"]: i for i in vault.parse_pine_inputs(_PINE)}
    m = inp["Day-profit exit mode"]
    assert m["default"] == "Day-cap (hard target)"          # quoted default with parens
    assert m["options"] == ["Off", "Day-cap (hard target)", "Trail + cap"]


# --- scanner ------------------------------------------------------------------

def test_scan_maps_known_signal_groups():
    sc = vault.scan_indicators(_PINE)
    assert set(sc["known"]) == {"fvg", "cvd_delta"}         # from the SIGNAL group labels


def test_scan_flags_unknown_ta_calls_only():
    sc = vault.scan_indicators(_PINE)
    # cci + tsi are not recognised -> adopt; atr is a primitive -> ignored
    assert set(sc["unknown"]) == {"ta_cci", "ta_tsi"}


def test_scan_recognises_wired_vwma_and_hma():
    """Regression: vwma/hma were the fleet's only unknowns; wiring BBWP/MFI (Fase 6)
    made them recognised building blocks, so an EL_REY-style upload no longer adopts
    phantom indicators for them."""
    sc = vault.scan_indicators(_PINE)
    assert "ta_vwma" not in sc["unknown"] and "ta_hma" not in sc["unknown"]


# --- adoption -----------------------------------------------------------------

def test_adopt_pine_adopts_unknown_and_builds_spec(tmp_path):
    res = vault.adopt_pine(_PINE, filename="thing.pine")
    assert set(res["adopted"]) == {"ta_cci", "ta_tsi"}
    assert "fvg" in res["known"] and "cvd_delta" in res["known"]
    # adopted indicators are now in the overlay AND the merged registry
    from backtest import spec
    groups = spec._all_groups(spec.load_registry())
    assert "ta_cci" in groups and "ta_tsi" in groups
    assert groups["ta_cci"][1]["engine"] == "todo"
    # a wiring request was queued for each
    reqs = {r["name"] for r in vault.list_requests()}
    assert {"ta_cci", "ta_tsi"} <= reqs


def test_overlay_never_shadows_a_sourced_group(tmp_path):
    # 'fvg' is a sourced group; adopting under that name must be namespaced away
    nm = vault.adopt_overlay_entry("fvg", desc="x", source="text")
    assert nm != "fvg" and nm.startswith("adopted_")


def test_adopt_text_queues_only_never_adopts():
    res = vault.adopt_text("A momentum burst indicator that fires when ...", "burst")
    assert res["queued"] == "burst"
    assert vault.list_adopted() == []                        # nothing adopted directly
    assert any(r["name"] == "burst" and r["source"] == "text" for r in vault.list_requests())


def test_wiring_request_carries_ground_rules():
    vault.adopt_pine(_PINE, filename="thing.pine")
    req = next(r for r in vault.list_requests() if r["name"] == "ta_cci")
    assert any("look-ahead" in g for g in req["ground_rules"])
    assert any("indicators.py" in t for t in req["touchpoints"])
