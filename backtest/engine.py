"""Bar-by-bar execution engine.

Reproduces the MEX ΞL TORO / ΞL DORΛDO order and position logic plus the Apex
account overlay. See README.md for the intrabar fill model and parity caveats.

Modelling choices (documented, not bit-exact to TradingView):
  * Limit entries rest from the bar AFTER placement; fill at the limit price
    (no entry slippage) when the bar trades through it.
  * The stop/target bracket set at the close of bar t is evaluated on bar t+1.
  * When a bar's range spans both stop and target, the STOP is assumed first
    (pessimistic).
  * Stop and market (auto-flat / halt / cap-lock) exits pay 1 tick of adverse
    slippage; target (limit) exits pay none.
  * Exits are checked from the bar after the fill (no same-bar stop-out).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .config import Config, ladder_cap


@dataclass
class Trade:
    dir: int            # +1 long, -1 short
    qty: float
    entry_bar: int
    entry_time: pd.Timestamp
    entry_px: float
    exit_bar: int = -1
    exit_time: Optional[pd.Timestamp] = None
    exit_px: float = np.nan
    reason: str = ""
    gross: float = 0.0
    commission: float = 0.0
    net: float = 0.0
    mfe_ticks: float = 0.0
    mae_ticks: float = 0.0


@dataclass
class Result:
    cfg_name: str
    trades: list = field(default_factory=list)
    # account overlay outcomes
    net_profit: float = 0.0
    eval_passed: bool = False
    eval_breached: bool = False
    eval_pass_bar: int = -1
    halt_bar: int = -1               # bar the account overlay stopped on (-1 = ran to the end)
    pa_total_banked: float = 0.0
    pa_breach_count: int = 0
    pa_milk_count: int = 0
    pa_payouts_this_cycle: int = 0
    pa_payout_total: int = 0         # every payout ever banked; the cycle counter resets on breach
    bars: int = 0
    first_time: Optional[pd.Timestamp] = None
    last_time: Optional[pd.Timestamp] = None


def extract(df: pd.DataFrame, ind: pd.DataFrame) -> dict:
    """Pull the numpy arrays the engine needs, once, so repeated runs (the eval
    funnel) don't re-extract full-length columns per construction."""
    return {
        "open": df["Open"].to_numpy(float),
        "high": df["High"].to_numpy(float),
        "low": df["Low"].to_numpy(float),
        "close": df["Close"].to_numpy(float),
        "time": df["et"].to_numpy(),
        "mod": df["mod"].to_numpy(),
        "weekday": df["weekday"].to_numpy(),
        "new_session": df["new_session"].to_numpy(bool),
        "fvg_dir": ind["fvg_dir"].to_numpy(),
        "fvg_top": ind["fvg_top"].to_numpy(),
        "fvg_bot": ind["fvg_bot"].to_numpy(),
        "fvg_mid": ind["fvg_mid"].to_numpy(),
        "fvg_pass": ind["fvg_pass"].to_numpy(bool),
        "piv_low": ind["piv_low"].to_numpy(),
        "piv_high": ind["piv_high"].to_numpy(),
        "atr": ind["atr"].to_numpy(),
        "bull_cvd": ind["bull_cvd"].to_numpy(bool),
        "bear_cvd": ind["bear_cvd"].to_numpy(bool),
        "veto_long": ind["veto_long"].to_numpy(bool),
        "veto_short": ind["veto_short"].to_numpy(bool),
    }


