"""Portfolio selection — pick a SET, not a ranking.

The mill and the OOS gate judge every candidate on its own merit (PF). That
criterion cannot produce a decorrelated fleet: it keeps rediscovering the same
edge under different names, so the "survivors" are largely clones of one trade.
Running five clones on five prop-firm accounts is not diversification — it is
one position at five times the size, and they breach on the same day.

This module measures what the labels cannot tell you:

  * **return correlation** — Pearson on the aligned daily P&L (non-trading days
    count as 0, because a flat day is information about the strategy). Only
    strong POSITIVE correlation is a veto: each prop account carries its own
    drawdown buffer, so two strategies that lose on opposite days are exactly
    what you want — negative correlation is a feature, not a duplicate;
  * **shared bad days** — Jaccard overlap of the days each strategy lost a
    meaningful slice of its drawdown buffer. For a prop account this is the
    metric that matters: what kills a fleet is several accounts taking a big
    loss on the SAME day, and plain correlation understates exactly that tail;
  * **regime overlap** — cosine similarity of the per-regime edge profiles
    (from metrics.edge_by_regime), the structural axis: does this candidate earn
    its money where the others already do?

Selection is greedy on realized edge, vetoed by those three measures, and every
rejection carries the reason and the offending peer. Nothing here assumes that
"SMC" and "classic indicators" are different — an FVG entry and a Bollinger
reversion often fire on the same 1m impulse. Difference is measured, not named.

    python -m backtest.portfolio --verified $LAB_DIR/verified_seed0.json
"""
from __future__ import annotations

import argparse
import json
import math

# Defaults are deliberately strict: this is a veto layer, and a fleet of three
# genuinely different strategies beats eight variations of one.
MAX_CORR = 0.35          # Pearson on daily P&L
MAX_BADDAY = 0.40        # Jaccard on shared bad days
MAX_REGIME = 0.90        # cosine on regime-edge profiles
BAD_DAY_FRAC = 0.20      # a "bad day" loses >= this fraction of the DD buffer


def _align(series: list[dict]) -> tuple[list, list[list[float]]]:
    """Union of all dates -> one equal-length vector per candidate (0 = flat)."""
    dates = sorted({d for s in series for d in s})
    return dates, [[float(s.get(d, 0.0)) for d in dates] for s in series]


def pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return max(-1.0, min(1.0, cov / math.sqrt(va * vb)))


def bad_days(daily: dict, drawdown: float, frac: float = BAD_DAY_FRAC) -> set:
    """Days this strategy lost >= frac of the account's drawdown buffer."""
    cut = -abs(drawdown) * frac
    return {d for d, v in daily.items() if float(v) <= cut}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    u = len(a | b)
    return (len(a & b) / u) if u else 0.0


def regime_cosine(pa: dict, pb: dict) -> float:
    """Cosine similarity of two per-regime edge profiles (net per regime).
    1.0 = earns in exactly the same regimes; 0 = disjoint. Only the positive
    part counts — where a strategy LOSES is not an edge to diversify."""
    if not pa or not pb:
        return 0.0
    keys = set(pa) | set(pb)
    va = [max(float((pa.get(k) or {}).get("net", 0.0)), 0.0) for k in keys]
    vb = [max(float((pb.get(k) or {}).get("net", 0.0)), 0.0) for k in keys]
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(x * x for x in vb))
    if na <= 0 or nb <= 0:
        return 0.0
    return sum(va[i] * vb[i] for i in range(len(keys))) / (na * nb)


