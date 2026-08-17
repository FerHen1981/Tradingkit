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
    # CME micros — SAME price series as the mini (distilled from mini data), 1/10 the
    # multiplier. Identical at the tick/PF level; different vs the fixed Apex $ rules.
    "MNQ": Contract("MNQ", 0.25, 2.0, 0.37),   # micro Nasdaq
    "MES": Contract("MES", 0.25, 5.0, 0.37),   # micro S&P
    "MYM": Contract("MYM", 1.0, 0.5, 0.37),    # micro Dow
    "M2K": Contract("M2K", 0.10, 5.0, 0.37),   # micro Russell
    "MGC": Contract("MGC", 0.10, 10.0, 0.52),  # micro gold, $1/tick
    # metals / energy
    "GC": Contract("GC", 0.10, 100.0, 1.75),   # gold, $10/tick
    "SI": Contract("SI", 0.005, 5000.0, 1.75), # silver, 5000oz, $25/tick
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
    # Spot FX (MT4/5/FTMO): qty in LOTS, 1 lot = 100k units, pointvalue = 100000
    # (USD-quote pairs give USD P&L directly; JPY-quote P&L is approximate — the
    # true pip value needs the live quote-currency rate). commission ~$3.5/lot/side.
    "EURUSD": Contract("EURUSD", 0.00001, 100000.0, 3.5),
    "GBPUSD": Contract("GBPUSD", 0.00001, 100000.0, 3.5),
    "AUDUSD": Contract("AUDUSD", 0.00001, 100000.0, 3.5),
    "EURGBP": Contract("EURGBP", 0.00001, 100000.0, 3.5),
    "USDJPY": Contract("USDJPY", 0.001, 100000.0, 3.5),   # JPY-quote: P&L approximate
    "CADJPY": Contract("CADJPY", 0.001, 100000.0, 3.5),   # JPY-quote: P&L approximate
}


def contract(symbol: str) -> Contract:
    key = symbol.upper()
    if key not in CONTRACTS:
        raise KeyError(f"unknown symbol {symbol!r}; known: {sorted(CONTRACTS)}")
    return CONTRACTS[key]


# mini -> its micro twin (same price series, 1/10 multiplier). Used by --micro to
# test a strategy on the micro contract in parallel (matters at the eval/funded lens).
MICRO_TWIN = {"NQ": "MNQ", "ES": "MES", "YM": "MYM", "RTY": "M2K", "GC": "MGC"}


def micro_twin(symbol: str) -> str | None:
    return MICRO_TWIN.get(symbol.upper())


# Canonical timeframe vocabulary: label -> minutes. The engines aggregate the
# 1-minute source up to any of these (session-aligned to the 18:00 ET open).
# 1d = one trade-date bar (elapsed//1440 folds a whole session into one bucket).
TIMEFRAMES = {
    "1m": 1, "5m": 5, "10m": 10, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "3h": 180, "4h": 240, "1d": 1440,
}


