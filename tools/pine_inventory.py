#!/usr/bin/env python3
"""D-100 — inventory of the Pine surface the live fleet actually uses.

Read-only scan of the 13 released scripts in ``pine/*.pine``. The scripts are one
family, so the hypothesis (spoor B) is that the language surface they use is a small,
enumerable set — and that number decides whether a reimplementation (D-101) is weeks
or months. This counts, per feature: total occurrences across the fleet AND how many
of the 13 scripts use it (ubiquity), so "core" (in all 13) is separable from "tail".

It does NOT mutate anything in ``pine/`` (Pine Dev's map) — it only reads. Run:
    python3 tools/pine_inventory.py            # markdown report to stdout
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

PINE_DIR = Path(__file__).resolve().parent.parent / "pine"

# Namespaced built-in calls: ns.fn( ...
_NS_CALL = re.compile(r"\b(ta|request|str|math|array|matrix|map|strategy|ticker|"
                      r"timeframe|syminfo|session|color|input|chart|runtime|log|"
                      r"time|dayofweek|barstate)\.([a-zA-Z_]\w*)")
# User-defined functions / methods:  name(args) =>
_USER_FN = re.compile(r"^\s*(?:export\s+)?(?:method\s+)?([a-zA-Z_]\w*)\s*\([^\n]*\)\s*=>",
                      re.M)
# Standalone drawing / output / control built-ins (not namespaced)
_BARE = {
    "plot": r"\bplot\s*\(", "plotshape": r"\bplotshape\s*\(",
    "plotchar": r"\bplotchar\s*\(", "plotcandle": r"\bplotcandle\s*\(",
    "bgcolor": r"\bbgcolor\s*\(", "fill": r"\bfill\s*\(", "hline": r"\bhline\s*\(",
    "alertcondition": r"\balertcondition\s*\(", "alert(": r"\balert\s*\(",
    "line.new": r"\bline\.new\b", "label.new": r"\blabel\.new\b",
    "box.new": r"\bbox\.new\b", "table.new": r"\btable\.new\b",
}
# Language constructs
_CONSTRUCT = {
    "if": r"(?m)^\s*if\s|(?<=\s)if\s",
    "else": r"\belse\b",
    "for": r"(?m)^\s*for\s|(?<=\s)for\s",
    "while": r"\bwhile\s",
    "switch": r"\bswitch\b",
    "ternary ?:": r"\?[^\n]{0,120}:",     # approximate, per line
    "var": r"\bvar\s+(?!ip)",
    "varip": r"\bvarip\s+",
    "=> (func/lambda)": r"=>",
    "request.security": r"\brequest\.security\b",
    "[N] history-ref": r"\]\s*(?:$|[^\s=])|\w\[\d+\]",
}
# Built-in series / scalars referenced as bare identifiers
_BUILTINS = ["close", "open", "high", "low", "hl2", "hlc3", "ohlc4", "volume",
             "bar_index", "last_bar_index", "na", "nz", "time", "time_close",
             "timenow", "timeframe.period", "syminfo.mintick", "syminfo.pointvalue"]


def _scripts() -> list[Path]:
    return sorted(p for p in PINE_DIR.glob("*.pine"))


def scan() -> dict:
    scripts = _scripts()
    total = defaultdict(int)          # feature -> total occurrences
    ubiq = defaultdict(set)           # feature -> set of scripts using it
    cats = defaultdict(lambda: defaultdict(int))   # category -> feature -> total
    catubiq = defaultdict(lambda: defaultdict(set))

    def bump(cat, feat, n, sname):
        if n:
            total[feat] += n
            ubiq[feat].add(sname)
            cats[cat][feat] += n
            catubiq[cat][feat].add(sname)

    for p in scripts:
        src = p.read_text(encoding="utf-8", errors="replace")
        # strip line comments so `//` text doesn't inflate counts
        code = "\n".join(re.sub(r"//.*$", "", ln) for ln in src.splitlines())
        s = p.name
        for m in _NS_CALL.finditer(code):
            bump(f"{m.group(1)}.*", f"{m.group(1)}.{m.group(2)}", 1, s)
        for name, pat in _BARE.items():
            bump("drawing/output", name, len(re.findall(pat, code)), s)
        for name, pat in _CONSTRUCT.items():
            bump("constructs", name, len(re.findall(pat, code)), s)
        for name in _BUILTINS:
            bump("built-in vars", name, len(re.findall(r"\b" + re.escape(name) + r"\b", code)), s)
        for m in _USER_FN.finditer(code):
            bump("user functions", m.group(1) + "()", 1, s)
    return {"scripts": [p.name for p in scripts], "total": total, "ubiq": ubiq,
            "cats": cats, "catubiq": catubiq}


def report() -> str:
    r = scan()
    n = len(r["scripts"])
    out = [f"# Pine-surface inventaris — {n} live scripts (D-100)", "",
           f"_Read-only scan van `pine/*.pine`. Gegenereerd door `tools/pine_inventory.py`._",
           "", f"**Scripts ({n}):** " + ", ".join(s.replace('MEX_', '').replace('_v1_0_0.pine', '')
                                                   for s in r["scripts"]), ""]
    # headline: distinct features per category and how many are "core" (all N)
    out.append("## Samenvatting — is de gebruikte taal een kleine, opsombare set?")
    out.append("")
    out.append("| Categorie | Distinct features | In ALLE scripts (core) | Totaal calls |")
    out.append("|---|---|---|---|")
    order = ["ta.*", "request.*", "str.*", "math.*", "array.*", "input.*",
             "strategy.*", "time.*", "session.*", "ticker.*", "timeframe.*",
             "syminfo.*", "color.*", "barstate.*", "dayofweek.*",
             "drawing/output", "constructs", "built-in vars", "user functions"]
    seen = set()
    for cat in order + [c for c in r["cats"] if c not in order]:
        if cat not in r["cats"]:
            continue
        seen.add(cat)
        feats = r["cats"][cat]
        core = sum(1 for f in feats if len(r["catubiq"][cat][f]) == n)
        out.append(f"| `{cat}` | {len(feats)} | {core} | {sum(feats.values())} |")
    out.append("")
    # per category: the features, sorted by ubiquity then frequency
    for cat in order + [c for c in r["cats"] if c not in seen]:
        if cat not in r["cats"]:
            continue
        out.append(f"## `{cat}`")
        out.append("")
        out.append("| feature | scripts | totaal |")
        out.append("|---|---|---|")
        feats = r["cats"][cat]
        for f in sorted(feats, key=lambda k: (-len(r["catubiq"][cat][k]), -feats[k], k)):
            out.append(f"| `{f}` | {len(r['catubiq'][cat][f])}/{n} | {feats[f]} |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
