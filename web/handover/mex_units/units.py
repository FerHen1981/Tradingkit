"""Geld → units. Het enige conversiepunt in de hele stack.

De viewer-rol en de publieke site krijgen nooit een bedrag te zien. Die belofte
is alleen iets waard als de omrekening één keer gebeurt, server-side, op één
plek — dit bestand.

**Contract-specs komen uit `backtest/config.py CONTRACTS`** en worden hier niet
herhaald (werkafspraken §3: nooit een tweede kopie). Wat hier wél staat is
presentatie: de Nederlandse naam van een markt en de eenheid waarin die markt
beweegt — ticks voor futures, pips voor spot FX. Dat zijn geen getallen uit de
registry en horen dus niet in de registry.

Draait dit als onderdeel van een service met een eigen werkmap, dan moet de
repo-root op `sys.path` staan; anders faalt de import hieronder meteen en
luidruchtig. Dat is met opzet: terugvallen op een ingebakken tabel zou de
registry stilzwijgend laten verouderen.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    from backtest.config import CONTRACTS as _CONTRACTS
except ImportError as exc:  # pragma: no cover - configuratiefout, geen logica
    raise ImportError(
        "mex_units heeft backtest.config.CONTRACTS nodig — dat is de single "
        "source voor tick-size en pointvalue (werkafspraken §3). Zet de "
        "repo-root op sys.path of installeer het pakket; dit bestand houdt "
        "bewust geen eigen kopie van de specs."
    ) from exc


#: Micro-contracten rollen op naar hun grote broer voor rapportage: het is
#: dezelfde trade-idee op andere omvang, en apart tonen versnippert het beeld
#: zonder er iets aan toe te voegen.
MICRO_PARENT = {"MGC": "GC", "MES": "ES", "MNQ": "NQ", "MYM": "YM", "M2K": "RTY"}

#: Presentatie per markt: hoe we hem noemen en waarin hij beweegt. Spot-FX
#: rekent in pips, futures in ticks. Symbolen die hier ontbreken vallen terug
#: op hun eigen code en "ticks".
PRESENTATION: dict[str, tuple[str, str]] = {
    "NQ": ("Nasdaq 100", "ticks"),
    "ES": ("S&P 500", "ticks"),
    "YM": ("Dow 30", "ticks"),
    "RTY": ("Russell 2000", "ticks"),
    "MNQ": ("Nasdaq 100 (micro)", "ticks"),
    "MES": ("S&P 500 (micro)", "ticks"),
    "MYM": ("Dow 30 (micro)", "ticks"),
    "M2K": ("Russell 2000 (micro)", "ticks"),
    "GC": ("Goud", "ticks"),
    "MGC": ("Goud (micro)", "ticks"),
    "SI": ("Zilver", "ticks"),
    "CL": ("Ruwe olie", "ticks"),
    "NG": ("Aardgas", "ticks"),
    "BTC": ("Bitcoin", "ticks"),
    "6E": ("EUR/USD future", "ticks"),
    "6B": ("GBP/USD future", "ticks"),
    "6J": ("JPY future", "ticks"),
    "6A": ("AUD/USD future", "ticks"),
    "6S": ("CHF future", "ticks"),
    "6C": ("CAD future", "ticks"),
    "EURUSD": ("EUR/USD", "pips"),
    "GBPUSD": ("GBP/USD", "pips"),
    "AUDUSD": ("AUD/USD", "pips"),
    "EURGBP": ("EUR/GBP", "pips"),
    "USDJPY": ("USD/JPY", "pips"),
    "CADJPY": ("CAD/JPY", "pips"),
}

#: Spot-FX noteert met vijf decimalen maar handelt in pips; één pip is tien
#: keer de mintick uit de registry. Voor JPY-paren geldt hetzelfde met 0,01.
_PIP_PER_TICK = 10.0


@dataclass(frozen=True)
class Spec:
    """Wat de omrekening nodig heeft, samengesteld uit registry + presentatie."""

    symbol: str
    tick: float
    per_point: float
    unit: str
    label: str

    @property
    def per_unit(self) -> float:
        """Bedrag per eenheid (tick of pip), per contract of lot."""
        money_per_tick = self.tick * self.per_point
        return money_per_tick * (_PIP_PER_TICK if self.unit == "pips" else 1.0)

    @property
    def unit_size(self) -> float:
        """Prijsafstand van één eenheid."""
        return self.tick * (_PIP_PER_TICK if self.unit == "pips" else 1.0)


def normalise(symbol: str) -> str:
    """'MGC1!' → 'MGC', 'COMEX:GC1!' → 'GC'.

    Chart- en brokersymbolen dragen beurs-, continuïteits- en expiratiesuffixen
    die de registry niet kent.
    """
    s = (symbol or "").upper().strip()
    s = s.split(":")[-1]
    s = s.rstrip("!")
    s = s.rstrip("0123456789")

    if s in _CONTRACTS:
        return s

    # Val terug op de langste registry-sleutel waar het symbool mee begint, zodat
    # een onverwacht suffix naar het juiste contract degradeert in plaats van
    # naar niets.
    for key in sorted(_CONTRACTS, key=len, reverse=True):
        if s.startswith(key):
            return key
    return s


def spec_for(symbol: str) -> Spec | None:
    key = normalise(symbol)
    contract = _CONTRACTS.get(key)
    if contract is None:
        return None
    label, unit = PRESENTATION.get(key, (key, "ticks"))
    return Spec(
        symbol=key,
        tick=contract.mintick,
        per_point=contract.pointvalue,
        unit=unit,
        label=label,
    )


def to_units(amount: float, symbol: str, qty: float = 1.0) -> float | None:
    """Reken een bedrag op `symbol` om naar de eenheid van die markt.

    Geeft None bij een onbekend symbool in plaats van een plausibel ogend getal —
    een verkeerd tick-aantal is erger dan een ontbrekend, omdat het onzichtbaar is.
    """
    spec = spec_for(symbol)
    if spec is None or not qty:
        return None
    per_unit = spec.per_unit * abs(qty)
    if per_unit == 0:
        return None
    return amount / per_unit


def price_to_units(price_delta: float, symbol: str) -> float | None:
    """Reken een prijsverschil (bijv. slippage) om naar ticks of pips."""
    spec = spec_for(symbol)
    if spec is None or spec.unit_size == 0:
        return None
    return price_delta / spec.unit_size


def unit_name(symbol: str) -> str:
    spec = spec_for(symbol)
    return spec.unit if spec else "units"


def label_for(symbol: str) -> str:
    spec = spec_for(symbol)
    return spec.label if spec else normalise(symbol)


def group_key(symbol: str) -> str:
    """Rapportagesleutel: micro's rollen op naar hun grote broer."""
    key = normalise(symbol)
    return MICRO_PARENT.get(key, key)
