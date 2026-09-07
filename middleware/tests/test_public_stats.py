"""public_stats writer — de brug tussen trades en `public-stats.json` (D-17)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from app import public_stats


def _fake_trade(sym: str, net: float, close: dt.date, acct: str = "PAAPEX111") -> dict:
    """Trade in het formaat dat `dashboard_state._sources()` teruggeeft."""
    return {"acct": acct, "sym": sym, "strat": "El Tesoro", "net": net, "ticks": 0,
            "close": close, "hour": 12, "dow": close.weekday(), "comm": 0.0,
            "mfe": None, "mae": None}


def test_adapter_maps_dashboard_trade_to_mex_units_shape():
    d = dt.date(2026, 8, 3)
    t = _fake_trade("MGC", 20.37, d)
    out = public_stats._to_mex_units_trade(t)
    assert out["symbol"] == "MGC"
    assert out["realized_usd"] == 20.37
    # ts moet naar 3 aug 2026 verwijzen (UTC 12:00 als anker)
    assert dt.datetime.fromtimestamp(out["ts"], dt.timezone.utc).date() == d
    # velden die we niet betrouwbaar hebben blijven None
    assert out["slippage_ticks"] is None
    assert out["hold_s"] is None


def test_write_produces_a_currency_free_payload(monkeypatch, tmp_path):
    """De hele weg — trades → build → for_public → assert_no_currency → write."""
    trades = [
        _fake_trade("GC1!", 20.37, dt.date(2026, 6, 15)),
        _fake_trade("GC1!", -50.63, dt.date(2026, 7, 8)),
        _fake_trade("ES1!", 125.41, dt.date(2026, 8, 5)),
        _fake_trade("MGC1!", 10.29, dt.date(2026, 8, 12)),
    ]
    monkeypatch.setattr(public_stats, "_sources", lambda: (trades, []))
    out = tmp_path / "public-stats.json"
    summary = public_stats.write(out)
    assert summary["trades"] == 4
    payload = json.loads(out.read_text())
    # markets moeten aanwezig zijn (MGC rolt op naar GC → 2 markten)
    assert {m["symbol"] for m in payload["markets"]} == {"GC", "ES"}
    # geen enkel dollarbedrag mag in de tekst voorkomen
    text = out.read_text()
    for amount in ("20.37", "50.63", "125.41", "10.29"):
        assert amount not in text, f"currency amount {amount} leaked to public-stats.json"


def test_write_refuses_a_payload_that_ever_gains_a_money_key(monkeypatch, tmp_path):
    """Als de builder ooit een geldveld toevoegt, moet write() weigeren te schrijven."""
    trades = [_fake_trade("GC1!", 20.37, dt.date(2026, 6, 15))]
    monkeypatch.setattr(public_stats, "_sources", lambda: (trades, []))

    from app.mex_units import roles

    real_for_public = roles.for_public

    def leaky_for_public(fleet, delay="T+1"):
        p = real_for_public(fleet, delay)
        p["headline"]["net_usd"] = 20.37
        return p

    monkeypatch.setattr(roles, "for_public", leaky_for_public)
    out = tmp_path / "public-stats.json"
    with pytest.raises(ValueError, match="net_usd"):
        public_stats.write(out)
    # en het bestand mag niet gemaakt zijn
    assert not out.exists()


def test_write_is_atomic_via_tmp_swap(monkeypatch, tmp_path):
    """Een lezer mag nooit een halve file zien: we schrijven naar .tmp en replaceen."""
    trades = [_fake_trade("GC1!", 20.37, dt.date(2026, 6, 15))]
    monkeypatch.setattr(public_stats, "_sources", lambda: (trades, []))
    out = tmp_path / "public-stats.json"
    public_stats.write(out)
    # de tmp mag niet blijven staan na een succesvolle swap
    assert not (out.with_suffix(out.suffix + ".tmp")).exists()
    assert out.exists()