class Engine:
    def __init__(self, cfg: Config, df: pd.DataFrame = None, ind: pd.DataFrame = None,
                 research_mode: bool = False, start_bar: int = 0, arrays: dict = None):
        self.cfg = cfg
        self.research = research_mode
        self.c = cfg.contract
        self.start_bar = start_bar

        a = arrays if arrays is not None else extract(df, ind)
        self.open = a["open"]; self.high = a["high"]; self.low = a["low"]; self.close = a["close"]
        self.time = a["time"]; self.mod = a["mod"]; self.weekday = a["weekday"]
        self.new_session = a["new_session"]
        self.fvg_dir = a["fvg_dir"]; self.fvg_top = a["fvg_top"]; self.fvg_bot = a["fvg_bot"]
        self.fvg_mid = a["fvg_mid"]; self.fvg_pass = a["fvg_pass"]
        self.piv_low = a["piv_low"]; self.piv_high = a["piv_high"]; self.atr = a["atr"]
        self.bull_cvd = a["bull_cvd"]; self.bear_cvd = a["bear_cvd"]
        self.veto_long = a["veto_long"]; self.veto_short = a["veto_short"]

        self.n = len(self.close)
        self._reset_state()

    # ------------------------------------------------------------------ state
    def _reset_state(self):
        self.pos = 0.0
        self.entry_avg = np.nan
        self.entry_bar = -1
        self.cur_stop = np.nan
        self.cur_limit = np.nan
        self.pos_hi = np.nan
        self.pos_lo = np.nan
        self.risk_off = False
        self.trail_on = False
        self.recov_on = False

        self.pend_dir = 0
        self.pend_bar = -1
        self.pend_limit = np.nan
        self.pend_stop = np.nan
        self.pend_tp = np.nan
        self.pend_qty = 0.0

        self.net_profit = 0.0

        # day/session
        self.risk_base = None
        self.risk_day_peak = 0.0
        self.day_halted = False
        self.halt_reason = ""
        self.flattened_today = False
        self.halt_close_sent = False
        self.has_traded = False

        # account
        self.acct_hwm = np.nan
        self.profit_since = 0.0
        self.best_day_since = 0.0
        self.qual_days = 0
        self.pa_reset_pnl_prev = 0.0
        self.pa_payouts_this_cycle = 0
        self.pa_breach_count = 0
        self.pa_reset_count = 0
        self.pa_milk_count = 0
        self.pa_payout_total = 0
        self.pa_total_banked = 0.0
        self.acct_halted = False
        self.acct_halt_reason = ""
        self.dd_room = None          # remaining trailing-DD room ($), for target_dd sizing

        # recovery-trail attempt tracking
        self.attempt_trade_no = 0
        self.attempt_first_loss = False

        # FVG confirmation memory (only if confirm_bars>0)
        self.mem = []  # list of dicts: bar,dir,mid,top,bot

        self._cur_i = self.start_bar
        self.trades: list[Trade] = []

    # --------------------------------------------------------------- helpers
    def _dist(self, units: float) -> float:
        """Convert a strategy distance input to a price distance per unit_mode.
        Uses the bar currently being processed (self._cur_i) for %/ATR modes."""
        m = self.cfg.unit_mode
        if m == "Ticks":
            return units * self.c.mintick
        if m == "Points":
            return units
        i = self._cur_i
        if m == "%":
            return self.close[i] * units / 100.0
        return units * self.atr[i]   # ATR mode

    def _slip(self) -> float:
        """Slippage is always in ticks, independent of unit_mode."""
        return self.c.slippage_ticks * self.c.mintick

    def _open_profit(self, i: int) -> float:
        if self.pos == 0:
            return 0.0
        return (self.close[i] - self.entry_avg) * np.sign(self.pos) * abs(self.pos) * self.c.pointvalue

    def _calc_qty(self, stop_dist: float) -> float:
        cfg = self.cfg
        # target-driven: risk a fraction of the remaining trailing-DD room per
        # trade. Size grows with runway and shrinks to 0 near the floor (protect).
        if (cfg.sizing_mode == "target_dd" and not self.research and cfg.phase_on
                and self.dd_room is not None and stop_dist > 0):
            risk_usd = max(self.dd_room, 0.0) * cfg.target_risk_frac
            q = risk_usd / (stop_dist * self.c.pointvalue)
            return float(np.floor(min(q, cfg.max_qty)))   # <1 -> 0 -> trade skipped
        # % of account balance risked per trade (forex/FTMO primitive)
        if cfg.sizing_mode == "pct_risk" and stop_dist > 0:
            bal = cfg.initial_capital + self.net_profit
            risk_usd = bal * cfg.pct_risk_per_trade / 100.0
            q = min(risk_usd / (stop_dist * self.c.pointvalue), cfg.max_qty)
            return round(q, 2) if cfg.fractional_qty else float(np.floor(q))
        q = min(cfg.contract_size, cfg.max_qty)
        return float(np.floor(q))

    # ------------------------------------------------------------ time gate
    def _time_gate(self, i: int) -> bool:
        wd = self.weekday[i]
        if wd not in self.cfg.trade_days:
            return False
        if self.time_hour(i) not in self.cfg.enabled_hours:
            return False
        if self.cfg.skip_monday_early and wd == 0 and self.mod[i] < 120:
            return False
        return True

    def time_hour(self, i: int) -> int:
        return int(self.mod[i] // 60)

    def _in_flat_window(self, i: int) -> bool:
        if not self.cfg.use_auto_flat:
            return False
        s = self.cfg.flat_from[0] * 60 + self.cfg.flat_from[1]
        e = self.cfg.flat_until[0] * 60 + self.cfg.flat_until[1]
        cur = self.mod[i]
        return (cur >= s and cur < e) if e > s else (cur >= s or cur < e)

    # ------------------------------------------------------------------ run
    def run(self, end_bar: Optional[int] = None) -> Result:
        end = self.n if end_bar is None else min(end_bar, self.n)
        halt_bar = -1
        for i in range(self.start_bar, end):
            self._cur_i = i
            self._broker(i)
            self._strategy(i)
            if self.acct_halted and self.pos == 0 and self.pend_dir == 0:
                # Eval account is done; stop simulating further bars.
                halt_bar = i
                break
        # force-close any residual position at the last processed close
        if self.pos != 0:
            self._close_at(min(i, end - 1), self.close[min(i, end - 1)], "EOD", slippage=False)

        res = Result(cfg_name=self.cfg.name, trades=self.trades)
        res.net_profit = self.net_profit
        res.pa_total_banked = self.pa_total_banked
        res.pa_breach_count = self.pa_breach_count
        res.pa_milk_count = self.pa_milk_count
        res.pa_payouts_this_cycle = self.pa_payouts_this_cycle
        res.pa_payout_total = self.pa_payout_total
        res.eval_passed = self.acct_halt_reason.startswith("EVAL PASSED")
        res.eval_breached = self.acct_halt_reason.startswith("TRAILING")
        res.halt_bar = halt_bar
        res.eval_pass_bar = halt_bar if res.eval_passed else -1
        res.bars = end - self.start_bar
        res.first_time = pd.Timestamp(self.time[self.start_bar])
        res.last_time = pd.Timestamp(self.time[min(end - 1, self.n - 1)])
        return res

    # --------------------------------------------------------------- broker
    def _broker(self, i: int):
        """Fills that use orders resting from prior bars."""
        # 1) resting limit entry
        if self.pos == 0 and self.pend_dir != 0 and self.cfg.entry_limit_mode:
            if i > self.pend_bar:  # earliest fill is the bar after placement
                if self.pend_dir == 1 and self.low[i] <= self.pend_limit:
                    self._fill_entry(i, self.pend_limit)
                elif self.pend_dir == -1 and self.high[i] >= self.pend_limit:
                    self._fill_entry(i, self.pend_limit)
        # 2) bracket exit for an open position (bracket set on a prior bar)
        if self.pos != 0 and i > self.entry_bar:
            self._check_bracket(i)

    def _fill_entry(self, i: int, px: float):
        self.pos = self.pend_dir * self.pend_qty
        self.entry_avg = px
        self.entry_bar = i
        self.cur_stop = self.pend_stop
        risk = abs(px - self.pend_stop)
        if self.cfg.tp_mode == "Swing structure":
            self.cur_limit = self.pend_tp
        elif self.cfg.tp_mode == "R-multiple":
            self.cur_limit = px + np.sign(self.pos) * self.cfg.r_multiple * risk
        else:  # Fixed (units)
            self.cur_limit = px + np.sign(self.pos) * self._dist(self.cfg.tp_fixed_ticks)
        # init excursions (Pine newLong/newShort semantics)
        if self.pos > 0:
            self.pos_hi = max(px, self.close[i])
            self.pos_lo = self.low[i]
        else:
            self.pos_hi = self.high[i]
            self.pos_lo = min(px, self.close[i])
        self.risk_off = False
        self.trail_on = False
        self.recov_on = False
        self.has_traded = True
        self.pend_dir = 0
        self.pend_limit = np.nan
        self.pend_stop = np.nan
        # allow BE/trail to move the stop already on the fill bar (Pine does)
        self._manage_position(i)

    def _check_bracket(self, i: int):
        slip = self._slip()
        if self.pos > 0:
            hit_stop = self.low[i] <= self.cur_stop
            hit_tp = (not np.isnan(self.cur_limit)) and self.high[i] >= self.cur_limit
            if hit_stop:  # stop-first pessimistic
                self._close_at(i, self.cur_stop - slip, self._exit_reason(), slippage=False)
            elif hit_tp:
                self._close_at(i, self.cur_limit, "TP", slippage=False)
            else:
                self._manage_position(i)
        else:
            hit_stop = self.high[i] >= self.cur_stop
            hit_tp = (not np.isnan(self.cur_limit)) and self.low[i] <= self.cur_limit
            if hit_stop:
                self._close_at(i, self.cur_stop + slip, self._exit_reason(), slippage=False)
            elif hit_tp:
                self._close_at(i, self.cur_limit, "TP", slippage=False)
            else:
                self._manage_position(i)

    def _exit_reason(self) -> str:
        return "RECOV-TRAIL" if self.recov_on else "TRAIL" if self.trail_on else "BE-STOP" if self.risk_off else "SL"

    # ----------------------------------------------------------- close trade
    def _close_at(self, i: int, px: float, reason: str, slippage: bool = True):
        if self.pos == 0:
            return
        d = int(np.sign(self.pos))
        qty = abs(self.pos)
        if slippage:
            px = px - d * self._slip()
        gross = (px - self.entry_avg) * d * qty * self.c.pointvalue
        comm = 2 * self.c.commission_per_contract * qty
        net = gross - comm
        self.net_profit += net
        mfe = (self.pos_hi - self.entry_avg) if d == 1 else (self.entry_avg - self.pos_lo)
        mae = (self.entry_avg - self.pos_lo) if d == 1 else (self.pos_hi - self.entry_avg)
        tr = Trade(dir=d, qty=qty, entry_bar=self.entry_bar,
                   entry_time=pd.Timestamp(self.time[self.entry_bar]), entry_px=self.entry_avg,
                   exit_bar=i, exit_time=pd.Timestamp(self.time[i]), exit_px=px, reason=reason,
                   gross=gross, commission=comm, net=net,
                   mfe_ticks=mfe / self.c.mintick, mae_ticks=max(mae, 0) / self.c.mintick)
        self.trades.append(tr)
        # recovery-trail attempt tracking (per eval attempt / continuous)
        self.attempt_trade_no += 1
        if self.attempt_trade_no == 1 and net < 0:
            self.attempt_first_loss = True
        # reset position state
        self.pos = 0.0
        self.entry_avg = np.nan
        self.cur_stop = np.nan
        self.cur_limit = np.nan
        self.pos_hi = np.nan
        self.pos_lo = np.nan
        self.risk_off = self.trail_on = self.recov_on = False

    # --------------------------------------------------- position management
    def _manage_position(self, i: int):
        """Update excursions and ratchet the stop (applies from next bar)."""
        cfg = self.cfg
        if self.pos > 0:
            if i != self.entry_bar:
                self.pos_hi = max(self.pos_hi, self.high[i])
                self.pos_lo = min(self.pos_lo, self.low[i])
            mfe = self.pos_hi - self.entry_avg
            cand = self.cur_stop
            if cfg.use_breakeven and mfe >= self._dist(cfg.be_trigger_ticks):
                cand = max(cand, self.entry_avg + self._dist(cfg.be_offset_ticks))
                self.risk_off = True
            if cfg.use_trail and mfe >= self._dist(cfg.trail_start_ticks):
                cand = max(cand, self.pos_hi - self._dist(cfg.trail_buffer_ticks))
                self.trail_on = True
            if (cfg.use_recov_trail and cfg.is_eval and self.attempt_trade_no == 1
                    and self.attempt_first_loss and mfe >= self._dist(cfg.recov_trail_start_ticks)):
                cand = max(cand, self.pos_hi - self._dist(cfg.recov_trail_buf_ticks))
                self.recov_on = True
            self.cur_stop = max(self.cur_stop, cand)
        elif self.pos < 0:
            if i != self.entry_bar:
                self.pos_hi = max(self.pos_hi, self.high[i])
                self.pos_lo = min(self.pos_lo, self.low[i])
            mfe = self.entry_avg - self.pos_lo
            cand = self.cur_stop
            if cfg.use_breakeven and mfe >= self._dist(cfg.be_trigger_ticks):
                cand = min(cand, self.entry_avg - self._dist(cfg.be_offset_ticks))
                self.risk_off = True
            if cfg.use_trail and mfe >= self._dist(cfg.trail_start_ticks):
                cand = min(cand, self.pos_lo + self._dist(cfg.trail_buffer_ticks))
                self.trail_on = True
            if (cfg.use_recov_trail and cfg.is_eval and self.attempt_trade_no == 1
                    and self.attempt_first_loss and mfe >= self._dist(cfg.recov_trail_start_ticks)):
                cand = min(cand, self.pos_lo + self._dist(cfg.recov_trail_buf_ticks))
                self.recov_on = True
            self.cur_stop = min(self.cur_stop, cand)

    # ------------------------------------------------------------- strategy
    def _strategy(self, i: int):
        cfg = self.cfg
        # --- session roll ---
        if self.new_session[i]:
            self._roll_session(i)

        # --- account overlay (may set day_halted / acct_halted / bank payout) ---
        if not self.research and cfg.phase_on:
            if cfg.is_static:
                self._account_static(i)
            else:
                self._account(i)

        day_halted = self.day_halted
        flat_win = self._in_flat_window(i)
        can_trade = (self._time_gate(i) and not day_halted and not flat_win
                     and not self.acct_halted)

        # --- signal detection (confirmed bar) ---
        long0, short0, mid, top, bot = self._signal(i, can_trade)
        long_sig, short_sig = long0, short0
        sig_mid, sig_top, sig_bot = mid, top, bot

        # FVG confirmation memory
        if cfg.confirm_bars > 0:
            long_sig, short_sig, sig_mid, sig_top, sig_bot = self._memory(
                i, can_trade, long0, short0)

        placed = False
        if (long_sig or short_sig) and self.pos == 0 and can_trade:
            placed = self._try_place(i, long_sig, sig_mid, sig_top, sig_bot)

        # --- pending expiry ---
        if self.pos == 0 and self.pend_dir != 0 and not placed:
            if (i - self.pend_bar > cfg.expiry_bars) or flat_win or day_halted:
                self.pend_dir = 0
                self.pend_limit = np.nan
                self.pend_stop = np.nan

        # --- auto-flat ---
        if flat_win and not self.flattened_today:
            self.flattened_today = True
            if self.pos != 0:
                self._close_at(i, self.close[i], "AUTO-FLAT")
            self.pend_dir = 0

        # --- day halt close ---
        if day_halted and not self.halt_close_sent:
            self.halt_close_sent = True
            self.pend_dir = 0
            if self.pos != 0:
                self._close_at(i, self.close[i], self.halt_reason)

        # --- account halt close (Eval breach / pass) ---
        if self.acct_halted and self.pos != 0:
            self._close_at(i, self.close[i], self.acct_halt_reason)
            self.pend_dir = 0

    def _roll_session(self, i: int):
        cfg = self.cfg
        prev_base = self.risk_base
        yday = self.net_profit - (prev_base if prev_base is not None else self.net_profit)
        if cfg.is_pa and prev_base is not None and yday > 0:
            self.profit_since += yday
            self.best_day_since = max(self.best_day_since, yday)
            if yday >= cfg.min_qual_day_usd:
                self.qual_days += 1
        if cfg.phase_on and cfg.dd_model == "EOD":
            base = np.nanmax([self.acct_hwm, 0.0]) if not np.isnan(self.acct_hwm) else 0.0
            self.acct_hwm = max(base, self.net_profit - self.pa_reset_pnl_prev)
        self.risk_base = self.net_profit
        self.risk_day_peak = 0.0
        self.day_halted = False
        self.flattened_today = False
        self.halt_close_sent = False
        self.halt_reason = ""
        self.has_traded = False

    def _account(self, i: int):
        cfg = self.cfg
        if self.risk_base is None:
            self.risk_base = self.net_profit
        today_real = self.net_profit - self.risk_base
        running = today_real + self._open_profit(i)
        self.risk_day_peak = max(self.risk_day_peak, running)
        today_dd = self.risk_day_peak - running

        # day exit conditions
        dex_trail = cfg.day_exit_mode in ("Day-trail (keep peak)", "Trail + cap")
        dex_cap = cfg.day_exit_mode in ("Day-cap (hard target)", "Trail + cap")
        day_trail_hit = dex_trail and self.risk_day_peak > cfg.day_trail_usd and running <= self.risk_day_peak - cfg.day_trail_usd
        day_cap_hit = dex_cap and self.risk_day_peak >= cfg.day_cap_usd
        dll_hit = (cfg.is_pa or (cfg.is_eval and cfg.dd_model == "EOD")) and running <= -cfg.acct_dll
        if not self.day_halted and (day_trail_hit or day_cap_hit or dll_hit):
            self.day_halted = True
            self.halt_reason = ("Day-cap" if day_cap_hit else "Day-trail" if day_trail_hit
                                else "PA Daily Loss Limit")

        # account trailing floor / eval goal / payout
        acct_realized = self.net_profit - self.pa_reset_pnl_prev
        acct_pnl = acct_realized + self._open_profit(i)
        if cfg.dd_model == "Intraday":
            self.acct_hwm = acct_pnl if np.isnan(self.acct_hwm) else max(self.acct_hwm, acct_pnl)
        elif np.isnan(self.acct_hwm):
            self.acct_hwm = 0.0
        acct_locked = self.acct_hwm >= cfg.acct_trail_dd + 100
        acct_floor = 100.0 if acct_locked else self.acct_hwm - cfg.acct_trail_dd
        self.dd_room = acct_pnl - acct_floor          # runway before a trailing breach

        consistency_ok = self.profit_since > 0 and (self.best_day_since / self.profit_since) < cfg.consistency_pct / 100.0
        eff_nr = min(self.pa_payouts_this_cycle + 1, 6)
        cap = ladder_cap(eff_nr)
        withdrawable = acct_realized - (cfg.acct_trail_dd + 100)
        payout_eligible = (cfg.is_pa and acct_locked
                           and acct_realized >= cfg.acct_trail_dd + 100 + cfg.payout_buffer + cfg.min_payout
                           and self.qual_days >= 5 and consistency_ok)
        full_cap_ready = payout_eligible and withdrawable >= cap
        payout_ready = full_cap_ready if cfg.use_wait_for_cap else payout_eligible

        if not self.acct_halted:
            if acct_pnl <= acct_floor:
                if cfg.is_pa:  # backtest mode: reset overlay, keep trading
                    self.pa_breach_count += 1
                    self.pa_reset_count += 1
                    self.pa_reset_pnl_prev = self.net_profit
                    self.acct_hwm = np.nan
                    self.profit_since = 0.0
                    self.best_day_since = 0.0
                    self.qual_days = 0
                    self.pa_payouts_this_cycle = 0
                else:
                    self.acct_halted = True
                    self.acct_halt_reason = "TRAILING BREACH (model)"
            elif cfg.is_eval and acct_realized >= cfg.acct_goal:
                self.acct_halted = True
                self.acct_halt_reason = "EVAL PASSED"

        # bank a payout (PA backtest)
        if cfg.is_pa and payout_ready:
            take = cap if cfg.use_wait_for_cap else min(withdrawable, cap)
            self.pa_total_banked += take
            self.pa_payouts_this_cycle += 1
            self.pa_payout_total += 1
            self.pa_reset_pnl_prev += take
            self.profit_since = 0.0
            self.best_day_since = 0.0
            self.qual_days = 0
            if self.pa_payouts_this_cycle >= 6:
                self.pa_milk_count += 1
                self.pa_reset_count += 1
                self.pa_payouts_this_cycle = 0
                self.acct_hwm = np.nan
                self.pa_reset_pnl_prev = self.net_profit

    def _account_static(self, i: int):
        """FTMO-style static account: fixed max-overall-loss (from the initial
        balance, never trails) + a daily loss limit measured from the day's start.
        Challenge passes at the profit target; any breach fails the account.
        `acct_trail_dd` is reused as the fixed max overall loss ($); `acct_goal`
        the target ($); `acct_dll` the daily loss ($)."""
        cfg = self.cfg
        if self.risk_base is None:
            self.risk_base = self.net_profit
        today = self.net_profit - self.risk_base
        running = today + self._open_profit(i)          # incl. floating (equity basis)
        total = self.net_profit + self._open_profit(i)   # from initial (offset 0)

        if self.acct_halted:
            return
        # daily loss limit -> whole account fails (FTMO)
        if cfg.acct_dll and running <= -cfg.acct_dll:
            self.acct_halted = True
            self.acct_halt_reason = "FAILED (daily loss)"
            self.day_halted = True
            self.halt_reason = "FAILED (daily loss)"
            return
        # fixed max overall loss (does NOT trail)
        if total <= -cfg.acct_trail_dd:
            self.acct_halted = True
            self.acct_halt_reason = "FAILED (max loss)"
            return
        # challenge passed
        if cfg.phase == "FTMO Challenge" and self.net_profit >= cfg.acct_goal:
            self.acct_halted = True
            self.acct_halt_reason = "CHALLENGE PASSED"

    # -------------------------------------------------------------- signals
    def _signal(self, i: int, can_trade: bool):
        d = self.fvg_dir[i]
        if not self.fvg_pass[i] or d == 0:
            return False, False, np.nan, np.nan, np.nan
        long0 = (d == 1 and self.bull_cvd[i] and self.veto_long[i] and can_trade)
        short0 = (d == -1 and self.bear_cvd[i] and self.veto_short[i] and can_trade)
        return long0, short0, self.fvg_mid[i], self.fvg_top[i], self.fvg_bot[i]

    def _memory(self, i: int, can_trade: bool, long0: bool, short0: bool):
        cfg = self.cfg
        cb = cfg.confirm_bars
        # prune expired
        self.mem = [m for m in self.mem if i - m["bar"] <= cb]
        # fill-check: drop gaps whose mid was touched
        if cfg.use_fill_check:
            self.mem = [m for m in self.mem
                        if not (self.low[i] <= m["mid"] <= self.high[i])]
        mem_dir, mem_mid, mem_top, mem_bot = 0, np.nan, np.nan, np.nan
        gate_ok = (self.pos == 0) and can_trade
        if not (long0 or short0) and gate_ok:
            for k in range(len(self.mem) - 1, -1, -1):
                m = self.mem[k]
                age = i - m["bar"]
                if 1 <= age <= cb:
                    ok = (self.bull_cvd[i] and self.veto_long[i]) if m["dir"] == 1 else (self.bear_cvd[i] and self.veto_short[i])
                    if ok:
                        mem_dir, mem_mid, mem_top, mem_bot = m["dir"], m["mid"], m["top"], m["bot"]
                        self.mem.pop(k)
                        break
        consumed = (long0 or short0) and (self.pos == 0)
        if self.fvg_dir[i] != 0 and self.fvg_pass[i] and not consumed:
            self.mem.append({"bar": i, "dir": int(self.fvg_dir[i]), "mid": self.fvg_mid[i],
                             "top": self.fvg_top[i], "bot": self.fvg_bot[i]})
        long_sig = long0 or mem_dir == 1
        short_sig = short0 or mem_dir == -1
        if long0 or short0:
            return long_sig, short_sig, self.fvg_mid[i], self.fvg_top[i], self.fvg_bot[i]
        return long_sig, short_sig, mem_mid, mem_top, mem_bot

    def _try_place(self, i: int, is_long: bool, mid: float, top: float, bot: float) -> bool:
        cfg = self.cfg
        entry_px = mid if cfg.entry_limit_mode else self.close[i]
        if is_long:
            if cfg.stop_swing:
                piv = self.piv_low[i]
                base = min(piv, bot) if not np.isnan(piv) else bot
                stop_px = base - self._dist(cfg.swing_buf_ticks)
            else:
                stop_px = entry_px - self._dist(cfg.fixed_stop_ticks)
        else:
            if cfg.stop_swing:
                piv = self.piv_high[i]
                base = max(piv, top) if not np.isnan(piv) else top
                stop_px = base + self._dist(cfg.swing_buf_ticks)
            else:
                stop_px = entry_px + self._dist(cfg.fixed_stop_ticks)

        stop_dist = abs(entry_px - stop_px)
        if np.isnan(stop_px) or stop_dist <= self.c.mintick or stop_dist > self._dist(cfg.max_stop_ticks):
            return False
        qty = self._calc_qty(stop_dist)
        qty = self._apply_mae_guard(qty, stop_dist)
        if qty < 1:
            return False

        # take-profit validity
        d = 1 if is_long else -1
        if cfg.tp_mode == "Swing structure":
            tp_px = self.piv_high[i] if is_long else self.piv_low[i]
        elif cfg.tp_mode == "R-multiple":
            tp_px = entry_px + d * cfg.r_multiple * stop_dist
        else:
            tp_px = entry_px + d * self._dist(cfg.tp_fixed_ticks)
        if np.isnan(tp_px) or (is_long and tp_px <= entry_px + self.c.mintick) or (not is_long and tp_px >= entry_px - self.c.mintick):
            return False

        self.pend_dir = d
        self.pend_bar = i
        self.pend_limit = entry_px if cfg.entry_limit_mode else np.nan
        self.pend_stop = stop_px
        self.pend_tp = tp_px
        self.pend_qty = qty
        # market mode: fill next bar open handled by broker? presets use limit.
        return True

    def _apply_mae_guard(self, qty: float, stop_dist: float) -> float:
        cfg = self.cfg
        if not (cfg.use_mae_guard and cfg.is_pa) or self.research:
            return qty
        sod_profit = self.net_profit  # start-of-day approximation (offset 0)
        safety = cfg.acct_trail_dd + 100
        pct = cfg.mae_grown_pct if sod_profit >= 2 * safety else cfg.mae_base_pct
        allow_usd = (pct / 100.0) * max(sod_profit, cfg.acct_trail_dd) * (1 - cfg.mae_margin_pct / 100.0)
        if stop_dist <= 0:
            return qty
        qmax = np.floor(allow_usd / (stop_dist * self.c.pointvalue))
        return min(qty, max(qmax, 0))
