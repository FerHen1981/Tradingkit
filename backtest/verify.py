"""One-shot OOS verification — the overfit gate.

Takes the coarse mill's survivors and scores each on the held-out out-of-sample
window, then reports its coarse in-sample PF (the window the mill selected on,
carried in candidates_seedN.json) next to the fresh OOS PF. Only candidates
whose edge survives OOS (enough trades, PF above threshold, and PF not
collapsing vs IS) are real; the rest won the in-sample lottery.

    python -m backtest.verify --data <csv> \
        --candidates $LAB_DIR/candidates_seed0.json --tf 5m --holdout-days 365 --lab

By default IS is REUSED from the candidates file (the coarse window the mill
optimized on) so verify runs only the OOS pass per candidate — roughly half the
work, and the methodologically correct comparison (coarse-IS vs untouched OOS).
Pass --recompute-is to re-run the full in-sample span instead (slower; dilutes
the coarse edge with bars the mill never saw).

This consumes the OOS window ONCE. Re-running tweaked variants against the same
OOS window is p-hacking — sample a fresh batch instead.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone


# The verification frames, handed to each worker once via the pool initializer
# (robust across fork/spawn start methods — same pattern as generate.py). Each
# task then only ships the small Config, not the 20-year frames. _IS_DF stays
# None unless --recompute-is is set (default reuses the stored coarse IS).
_IS_DF = None
_OOS_DF = None


def _pool_init(is_df, oos_df):
    global _IS_DF, _OOS_DF
    _IS_DF, _OOS_DF = is_df, oos_df


def _verify_cfg(cfg):
    """Worker: score one candidate on the shared OOS frame. Returns kpis_oos."""
    from .generate import run_cfg
    return run_cfg(cfg, _OOS_DF)


def _verify_cfg_both(cfg):
    """Worker (--recompute-is): run on BOTH frames. Returns (kpis_is, kpis_oos)."""
    from .generate import run_cfg
    return run_cfg(cfg, _IS_DF), run_cfg(cfg, _OOS_DF)


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
    ap.add_argument("--jobs", type=int, default=0,
                    help="parallel worker processes (0 = all CPU cores). Big speed-up on 1m data.")
    ap.add_argument("--recompute-is", action="store_true",
                    help="re-run the full in-sample span instead of reusing the coarse IS "
                         "carried in the candidates file (slower; default reuses it)")
    ap.add_argument("--lab", action="store_true")
    args = ap.parse_args()

    from . import data as data_mod
    from .generate import _cfg_for
    from .spec import load_registry

    registry = load_registry()
    cands = json.loads(open(args.candidates).read())
    reuse_is = not args.recompute_is
    print(f"loading {args.data} ... ({len(cands)} candidates; "
          f"{'reusing coarse IS' if reuse_is else 'recomputing full IS'})")
    print("PROGRESS 0 100 loading dataset (cached after the first load)", flush=True)
    if reuse_is:
        # only the OOS tail is actually run — load a slice that safely covers the
        # holdout instead of holding the whole 20y frame in memory.
        years = max(2, int(args.holdout_days / 365) + 1)
        df = data_mod.load_window(args.data, years=years)
    else:
        df = data_mod.load(args.data)
    is_df, oos_df, cut = data_mod.holdout_split(df, args.holdout_days)
    oos_tf = oos_df if args.tf == "1m" else data_mod.resample_tf(oos_df, args.tf)
    # IS frame is only built when recomputing; otherwise we reuse the stored
    # coarse KPIs and skip the (expensive) 19-year resample entirely.
    is_tf = None
    if args.recompute_is:
        is_tf = is_df if args.tf == "1m" else data_mod.resample_tf(is_df, args.tf)
    isw = {"first": str(is_df["et"].iloc[0])[:19], "last": str(is_df["et"].iloc[-1])[:19], "bars_1m": len(is_df)}
    oosw = {"first": str(oos_tf["et"].iloc[0])[:19], "last": str(oos_tf["et"].iloc[-1])[:19], "bars_1m": len(oos_df)}
    if reuse_is:
        print(f"  IS = coarse window from the candidates file (reused)  |  "
              f"OOS {oosw['first']}->{oosw['last']}")
    else:
        print(f"  IS {isw['first']}->{isw['last']}  |  OOS {oosw['first']}->{oosw['last']}")

    recs = []
    if args.lab:
        from .lab.runs import fingerprint, make_run_id, record_run
        from .lab.paths import ensure_dirs, lab_root
        ensure_dirs()

    # Pass 1 (cheap, serial): build the cfg and grab the stored coarse IS KPIs.
    prepared, errors, missing_is = [], 0, 0
    for c in cands:
        spec = c["spec"]
        try:
            cfg, _ = _cfg_for(spec, registry, args.base_asset)
            kis_stored = c.get("kpis_is") or c.get("kpis") or {}
            if reuse_is and not kis_stored:
                missing_is += 1
            prepared.append((spec, cfg, kis_stored))
        except Exception:
            errors += 1
    if reuse_is and missing_is:
        print(f"  note: {missing_is} candidate(s) had no stored IS KPIs "
              f"(their retain ratio will read 0 — regenerate or use --recompute-is)")

    # Pass 2 (the expensive part): score each candidate on OOS across worker
    # processes. Workers get the OOS frame (and IS frame only if --recompute-is)
    # once via the pool initializer, so only the small Config ships per task.
    jobs = args.jobs if args.jobs and args.jobs > 0 else (os.cpu_count() or 1)
    t0 = time.time()
    print(f"  verifying {len(prepared)} candidates on {jobs} core(s) "
          f"({'OOS pass only' if reuse_is else 'IS+OOS passes'}) ...")

    def _record(spec, kis, koos):
        v = _verdict(kis, koos, args.min_oos_trades, args.min_oos_pf, args.retain)
        recs.append({"spec": spec, "kpis_is": kis, "kpis_oos": koos, "verdict": v})
        if args.lab:
            segs = (("oos", koos, oosw),) if reuse_is else (("is", kis, isw), ("oos", koos, oosw))
            for seg, k, win in segs:
                fp = fingerprint({"groups": spec["groups"], "tf": args.tf, "seg": seg,
                                  "asset": args.base_asset, "data": data_mod.dataset_id(args.data)})
                rid = make_run_id(args.base_asset, spec["name"], args.tf, "classic", fp)
                record_run({"run_id": rid, "asset": args.base_asset, "strategy": spec["name"],
                            "timeframe": args.tf, "lens": "classic", "segment": seg, "kind": "generated",
                            "source": "verify", "window": win, "groups": spec["groups"],
                            "created_at": datetime.now(timezone.utc).isoformat(), "kpis": k},
                           {"kpis.json": json.dumps(k, default=str)})

    worker = _verify_cfg_both if args.recompute_is else _verify_cfg

    def _unpack(result, kis_stored):
        # both-mode returns (kis, koos); OOS-only mode returns koos.
        return result if args.recompute_is else (kis_stored, result)

    ntot = len(prepared)
    if jobs <= 1:                       # serial path (debug / single core)
        _pool_init(is_tf, oos_tf)
        for i, (spec, cfg, kis_stored) in enumerate(prepared, 1):
            try:
                kis, koos = _unpack(worker(cfg), kis_stored)
            except Exception:
                errors += 1
                continue
            _record(spec, kis, koos)
            npass = sum(1 for r in recs if r['verdict']['pass'])
            print(f"PROGRESS {i} {ntot} verify OOS · survivors={npass}", flush=True)
            if i % 5 == 0:
                print(f"    {i}/{ntot}  survivors={npass}  ({time.time()-t0:.0f}s)", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=jobs, initializer=_pool_init,
                                 initargs=(is_tf, oos_tf)) as ex:
            futs = {ex.submit(worker, cfg): i for i, (spec, cfg, _k) in enumerate(prepared)}
            for done, fut in enumerate(as_completed(futs), 1):
                spec, cfg, kis_stored = prepared[futs[fut]]
                try:
                    kis, koos = _unpack(fut.result(), kis_stored)
                except Exception:
                    errors += 1
                    continue
                _record(spec, kis, koos)
                npass = sum(1 for r in recs if r['verdict']['pass'])
                print(f"PROGRESS {done} {ntot} verify OOS · survivors={npass}", flush=True)
                if done % 5 == 0:
                    print(f"    {done}/{ntot}  survivors={npass}  ({time.time()-t0:.0f}s)", flush=True)

    if errors:
        print(f"  note: {errors} candidate(s) errored/skipped")
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
