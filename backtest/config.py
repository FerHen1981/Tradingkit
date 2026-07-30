"""Strategy configuration and the two presets that reproduce the Pine defaults.

All distance inputs in the Pine scripts use ``unitMode = "Ticks"`` by default, so
every ``*_ticks`` field below is a number of ticks that the engine converts to a
price distance via ``ticks * mintick``.

Contract specs are NQ (E-mini Nasdaq-100 futures): tick = 0.25 index points,
point value = $20, so one tick = $5.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Contract:
    symbol: str = "NQ"
    mintick: float = 0.25          # price increment per tick
    pointvalue: float = 20.0       # $ per 1.0 price move  -> $5 per tick
    commission_per_contract: float = 1.55   # cash per contract, per side
    slippage_ticks: float = 1.0    # adverse ticks on market/stop fills

    @property
    def tickvalue(self) -> float:
        return self.mintick * self.pointvalue


# Contract registry. pointvalue = $ per 1.0 move; tickvalue = mintick*pointvalue.
# Commissions are round-trip-per-side estimates; adjust to your broker.
# FX-futures specs are approximate — verify per exchange before trusting P&L.
CONTRACTS = {
    # CME equity index
    "NQ": Contract("NQ", 0.25, 20.0, 1.55),
    "ES": Contract("ES", 0.25, 50.0, 1.55),
    "YM": Contract("YM", 1.0, 5.0, 1.55),
    "RTY": Contract("RTY", 0.10, 50.0, 1.55),
    # metals / energy
    "GC": Contract("GC", 0.10, 100.0, 1.75),   # gold, $10/tick
    "CL": Contract("CL", 0.01, 1000.0, 1.75),  # crude, $10/tick
    # crypto (CME BTC future = 5 BTC; VERIFY — may be MBT micro in your data)
    "BTC": Contract("BTC", 5.0, 5.0, 5.0),     # $25/tick
    # CME FX futures (approximate; verify multipliers)
    "6E": Contract("6E", 0.00005, 125000.0, 1.75),  # EUR, $6.25/tick
    "6B": Contract("6B", 0.0001, 62500.0, 1.75),    # GBP, $6.25/tick
    "6J": Contract("6J", 0.0000005, 12500000.0, 1.75),  # JPY, $6.25/tick
    "6A": Contract("6A", 0.0001, 100000.0, 1.75),   # AUD, $10/tick
    "6S": Contract("6S", 0.0001, 125000.0, 1.75),   # CHF, $12.50/tick
    "6C": Contract("6C", 0.00005, 100000.0, 1.75),  # CAD, $5/tick
}


def contract(symbol: str) -> Contract:
    key = symbol.upper()
    if key not in CONTRACTS:
        raise KeyError(f"unknown symbol {symbol!r}; known: {sorted(CONTRACTS)}")
    return CONTRACTS[key]


@dataclass(frozen=True)
class Config:
    name: str
    contract: Contract = field(default_factory=Contract)

    # --- account / capital ---
    initial_capital: float = 50_000.0

    # --- distance unit for all *_ticks inputs ---
    # "Ticks" (default) keeps the Pine behaviour; "ATR" makes the tick-unit
    # inputs scale with volatility so one config ports across instruments.
    unit_mode: str = "Ticks"             # "Ticks" | "Points" | "%" | "ATR"
    atr_len: int = 14

    # --- position sizing (Fixed contracts) ---
    contract_size: float = 2.0
    max_qty: float = 100.0

    # --- entry & stop ---
    entry_limit_mode: bool = True        # "Limit @ 50% FVG" vs market
    expiry_bars: int = 12                # resting limit lifetime
    stop_swing: bool = True              # "Swing structure" vs fixed
    pivot_k: int = 3
    swing_buf_ticks: float = 2.0
    max_stop_ticks: float = 72.0         # skip signal if stop wider
    fixed_stop_ticks: float = 28.0       # legacy fixed-stop mode

    # --- take-profit / trade management ---
    tp_mode: str = "R-multiple"          # "R-multiple" | "Swing structure" | "Fixed (units)"
    r_multiple: float = 2.5
    tp_fixed_ticks: float = 122.0
    use_breakeven: bool = True
    be_trigger_ticks: float = 20.0
    be_offset_ticks: float = 8.0
    use_trail: bool = True
    trail_start_ticks: float = 48.0
    trail_buffer_ticks: float = 24.0
    use_recov_trail: bool = False        # Eval only, trade #2 after a first-trade loss
    recov_trail_start_ticks: float = 40.0
    recov_trail_buf_ticks: float = 16.0
    use_fill_check: bool = True          # FVG invalid once its mid is touched

    # --- filters ---
    use_gap_filter: bool = True
    gap_min_ticks: float = 9.0
    gap_max_ticks: float = 12.0
    confirm_bars: int = 0                # FVG confirmation memory window
    use_vwap_veto: bool = True           # long above / short below session VWAP
    use_cvd_filter: bool = True          # per-bar volume delta direction
    use_cvd_streak: bool = True
    cvd_trend_count: int = 4             # consecutive same-side delta bars

    # --- time gate ---
    trade_days: tuple = (0, 1, 2, 3, 4)  # Mon..Fri (ET weekday, 0=Mon)
    enabled_hours: frozenset = frozenset(set(range(24)) - {17})  # ET hours; 17 = daily break
    skip_monday_early: bool = True       # no entries Mon 00:00-02:00 ET
    use_auto_flat: bool = True
    flat_from: tuple = (16, 55)          # (hour, minute) ET
    flat_until: tuple = (18, 0)

    # --- daily risk ---
    day_exit_mode: str = "Off"           # "Off" | "Day-trail (keep peak)" | "Day-cap (hard target)" | "Trail + cap"
    day_trail_usd: float = 75.0
    day_cap_usd: float = 300.0

    # --- account phase (Apex) ---
    phase: str = "Research"              # "Research" | "Apex Eval" | "Apex PA"
    dd_model: str = "Intraday"           # "Intraday" | "EOD"
    acct_trail_dd: float = 2000.0
    acct_goal: float = 3000.0            # Eval profit target
    acct_dll: float = 1000.0             # PA daily loss limit
    consistency_pct: float = 50.0
    min_payout: float = 500.0
    min_qual_day_usd: float = 50.0
    payout_buffer: float = 500.0
    use_wait_for_cap: bool = True
    # MAE guard (Apex Legacy 30% rule), PA only
    use_mae_guard: bool = False
    mae_base_pct: float = 30.0
    mae_grown_pct: float = 50.0
    mae_margin_pct: float = 10.0

    # ---- helpers -------------------------------------------------------------
    @property
    def is_eval(self) -> bool:
        return self.phase == "Apex Eval"

    @property
    def is_pa(self) -> bool:
        return self.phase == "Apex PA"

    @property
    def phase_on(self) -> bool:
        return self.is_eval or self.is_pa

    def ticks(self, n: float) -> float:
        """Convert a tick-unit input to a price distance."""
        return n * self.contract.mintick

    def with_(self, **kw) -> "Config":
        return replace(self, **kw)


# Ladder caps per payout number (1..6) for the Apex 50k plan.
LADDER_CAPS = {1: 1500.0, 2: 1500.0, 3: 2000.0, 4: 2500.0, 5: 2500.0, 6: 3000.0}


def ladder_cap(n: int) -> float:
    return LADDER_CAPS.get(min(max(n, 1), 6), 3000.0)


# ---------------------------------------------------------------------------
# Presets matching the two Pine scripts' default inputs.
# ---------------------------------------------------------------------------
EL_TORO = Config(
    name="EL_TORO",
    contract_size=5.0,
    tp_mode="Fixed (units)",
    tp_fixed_ticks=122.0,
    r_multiple=2.5,
    use_breakeven=False,
    use_trail=False,
    use_recov_trail=True,
    confirm_bars=2,
    gap_min_ticks=9.0,
    gap_max_ticks=15.0,
    day_exit_mode="Off",
    phase="Apex Eval",
    dd_model="Intraday",
    acct_trail_dd=2500.0,
    acct_goal=3000.0,
    use_wait_for_cap=False,
    use_mae_guard=False,
)

EL_DORADO = Config(
    name="EL_DORADO",
    contract_size=2.0,
    tp_mode="R-multiple",
    r_multiple=2.5,
    tp_fixed_ticks=122.0,
    use_breakeven=True,
    be_trigger_ticks=20.0,
    be_offset_ticks=8.0,
    use_trail=True,
    trail_start_ticks=48.0,
    trail_buffer_ticks=24.0,
    use_recov_trail=False,
    confirm_bars=0,
    gap_min_ticks=9.0,
    gap_max_ticks=12.0,
    day_exit_mode="Day-trail (keep peak)",
    day_trail_usd=75.0,
    phase="Apex PA",
    dd_model="Intraday",
    acct_trail_dd=2000.0,
    acct_dll=1000.0,
    consistency_pct=50.0,
    min_payout=500.0,
    payout_buffer=500.0,
    use_wait_for_cap=True,
    use_mae_guard=True,
)

# Walk-forward-validated money-management tweak (see docs/optimization.md).
# The single robust change: loosen the day-profit trail from $75 to $300 so the
# account can actually build to payout eligibility instead of being chopped daily.
# Held up out-of-sample (2025-06..2026-06: PF 1.05, +$1.9k, $643 banked/breach).
# The aggressive "let it all run" combos were rejected as in-sample overfit.
EL_DORADO_TUNED = EL_DORADO.with_(
    name="EL_DORADO_TUNED",
    day_exit_mode="Day-trail (keep peak)",
    day_trail_usd=300.0,
)

# Walk-forward-validated El Toro tweak (see docs/optimization.md): restrict
# entries to the US regular session (09:00-15:59 ET). Pass-rate 29.8->32.7% IS
# and 27.7->38.3% OOS. Optionally loosen delta streak to 2 (OOS 46.8%, more
# regime-dependent). Recovery-trail left ON (adds ~4pp; fix A1 for live use).
EL_TORO_TUNED = EL_TORO.with_(
    name="EL_TORO_TUNED",
    enabled_hours=frozenset(range(9, 16)),
)

PRESETS = {
    "EL_TORO": EL_TORO,
    "EL_TORO_TUNED": EL_TORO_TUNED,
    "EL_DORADO": EL_DORADO,
    "EL_DORADO_TUNED": EL_DORADO_TUNED,
}
