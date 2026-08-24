#!/usr/bin/env python3
"""Auto-generate the Pine `PropFirms` library from data/propfirms.json.

Single source of truth: edit data/propfirms.json, re-run this, and the Python
backtester, the Pine library and the eight strategy files all stay in sync.

Emits pine/lib/PropFirms.pine, and rewrites two generated regions inside every
strategy file: the "Firm program" dropdown and the inline f_firmRules() body.
The strategies carry an inline copy rather than importing the library, because a
Pine library has to be published on TradingView before a script can import it.

    python3 tools/gen_pine_firms.py

The generated library exports:
    rules(preset) -> [ddType, maxLoss, goal, dll, consPct, acctSize]  (all the
    account inputs the strategy needs); ddType is "Intraday" | "EOD" | "Static".
"""
from __future__ import annotations

import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
from backtest import firms  # noqa: E402
from backtest.config import CONTRACTS  # noqa: E402  -- THE source for contract specs (D-08)

# Which contract each script actually trades, per the Operating Schema in CLAUDE.md: funded runs
# the edge on MICROS, eval accounts are pass-hunters on the full MINIS. Drives the compile-time
# commission constant, which Pine's strategy() will not take as an expression.
ASSET_DEFAULT = {
    "MEX_EL_TESORO.pine":  "MGC",   # GC funded  -> micro
    "MEX_EL_REY.pine":     "MES",   # ES funded  -> micro
    "MEX_EL_PATRON.pine":  "MNQ",   # NQ funded  -> micro
    "MEX_EL_DORADO.pine":  "MNQ",   # NQ funded  -> micro
    "MEX_EL_MINERO.pine":  "GC",    # GC eval    -> mini
    "MEX_EL_LEON.pine":    "ES",    # ES eval    -> mini
    "MEX_EL_MATADOR.pine": "NQ",    # NQ eval    -> mini
}

# The 24-08 fleet. Only the commission is generated for these: their firm-rules region and
# firmPreset are deliberately left alone, because repointing those rewrites account rules on
# scripts that are about to go live. Path is relative to pine/.
# Kosten komen uit de registry -- besluit Ferry 24-08: `backtest/config.py` is leidend en
# overruled zowel de pakketaanname ($0,51) als elk hand-getypt getal.
FLEET_ASSET = {
    "v1_0_0/MEX_EL_TESORO_MGC_CON_EOD_v1_0_0.pine":    "MGC",
    "v1_0_0/MEX_EL_PATRON_MGC_AGG_EOD_v1_0_0.pine":    "MGC",
    "v1_0_0/MEX_EL_REY_MNQ_PROD_EOD_v1_0_0.pine":      "MNQ",
    "v1_0_0/MEX_EL_REY_MNQ_PROD_INTRA_v1_0_0.pine":    "MNQ",
    "v1_0_0/MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0.pine":  "MES",
    "v1_0_0/MEX_EL_LEON_MYM_PROD_EOD_v1_0_0.pine":     "MYM",
    "v1_0_0/MEX_EL_LEON_MYM_CON_EOD_Q2_v1_0_0.pine":   "MYM",
    "v1_0_0/MEX_EL_LEON_MYM_CON_INTRA_Q2_v1_0_0.pine": "MYM",
    "v1_0_0/MEX_EL_BANDIDO_MYM_HF_EOD_v1_0_0.pine":    "MYM",
    # EL TORO is eval-only and trades the full minis, not the micros.
    "MEX_EL_TORO_NQ_HF_INTRA_v1_0_0.pine":             "NQ",
    "MEX_EL_TORO_NQ_SNIPER_INTRA_v1_0_0.pine":         "NQ",
    "MEX_EL_TORO_ES_FAST_INTRA_v1_0_0.pine":           "ES",
    "MEX_EL_TORO_GC_SNIPER_EOD_v1_0_0.pine":           "GC",
}


