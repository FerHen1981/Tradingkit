"""Money -> units. The single conversion point in the whole stack.

The viewer role and the public site never receive currency. That guarantee is
only worth something if the conversion happens once, on the server, in a place
that also owns the contract specs. This module is that place.

Tick sizes and point values mirror `backtest/config.py::CONTRACTS`. They are
restated here rather than imported because the portal must be deployable on its
own — but they are the same numbers, and `test_units.py` asserts that they stay
in step with the registry when both are present.
"""
from __future__ import annotations

from dataclasses import dataclass

# Micro contracts share their parent's tick size at a fraction of the value,
# so they must be listed separately or a micro fill converts to the wrong
# number of ticks.
MICRO_PARENT = {"MGC": "GC", "MES": "ES", "MNQ": "NQ", "MYM": "YM", "M2K": "RTY"}


@dataclass(frozen=True)
class Spec:
    symbol: str
    tick: float
    """Smallest price increment."""
    per_point: float
    """Currency per one full point of price movement, per contract."""
    unit: str = "ticks"
    label: str = ""

    @property
    def per_tick(self) -> float:
        """Currency per tick, per contract."""
        return self.tick * self.per_point


SPECS: dict[str, Spec] = {
    # CME equity index
    "NQ": Spec("NQ", 0.25, 20.0, "ticks", "Nasdaq 100"),
    "ES": Spec("ES", 0.25, 50.0, "ticks", "S&P 500"),
    "YM": Spec("YM", 1.0, 5.0, "ticks", "Dow 30"),
    "RTY": Spec("RTY", 0.10, 50.0, "ticks", "Russell 2000"),
    "MNQ": Spec("MNQ", 0.25, 2.0, "ticks", "Nasdaq 100 (micro)"),
    "MES": Spec("MES", 0.25, 5.0, "ticks", "S&P 500 (micro)"),
    "MYM": Spec("MYM", 1.0, 0.5, "ticks", "Dow 30 (micro)"),
    "M2K": Spec("M2K", 0.10, 5.0, "ticks", "Russell 2000 (micro)"),
    # metals / energy
    "GC": Spec("GC", 0.10, 100.0, "ticks", "Goud"),
    "MGC": Spec("MGC", 0.10, 10.0, "ticks", "Goud (micro)"),
    "SI": Spec("SI", 0.005, 5000.0, "ticks", "Zilver"),
    "CL": Spec("CL", 0.01, 1000.0, "ticks", "Ruwe olie"),
    # CME FX futures
    "6E": Spec("6E", 0.00005, 125000.0, "ticks", "EUR/USD future"),
    "6B": Spec("6B", 0.0001, 62500.0, "ticks", "GBP/USD future"),
    "6J": Spec("6J", 0.0000005, 12500000.0, "ticks", "JPY future"),
    "6A": Spec("6A", 0.0001, 100000.0, "ticks", "AUD/USD future"),
    "6S": Spec("6S", 0.0001, 125000.0, "ticks", "CHF future"),
    "6C": Spec("6C", 0.00005, 100000.0, "ticks", "CAD future"),
    # Spot FX (MT5 / FTMO) — quoted in pips, not ticks.
    "EURUSD": Spec("EURUSD", 0.0001, 100000.0, "pips", "EUR/USD"),
    "GBPUSD": Spec("GBPUSD", 0.0001, 100000.0, "pips", "GBP/USD"),
    "AUDUSD": Spec("AUDUSD", 0.0001, 100000.0, "pips", "AUD/USD"),
    "EURGBP": Spec("EURGBP", 0.0001, 100000.0, "pips", "EUR/GBP"),
    "USDJPY": Spec("USDJPY", 0.01, 100000.0, "pips", "USD/JPY"),
    "CADJPY": Spec("CADJPY", 0.01, 100000.0, "pips", "CAD/JPY"),
}


def normalise(symbol: str) -> str:
    """'MGC1!' -> 'MGC', 'GCZ2026' -> 'GC'. Chart and broker symbols carry
    continuation and expiry suffixes that the registry does not."""
    s = (symbol or "").upper().strip()
    s = s.split(":")[-1]            # strip an exchange prefix like COMEX:GC1!
    s = s.rstrip("!")
    s = s.rstrip("0123456789")      # strip an expiry code's year digits

    if s in SPECS:
        return s

    # Fall back to the longest registry key the symbol starts with, so an
    # unexpected suffix degrades to the right contract instead of to nothing.
    for key in sorted(SPECS, key=len, reverse=True):
        if s.startswith(key):
            return key
    return s


def spec_for(symbol: str) -> Spec | None:
    return SPECS.get(normalise(symbol))


def to_units(amount_usd: float, symbol: str, qty: float = 1.0) -> float | None:
    """Convert a currency amount on `symbol` into that market's own unit.

    Returns None for an unknown symbol rather than a plausible-looking number —
    a wrong tick count is worse than a missing one, because it is invisible.
    """
    spec = spec_for(symbol)
    if spec is None or not qty:
        return None
    per_unit = spec.per_tick * abs(qty)
    if per_unit == 0:
        return None
    return amount_usd / per_unit


def price_to_units(price_delta: float, symbol: str) -> float | None:
    """Convert a price difference (e.g. slippage) into ticks or pips."""
    spec = spec_for(symbol)
    if spec is None or spec.tick == 0:
        return None
    return price_delta / spec.tick


def unit_name(symbol: str) -> str:
    spec = spec_for(symbol)
    return spec.unit if spec else "units"


def label_for(symbol: str) -> str:
    spec = spec_for(symbol)
    return spec.label or normalise(symbol)


def group_key(symbol: str) -> str:
    """Micros roll up into their parent market for reporting: MGC and GC are
    the same trade idea at different size, and splitting them would fragment
    the per-market view for no analytical gain."""
    key = normalise(symbol)
    return MICRO_PARENT.get(key, key)
