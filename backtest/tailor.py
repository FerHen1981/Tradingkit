"""Per-account settings tailoring — the reken-kant of the fleet playbook (Release 3b).

WHAT THIS IS. The fleet doc (A-84/A-85 in docs/state.md) is not a fixed doctrine table;
it is ONE scoring rule run per account against the rules of that account. Ferry, 08-10:
*"je hebt inzage hoe het doc opgebouwd wordt en die logica wil ik terugzien in het Playbook
zonder documenten aan te leveren."* So this module turns that scratchpad into a job: it
scores the candidate settings for an account's profile on the Pine year-stream and writes
the winner to a file the cockpit reads — the same pattern as the publication task. The
cockpit then shows a route per account without anyone delivering a PDF.

THE SCORING RULE (A-84). For an account:
  * inputs — room to liquidation · locked or fresh (fresh trails the floor with the peak,
    locked sits fixed at -room) · best day since the last payout · the NEXT payout maximum ·
    that account's rules: consistency % and the qualifying-day minimum.
  * candidates — 24 sets: qty 1-4 x {150/50/300, 250/100/500, 320/100/900} per contract x
    with/without a day-stop. The triple is activation/giveback/cap (the day-trail), per
    contract, scaled linearly by qty (state.md A-76 "Schaalregel"). The day-stop, when on,
    is the Tradovate daily-loss limit set to the set's CAP (state.md A-84/A-85: 150/50/300
    -> DLL 300, 300/100/600 -> DLL 600, ... ; cap = 3 x SL by construction, so "DLL = 3 SL"
    and "DLL = cap" are the same number).
  * measure — each set over rolling windows of the year: P(reached the step maximum within
    20/40/60 days) and P(breach). Gates: 8 trading days, 5 qualifying days at the account
    minimum, consistency at the account percentage.
  * score — haal-40d - 0.5 x breach-40d. Highest wins. Output per account: the chosen set,
    haal %, breach %, median days.

TWO THINGS THAT ARE NOT YET CLOSED, and this module is explicit about both rather than
quietly picking an answer:
  1. DATA. The A-84 reproduction needs the MGC Pine year-stream in the repo; it is hosted as
     a Parquet Release-asset (D-141, Ferry provides). Until it lands, `score_account` runs on
     whatever daily series the caller injects, and the 013/018/022 acceptance cannot run — it
     is NOT silently approximated.
  2. THE ACCOUNT-STATE -> SIM MAPPING (locked/fresh, room, best-day-since) was first written
     in the Analyses & Data scratchpad that produced A-84; the reading here is documented at
     `_window_rules` and must be confirmed against that scratchpad before the output is trusted
     as the A-84 replacement.

Backtest Setup owns this (backtest/**). It reuses the funded sim (funded.simulate_funded,
now D-130/D-148-correct) as the per-set evaluator, so there is one payout model, not two.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .funded import simulate_funded

# The three per-contract guard families (activation / giveback / cap), A-84. The cap is
# also the day-stop (DLL) value when the day-stop is on; cap = 3 x the family's SL.
GUARD_FAMILIES = (
    (150.0, 50.0, 300.0),
    (250.0, 100.0, 500.0),
    (320.0, 100.0, 900.0),
)
QTYS = (1, 2, 3, 4)
HORIZONS = (20, 40, 60)          # trading-day horizons for the haal/breach probabilities
SCORE_HORIZON = 40               # the horizon the score is taken at (A-84: haal-40d - ½·breach-40d)


@dataclass(frozen=True)
class Guards:
    """One candidate set. Dollar guards are PER CONTRACT; `.scaled()` applies qty."""
    qty: int
    act: float                    # activation $ / contract
    gb: float                     # giveback $ / contract
    cap: float                    # hard day-cap $ / contract (= day-stop value when daystop on)
    daystop: bool                 # Tradovate daily-loss limit on, set to the (scaled) cap

    def scaled(self) -> tuple[float, float, float, float | None]:
        """(activation, giveback, cap, day_stop) in $, at this qty. day_stop is None when off."""
        a, g, c = self.act * self.qty, self.gb * self.qty, self.cap * self.qty
        return a, g, c, (c if self.daystop else None)

    def label(self) -> str:
        a, g, c, dll = self.scaled()
        return (f"qty{self.qty} {a:.0f}/{g:.0f}/{c:.0f}"
                f" DLL {dll:.0f}" if dll is not None else
                f"qty{self.qty} {a:.0f}/{g:.0f}/{c:.0f} no-DLL")


def candidate_sets() -> list[Guards]:
    """The 24 sets: qty 1-4 x 3 guard families x day-stop on/off."""
    return [Guards(q, a, g, c, ds)
            for q in QTYS
            for (a, g, c) in GUARD_FAMILIES
            for ds in (True, False)]


@dataclass(frozen=True)
class AccountProfile:
    """The live state of one funded account that drives the scoring (A-84 inputs)."""
    name: str
    account_size: float
    room_to_liq: float            # $ from the current balance down to liquidation
    locked: bool                  # True = floor fixed at -room; False (fresh) = floor trails
    best_day_since: float         # best winning day since the last payout ($)
    next_cap: float | None        # the next payout maximum ($); None = uncapped (Apex legacy #6+)
    consistency_pct: float        # that account's consistency rule (e.g. 30.0 or 50.0)
    min_qual_usd: float           # qualifying-day minimum ($50 or $250)
    min_qual_days: int = 5        # payouts need >=5 qualifying days in the cycle
    min_trading_days: int = 8     # ... within >=8 trading days


@dataclass
class SetScore:
    guards: Guards
    haal: dict = field(default_factory=dict)      # horizon -> reached-step-max probability (0..1)
    breach: dict = field(default_factory=dict)    # horizon -> breach probability (0..1)
    median_days: float | None = None              # median trading days to reach, over windows that did
    score: float = 0.0
    windows: int = 0


def _window_rules(profile: AccountProfile) -> dict:
    """Translate an account profile into a `simulate_funded` rule set.

    DOCUMENTED READING (confirm against the Analyses & Data scratchpad, see module header):
      * `drawdown` = room to liquidation. A FRESH account trails the floor with the peak
        (simulate_funded's default eod_trailing), a LOCKED account's floor is fixed — modelled
        by `drawdown_type="static"` so the floor stays at start-room and does not trail up.
      * consistency and qualifying-day gates come straight from the account's own rules.
      * the payout cap for the step is `next_cap` (None = uncapped): fed as a one-rung ladder
        / fixed cap so the sim banks exactly at the step maximum under test.
    `best_day_since` seeds the consistency ratio's numerator; simulate_funded recomputes the
    best day within each window, so it is carried on the profile for the cockpit display and
    as the floor for the very first cycle (handled by the caller when it matters)."""
    rules = {
        "drawdown": float(profile.room_to_liq),
        # simulate_funded gates payout on qualifying days (>= min_day_profit); the separate
        # "8 trading days" part of the Apex gate is NOT independently enforced by the sim —
        # a known fidelity item to reconcile against the scratchpad before trusting as A-84.
        "min_qual_days": int(profile.min_qual_days),
        "min_day_profit": float(profile.min_qual_usd),
        "consistency_limit": float(profile.consistency_pct) / 100.0,
        "safety_buffer": 100.0,
        "min_payout": 0.0,
        "profit_split": 1.0,
        "daily_loss_limit": None,
    }
    if profile.next_cap is None:
        # uncapped step (Apex legacy #6+): a very large cap so the sim banks the full amount.
        rules["ladder"], rules["cap"], rules["uncapped_from"] = None, 1e12, 0
    else:
        rules["ladder"], rules["cap"], rules["uncapped_from"] = None, float(profile.next_cap), 0
    return rules


def _reached_step(res, next_cap: float | None) -> bool:
    """True when a payout at (at least) the step maximum was banked. For an uncapped step any
    payout counts; otherwise the first payout must have hit the cap (not a partial)."""
    if not res.payouts:
        return False
    if next_cap is None:
        return True
    return res.payouts[0].amount >= 0.99 * float(next_cap)


def score_set(windows: list[dict], profile: AccountProfile,
              guards: Guards | None = None) -> SetScore:
    """Score ONE set over a list of rolling-window daily-P&L series ({date: net} each).

    The daily series already reflect `guards` (they were produced by running the engine with
    that set — see `daily_series_by_window`); this layer applies the funded gates and reduces
    to haal/breach probabilities and the score. It is deliberately pure so it can be tested on
    synthetic series without the year data."""
    rules = _window_rules(profile)
    dd_type = "static" if profile.locked else "eod_trailing"
    reached_at: list[int] = []
    breaches = {h: 0 for h in HORIZONS}
    reached = {h: 0 for h in HORIZONS}
    n = 0
    for daily in windows:
        if not daily:
            continue
        n += 1
        series = sorted(daily.items())
        for h in HORIZONS:
            sub = dict(series[:h])
            res = simulate_funded(sub, account_size=profile.account_size,
                                  drawdown_type=dd_type, drawdown=profile.room_to_liq,
                                  rules=rules)
            if _reached_step(res, profile.next_cap):
                reached[h] += 1
                if h == SCORE_HORIZON and res.days_to_first_payout is not None:
                    reached_at.append(res.days_to_first_payout)
            if res.breached:
                breaches[h] += 1
    sc = SetScore(guards=guards, windows=n)
    if n:
        sc.haal = {h: reached[h] / n for h in HORIZONS}
        sc.breach = {h: breaches[h] / n for h in HORIZONS}
        sc.median_days = statistics.median(reached_at) if reached_at else None
        sc.score = sc.haal[SCORE_HORIZON] - 0.5 * sc.breach[SCORE_HORIZON]
    return sc


def rank(windows_by_set: dict, profile: AccountProfile) -> list[SetScore]:
    """Score every candidate set and return them best-first (score desc, then fewer breaches).
    `windows_by_set` maps a Guards to its list of rolling-window daily series."""
    scored = [score_set(windows_by_set[g], profile, guards=g) for g in windows_by_set]
    scored.sort(key=lambda s: (-s.score, s.breach.get(SCORE_HORIZON, 1.0)))
    return scored


def tailor_account(windows_by_set: dict, profile: AccountProfile) -> dict:
    """The cockpit record for one account: the winning set and its metrics, plus the live
    inputs the Playbook tab shows. Numbers only — no account identifiers beyond the name the
    caller passed, which it controls."""
    ranked = rank(windows_by_set, profile)
    best = ranked[0] if ranked else None
    out = {
        "account": profile.name,
        "inputs": {
            "room_to_liq": profile.room_to_liq,
            "locked": profile.locked,
            "best_day_since": profile.best_day_since,
            "next_cap": profile.next_cap,
            "consistency_pct": profile.consistency_pct,
            "min_qual_usd": profile.min_qual_usd,
            # Apex's own consistency formula: highest winning day / 0.30 = min total win required.
            "min_total_win_for_consistency": (round(profile.best_day_since / (profile.consistency_pct / 100.0), 2)
                                              if profile.consistency_pct else None),
        },
        "chosen": None,
    }
    if best and best.guards is not None:
        a, g, c, dll = best.guards.scaled()
        out["chosen"] = {
            "qty": best.guards.qty, "activation": a, "giveback": g, "cap": c,
            "day_stop": dll, "label": best.guards.label(),
            "haal_pct": round(100 * best.haal.get(SCORE_HORIZON, 0.0), 1),
            "breach_pct": round(100 * best.breach.get(SCORE_HORIZON, 0.0), 1),
            "median_days": best.median_days, "score": round(best.score, 4),
        }
    return out


def write_cockpit_file(records: list[dict], path: str, *, meta: dict | None = None) -> str:
    """Write the per-account records as the single JSON the cockpit reads (same pattern as the
    publication task). Returns the path written."""
    import json
    from datetime import date
    doc = {"kind": "fleet_tailor", "as_of": date.today().isoformat(),
           "score_rule": "haal-40d - 0.5 * breach-40d", "horizons": list(HORIZONS),
           "meta": meta or {}, "accounts": records}
    with open(path, "w") as f:
        json.dump(doc, f, indent=2)
    return path


# --- generation layer: daily P&L per set from the year bars (needs the data) ----------------
def daily_series_by_window(bars, ind, base_cfg, guards: Guards, *, step: int = 3) -> list[dict]:
    """Run the engine over the year with `guards` applied, from rolling start offsets (every
    `step` trading days), returning one {session_date: net} series per window.

    This is the layer that needs the MGC year-stream (D-141). It reuses the engine so the
    day-trail/day-stop behave exactly as live (the D-113 brake), which is the whole point of
    reading the .pine logic rather than re-implementing it. Kept importable and documented so
    it runs the moment the data lands; `score_set`/`rank` above are tested without it."""
    from .engine import Engine
    from .funded import daily_from_trades, session_date
    import numpy as np

    a, g, c, dll = guards.scaled()
    cfg = base_cfg.with_(
        contract_size=float(guards.qty),
        day_exit_mode="Trail + cap", day_trail_model="Activation + giveback",
        day_trail_activation_usd=a, day_trail_giveback_usd=g, day_cap_usd=c,
        owner_dll_enabled=bool(guards.daystop),
        owner_dll_override=float(dll) if dll is not None else 0.0,
    )
    times = bars["et"].to_numpy() if "et" in getattr(bars, "columns", []) else None
    # session starts: first bar of each trade date
    sess = np.asarray([session_date(t) for t in (times if times is not None else [])])
    starts = []
    if sess.size:
        seen = set()
        for i, d in enumerate(sess):
            if d not in seen:
                seen.add(d)
                starts.append(i)
    windows: list[dict] = []
    for k in range(0, len(starts), max(step, 1)):
        sb = starts[k]
        res = Engine(cfg, bars, ind, start_bar=sb).run()
        daily = daily_from_trades(res.trades)
        if daily:
            windows.append(daily)
    return windows