def tf_minutes(label: str) -> int:
    key = str(label).strip().lower()
    if key not in TIMEFRAMES:
        raise KeyError(f"unknown timeframe {label!r}; known: {list(TIMEFRAMES)}")
    return TIMEFRAMES[key]


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

    # --- position sizing ---
    # "fixed"     : fixed contract_size (the Pine default)
    # "target_dd" : target-driven — risk a fraction of the remaining trailing-DD
    #               room per trade, so size scales with how much runway is left
    #               (big early / when far from the floor, small near breach).
    #  "fixed"     : fixed contract_size (futures default)
    #  "target_dd" : risk a fraction of remaining trailing-DD room
    #  "pct_risk"  : risk pct_risk_per_trade % of account balance per trade
    #                (the forex/FTMO primitive — lots computed from the stop)
    sizing_mode: str = "fixed"           # "fixed" | "target_dd" | "pct_risk"
    target_risk_frac: float = 0.5        # fraction of DD room risked per trade (target_dd)
    pct_risk_per_trade: float = 0.5      # % of balance risked per trade (pct_risk)
    fractional_qty: bool = False         # True for forex lots (0.01), False for whole contracts
    contract_size: float = 2.0
    max_qty: float = 100.0
    min_qty: float = 1.0

    # --- entry generators (Level B; FVG is the default entry) ---
    # Each flag adds one pluggable entry generator; all default OFF so any preset
    # without a spec (El Toro etc.) is byte-identical. Generators stack in the
    # engine's priority order; the CVD/VWAP filters + stop/TP/sizing are shared.
    use_fvg_entry: bool = True           # FVG imbalance entry (El Toro's core)
    use_ema_cross: bool = False          # EMA fast/slow crossover entry
    ema_fast: int = 20
    ema_slow: int = 50
    use_bos_entry: bool = False          # break-of-structure (swing break) momentum entry
    # --- price-action / order-flow entries ---
    use_choch_entry: bool = False        # change-of-character (first counter-break) reversal
    use_liq_sweep: bool = False          # liquidity sweep of a swing + reclaim (reversal)
    use_cvd_div: bool = False            # price/CVD divergence at pivots (reversal)
    cvd_div_pivot_k: int = 5
    use_order_block: bool = False        # order-block mitigation (continuation)
    ob_impulse_atr: float = 1.0          # impulse body >= x*ATR marks the OB
    ob_max_age: int = 50                 # OB expires after N bars unmitigated
    ob_mit_pct: float = 0.5              # how far into the OB zone counts as mitigation
    use_momentum: bool = False           # displacement/impulse bar entry (momentum)
    momentum_body_atr: float = 1.0       # entry when |close-open| >= x*ATR in-trend
    # --- classic (analyst) entries ---
    use_macd_cross: bool = False         # MACD line crosses its signal
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    use_rsi_rev: bool = False            # RSI exits oversold/overbought (mean reversion)
    rsi_length: int = 14
    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    use_donchian: bool = False           # close breaks the prior-N high/low channel
    donchian_len: int = 20
    use_ma_pullback: bool = False        # trend pullback-and-resume to a moving average
    ma_fast: int = 50
    ma_slow: int = 200
    ma_type: str = "EMA"                 # "EMA" | "SMA"
    use_bb_revert: bool = False          # Bollinger-band extreme reversion
    bb_len: int = 20
    bb_mult: float = 2.0

    # --- confluence layer (Level C): require several mechanisms for ONE entry ---
    # When on, the roster's OR-of-generators is replaced by a single PRIMARY
    # trigger that only fires when every required condition also holds (AND +
    # a light sequence: a required event must have fired within confl_lookback
    # bars, same direction). This is what turns single triggers into real
    # confluence strategies (e.g. the ICT Silver Bullet).
    use_confluence: bool = False
    confl_primary: str = "fvg"           # generator that produces the entry price/dir
    confl_require: tuple = ()            # ("liq_sweep","cvd_div","bos","bias_vwap")
    confl_lookback: int = 18             # bars within which a required event must have fired

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

    # --- regime (L1 classifier: MA-stack + ADX + ATR percentile) ---
    # Objective trend x volatility regime tag. See lab/FRAMEWORK.md §1/§6. The
    # tag is the framework's gatekeeper (which setup-class a regime allows); it
    # is computed and surfaced per run, and consumed by the sampler (step 4).
    regime_ma_fast: int = 20             # fast EMA of the trend stack
    regime_ma_mid: int = 50              # mid EMA
    regime_ma_slow: int = 200            # slow EMA (the trend spine)
    adx_len: int = 14                    # Wilder ADX length
    adx_trend: float = 25.0              # ADX >= this = a real trend (else controlled/flat)
    regime_atr_lookback: int = 100       # window for the ATR volatility percentile
    regime_slope_lookback: int = 20      # bars for slow-MA slope + ATR direction
    # Optional regime GATE: when non-empty, entries fire ONLY when the causal
    # per-bar regime tag is in this set (finetune "trade the right conditions").
    # Empty = trade every regime (no gate, zero cost). See lab/FRAMEWORK.md §8a.
    regime_filter: frozenset = frozenset()

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

    # --- account phase ---
    # Apex-style trailing: phase Apex Eval/PA + dd_model Intraday/EOD.
    # FTMO-style static:   phase FTMO Challenge/Funded + dd_model Static.
    phase: str = "Research"              # Research | Apex Eval | Apex PA | FTMO Challenge | FTMO Funded
    dd_model: str = "Intraday"           # "Intraday" | "EOD" | "Static"
    acct_trail_dd: float = 2000.0        # trailing DD ($) — or, for Static, the fixed max overall loss ($)
    acct_goal: float = 3000.0            # Eval/Challenge profit target ($)
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
    def is_static(self) -> bool:
        return self.dd_model == "Static"

    @property
    def is_ftmo(self) -> bool:
        return self.phase in ("FTMO Challenge", "FTMO Funded")

    @property
    def phase_on(self) -> bool:
        return self.phase in ("Apex Eval", "Apex PA", "FTMO Challenge", "FTMO Funded")

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

