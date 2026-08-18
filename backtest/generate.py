"""Coarse mill — sample candidates and screen them through the classic lens on
in-sample data, keeping only the survivors (trades >= N, PF >= threshold).

This is stage 1 of the funnel (grof-random). Refine (finer ranges around the
winners) and the one-shot OOS verification are separate stages that consume the
survivors this writes. Every candidate is one whole strategy run intact — the
mill only decides which advance.

    python -m backtest.generate --data <csv> --n 500 --tf 5m --holdout-days 365 \
        --min-trades 100 --min-pf 1.1 --coarse-since 2022-01-01 --lab

Speed note: each candidate is a full engine pass over the in-sample bars. Use
--coarse-since to shrink the coarse window (the gate is a rough first sieve);
verify survivors on the full IS + OOS later.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone

from . import data as data_mod
from . import indicators as ind_mod
from .config import contract
from .engine import Engine
from .generator import sample_batch
from .metrics import kpis
from .scoring import score_strategy
from .spec import (WIRED_GROUPS, describe_config, effective_signature, load_registry,
                   spec_to_config, validate_spec)


def _cfg_for(spec, registry, asset):
    rspec = validate_spec(spec, registry)
    cfg, unmapped = spec_to_config(rspec)
    if asset:
        cfg = cfg.with_(contract=contract(asset))
    return cfg, unmapped


def run_cfg(cfg, df_tf):
    ind = ind_mod.compute(df_tf, cfg)
    return kpis(Engine(cfg, df_tf, ind, research_mode=True).run())


# The coarse in-sample frame, handed to each worker once via the pool
# initializer (robust across fork/spawn start methods — not fork-inheritance).
_G_DF = None


def _pool_init(df):
    global _G_DF
    _G_DF = df


def _screen_cfg(cfg):
    """Worker: run one candidate on the shared coarse frame. Returns its KPIs."""
    return run_cfg(cfg, _G_DF)


def run_classic(spec, registry, df_tf, asset):
    """Run one candidate spec through the classic lens on a prepared tf frame."""
    cfg, _ = _cfg_for(spec, registry, asset)
    return run_cfg(cfg, df_tf)


def main():
    ap = argparse.ArgumentParser(description="Coarse mill: sample + screen candidates on in-sample.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--n", type=int, default=200, help="candidates to sample")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--holdout-days", type=int, default=365, help="OOS holdout (excluded from the screen)")
    ap.add_argument("--coarse-since", help="limit the coarse screen to data on/after this date (speed)")
    ap.add_argument("--min-trades", type=int, default=100)
    ap.add_argument("--min-pf", type=float, default=1.1)
    ap.add_argument("--jobs", type=int, default=0,
                    help="parallel worker processes for the screen (0 = all CPU cores). "
                         "Big speed-up on 1m data.")
    ap.add_argument("--price-action-only", action="store_true")
    ap.add_argument("--max-groups", type=int, default=5)
    ap.add_argument("--base-preset", default="",
                    help="pin engine mechanics (TP/stop/sizing) to this preset; empty = "
                         "SAMPLE neutral mechanics per candidate (discovered, not assumed)")
    ap.add_argument("--base-asset", default="NQ")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--top", type=int, default=50, help="how many survivors to record")
    ap.add_argument("--include-unwired", action="store_true",
                    help="also sample engine:todo indicators (inert today — for experiments only)")
    ap.add_argument("--sampler", choices=["role", "random"], default="role",
                    help="role = framework role-composer (default); random = legacy random-subset")
    ap.add_argument("--regimes", default="",
                    help="comma-separated regime hints to spread role-composed candidates across "
                         "(e.g. 'Strong Bull Trend,Low-Volatility Range'); empty = unbiased")
    ap.add_argument("--setup-class", default="",
                    help="constrain the search to ONE thesis (trend_pullback|breakout|"
                         "mean_reversion|reversal|confluence); empty = discover across all")
    ap.add_argument("--lab", action="store_true", help="record survivors + a candidates summary in $LAB_DIR")
    args = ap.parse_args()

    registry = load_registry()
    print(f"loading {args.data} ...")
    df = data_mod.load(args.data)
    if args.coarse_since:
        df = data_mod.slice_dates(df, since=args.coarse_since)
    is_df, _oos, cut = data_mod.holdout_split(df, args.holdout_days)
    df_tf = is_df if args.tf == "1m" else data_mod.resample_tf(is_df, args.tf)
    print(f"  IS coarse window: {df_tf['et'].iloc[0]} -> {df_tf['et'].iloc[-1]}  "
          f"({len(df_tf):,} {args.tf} bars; last {args.holdout_days}d held out for OOS)")

    if args.sampler == "role":
        from .generator import compose_batch
        regimes = [r.strip() for r in args.regimes.split(",") if r.strip()] or None
        setup_class = args.setup_class.strip() or None
        kw = {"setup_class": setup_class} if setup_class else {}
        batch = compose_batch(args.n, registry, seed=args.seed, base_asset=args.base_asset,
                              timeframe=args.tf, price_action_only=args.price_action_only,
                              base_preset=(args.base_preset or None), regimes=regimes, **kw)
        classes = {}
        for s in batch:
            classes[s.get("setup_class", "?")] = classes.get(s.get("setup_class", "?"), 0) + 1
        thesis = f"thesis={setup_class}" if setup_class else "all theses"
        print(f"  role-composer (framework §4), {thesis}: one slot per layer, redundancy-guarded. "
              f"filters/entries are DISCOVERED. setup-classes {classes}"
              + (f"; regimes {regimes}" if regimes else ""))
    else:
        batch = sample_batch(args.n, registry, seed=args.seed, base_asset=args.base_asset,
                             timeframe=args.tf, price_action_only=args.price_action_only,
                             max_groups=args.max_groups, base_preset=args.base_preset,
                             wired_only=not args.include_unwired)
        if args.include_unwired:
            print("  WARNING: --include-unwired samples engine:todo indicators that are inert today; "
                  "candidates collapse to their wired core (dedup below still applies).")
        else:
            print(f"  honest search: only wired indicators {list(WIRED_GROUPS)} "
                  f"(engine:todo blocks not searched — grow via the wiring roadmap)")
    print(f"  sampled {len(batch)} candidates; screening (min trades {args.min_trades}, "
          f"PF {args.min_pf}) ...")

    # Pass 1 (cheap, serial): build cfgs and collapse inert-only duplicates.
    uniq, seen, dups, errors = [], set(), 0, 0
    for spec in batch:
        try:
            cfg, _ = _cfg_for(spec, registry, args.base_asset)
            sig = effective_signature(cfg)
            if sig in seen:
                dups += 1
                continue
            seen.add(sig)
            uniq.append((spec, cfg))
        except Exception:
            errors += 1

    # Pass 2 (the expensive part): run each unique candidate through the engine,
    # spread across worker processes. Each worker gets the coarse frame once via
    # the pool initializer (robust across fork/spawn), so only the small Config
    # is sent per task.
    jobs = args.jobs if args.jobs and args.jobs > 0 else (os.cpu_count() or 1)
    survivors, t0, first_err = [], time.time(), None
    print(f"  screening {len(uniq)} distinct candidates on {jobs} core(s) "
          f"({dups} inert dups collapsed) ...")

    def _consume(k, spec, cfg):
        if (k.get("trades") or 0) >= args.min_trades and (k.get("profit_factor") or 0) >= args.min_pf:
            ignored = [g for g in spec["groups"] if g not in WIRED_GROUPS]
            sc = score_strategy(describe_config(cfg), regime=spec.get("target_regime"),
                                setup_class=spec.get("setup_class"))
            survivors.append({"spec": spec, "kpis": k, "ignored": ignored, "score": sc})

    ntot = len(uniq)
    if jobs <= 1:                       # serial path (debug / single core)
        _pool_init(df_tf)
        for done, (spec, cfg) in enumerate(uniq, 1):
            try:
                _consume(_screen_cfg(cfg), spec, cfg)
            except Exception as e:
                errors += 1
                first_err = first_err or repr(e)
            print(f"PROGRESS {done} {ntot} screening · survivors={len(survivors)} "
                  f"errors={errors}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=jobs, initializer=_pool_init,
                                 initargs=(df_tf,)) as ex:
            futs = {ex.submit(_screen_cfg, cfg): i for i, (spec, cfg) in enumerate(uniq)}
            for done, fut in enumerate(as_completed(futs), 1):
                spec, cfg = uniq[futs[fut]]
                try:
                    _consume(fut.result(), spec, cfg)
                except Exception as e:
                    errors += 1
                    first_err = first_err or repr(e)
                print(f"PROGRESS {done} {ntot} screening · survivors={len(survivors)} "
                      f"errors={errors}", flush=True)
                if done % 25 == 0:
                    print(f"    {done}/{ntot}  survivors={len(survivors)}  "
                          f"errors={errors}  ({time.time()-t0:.0f}s)")

    if errors:
        print(f"  note: {errors} candidate(s) errored; first: {first_err}")
    seen = uniq   # for the DONE line's distinct-count
    survivors.sort(key=lambda s: s["kpis"].get("profit_factor", 0), reverse=True)
    print(f"\n  DONE: {len(survivors)} survivors of {len(seen)} DISTINCT effective configs "
          f"({len(batch)} sampled, {dups} inert dups collapsed, {errors} errored, {time.time()-t0:.0f}s)")
    for s in survivors[:min(args.top, 20)]:
        k = s["kpis"]
        g = (s.get("score") or {}).get("grade", "?")
        sc = (s.get("score") or {}).get("score", 0)
        setup = s["spec"].get("setup_class", "")
        mech = s["spec"].get("base_preset", "")
        print(f"    PF {k['profit_factor']:.2f}  win {k.get('win_rate_pct', 0)}%  "
              f"trades {k['trades']}  net ${k['net_profit']:,.0f}  "
              f"[{g} {sc} · {setup} · {mech}]  {list(s['spec']['groups'])}")

    if args.lab:
        from .lab.runs import fingerprint, make_run_id, record_run
        from .lab.paths import lab_root, ensure_dirs
        ensure_dirs()
        for s in survivors[:args.top]:
            spec, k = s["spec"], s["kpis"]
            fp = fingerprint({"groups": spec["groups"], "tf": args.tf, "seg": "is", "asset": args.base_asset})
            rid = make_run_id(args.base_asset, spec["name"], args.tf, "classic", fp)
            record_run({"run_id": rid, "asset": args.base_asset, "strategy": spec["name"],
                        "timeframe": args.tf, "lens": "classic", "segment": "is", "kind": "generated",
                        "source": f"generator:seed{args.seed}", "window": {},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "kpis": k, "groups": spec["groups"], "ignored": s.get("ignored", []),
                        "score": s.get("score"), "setup_class": spec.get("setup_class"),
                        "target_regime": spec.get("target_regime")},
                       {"kpis.json": json.dumps(k, default=str)})
        summ = lab_root() / f"candidates_seed{args.seed}.json"
        summ.write_text(json.dumps([{"spec": s["spec"], "kpis_is": s["kpis"],
                                     "ignored": s.get("ignored", [])} for s in survivors],
                                   indent=2, default=str))
        print(f"  recorded top {min(len(survivors), args.top)} survivors + summary -> {summ}")


if __name__ == "__main__":
    main()