def analyse(cands: list[dict], drawdown: float = 2_500.0,
            max_corr: float = MAX_CORR, max_badday: float = MAX_BADDAY,
            max_regime: float = MAX_REGIME, bad_frac: float = BAD_DAY_FRAC) -> dict:
    """cands: records with {name, edge, daily, regime_profile}. Returns
    {selected, rejected, matrix, n} — selected is the decorrelated set."""
    n = len(cands)
    if n == 0:
        return {"selected": [], "rejected": [], "matrix": [], "n": 0}

    _dates, vecs = _align([c.get("daily") or {} for c in cands])
    bads = [bad_days(c.get("daily") or {}, drawdown, bad_frac) for c in cands]

    corr = [[0.0] * n for _ in range(n)]
    over = [[0.0] * n for _ in range(n)]
    reg = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            corr[i][j] = corr[j][i] = round(pearson(vecs[i], vecs[j]), 3)
            over[i][j] = over[j][i] = round(jaccard(bads[i], bads[j]), 3)
            reg[i][j] = reg[j][i] = round(regime_cosine(cands[i].get("regime_profile") or {},
                                                        cands[j].get("regime_profile") or {}), 3)

    order = sorted(range(n), key=lambda i: -(cands[i].get("edge") or 0.0))
    selected, rejected = [], []
    for i in order:
        clash = None
        for k in selected:
            if corr[i][k] > max_corr:
                clash = ("return correlation", corr[i][k], max_corr, k)
            elif over[i][k] > max_badday:
                clash = ("shared bad days", over[i][k], max_badday, k)
            elif reg[i][k] > max_regime:
                clash = ("same regimes", reg[i][k], max_regime, k)
            if clash:
                break
        if clash:
            what, val, lim, k = clash
            rejected.append({"name": cands[i]["name"], "edge": cands[i].get("edge"),
                             "reason": what, "value": val, "limit": lim,
                             "clashes_with": cands[k]["name"],
                             "message": (f"{what} {val} with {cands[k]['name']} "
                                         f"(limit {lim}) — same trade under another name")})
        else:
            selected.append(i)

    return {
        "n": n,
        "selected": [{"name": cands[i]["name"], "edge": cands[i].get("edge"),
                      "bad_days": len(bads[i]),
                      "top_regimes": _top_regimes(cands[i].get("regime_profile") or {})}
                     for i in selected],
        "rejected": rejected,
        "matrix": {"names": [c["name"] for c in cands],
                   "corr": corr, "bad_day_overlap": over, "regime": reg},
        "thresholds": {"max_corr": max_corr, "max_badday": max_badday,
                       "max_regime": max_regime, "bad_day_frac": bad_frac,
                       "drawdown": drawdown},
    }


def _top_regimes(profile: dict, k: int = 2) -> list:
    pos = [(r, float((m or {}).get("net", 0.0))) for r, m in profile.items()]
    pos = [p for p in pos if p[1] > 0]
    pos.sort(key=lambda p: -p[1])
    return [r for r, _ in pos[:k]]


def from_verified(path: str, only_passed: bool = True) -> list[dict]:
    """Read verified_seedN.json into the record shape analyse() expects."""
    data = json.loads(open(path).read())
    out = []
    for r in data:
        v = r.get("verdict") or {}
        if only_passed and not v.get("pass"):
            continue
        k = r.get("kpis_oos") or {}
        out.append({"name": (r.get("spec") or {}).get("name", "?"),
                    "edge": k.get("net_profit", 0.0),
                    "daily": r.get("daily_oos") or {},
                    "regime_profile": r.get("edge_by_regime") or {}})
    return out


def main():
    ap = argparse.ArgumentParser(description="Decorrelated portfolio selection from OOS survivors.")
    ap.add_argument("--verified", required=True, help="verified_seedN.json from backtest.verify")
    ap.add_argument("--all", action="store_true", help="include candidates that failed the OOS gate")
    ap.add_argument("--drawdown", type=float, default=2_500.0, help="account DD buffer for 'bad day'")
    ap.add_argument("--max-corr", type=float, default=MAX_CORR)
    ap.add_argument("--max-badday", type=float, default=MAX_BADDAY)
    ap.add_argument("--max-regime", type=float, default=MAX_REGIME)
    args = ap.parse_args()

    cands = from_verified(args.verified, only_passed=not args.all)
    if not cands:
        print("no candidates (did verify run, and did anything pass?)")
        return
    missing = [c["name"] for c in cands if not c["daily"]]
    if missing:
        print(f"  note: {len(missing)} candidate(s) carry no daily series — re-run verify "
              f"to record it (they cannot be correlated and are skipped)")
        cands = [c for c in cands if c["daily"]]
    if not cands:
        return

    out = analyse(cands, drawdown=args.drawdown, max_corr=args.max_corr,
                  max_badday=args.max_badday, max_regime=args.max_regime)
    print(f"\n  PORTFOLIO: {len(out['selected'])} decorrelated of {out['n']} survivors")
    print(f"  vetoes: positive corr <= {args.max_corr} (negative is welcome) · "
          f"shared bad days <= {args.max_badday} · regime overlap <= {args.max_regime}\n")
    for s in out["selected"]:
        regs = (", ".join(s["top_regimes"]) or "—")
        print(f"    KEEP  {s['name']:<16} net ${s['edge']:>10,.0f}  bad days {s['bad_days']:>3}  earns in: {regs}")
    for r in out["rejected"]:
        print(f"    drop  {r['name']:<16} net ${(r['edge'] or 0):>10,.0f}  {r['message']}")
    print("\n  A set of three genuinely different strategies beats eight variations of one:")
    print("  the dropped ones add size to a position you already hold, not diversification.")
    print("PORTFOLIO_JSON " + json.dumps(out, default=str), flush=True)


if __name__ == "__main__":
    main()
