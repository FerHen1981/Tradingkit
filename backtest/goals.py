"""Goal-oriented metrics.

The heatmap answers "where is the edge". Neither goal asks that. These two do:

  **Goal A — pass evals fast.** An eval is a cheap lottery ticket, so the
  question is not "is this profitable" but "how many attempts and how many weeks
  until an account is funded, and what does that cost". A config with a lower
  pass rate that resolves in a third of the time can be the better buy.

  **Goal B — milk funded accounts to 6/6 payouts.** A funded account never
  "passes"; it earns until it breaches. So the question is payout *cadence* and
  *survival*: how many payouts per account-year, and how likely is the full
  six-step ladder before the trailing drawdown ends the run.

Everything is normalised to **DD-units** — the account's trailing-drawdown
allowance — because that is the unit both goals are defined in, and the only one
that makes GC on a 50k Apex comparable to 6E on a 100k FTMO.
"""
from __future__ import annotations

import numpy as np

from .funnel import FunnelOutcome

SESSIONS_PER_YEAR = 252


def _pct(values, q: float) -> float:
    return float(np.percentile(values, q)) if len(values) else float("nan")


def _spread(values) -> dict:
    """Median plus quartiles. A median alone hides whether the tail is the risk."""
    return {
        "p25": round(_pct(values, 25), 1),
        "median": round(_pct(values, 50), 1),
        "p75": round(_pct(values, 75), 1),
    }


def eval_throughput(outcomes: list[FunnelOutcome], eval_fee: float = 0.0,
                    horizon_sessions: int | None = None) -> dict:
    """How reliably and how fast does this config fund an account?

    ``eval_fee`` is what one attempt costs; leave at 0 to get counts only.
    """
    n = len(outcomes)
    if n == 0:
        return {"starts": 0}

    results = np.array([o.result for o in outcomes])
    npass = int((results == "PASS").sum())
    nbreach = int((results == "BREACH").sum())
    ntimeout = int((results == "TIMEOUT").sum())
    resolved = npass + nbreach

    pass_sessions = [o.resolve_sessions for o in outcomes
                     if o.result == "PASS" and o.resolve_sessions >= 0]
    breach_sessions = [o.resolve_sessions for o in outcomes
                       if o.result == "BREACH" and o.resolve_sessions >= 0]
    pass_trades = [o.trades for o in outcomes if o.result == "PASS"]

    p = npass / n
    out = {
        "starts": n,
        "pass": npass, "breach": nbreach, "timeout": ntimeout,
        "pass_rate_pct": round(100 * p, 1),
        "pass_rate_of_resolved_pct": round(100 * npass / resolved, 1) if resolved else 0.0,
        "sessions_to_pass": _spread(pass_sessions),
        "sessions_to_breach": _spread(breach_sessions),
        "trades_to_pass": _spread(pass_trades),
    }

    if p > 0:
        attempts = 1.0 / p
        # A timeout is not free: it consumed the whole horizon before you could
        # start over, so it has to be priced at the full window.
        horizon = horizon_sessions if horizon_sessions is not None else max(
            (o.resolve_sessions for o in outcomes), default=0)
        per_attempt = float(np.mean([
            o.resolve_sessions if o.resolve_sessions >= 0 else horizon
            for o in outcomes]))
        out["expected_attempts_per_funded"] = round(attempts, 2)
        out["expected_sessions_to_funded"] = round(attempts * per_attempt, 1)
        out["expected_weeks_to_funded"] = round(attempts * per_attempt / 5.0, 1)
        if eval_fee:
            out["expected_cost_per_funded"] = round(attempts * eval_fee, 2)
    else:
        out["expected_attempts_per_funded"] = float("inf")
        out["expected_sessions_to_funded"] = float("inf")
        out["expected_weeks_to_funded"] = float("inf")
        if eval_fee:
            out["expected_cost_per_funded"] = float("inf")

    return out


def payout_throughput(outcomes: list[FunnelOutcome], acct_trail_dd: float,
                      horizon_sessions: int) -> dict:
    """How much does a funded account actually pay out before it dies?"""
    n = len(outcomes)
    if n == 0:
        return {"starts": 0}

    payouts = np.array([o.payouts for o in outcomes], dtype=float)
    banked = np.array([o.banked for o in outcomes], dtype=float)
    breaches = np.array([o.breaches for o in outcomes], dtype=float)
    milks = np.array([o.milks for o in outcomes], dtype=float)

    # A horizon is a slice of an account's life, so scale it to a year to make
    # windows of different lengths comparable.
    year_factor = SESSIONS_PER_YEAR / horizon_sessions if horizon_sessions else float("nan")

    return {
        "starts": n,
        "horizon_sessions": horizon_sessions,
        "payouts": _spread(payouts),
        "payouts_per_account_year": round(float(payouts.mean()) * year_factor, 2),
        "p_any_payout_pct": round(100 * float((payouts >= 1).mean()), 1),
        "p_full_ladder_pct": round(100 * float((payouts >= 6).mean()), 1),
        "completed_ladders": int(milks.sum()),
        "banked_mean": round(float(banked.mean()), 2),
        "banked_mean_dd_units": round(float(banked.mean()) / acct_trail_dd, 2)
        if acct_trail_dd else float("nan"),
        "banked_per_account_year": round(float(banked.mean()) * year_factor, 2),
        "breaches_mean": round(float(breaches.mean()), 2),
        "breaches_per_account_year": round(float(breaches.mean()) * year_factor, 2),
        "survival_rate_pct": round(100 * float((breaches == 0).mean()), 1),
    }


def format_eval(m: dict) -> str:
    if not m.get("starts"):
        return "  no eval windows — dataset shorter than one horizon?"
    s2p, s2b = m["sessions_to_pass"], m["sessions_to_breach"]
    lines = [
        f"  starts {m['starts']}   pass {m['pass']}  breach {m['breach']}  timeout {m['timeout']}",
        f"  pass rate           {m['pass_rate_pct']}%  "
        f"({m['pass_rate_of_resolved_pct']}% of resolved)",
        f"  sessions to pass    {s2p['median']}  (p25 {s2p['p25']} / p75 {s2p['p75']})",
        f"  sessions to breach  {s2b['median']}  (p25 {s2b['p25']} / p75 {s2b['p75']})",
        f"  attempts per funded {m['expected_attempts_per_funded']}",
        f"  weeks to funded     {m['expected_weeks_to_funded']}",
    ]
    if "expected_cost_per_funded" in m:
        lines.append(f"  cost per funded     ${m['expected_cost_per_funded']:,.0f}")
    return "\n".join(lines)


def format_payout(m: dict) -> str:
    if not m.get("starts"):
        return "  no funded windows — dataset shorter than one horizon?"
    p = m["payouts"]
    return "\n".join([
        f"  starts {m['starts']}   horizon {m['horizon_sessions']} sessions",
        f"  payouts per window  {p['median']}  (p25 {p['p25']} / p75 {p['p75']})",
        f"  payouts / acct-year {m['payouts_per_account_year']}",
        f"  P(any payout)       {m['p_any_payout_pct']}%",
        f"  P(full 6/6 ladder)  {m['p_full_ladder_pct']}%",
        f"  banked / acct-year  ${m['banked_per_account_year']:,.0f}  "
        f"({m['banked_mean_dd_units']} DD-units per window)",
        f"  breaches / acct-yr  {m['breaches_per_account_year']}",
        f"  survived the window {m['survival_rate_pct']}%",
    ])