# EOD-drawdown siblings (same engine, ddModel="EOD"): the trailing DD ratchets
# only on the daily *closing* balance, not the intraday unrealised peak — much
# gentler on giving back open profit.
EL_MATADOR = EL_TORO.with_(name="EL_MATADOR", dd_model="EOD")     # Eval, EOD
EL_PATRON = EL_DORADO.with_(name="EL_PATRON", dd_model="EOD")     # Funded/PA, EOD

# Walk-forward-validated El Toro tweak (see docs/optimization.md): restrict
# entries to the US regular session (09:00-15:59 ET). Pass-rate 29.8->32.7% IS
# and 27.7->38.3% OOS. Optionally loosen delta streak to 2 (OOS 46.8%, more
# regime-dependent). Recovery-trail left ON (adds ~4pp; fix A1 for live use).
EL_TORO_TUNED = EL_TORO.with_(
    name="EL_TORO_TUNED",
    enabled_hours=frozenset(range(9, 16)),
)

# Best funder found: EOD drawdown model + RTH hours. Walk-forward: EOD lifts the
# baseline (OOS 31.9% vs Toro 27.7%) and RTH lifts it further (~41% IS). Keep both
# DD models available — some accounts are Intraday, not EOD.
EL_MATADOR_TUNED = EL_MATADOR.with_(
    name="EL_MATADOR_TUNED",
    enabled_hours=frozenset(range(9, 16)),
)

# Management preset for CONFLUENCE reversals (Silver Bullet et al.): the entry
# edge is a high hit-rate, so the job of management is to LET WINNERS RUN to a
# clean R target, not protect a funded account. So: limit entry + swing stop
# (inherited), but break-even and trailing OFF (they scratch/cap the winners —
# see the SB batch: 351 BE-scratches, only 58 real TPs) and an R-multiple 2.0
# target. Research-lens tuning; account phase is irrelevant under --research.
EL_SILVER = EL_DORADO.with_(
    name="EL_SILVER",
    tp_mode="R-multiple",
    r_multiple=2.0,
    use_breakeven=False,
    use_trail=False,
    use_recov_trail=False,
    confirm_bars=0,
)

PRESETS = {
    "EL_TORO": EL_TORO,
    "EL_SILVER": EL_SILVER,
    "EL_TORO_TUNED": EL_TORO_TUNED,
    "EL_MATADOR": EL_MATADOR,
    "EL_MATADOR_TUNED": EL_MATADOR_TUNED,
    "EL_DORADO": EL_DORADO,
    "EL_DORADO_TUNED": EL_DORADO_TUNED,
    "EL_PATRON": EL_PATRON,
}
