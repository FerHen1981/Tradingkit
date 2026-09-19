"""Waar-gaat-deze-notificatie-heen — één plek, geen tweede kopie.

Kern: **één functie**, `webhook_for(account, kind)`, die op basis van env-vars
en het account bepaalt naar welke Discord/Telegram-webhook een bericht moet.
Vervangt de simpele `NOTIFY_WEBHOOK` uit `config.py` (die één globale webhook
kent) met een routing-tabel: funded gescheiden van eval, per-firm override,
Telegram-pariteit, en een aparte failure-kanaal (zoals de oude `ALERT_WEBHOOK`).

Deze module doet zelf **geen** HTTP-calls en heeft géén datatoegang — puur een
lookup. Dat maakt hem:

  1. Bruikbaar door de Python-kant (reconcile-alerts, `journal_sync` failures,
     iedere service die iets naar Discord wil sturen zonder eigen env-vars).
  2. Even bruikbaar door de .NET-receiver — die kan diezelfde env-vars lezen
     en hetzelfde patroon volgen zonder een tweede routing-tabel te dragen.

De Python fan-out (`main.py`/`notify.py`) is DEAD PATH (D-05); die krijgt hier
geen nieuwe wire — het live executiepad is de .NET-receiver, die de env-vars
zelf al leest. Dit bestand is er om de **beslislogica** één keer vast te leggen
zodat beide kanten hem synchroon houden.

## Env

    NOTIFY_WEBHOOK              default voor trades (Discord). Blijft de fallback
                                als geen van de meer specifieke gezet is.
    NOTIFY_WEBHOOK_FUNDED       trades op funded accounts (PAAPEX*)
    NOTIFY_WEBHOOK_EVAL         trades op eval accounts (APEX* zonder PA)
    NOTIFY_WEBHOOK_APEX         per-firm override (wint van FUNDED/EVAL)
    NOTIFY_WEBHOOK_FTMO         per-firm override
    ALERT_WEBHOOK               failure-alerts (broken order, dispatch fout, etc.)
    TELEGRAM_WEBHOOK*           idem, maar voor Telegram. `_post` in de .NET-kant
                                leest zelf {content, text}, dus dezelfde payload
                                werkt op beide kanten.
"""
from __future__ import annotations

import os
from typing import Literal

Kind = Literal["trade", "failure"]


def _phase(account: str) -> str:
    """'PAAPEX...' = funded, 'APEX...' zonder PA = eval, andere strings = other."""
    a = (account or "").upper().strip()
    if a.startswith("PA"):
        return "funded"
    if a.startswith("APEX") or a.startswith("AP"):
        return "eval"
    return "other"


def _firm(account: str) -> str:
    """Ruwe firm-detectie uit de account-string. Uitbreidbaar zonder de call-site
    te raken — voeg een nieuwe herkenner toe zodra er een nieuwe firm bijkomt."""
    a = (account or "").upper().strip()
    if "APEX" in a:
        return "apex"
    if "FTMO" in a:
        return "ftmo"
    if "MFF" in a or "MYFOREXFUNDS" in a:
        return "mff"
    return ""


def _env(*names: str) -> str:
    """Eerste niet-lege waarde uit een reeks env-namen, of een lege string."""
    for name in names:
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""


def webhook_for(account: str, kind: Kind = "trade", channel: str = "discord") -> str:
    """Bepaal welke webhook een bericht krijgt.

    Volgorde (meest specifiek eerst):
      failure  → ALERT_WEBHOOK (of TELEGRAM_ALERT_WEBHOOK), zonder verdere routing
      trade    → per-firm ⇒ per-fase ⇒ globaal

    Retourneert een lege string als er niets geconfigureerd is; de aanroeper mag
    daar zelf op reageren (skip of loggen). Nooit een None — een lege string is
    het "geen webhook"-signaal.
    """
    if kind == "failure":
        if channel == "telegram":
            return _env("TELEGRAM_ALERT_WEBHOOK", "ALERT_WEBHOOK")
        return _env("ALERT_WEBHOOK")

    firm = _firm(account).upper()
    phase = _phase(account).upper()
    prefix = "TELEGRAM_NOTIFY_WEBHOOK" if channel == "telegram" else "NOTIFY_WEBHOOK"

    # per-firm override wint van fase
    candidates = []
    if firm:
        candidates.append(f"{prefix}_{firm}")
    if phase != "OTHER":
        candidates.append(f"{prefix}_{phase}")
    candidates.append(prefix)                                # de globale fallback
    if channel == "telegram":
        candidates.append("NOTIFY_WEBHOOK")                  # cross-channel fallback
    return _env(*candidates)


def describe(account: str) -> dict:
    """Voor debug/log: welke webhook zou dit bericht gekregen hebben, en waarom.
    Nooit de webhook-URL zelf terug — alleen de env-naam die de match leverde."""
    firm = _firm(account).upper()
    phase = _phase(account).upper()
    result = {"account": account, "firm": firm.lower() or None,
              "phase": phase.lower(), "channels": {}}
    for kind in ("trade", "failure"):
        for channel in ("discord", "telegram"):
            names = _candidate_env_names(account, kind, channel)  # type: ignore[arg-type]
            hit = next((n for n in names if os.environ.get(n, "").strip()), None)
            result["channels"][f"{kind}.{channel}"] = {
                "candidates": names,
                "matched": hit,
                "configured": bool(hit),
            }
    return result


def _candidate_env_names(account: str, kind: Kind, channel: str) -> list[str]:
    """Zelfde volgorde als `webhook_for`, maar geeft de kandidaten terug voor
    logging/introspectie. Gehouden naast `webhook_for` zodat de twee samen kunnen
    veranderen zonder een van beide te vergeten (er is een test die dit borgt)."""
    if kind == "failure":
        return ["TELEGRAM_ALERT_WEBHOOK", "ALERT_WEBHOOK"] if channel == "telegram" \
            else ["ALERT_WEBHOOK"]
    firm = _firm(account).upper()
    phase = _phase(account).upper()
    prefix = "TELEGRAM_NOTIFY_WEBHOOK" if channel == "telegram" else "NOTIFY_WEBHOOK"
    names = []
    if firm:
        names.append(f"{prefix}_{firm}")
    if phase != "OTHER":
        names.append(f"{prefix}_{phase}")
    names.append(prefix)
    if channel == "telegram":
        names.append("NOTIFY_WEBHOOK")
    return names