def patch_fleet_commission() -> None:
    """Write each fleet script's commission from backtest/config.py (D-08: one source)."""
    for rel, asset in sorted(FLEET_ASSET.items()):
        path = os.path.join(PINE, rel)
        if not os.path.exists(path):
            print(f"  OVERGESLAGEN {rel} — bestaat niet")
            continue
        if asset not in CONTRACTS:
            raise SystemExit(f"{rel}: onbekend contract {asset} in backtest/config.py")
        comm = float(CONTRACTS[asset].commission_per_contract)
        lines = open(path, encoding="utf-8").read().split("\n")
        for k, l in enumerate(lines):
            if "commission_type=strategy.commission.cash_per_contract" in l:
                before = re.search(r"commission_value=([0-9.]+)", l)
                lines[k] = re.sub(r"commission_value=[0-9.]+", "commission_value=%s" % comm, l)
                open(path, "w", encoding="utf-8").write("\n".join(lines))
                was = before.group(1) if before else "?"
                mark = "" if was == str(comm) else f"   <-- was {was}"
                print(f"  {os.path.basename(rel):48} {asset:4} {comm}{mark}")
                break
        else:
            print(f"  GEEN commission_value-regel in {rel}")


OUT = os.path.join(REPO, "pine", "lib", "PropFirms.pine")
PINE = os.path.join(REPO, "pine")

# Each strategy opens on the firm program that matches its own phase and drawdown model.
# Before this was generated, all eight defaulted to apex_50k_eod_eval -- including the four
# funded scripts and the two intraday ones, so switching the preset on rewrote their account
# rules to an eval account's.
# EL TORO staat hier NIET meer in: sinds 24-08 is hij vier v1_0_0-bestanden
# (NQ HF/SNIPER, ES FAST, GC SNIPER) en is de v6.9.5 naar pine/history/ verhuisd. Deze
# generator kent de v1_0_0-lijn nog niet -- zie docs/inbox.md item 18 voor wat dat kost.
STRATEGY_DEFAULT = {
    "MEX_EL_TESORO.pine":  "apex_50k_eod_pa",        # GC funded, EOD
    "MEX_EL_REY.pine":     "apex_50k_eod_pa",        # ES funded, EOD
    "MEX_EL_PATRON.pine":  "apex_50k_eod_pa",        # NQ funded, EOD
    "MEX_EL_DORADO.pine":  "apex_intraday_pa",       # NQ funded, intraday
    "MEX_EL_MINERO.pine":  "apex_50k_eod_eval",      # GC eval, EOD
    "MEX_EL_LEON.pine":    "apex_50k_eod_eval",      # ES eval, EOD
    "MEX_EL_MATADOR.pine": "apex_50k_eod_eval",      # NQ eval, EOD
}


def tradeable(p):
    """Programs a futures strategy can actually be run against: futures, trailing drawdown.
    Static-drawdown and forex programs stay in the library but out of the strategy dropdown."""
    return p.asset_class == "futures" and p.drawdown_type in ("eod_trailing", "intraday_trailing")


_RAW = None


def p_raw(key):
    """The raw registry record for a program key (the Program dataclass drops these fields)."""
    global _RAW
    if _RAW is None:
        import json as _j
        with open(os.path.join(REPO, "data", "propfirms.json"), encoding="utf-8") as fh:
            _RAW = {r["key"]: r for r in _j.load(fh)["programs"]}
    return _RAW.get(key, {})


