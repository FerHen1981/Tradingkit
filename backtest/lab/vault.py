"""Vault ingest — adopt indicators from an uploaded Pine script or a text note.

Deterministic and pure-Python: the lab server has no LLM/MCP at runtime, so this
does the DEFINITION side of self-learning (parse + detect + adopt), never the
engine wiring. Two jobs:

  1. Parse a Pine script's `input.*` declarations (name, title, default, bounds,
     options) — an extended version of the parity-guard regex.
  2. Scan the source for which INDICATORS it uses, split into KNOWN (already in
     the registry vocabulary) and UNKNOWN. Known ones map to a strategy spec
     (route B). Unknown ones are adopted into the lab registry overlay as
     `engine: todo` and queued as a WIRING REQUEST for a Claude Code session to
     turn into real engine code (layer 2), reviewed before commit.

Free-text descriptions never adopt directly — they only queue a wiring request,
because turning prose into a registry entry + engine code is the reviewed
Claude-codegen step, not something the deterministic server should guess.

Detection signals (from the fleet's Pine sources): the group constants
`"N · SIGNAL — <name>"` are the authoritative "what this script trades on"; the
`ta.*` call set is used mainly to catch UNKNOWN indicators (a `ta.*` the lab
neither maps nor treats as a primitive — e.g. `ta.vwma`, `ta.hma`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
# SIGNAL group-label keyword -> registry group name.
_GROUP_KNOWN = {
    "fvg": "fvg", "fair value gap": "fvg",
    "volume delta": "cvd_delta", "delta": "cvd_delta", "cvd": "cvd_delta",
    "vwap": "vwap", "bias": "vwap",
}
# ta.* names the lab already recognises — either a real group or a primitive it
# does not need to adopt. Anything NOT here is treated as an unknown indicator.
_TA_RECOGNIZED = {
    # mapped indicators
    "vwap", "ema", "sma", "wma", "rsi", "macd",
    # primitives / plumbing
    "atr", "stdev", "highest", "lowest", "pivothigh", "pivotlow", "barssince",
    "percentrank", "requestvolumedelta", "change", "cum", "rma", "tr", "nz",
    "cross", "crossover", "crossunder", "valuewhen", "sar", "mom", "roc",
    "median", "variance", "dev", "linreg", "correlation", "stoch",
}


# --------------------------------------------------------------------------- #
# Pine input parser (pure Python, no MCP)
# --------------------------------------------------------------------------- #
def _match_paren(src: str, open_idx: int) -> int:
    """Index just past the ')' matching the '(' at open_idx, tracking () and []."""
    depth = 0
    i = open_idx
    n = len(src)
    while i < n:
        c = src[i]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
            if depth == 0:
                return i + 1
        elif c in "\"'":                       # skip string literals
            i += 1
            while i < n and src[i] != c:
                i += 1
        i += 1
    return n


def _split_args(argstr: str) -> list[str]:
    """Top-level comma split, respecting (), [] and string literals."""
    out, depth, buf, i, n = [], 0, [], 0, len(argstr)
    while i < n:
        c = argstr[i]
        if c in "([":
            depth += 1; buf.append(c)
        elif c in ")]":
            depth -= 1; buf.append(c)
        elif c in "\"'":
            buf.append(c); i += 1
            while i < n and argstr[i] != c:
                buf.append(argstr[i]); i += 1
            if i < n:
                buf.append(argstr[i])
        elif c == "," and depth == 0:
            out.append("".join(buf).strip()); buf = []
        else:
            buf.append(c)
        i += 1
    if buf:
        out.append("".join(buf).strip())
    return out


_INPUT_CALL = re.compile(r"input\.(int|float|bool|string)\s*\(")
_KW = re.compile(r"^(\w+)\s*=\s*(.*)$", re.S)
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def _val(tok: str):
    tok = tok.strip()
    if _NUM.match(tok):
        return float(tok) if "." in tok else int(tok)
    if tok in ("true", "false"):
        return tok == "true"
    if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
        return tok[1:-1]
    return tok                                  # identifier / expression, kept raw


def parse_pine_inputs(src: str) -> list[dict]:
    """Every input.* declaration -> {type,title,default,min,max,step,options,var}.

    Richer than the parity-guard regex: it also pulls minval/maxval/step/options,
    which the adoption path needs to seed param bounds."""
    out = []
    for m in _INPUT_CALL.finditer(src):
        typ = m.group(1)
        open_idx = m.end() - 1
        end = _match_paren(src, open_idx)
        args = _split_args(src[open_idx + 1:end - 1])
        pos, kw = [], {}
        for a in args:
            km = _KW.match(a)
            if km and not (a[0] in "\"'"):
                kw[km.group(1)] = km.group(2).strip()
            else:
                pos.append(a)
        # assignment target just before the call, e.g. `contractSize = input.float(...)`
        line_start = src.rfind("\n", 0, m.start()) + 1
        lhs = src[line_start:m.start()]
        var = (lhs.split("=")[0].strip().split()[-1] if "=" in lhs else "")
        rec = {"type": typ, "var": var,
               "default": _val(pos[0]) if pos else None,
               "title": _val(pos[1]) if len(pos) > 1 else _val(kw.get("title", "")),
               "min": _val(kw["minval"]) if "minval" in kw else None,
               "max": _val(kw["maxval"]) if "maxval" in kw else None,
               "step": _val(kw["step"]) if "step" in kw else None,
               "options": None}
        if "options" in kw:
            opt = kw["options"].strip()
            if opt.startswith("[") and opt.endswith("]"):
                rec["options"] = [_val(x) for x in _split_args(opt[1:-1])]
        out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# Indicator scanner
# --------------------------------------------------------------------------- #
_GROUP_LABEL = re.compile(r'GROUP_\w+\s*=\s*"[^"]*SIGNAL\s*[—-]\s*([^"]+)"')
_TA_CALL = re.compile(r"\bta\.([a-zA-Z_]\w*)")


def scan_indicators(src: str) -> dict:
    """KNOWN (in the lab vocabulary) vs UNKNOWN (to adopt) indicators in a script."""
    known: dict[str, str] = {}       # registry group -> evidence label
    for m in _GROUP_LABEL.finditer(src):
        label = m.group(1).strip().lower()
        for kw, group in _GROUP_KNOWN.items():
            if kw in label:
                known[group] = f"group '{m.group(1).strip()}'"
    unknown: dict[str, dict] = {}
    for m in _TA_CALL.finditer(src):
        fn = m.group(1).lower()
        if fn in _TA_RECOGNIZED:
            continue
        unknown.setdefault(f"ta_{fn}", {"ta": fn, "evidence": f"ta.{m.group(1)} call"})
    return {"known": known, "unknown": unknown}


# --------------------------------------------------------------------------- #
# Overlay + request storage
# --------------------------------------------------------------------------- #
def _lab_dir() -> Path:
    import os
    return Path(os.environ.get("LAB_DIR", "/data/lab"))


def _overlay_file() -> Path:
    return _lab_dir() / "adopted_indicators.yaml"


def _requests_dir() -> Path:
    return _lab_dir() / "indicator_requests"


def _load_overlay() -> dict:
    import yaml
    f = _overlay_file()
    if f.exists():
        try:
            return yaml.safe_load(f.read_text()) or {}
        except Exception:
            pass
    return {}


def _save_overlay(ov: dict) -> None:
    import yaml
    f = _overlay_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(ov, sort_keys=False, allow_unicode=True))


def _safe_name(raw: str) -> str:
    s = "".join(c if (c.isalnum() or c in "_-") else "_" for c in raw).strip("_")
    return s.lower() or "adopted"


def adopt_overlay_entry(name: str, *, desc: str, source: str, params: dict | None = None,
                        layer: str = "L6", role: str = "custom",
                        info_category: str = "custom") -> str:
    """Add ONE adopted indicator to the lab overlay (engine: todo). Returns the name.
    Base registry always wins on a name clash — adopted names are namespaced."""
    from .. import spec as spec_mod
    base = spec_mod.load_registry(with_overlay=False)
    existing = set(base.get("price_action") or {}) | set(base.get("classic") or {})
    nm = _safe_name(name)
    if nm in existing:                          # never shadow a sourced group
        nm = "adopted_" + nm
    ov = _load_overlay()
    ov.setdefault("classic", {})[nm] = {
        "desc": desc, "layer": layer, "role": role, "info_category": info_category,
        "price_action": False, "provenance": "adopted", "engine": "todo",
        "source": source,
        "params": params or {"threshold": {"default": 0.0, "min": -100.0,
                                            "max": 100.0, "step": 1.0, "type": "opt"}},
    }
    _save_overlay(ov)
    return nm


def queue_wiring_request(name: str, payload: dict) -> str:
    """Write a wiring request (the input to the layer-2 Claude-codegen step)."""
    d = _requests_dir()
    d.mkdir(parents=True, exist_ok=True)
    nm = _safe_name(name)
    (d / f"{nm}.json").write_text(json.dumps({
        "name": nm,
        "ground_rules": [
            "repaint-free: compute once from confirmed-bar data, no look-ahead",
            "if order-flow: use the canonical OHLCV polarity proxy, never raw Delta",
            "no same-bar fill leakage",
            "emit a per-bar *_dir int array (+1/-1/0) like the other entry indicators",
        ],
        "touchpoints": [
            "config.py: use_* flag + params",
            "indicators.py: compute block writing <name>_dir",
            "engine.py: extract() key + __init__ bind + _entry_* one-liner (_mkt) + roster row",
            "spec.py: _PARAM_MAP / WIRED_GROUPS / labels",
            "registry overlay: engine todo -> implemented (or promote into registry.yaml)",
            "a unit test",
        ],
        **payload,
    }, indent=2))
    return nm


def list_requests() -> list[dict]:
    d = _requests_dir()
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            pass
    return out


def list_adopted() -> list[dict]:
    ov = _load_overlay()
    out = []
    for fam in ("price_action", "classic"):
        for nm, g in (ov.get(fam) or {}).items():
            out.append({"name": nm, "desc": g.get("desc", ""), "engine": g.get("engine"),
                        "source": g.get("source"), "family": fam,
                        "params": list((g.get("params") or {}).keys())})
    return out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _save_spec_from_known(name: str, known_groups: dict, base_asset: str) -> str | None:
    """Route B: build + save a strategy spec from the detected KNOWN groups.
    Returns the saved spec id, or None if nothing usable was detected."""
    import yaml
    from .. import spec as spec_mod
    groups = {g: {} for g in known_groups}
    if not groups:
        return None
    groups.setdefault("swing_stops", {})       # always the L10 protective stop
    spec = {"name": name, "base_asset": base_asset or "NQ",
            "groups": groups,
            "policy": {"price_action_only": False, "max_active_groups": max(4, len(groups))}}
    reg = spec_mod.load_registry()
    spec_mod.validate_spec(spec, reg)          # never write an invalid spec
    from .lab_viewer import _specs_dir
    safe = _safe_name(name)
    if not safe.startswith("custom"):
        safe = "custom_" + safe
    path = _specs_dir() / f"{safe}.yaml"
    path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    return f"spec:{safe}.yaml"


def adopt_pine(src: str, filename: str = "upload.pine") -> dict:
    """Deterministic Pine ingest: known indicators -> a saved spec; unknown ones ->
    adopted into the overlay (engine: todo) + a queued wiring request."""
    stem = _safe_name(Path(filename).stem) or "upload"
    inputs = parse_pine_inputs(src)
    scan = scan_indicators(src)
    known, unknown = scan["known"], scan["unknown"]

    adopted = []
    for nm, info in unknown.items():
        overlay_name = adopt_overlay_entry(
            nm, desc=f"Adopted from {filename}: {info['evidence']}", source="pine")
        queue_wiring_request(overlay_name, {
            "source": "pine", "from_file": filename, "evidence": info["evidence"],
            "ta": info.get("ta"),
            "inputs": [i for i in inputs if info.get("ta", "") and
                       info["ta"] in (str(i.get("var", "")).lower() + str(i.get("title", "")).lower())],
            "desc": f"Indicator {info.get('ta')} referenced by {filename} but not modelled by the lab.",
        })
        adopted.append(overlay_name)

    spec_id = None
    if known:
        spec_id = _save_spec_from_known(f"custom_{stem}", known, base_asset="")
    return {"file": filename, "n_inputs": len(inputs),
            "known": known, "adopted": adopted, "spec": spec_id}


def adopt_text(description: str, name: str) -> dict:
    """Free-text ingest: NEVER adopts directly — queues a wiring request for the
    reviewed Claude-codegen step (turning prose into a registry entry + engine code
    is not something the deterministic server should guess)."""
    nm = queue_wiring_request(name or "described_indicator", {
        "source": "text", "description": description,
        "desc": "User-described indicator; needs a Claude Code session to turn the "
                "description into a registry entry + engine code, reviewed before commit.",
    })
    return {"queued": nm, "source": "text"}


def main(argv=None):
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Vault ingest: adopt indicators from Pine/text.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("pine"); pp.set_defaults(fn="pine")
    pp.add_argument("--file", required=True, help="path to a .pine source")
    pt = sub.add_parser("text"); pt.set_defaults(fn="text")
    pt.add_argument("--name", required=True)
    pt.add_argument("--desc", required=True)
    args = ap.parse_args(argv)
    if args.fn == "pine":
        src = Path(args.file).read_text(encoding="utf-8", errors="replace")
        res = adopt_pine(src, filename=Path(args.file).name)
        print("ADOPT_JSON " + json.dumps(res, default=str), flush=True)
    else:
        res = adopt_text(args.desc, args.name)
        print("ADOPT_JSON " + json.dumps(res, default=str), flush=True)


if __name__ == "__main__":
    main()
