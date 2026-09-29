"""notify_routing: één plek voor 'waar-gaat-deze-notificatie-heen' (D-28).

Deze tests borgen twee dingen:
  1. De prioriteit klopt — per-firm slaat per-fase; per-fase slaat de globale.
  2. `webhook_for()` en `_candidate_env_names()` blijven in sync — het
     debug-endpoint mag niet uit de pas lopen met de echte routing.
"""
from __future__ import annotations

import pytest

from app import notify_routing as nr


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Elke test start met een schone lei; anders leken tests van elkaar over."""
    for k in list(os.environ if False else ()):  # placeholder: monkeypatch geeft de reset
        pass
    for name in ("NOTIFY_WEBHOOK", "NOTIFY_WEBHOOK_FUNDED", "NOTIFY_WEBHOOK_EVAL",
                 "NOTIFY_WEBHOOK_APEX", "NOTIFY_WEBHOOK_FTMO",
                 "ALERT_WEBHOOK",
                 "TELEGRAM_NOTIFY_WEBHOOK", "TELEGRAM_NOTIFY_WEBHOOK_FUNDED",
                 "TELEGRAM_ALERT_WEBHOOK"):
        monkeypatch.delenv(name, raising=False)


import os  # noqa: E402  (na de fixture zodat monkeypatch importvolgorde niet stoort)


def test_phase_detection_from_account_prefix():
    assert nr._phase("PAAPEX2700250000015") == "funded"
    assert nr._phase("APEX27002500000209") == "eval"
    assert nr._phase("AP015") == "eval"
    assert nr._phase("random") == "other"


def test_firm_detection():
    assert nr._firm("PAAPEX2700250000015") == "apex"
    assert nr._firm("FTMO12345") == "ftmo"
    assert nr._firm("random") == ""


def test_globale_fallback(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK", "https://globaal")
    assert nr.webhook_for("PAAPEX2700250000015") == "https://globaal"
    assert nr.webhook_for("APEX27002500000209") == "https://globaal"


def test_fase_wint_van_globaal(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK", "https://globaal")
    monkeypatch.setenv("NOTIFY_WEBHOOK_FUNDED", "https://funded")
    monkeypatch.setenv("NOTIFY_WEBHOOK_EVAL", "https://eval")
    assert nr.webhook_for("PAAPEX2700250000015") == "https://funded"
    assert nr.webhook_for("APEX27002500000209") == "https://eval"


def test_firm_wint_van_fase(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK", "https://globaal")
    monkeypatch.setenv("NOTIFY_WEBHOOK_FUNDED", "https://funded")
    monkeypatch.setenv("NOTIFY_WEBHOOK_APEX", "https://apex")
    # apex komt voor funded uit
    assert nr.webhook_for("PAAPEX2700250000015") == "https://apex"


def test_failure_gaat_naar_alert_kanaal(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK", "https://trades")
    monkeypatch.setenv("ALERT_WEBHOOK", "https://fouten")
    assert nr.webhook_for("PAAPEX2700250000015", kind="failure") == "https://fouten"
    # failure gebruikt geen firm/fase routing
    monkeypatch.setenv("NOTIFY_WEBHOOK_FUNDED", "https://funded")
    assert nr.webhook_for("PAAPEX2700250000015", kind="failure") == "https://fouten"


def test_telegram_gebruikt_eigen_env_maar_valt_terug_op_notify(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK", "https://discord-globaal")
    # Geen telegram-env → val terug op de gewone NOTIFY_WEBHOOK, want de _post
    # helper stuurt beide keys ({content, text}); één webhook kan beide bedienen.
    assert nr.webhook_for("PAAPEX2700250000015", channel="telegram") == "https://discord-globaal"
    monkeypatch.setenv("TELEGRAM_NOTIFY_WEBHOOK", "https://tg-globaal")
    assert nr.webhook_for("PAAPEX2700250000015", channel="telegram") == "https://tg-globaal"


def test_geen_configuratie_geeft_lege_string_geen_none():
    # Kritiek: een None zou een AttributeError op de call-site geven; leeg = "skip".
    assert nr.webhook_for("PAAPEX2700250000015") == ""
    assert nr.webhook_for("PAAPEX2700250000015", kind="failure") == ""


def test_describe_toont_env_naam_niet_de_url(monkeypatch):
    """describe() mag geen webhook-URL retourneren — dat is een secret."""
    monkeypatch.setenv("NOTIFY_WEBHOOK", "https://GEHEIM-globaal-url")
    monkeypatch.setenv("NOTIFY_WEBHOOK_FUNDED", "https://GEHEIM-funded-url")
    d = nr.describe("PAAPEX2700250000015")
    rendered = repr(d)
    assert "GEHEIM" not in rendered
    assert d["channels"]["trade.discord"]["matched"] == "NOTIFY_WEBHOOK_FUNDED"
    assert d["channels"]["trade.discord"]["configured"] is True


def test_candidates_en_webhook_for_zijn_in_sync(monkeypatch):
    """Elke naam die _candidate_env_names oplevert moet, als hij als enige gezet
    staat, ook door webhook_for gekozen worden. Anders raken debug en runtime uit
    de pas — precies het probleem dat we hier proberen te voorkomen."""
    account = "PAAPEX2700250000015"   # funded / apex
    for kind in ("trade", "failure"):
        for channel in ("discord", "telegram"):
            names = nr._candidate_env_names(account, kind, channel)  # type: ignore[arg-type]
            for name in names:
                # zet alleen deze env en check dat webhook_for hem kiest
                for other in names:
                    monkeypatch.delenv(other, raising=False)
                monkeypatch.setenv(name, f"https://{name}")
                got = nr.webhook_for(account, kind=kind, channel=channel)  # type: ignore[arg-type]
                assert got == f"https://{name}", (
                    f"kandidaat {name} werd niet gekozen door webhook_for "
                    f"(kind={kind}, channel={channel}); got={got!r}"
                )
