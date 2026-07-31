#!/usr/bin/env python3
"""Auto-generate the Pine `PropFirms` library from data/propfirms.json.

Single source of truth: edit data/propfirms.json, re-run this, and both the
Python backtester and the Pine scripts stay in sync. Emits pine/lib/PropFirms.pine.

    python3 tools/gen_pine_firms.py

The generated library exports:
    rules(preset) -> [ddType, maxLoss, goal, dll, consPct, acctSize]  (all the
    account inputs the strategy needs); ddType is "Intraday" | "EOD" | "Static".
"""
from __future__ import annotations

import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
from backtest import firms  # noqa: E402

OUT = os.path.join(REPO, "pine", "lib", "PropFirms.pine")


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


if __name__ == "__main__":
    main()
