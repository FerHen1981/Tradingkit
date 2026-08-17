"""One-shot OOS verification — the overfit gate.

Takes the coarse mill's survivors and runs each on BOTH the full in-sample span
and the held-out out-of-sample window, then reports IS score next to OOS score.
Only candidates whose edge survives OOS (enough trades, PF above threshold, and
PF not collapsing vs IS) are real; the rest won the in-sample lottery.

    python -m backtest.verify --data <csv> \
        --candidates $LAB_DIR/candidates_seed0.json --tf 5m --holdout-days 365 --lab

This consumes the OOS window ONCE. Re-running tweaked variants against the same
OOS window is p-hacking — sample a fresh batch instead.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone


def _verdict(kis: dict, koos: dict, min_trades: int, min_pf: float, retain: float) -> dict:
    is_pf = kis.get("profit_factor") or 0
    oos_pf = koos.get("profit_factor") or 0
    oos_n = koos.get("trades") or 0
    ratio = round(oos_pf / is_pf, 2) if is_pf > 0 else 0.0
    passed = oos_n >= min_trades and oos_pf >= min_pf and ratio >= retain
    reason = ("holds out of sample" if passed else
              "too few OOS trades" if oos_n < min_trades else
              f"OOS PF {oos_pf:.2f} < {min_pf}" if oos_pf < min_pf else
              f"edge decayed (OOS/IS {ratio:.2f} < {retain})")
    return {"pass": passed, "retain": ratio, "reason": reason,
            "is_pf": round(is_pf, 2), "oos_pf": round(oos_pf, 2), "oos_trades": oos_n}


def main():
    ap = argparse.ArgumentParser(description="One-shot OOS verification of coarse-mill survivors.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--candidates", required=True, help="candidates_seedN.json from backtest.generate")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--holdout-days", type=int, default=365)
    ap.add_argument("--min-oos-trades", type=int, default=20)
    ap.add_argument("--min-oos-pf", type=float, default=1.05)
    ap.add_argument("--retain", type=float, default=0.6, help="OOS PF must be >= retain * IS PF")
    ap.add_argument("--base-asset", default="NQ")
    ap.add_argument("--lab", action="store_true")
    args = ap.parse_args()

    from . import data as data_mod
    from .generate import run_classic
    from .spec import load_registry

    registry = load_registry()
    cands = json.loads(open(args.candidates).read())
    print(f"loading {args.data} ... ({len(cands)} candidates)")
    df = data_mod.load(args.data)
    is_df, oos_df, cut = data_mod.holdout_split(df, args.holdout_days)
    is_tf = is_df if args.tf == "1m" else data_mod.resample_tf(is_df, args.tf)
    oos_tf = oos_df if args.tf == "1m" else data_mod.resample_tf(oos_df, args.tf)
    isw = {"first": str(is_tf["et"].iloc[0])[:19], "last": str(is_tf["et"].iloc[-1])[:19], "bars_1m": len(is_df)}
    oosw = {"first": str(oos_tf["et"].iloc[0])[:19], "last": str(oos_tf["et"].iloc[-1])[:19], "bars_1m": len(oos_df)}
    print(f"  IS {isw['first']}->{isw['last']}  |  OOS {oosw['first']}->{oosw['last']}")

    recs = []
    if args.lab:
        from .lab.runs import fingerprint, make_run_id, record_run
        from .lab.paths import ensure_dirs, lab_root
        ensure_dirs()

    t0 = time.time()
    for i, c in enumerate(cands, 1):
        spec = c["spec"]
        try:
            kis = run_classic(spec, registry, is_tf, args.base_asset)
            koos = run_classic(spec, registry, oos_tf, args.base_asset)
        except Exception:
            continue
        v = _verdict(kis, koos, args.min_oos_trades, args.min_oos_pf, args.retain)
        recs.append({"spec": spec, "kpis_is": kis, "kpis_oos": koos, "verdict": v})
        if args.lab:
            for seg, k, win in (("is", kis, isw), ("oos", koos, oosw)):
                fp = fingerprint({"groups": spec["groups"], "tf": args.tf, "seg": seg, "asset": args.base_asset})
                rid = make_run_id(args.base_asset, spec["name"], args.tf, "classic", fp)
                record_run({"run_id": rid, "asset": args.base_asset, "strategy": spec["name"],
                            "timeframe": args.tf, "lens": "classic", "segment": seg, "kind": "generated",
                            "source": "verify", "window": win, "groups": spec["groups"],
                            "created_at": datetime.now(timezone.utc).isoformat(), "kpis": k},
                           {"kpis.json": json.dumps(k, default=str)})
        if i % 10 == 0:
            print(f"    {i}/{len(cands)}  ({time.time()-t0:.0f}s)")

    recs.sort(key=lambda r: r["verdict"]["oos_pf"], reverse=True)
    survivors = [r for r in recs if r["verdict"]["pass"]]
    print(f"\n  OOS-VERIFIED: {len(survivors)} of {len(recs)} hold out of sample\n")
    print(f"    {'strategy':<20} {'IS PF':>6} {'OOS PF':>7} {'ret':>5} {'OOSn':>5}  verdict")
    for r in recs[:30]:
        v = r["verdict"]
        mark = "PASS" if v["pass"] else "----"
        print(f"    {r['spec']['name']:<20} {v['is_pf']:>6.2f} {v['oos_pf']:>7.2f} "
              f"{v['retain']:>5.2f} {v['oos_trades']:>5}  {mark}  {v['reason']}")

    if args.lab:
        out = lab_root() / (args.candidates.split("/")[-1].replace("candidates", "verified"))
        out.write_text(json.dumps(recs, indent=2, default=str))
        print(f"\n  wrote {out}  ({len(survivors)} fleet candidates)")


if __name__ == "__main__":
    main()
