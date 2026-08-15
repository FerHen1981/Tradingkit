"""Rule-based insight generation for the Backtest Lab Journey.

Turns a strategy's runs (across timeframes and the three lenses) into a guided,
lens-by-lens walkthrough — deterministic prose derived from the numbers, no LLM.
Each lens answers one question:

    classic  — is there a real edge, after costs?
    eval     — how reliably does it fund an account? (PASS/BREACH/TIMEOUT)
    funded   — once funded, does it actually pay out? (overlay TBD)

Every insight is {tone, text}; tone in {good, warn, bad, info}.
"""
from __future__ import annotations

from ..config import TIMEFRAMES

LENS_ORDER = ["classic", "eval", "funded"]
LENS_QUESTION = {
    "classic": "Is there a real edge, after costs?",
    "eval": "How reliably does it fund an account?",
    "funded": "Once funded, does it actually pay out?",
}
_TF_RANK = {tf: i for i, tf in enumerate(TIMEFRAMES)}
_MIN_TRADES = 100          # below this a result is not decision-grade


def _money(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    return ("+$" if n >= 0 else "-$") + f"{abs(round(n)):,}"


def _insight(tone: str, text: str) -> dict:
    return {"tone": tone, "text": text}


def _k(run: dict) -> dict:
    return run.get("kpis") or {}


def _tf_key(run: dict) -> int:
    return _TF_RANK.get(run.get("timeframe", ""), 99)


# --------------------------------------------------------------------------- #
# Classic lens — edge quality across timeframes
# --------------------------------------------------------------------------- #
def classic_insights(runs: list[dict]) -> list[dict]:
    runs = sorted(runs, key=_tf_key)
    graded = [(r, _k(r)) for r in runs]
    real = [(r, k) for r, k in graded if (k.get("trades") or 0) >= _MIN_TRADES]
    out: list[dict] = []

    if not graded:
        return [_insight("info", "No classic runs yet.")]

    # Best decision-grade timeframe by profit factor.
    if real:
        best_r, best_k = max(real, key=lambda rk: rk[1].get("profit_factor", 0))
        tf, pf = best_r.get("timeframe"), best_k.get("profit_factor", 0)
        exp = best_k.get("expectancy", 0)
        tone = "good" if pf >= 1.2 else ("warn" if pf >= 1.0 else "bad")
        out.append(_insight(tone,
            f"Edge concentrates on {tf}: PF {pf:.2f}, {_money(exp)}/trade "
            f"over {best_k.get('trades', 0):,} trades."))
    else:
        out.append(_insight("warn",
            f"No timeframe reaches {_MIN_TRADES}+ trades — nothing is decision-grade yet; "
            f"treat every result below as a hint, not a verdict."))

    # Per-timeframe reads.
    for r, k in graded:
        tf, n = r.get("timeframe"), k.get("trades") or 0
        pf = k.get("profit_factor")
        if n == 0:
            out.append(_insight("info", f"{tf}: no trades — the filters never triggered here."))
            continue
        if n < _MIN_TRADES:
            out.append(_insight("warn",
                f"{tf}: only {n} trades — thin sample, not decision-grade."))
            continue
        if pf is not None and pf < 1.0:
            out.append(_insight("bad",
                f"{tf}: PF {pf:.2f} — loses money after costs; no edge here."))

    # Win% vs payoff asymmetry on the best timeframe.
    if real:
        aw, al = best_k.get("avg_win"), best_k.get("avg_loss")
        wr = best_k.get("win_rate_pct")
        if aw and al and wr is not None:
            ratio = abs(al) / aw if aw else 0
            if wr >= 60 and ratio >= 1.5:
                out.append(_insight("info",
                    f"High win rate ({wr:.0f}%) but losers are {ratio:.1f}× winners "
                    f"({_money(aw)} vs {_money(al)}) — the edge rides on hit-rate; "
                    f"a few big losers can flip it."))
        net, dd = best_k.get("net_profit"), best_k.get("max_drawdown")
        if net and dd:
            out.append(_insight("good" if net / dd >= 2 else "warn",
                f"Return/drawdown on {best_r.get('timeframe')}: {_money(net)} net "
                f"against {_money(dd)} max drawdown (≈{net / dd:.1f}×)."))
    return out


# --------------------------------------------------------------------------- #
# Eval lens — funnel pass/breach/timeout
# --------------------------------------------------------------------------- #
def eval_insights(runs: list[dict]) -> list[dict]:
    runs = sorted(runs, key=_tf_key)
    out: list[dict] = []
    if not runs:
        return [_insight("info", "No eval-funnel runs yet — run the strategy with the eval lens "
                                 "to see how reliably it funds an account.")]
    for r in runs:
        k = _k(r)
        tf = r.get("timeframe")
        starts = k.get("starts")
        rate = k.get("pass_rate_pct")
        if starts is None or rate is None:
            out.append(_insight("info", f"{tf}: eval run recorded (no funnel summary)."))
            continue
        tone = "good" if rate >= 40 else ("warn" if rate >= 20 else "bad")
        out.append(_insight(tone,
            f"{tf}: {rate:.0f}% of {starts} fresh evals PASS "
            f"(BREACH {k.get('breach', 0)}, TIMEOUT {k.get('timeout', 0)}) — "
            f"median {k.get('median_trades_to_resolve', '—')} trades to resolve."))
    return out


# --------------------------------------------------------------------------- #
# Funded lens — payout overlay (built next)
# --------------------------------------------------------------------------- #
def funded_insights(runs: list[dict]) -> list[dict]:
    if not runs:
        return [_insight("info", "Funded lens not run yet — the payout overlay (min trading days, "
                                 "consistency, safety-net → payout timeline) is the next build.")]
    out = []
    for r in runs:
        k = _k(r)
        out.append(_insight("info", f"{r.get('timeframe')}: funded run recorded "
                                    f"({k.get('payouts', '—')} payouts, "
                                    f"{_money(k.get('withdrawable', 0))} withdrawable)."))
    return out


_LENS_FN = {"classic": classic_insights, "eval": eval_insights, "funded": funded_insights}


# --------------------------------------------------------------------------- #
# Journey — the whole walkthrough for one strategy
# --------------------------------------------------------------------------- #
def build_journey(runs: list[dict], strategy: str | None = None) -> dict:
    """Group a strategy's runs by lens and produce the guided walkthrough."""
    if strategy:
        runs = [r for r in runs if r.get("strategy") == strategy]
    by_lens: dict[str, list[dict]] = {}
    for r in runs:
        by_lens.setdefault(r.get("lens", "classic"), []).append(r)

    strat = strategy or (runs[0].get("strategy") if runs else "—")
    assets = sorted({r.get("asset", "") for r in runs if r.get("asset")})
    lenses = []
    for lens in LENS_ORDER:
        lens_runs = sorted(by_lens.get(lens, []), key=_tf_key)
        lenses.append({
            "lens": lens,
            "question": LENS_QUESTION[lens],
            "runs": lens_runs,
            "insights": _LENS_FN[lens](lens_runs),
        })
    return {"strategy": strat, "assets": assets, "lenses": lenses,
            "verdict": _verdict(by_lens)}


def _verdict(by_lens: dict[str, list[dict]]) -> dict:
    """One-line bottom line across the lenses."""
    classic = by_lens.get("classic", [])
    real = [r for r in classic if (_k(r).get("trades") or 0) >= _MIN_TRADES
            and (_k(r).get("profit_factor") or 0) >= 1.2]
    if not classic:
        return _insight("info", "Run the classic lens first to establish whether there is an edge.")
    if not real:
        return _insight("bad", "No decision-grade edge yet — no timeframe clears PF 1.2 on a "
                               "100+ trade sample. Not a fleet candidate.")
    best = max(real, key=lambda r: _k(r).get("profit_factor", 0))
    tf = best.get("timeframe")
    if not by_lens.get("eval"):
        return _insight("warn", f"Edge on {tf} (PF {_k(best).get('profit_factor', 0):.2f}) — "
                                f"now run the eval lens to see if it funds reliably.")
    return _insight("good", f"Edge on {tf}; eval + funded lenses next to confirm it funds and pays.")
