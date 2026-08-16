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
import time
from datetime import datetime, timezone

from . import data as data_mod
from . import indicators as ind_mod
from .config import contract
from .engine import Engine
from .generator import sample_batch
from .metrics import kpis
from .spec import load_registry, spec_to_config, validate_spec


def _screen_one(spec, registry, df_tf, asset):
    rspec = validate_spec(spec, registry)
    cfg, _ = spec_to_config(rspec)
    if asset:
        cfg = cfg.with_(contract=contract(asset))
    ind = ind_mod.compute(df_tf, cfg)
    res = Engine(cfg, df_tf, ind, research_mode=True).run()
    return kpis(res)


def main():
    ap = argparse.ArgumentParser(description="Coarse mill: sample + screen candidates on in-sample.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--n", type=int, default=200, help="candidates to sample")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--holdout-days", type=int, default=365, help="OOS holdout (excluded from the screen)")
    ap.add_argument("--coarse-since", help="limit the coarse screen to data on/after this date (speed)")
    ap.add_argument("--min-trades", type=int, default=100)
    ap.add_argument("--min-pf", type=float, default=1.1)
    ap.add_argument("--price-action-only", action="store_true")
    ap.add_argument("--max-groups", type=int, default=5)
    ap.add_argument("--base-preset", default="EL_TORO", help="engine mechanics to inherit (TP/entry/sizing)")
    ap.add_argument("--base-asset", default="NQ")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--top", type=int, default=50, help="how many survivors to record")
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

    batch = sample_batch(args.n, registry, seed=args.seed, base_asset=args.base_asset,
                         timeframe=args.tf, price_action_only=args.price_action_only,
                         max_groups=args.max_groups, base_preset=args.base_preset)
    print(f"  sampled {len(batch)} candidates; screening (min trades {args.min_trades}, "
          f"PF {args.min_pf}) ...")

    survivors, errors, t0 = [], 0, time.time()
    for i, spec in enumerate(batch, 1):
        try:
            k = _screen_one(spec, registry, df_tf, args.base_asset)
        except Exception:
            errors += 1
            continue
        if (k.get("trades") or 0) >= args.min_trades and (k.get("profit_factor") or 0) >= args.min_pf:
            survivors.append({"spec": spec, "kpis": k})
        if i % 25 == 0:
            print(f"    {i}/{len(batch)}  survivors={len(survivors)}  errors={errors}  "
                  f"({time.time()-t0:.0f}s)")

    survivors.sort(key=lambda s: s["kpis"].get("profit_factor", 0), reverse=True)
    print(f"\n  DONE: {len(survivors)} survivors of {len(batch)} "
          f"({time.time()-t0:.0f}s, {errors} errored)")
    for s in survivors[:min(args.top, 20)]:
        k = s["kpis"]
        print(f"    PF {k['profit_factor']:.2f}  win {k.get('win_rate_pct', 0)}%  "
              f"trades {k['trades']}  net ${k['net_profit']:,.0f}  {list(s['spec']['groups'])}")

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
                        "kpis": k, "groups": spec["groups"]},
                       {"kpis.json": json.dumps(k, default=str)})
        summ = lab_root() / f"candidates_seed{args.seed}.json"
        summ.write_text(json.dumps([{"name": s["spec"]["name"], "groups": s["spec"]["groups"],
                                     "kpis": s["kpis"]} for s in survivors], indent=2, default=str))
        print(f"  recorded top {min(len(survivors), args.top)} survivors + summary -> {summ}")


if __name__ == "__main__":
    main()
