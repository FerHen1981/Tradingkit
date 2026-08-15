"""Aggregation, and the role boundary.

The security property this module exists to guarantee:

    A `viewer` response contains no currency field. Not hidden, not zeroed —
    absent.

That is enforced structurally. Each role has its own builder function that
constructs its payload from scratch. Nothing filters a "full" dict down, because
a filter silently leaks every field somebody adds later and forgets to list.
`tests/test_roles.py` walks the serialised viewer and public payloads and fails
on any key or value that looks monetary.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from . import units

Role = Literal["owner", "partner", "viewer", "public"]

#: Roles allowed to see currency. Everything else gets units only.
MONEY_ROLES: frozenset[str] = frozenset({"owner", "partner"})


@dataclass
class MarketAgg:
    symbol: str
    label: str
    unit: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    net_units: float = 0.0
    r_total: float = 0.0
    gross_win_r: float = 0.0
    gross_loss_r: float = 0.0
    slippage_ticks: list[float] = field(default_factory=list)
    hold_s: list[float] = field(default_factory=list)
    net_usd: float = 0.0

    @property
    def win_rate(self) -> float | None:
        decided = self.wins + self.losses
        return round(100.0 * self.wins / decided, 1) if decided else None

    @property
    def profit_factor(self) -> float | None:
        if self.gross_loss_r <= 0:
            return None
        return round(self.gross_win_r / self.gross_loss_r, 2)

    @property
    def avg_slippage(self) -> float | None:
        vals = [v for v in self.slippage_ticks if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    @property
    def avg_hold_min(self) -> float | None:
        vals = [v for v in self.hold_s if v]
        return round(sum(vals) / len(vals) / 60.0, 1) if vals else None


@dataclass
class Fleet:
    """Everything derived from the journal, before any role is applied."""

    markets: dict[str, MarketAgg] = field(default_factory=dict)
    equity: list[tuple[str, float]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    first_ts: float = 0.0
    last_ts: float = 0.0
    generated_at: float = field(default_factory=time.time)

    # ---- fleet-level rollups ----

    @property
    def trades(self) -> int:
        return sum(m.trades for m in self.markets.values())

    @property
    def wins(self) -> int:
        return sum(m.wins for m in self.markets.values())

    @property
    def losses(self) -> int:
        return sum(m.losses for m in self.markets.values())

    @property
    def win_rate(self) -> float | None:
        decided = self.wins + self.losses
        return round(100.0 * self.wins / decided, 1) if decided else None

    @property
    def r_total(self) -> float | None:
        if not self.markets:
            return None
        return round(sum(m.r_total for m in self.markets.values()), 1)

    @property
    def expectancy_r(self) -> float | None:
        total = self.trades
        if not total:
            return None
        return round(sum(m.r_total for m in self.markets.values()) / total, 3)

    @property
    def profit_factor(self) -> float | None:
        gross_win = sum(m.gross_win_r for m in self.markets.values())
        gross_loss = sum(m.gross_loss_r for m in self.markets.values())
        if gross_loss <= 0:
            return None
        return round(gross_win / gross_loss, 2)

    @property
    def avg_slippage_ticks(self) -> float | None:
        vals = [v for m in self.markets.values() for v in m.slippage_ticks if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    @property
    def months_live(self) -> int | None:
        if not self.first_ts or not self.last_ts:
            return None
        return max(1, int((self.last_ts - self.first_ts) / (30.44 * 86400)))

    @property
    def net_usd(self) -> float:
        return round(sum(m.net_usd for m in self.markets.values()), 2)


def _month(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


def build(trades: Iterable[dict[str, Any]], accounts: list[dict[str, Any]] | None = None) -> Fleet:
    """Aggregate reconciled trades into a Fleet."""
    fleet = Fleet(accounts=accounts or [])
    monthly_r: dict[str, float] = defaultdict(float)

    for row in trades:
        symbol = row.get("symbol") or ""
        key = units.group_key(symbol)
        if not key:
            continue

        market = fleet.markets.get(key)
        if market is None:
            market = MarketAgg(symbol=key, label=units.label_for(key), unit=units.unit_name(key))
            fleet.markets[key] = market

        ts = float(row.get("ts") or 0.0)
        if ts:
            fleet.first_ts = ts if not fleet.first_ts else min(fleet.first_ts, ts)
            fleet.last_ts = max(fleet.last_ts, ts)

        realized_usd = row.get("realized_usd")
        realized_r = row.get("realized_r")
        qty = row.get("fill_qty") or row.get("intended_qty") or 1.0

        market.trades += 1

        # Win/loss is decided on R when available and on currency otherwise;
        # a trade that closed exactly flat counts as neither.
        decider = realized_r if realized_r is not None else realized_usd
        if decider is not None:
            if decider > 0:
                market.wins += 1
            elif decider < 0:
                market.losses += 1

        if realized_r is not None:
            r = float(realized_r)
            market.r_total += r
            if r > 0:
                market.gross_win_r += r
            else:
                market.gross_loss_r += abs(r)
            if ts:
                monthly_r[_month(ts)] += r

        if realized_usd is not None:
            usd = float(realized_usd)
            market.net_usd += usd
            converted = units.to_units(usd, symbol, qty)
            if converted is not None:
                market.net_units += converted

        slip = row.get("slippage_ticks")
        if slip is not None:
            market.slippage_ticks.append(float(slip))

        hold = row.get("hold_s")
        if hold:
            market.hold_s.append(float(hold))

    # Cumulative R by month — the public curve.
    running = 0.0
    for month in sorted(monthly_r):
        running += monthly_r[month]
        fleet.equity.append((month, round(running, 2)))

    # Anchor the curve at zero so the first month reads as a change, not as a
    # starting level the reader has to guess at.
    if fleet.equity:
        first_month = fleet.equity[0][0]
        year, mon = (int(p) for p in first_month.split("-"))
        prev = f"{year - 1}-12" if mon == 1 else f"{year}-{mon - 1:02d}"
        fleet.equity.insert(0, (prev, 0.0))

    return fleet


# ---------------------------------------------------------------------------
# Role boundary — one builder per role, no shared dict, no filtering.
# ---------------------------------------------------------------------------


def _market_units(m: MarketAgg) -> dict[str, Any]:
    """Unit-only view of one market. Contains no currency by construction."""
    return {
        "symbol": m.symbol,
        "label": m.label,
        "unit": m.unit,
        "net_units": round(m.net_units, 0),
        "trades": m.trades,
        "win_rate": m.win_rate,
        "r_total": round(m.r_total, 1) if m.trades else None,
        "profit_factor": m.profit_factor,
        "slippage_ticks": m.avg_slippage,
        "avg_hold_min": m.avg_hold_min,
    }


def _headline_units(f: Fleet) -> dict[str, Any]:
    return {
        "trades": f.trades,
        "win_rate": f.win_rate,
        "profit_factor": f.profit_factor,
        "r_total": f.r_total,
        "expectancy_r": f.expectancy_r,
        "months_live": f.months_live,
        "avg_slippage_ticks": f.avg_slippage_ticks,
    }


def _equity(f: Fleet) -> list[dict[str, Any]]:
    return [{"t": month, "v": value} for month, value in f.equity]


def for_viewer(f: Fleet) -> dict[str, Any]:
    """Units only. This payload must never gain a currency field."""
    return {
        "role": "viewer",
        "generated_at": f.generated_at,
        "unit_mode": True,
        "headline": _headline_units(f),
        "markets": [_market_units(m) for m in _sorted(f)],
        "equity": _equity(f),
        "equity_unit": "R",
        "accounts": [
            # Even here accounts are reduced to a count per phase: an account
            # list with identifiers is exactly what the prop-firm agreements
            # restrict, and a viewer has no use for it.
            {"phase": phase, "count": count}
            for phase, count in _phase_counts(f).items()
        ],
    }


def for_public(f: Fleet, delay: str = "T+1") -> dict[str, Any]:
    """What ships to the static sites. Viewer payload minus the account shape,
    plus the provenance a public reader needs to judge it."""
    return {
        "generated_at": datetime.fromtimestamp(f.generated_at, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "period": {
            "from": _month(f.first_ts) if f.first_ts else None,
            "to": _month(f.last_ts) if f.last_ts else None,
        },
        "delay": delay,
        "headline": _headline_units(f),
        "markets": [_market_units(m) for m in _sorted(f)],
        "equity_unit": "R",
        "equity": _equity(f),
    }


def for_owner(f: Fleet) -> dict[str, Any]:
    """Full fidelity, currency included. Never served to any other role."""
    return {
        "role": "owner",
        "generated_at": f.generated_at,
        "unit_mode": False,
        "headline": {**_headline_units(f), "net_usd": f.net_usd},
        "markets": [
            {**_market_units(m), "net_usd": round(m.net_usd, 2)} for m in _sorted(f)
        ],
        "equity": _equity(f),
        "equity_unit": "R",
        "accounts": f.accounts,
    }


def for_partner(f: Fleet) -> dict[str, Any]:
    """Same figures as the owner, without the operational controls the owner
    view exposes elsewhere. Currency is included by design."""
    return {**for_owner(f), "role": "partner"}


_BUILDERS = {
    "owner": for_owner,
    "partner": for_partner,
    "viewer": for_viewer,
}


def serialise(f: Fleet, role: Role) -> dict[str, Any]:
    """Dispatch to the builder for `role`, defaulting to the most restrictive.

    An unknown role gets the viewer payload rather than an error, so a typo in
    a user record can never widen access.
    """
    return _BUILDERS.get(role, for_viewer)(f)


def _sorted(f: Fleet) -> list[MarketAgg]:
    """Markets by absolute contribution — the biggest driver first."""
    return sorted(f.markets.values(), key=lambda m: -abs(m.r_total or m.trades))


def _phase_counts(f: Fleet) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for account in f.accounts:
        name = str(account.get("account", ""))
        phase = "funded" if name.upper().startswith("PA") else "evaluatie"
        counts[phase] += 1
    return dict(counts)