def patch_strategies(progs):
    """Rewrite the two generated regions in each strategy file."""
    keep = [p for p in progs if tradeable(p)]
    opts = ", ".join(f'"{p.key}"' for p in keep)
    body = ["f_firmRules(string _p) =>",
            '    string _dd = "Intraday"',
            "    float _ml = 2500.0",
            "    float _g = 3000.0",
            "    float _dll = 1000.0",
            "    float _cons = 50.0"]
    for i, p in enumerate(keep):
        ov = firms.to_overlay(p)
        body += [f'    {"if" if i == 0 else "else if"} _p == "{p.key}"',
                 f'        _dd := "{ov.get("dd_model", "Intraday")}"',
                 f'        _ml := {float(ov.get("acct_trail_dd", 0) or 0)}',
                 f'        _g := {float(ov.get("acct_goal", 0) or 0)}',
                 f'        _dll := {float(ov.get("acct_dll", 0) or 0)}',
                 f'        _cons := {float(ov.get("consistency_pct", 0) or 0)}']
    body.append("    [_dd, _ml, _g, _dll, _cons]")
    # minimum payout per program -- a pure firm rule, never a per-account choice
    body += ["f_firmMinPayout(string _p) =>", "    float _mp = 500.0"]
    emitted = 0
    for p in keep:
        mp = None
        tiers = p_raw(p.key).get("sizes") or []
        pick = next((t for t in tiers if int(t.get("size", 0)) == int(p.account_size)), None) \
            or next((t for t in tiers if t.get("min_payout")), None)
        if pick and pick.get("min_payout"):
            mp = float(pick["min_payout"]["value"])
        if mp is None:
            mp = float((p_raw(p.key).get("funded") or {}).get("min_payout") or 500.0)
        body += ['    %s _p == "%s"' % ("if" if emitted == 0 else "else if", p.key),
                 "        _mp := %s" % mp]
        emitted += 1
    body.append("    _mp")
    # payout ladder per program: the cap on payout number _n (1-based)
    body += ["f_firmLadder(string _p, int _n) =>", "    float[] _l = array.from(1500.0, 1500.0, 2000.0, 2500.0, 2500.0, 3000.0)"]
    emitted = 0
    for p in keep:
        lad = None
        # Pick the tier that matches the program's own account size -- Apex now carries seven
        # sizes and the first one is the 25K, whose ladder is half the 50K's. Taking the first
        # row silently halved every payout cap.
        tiers = p_raw(p.key).get("sizes") or []
        pick = next((t for t in tiers if int(t.get("size", 0)) == int(p.account_size)), None) \
            or next((t for t in tiers if t.get("payout_ladder")), None)
        if pick and pick.get("payout_ladder"):
            lad = [float(x) for x in pick["payout_ladder"]]
        if lad is None:
            lad = [float(x) for x in ((p_raw(p.key).get("funded") or {}).get("payout_ladder") or [])]
        if lad:
            # Count branches actually written, not loop position: the eval programs carry no
            # ladder, so keying off the loop index opened the chain with "else if".
            body += ['    %s _p == "%s"' % ("if" if emitted == 0 else "else if", p.key),
                     "        _l := array.from(%s)" % ", ".join(str(x) for x in lad)]
            emitted += 1
    body.append("    array.get(_l, math.max(0, math.min(_n - 1, array.size(_l) - 1)))")
    # day counters per program: a firm runs TWO of them and they are not the same number.
    # _md = days with FILLS, _pd = days that cleared _qd in profit. Apex legacy: 8 and 5x$50.
    body += ["f_firmDays(string _p) =>", "    int _md = 0", "    int _pd = 0", "    float _qd = 50.0"]
    emitted = 0
    for p in keep:
        tr = p_raw(p.key).get("trading_rules") or {}
        mpd = tr.get("min_profitable_days") or {}
        qd = (mpd.get("min_each") or {}).get("value")
        if qd is None:
            tiers = p_raw(p.key).get("sizes") or []
            pick = next((t for t in tiers if int(t.get("size", 0)) == int(p.account_size)), None) or {}
            qd = (pick.get("qualifying_day_min") or {}).get("value")
        body += ['    %s _p == "%s"' % ("if" if emitted == 0 else "else if", p.key),
                 "        _md := %d" % int(tr.get("min_trading_days") or 0),
                 "        _pd := %d" % int(mpd.get("days") or 0),
                 "        _qd := %s" % float(qd if qd is not None else 50.0)]
        emitted += 1
    body.append("    [_md, _pd, _qd]")
    # contract specs -- generated from backtest/config.py CONTRACTS, THE source (D-08). Pine's
    # strategy() takes only a constant for commission_value, so the header carries the value for
    # this script's own asset and the runtime compares it against the spec of the CHART symbol.
    body += ["f_contractSpec(string _root) =>", "    float _mt = 0.0", "    float _pv = 0.0",
             "    float _cm = 0.0", "    float _sl = 0.0"]
    for i, (sym, c) in enumerate(sorted(CONTRACTS.items())):
        body += ['    %s _root == "%s"' % ("if" if i == 0 else "else if", sym),
                 "        _mt := %s" % float(c.mintick),
                 "        _pv := %s" % float(c.pointvalue),
                 "        _cm := %s" % float(c.commission_per_contract),
                 "        _sl := %s" % float(c.slippage_ticks)]
    body.append("    [_mt, _pv, _cm, _sl]")
    body.append("// <<< GENERATED — do not edit above by hand; run tools/gen_pine_firms.py")

    for name, default in sorted(STRATEGY_DEFAULT.items()):
        path = os.path.join(PINE, name)
        # A renamed or archived script must not take the generator down with it: the fleet moves
        # faster than this map, and a hard crash here leaves every OTHER script unpatched.
        if not os.path.exists(path):
            print(f"  OVERGESLAGEN {name} — bestaat niet meer in pine/; werk de kaarten bij")
            continue
        lines = open(path, encoding="utf-8").read().split("\n")
        i = next(k for k, l in enumerate(lines) if l.startswith("firmPreset    = input.string("))
        tip = lines[i].split("tooltip=", 1)[1]
        lines[i] = (f'firmPreset    = input.string("{default}", "Firm program", options=[{opts}], '
                    f'group=GROUP_PHASE, tooltip={tip}')
        a = next(k for k, l in enumerate(lines) if l.startswith("f_firmRules(string _p) =>"))
        end = next((k for k in range(a, len(lines)) if lines[k].startswith("// <<< GENERATED")), None)
        if end is None:   # first run on a file that still has the hand-written block
            end = next(k for k in range(a, len(lines)) if lines[k].strip() == "[_dd, _ml, _g, _dll, _cons]")
        lines[a:end + 1] = body
        # commission_value from the source, never hand-typed (D-08)
        asset = ASSET_DEFAULT.get(name)
        if asset and asset in CONTRACTS:
            comm = float(CONTRACTS[asset].commission_per_contract)
            for k, l in enumerate(lines):
                if "commission_type=strategy.commission.cash_per_contract" in l:
                    lines[k] = re.sub(r"commission_value=[0-9.]+",
                                      "commission_value=%s" % comm, l)
                    break
            for k, l in enumerate(lines):
                if l.startswith("float SPEC_COMMISSION_SET"):
                    lines[k] = ("float SPEC_COMMISSION_SET = %s    // generated: %s per side, "
                                "from backtest/config.py CONTRACTS" % (comm, asset))
                    break
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        print(f"  patched {name}  default={default}")
        # A firm key that matches no branch does not fail — the lookups silently return their
        # defaults, which on f_firmDays is 0/0: the payout day gate opens for free. That is how
        # a MEX Policy preset naming a pre-rename key went unnoticed on a live chart. Catch it.
        known = {p.key for p in keep}
        used = set(re.findall(r'true,\s*"([a-z0-9_]+)"\]', "\n".join(lines)))
        orphans = sorted(used - known)
        if orphans:
            raise SystemExit(f"{name}: MEX Policy preset names a firm key that is not in the "
                             f"registry: {', '.join(orphans)} — the rules would fall back to "
                             f"defaults. Fix the f_pol table or data/propfirms.json.")
    return len(keep)


def main():
    progs = sorted(firms.REGISTRY.values(), key=lambda p: p.key)
    lines = [
        "// AUTO-GENERATED from data/propfirms.json by tools/gen_pine_firms.py — DO NOT EDIT.",
        "// Single source of truth is the JSON; re-run the generator after editing it.",
        "//@version=6",
        'library("PropFirms")',
        "",
        "// rules(preset) -> [ddType, maxLoss$, goal$, dll$, consPct, acctSize$]",
        "// ddType: \"Intraday\" | \"EOD\" | \"Static\". Feed these into the account inputs.",
        "export rules(string preset) =>",
        '    string ddType = "Intraday"',
        "    float maxLoss = 0.0",
        "    float goal = 0.0",
        "    float dll = 0.0",
        "    float consPct = 0.0",
        "    float acctSize = 0.0",
    ]
    first = True
    for p in progs:
        ov = firms.to_overlay(p)
        ddt = {"Intraday": "Intraday", "EOD": "EOD", "Static": "Static"}.get(ov.get("dd_model", "Intraday"), "Intraday")
        kw = "if" if first else "else if"
        first = False
        lines += [
            f'    {kw} preset == "{p.key}"',
            f'        ddType := "{ddt}"',
            f'        maxLoss := {float(ov.get("acct_trail_dd", 0) or 0)}',
            f'        goal := {float(ov.get("acct_goal", 0) or 0)}',
            f'        dll := {float(ov.get("acct_dll", 0) or 0)}',
            f'        consPct := {float(ov.get("consistency_pct", 0) or 0)}',
            f'        acctSize := {float(p.account_size)}',
        ]
    lines += [
        "    [ddType, maxLoss, goal, dll, consPct, acctSize]",
        "",
        "// Preset keys (for the strategy's input.string options=[...]):",
    ]
    keys = ", ".join(f'"{p.key}"' for p in progs)
    lines.append(f"// {keys}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {OUT}  ({len(progs)} presets)")
    n = patch_strategies(progs)
    print(f"patched {len(STRATEGY_DEFAULT)} strategy files ({n} presets in the dropdown)")
    print("fleet commissions from backtest/config.py:")
    patch_fleet_commission()


if __name__ == "__main__":
    main()
