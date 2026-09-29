#!/usr/bin/env python3
"""D-73 · Meet wat er in PMT's antwoord-body zit.

De vraag onder T2: **draagt PMT's antwoord een fill-prijs, of alleen een
bevestiging van ontvangst?** Zonder deze meting kan de bevestigingslaag
(D-91) niet ontworpen worden — die zou dan een aanname zijn, geen feit.

`routed_*.jsonl` slaat PMT's antwoord vandaag al op onder `result` in de
vorm `"sent <code> (poging <n>) · <body>"` (of `"GEWEIGERD … <body>"`
voor weigeringen). Dit script trekt die body's uit de log, groepeert ze
op vorm, en meldt wat het ziet.

Gebruik:
    python3 middleware/tools/analyze_pmt_bodies.py                     # default /root/intent-store
    python3 middleware/tools/analyze_pmt_bodies.py --dir /pad/naar/log
    python3 middleware/tools/analyze_pmt_bodies.py --samples 20        # aantal voorbeelden per shape
    python3 middleware/tools/analyze_pmt_bodies.py --since 2026-09-01  # alleen files vanaf deze datum

De output eindigt met een oordeel: bevatten de bodies een fill-prijs, of
alleen een confirmatie? Dat oordeel is het antwoord op D-73.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path


# ── extraction ─────────────────────────────────────────────────────────────

# `result` is opgebouwd door ForwardAsync in Program.cs:
#   sent {code} (poging {n}) · {body}          (accepted, met of zonder body)
#   GEWEIGERD {code} door doelserver: {body}   (rejected, altijd met body)
_RESULT_RE = re.compile(
    r"^(?P<verdict>sent \d+|GEWEIGERD \d+)"
    r"(?: \(poging \d+\))?"
    r"(?: (?:·|door doelserver:) (?P<body>.*))?$"
)


def extract_body(result: str) -> tuple[str, str]:
    """→ (verdict, body). Body is een string; leeg als PMT niks stuurde."""
    m = _RESULT_RE.match(result or "")
    if not m:
        return ("other", (result or "").strip())
    return (m.group("verdict"), (m.group("body") or "").strip())


# ── classification ─────────────────────────────────────────────────────────

# Wat maakt een body "fill-info-dragend"? Sleutels of woorden die naar een
# broker-fill wijzen. Bewust breed — beter een vals-positief dan een gemist
# signaal, want dit is een verkennende meting.
_FILL_HINTS = (
    "fill", "price", "avg_price", "avgprice", "avgpx", "fillprice",
    "executed", "executed_price", "executedprice", "execprice", "px",
    "orderid", "order_id", "trade_id", "tradeid", "positionid",
    "quantity_filled", "qty_filled", "quantityfilled",
)

# Wat kenmerkt een pure confirmatie ("we hebben je POST ontvangen")?
_CONFIRM_HINTS = (
    "successfully send", "success", "queued", "accepted", "received",
    "ok", "res", "message",
)

_ERROR_HINTS = (
    "error", "reject", "denied", "invalid", "unauthorized",
    "insufficient", "cap", "limit", "halt",
)


def classify(body: str) -> str:
    low = body.lower()
    has_fill = any(h in low for h in _FILL_HINTS)
    has_err = any(h in low for h in _ERROR_HINTS) and '"error":false' not in low.replace(" ", "")
    if has_fill:
        return "fill-info"
    if has_err:
        return "error"
    if any(h in low for h in _CONFIRM_HINTS):
        return "confirm"
    return "unknown"


def body_shape(body: str) -> str:
    """Compacte weergave van het JSON-schema van de body, voor groepering.
    Niet-JSON body's krijgen "text:<eerste 40 chars>"."""
    if not body:
        return "empty"
    try:
        obj = json.loads(body)
    except Exception:
        return f"text:{body[:40]!r}"
    if isinstance(obj, dict):
        return "{" + ",".join(sorted(obj.keys())) + "}"
    if isinstance(obj, list):
        return f"[{len(obj)} items]"
    return f"scalar:{type(obj).__name__}"


# ── main ──────────────────────────────────────────────────────────────────


def iter_pmt_rows(paths):
    for path in sorted(paths):
        try:
            for line in open(path, encoding="utf-8", errors="replace"):
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("kind") != "pmt":
                    continue
                yield row
        except OSError:
            continue


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=os.environ.get("ROUTED_DIR", "/root/intent-store"))
    ap.add_argument("--samples", type=int, default=20,
                    help="voorbeelden per gevonden body-shape (default 20)")
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="alleen routed_YYYYMMDD.jsonl vanaf deze datum")
    args = ap.parse_args()

    root = Path(args.dir)
    files = glob.glob(str(root / "routed_*.jsonl"))
    if args.since:
        cutoff = args.since.replace("-", "")
        files = [f for f in files if Path(f).stem >= f"routed_{cutoff}"]

    if not files:
        print(f"geen routed_*.jsonl in {root}", file=sys.stderr)
        return 2

    verdict_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    shape_counts: Counter[str] = Counter()
    # examples[shape] = list of (verdict, body, account)
    examples: dict[str, list[tuple[str, str, str]]] = {}

    for row in iter_pmt_rows(files):
        verdict, body = extract_body(row.get("result", ""))
        verdict_counts[verdict] += 1
        cls = classify(body)
        class_counts[cls] += 1
        shape = body_shape(body)
        shape_counts[shape] += 1
        examples.setdefault(shape, [])
        if len(examples[shape]) < args.samples:
            examples[shape].append((verdict, body, row.get("account") or ""))

    total = sum(verdict_counts.values())
    print(f"# D-73 · PMT antwoord-body meting")
    print(f"# {len(files)} bestand(en), {total} PMT-rijen")
    print()

    print("## Verdict (sent / GEWEIGERD / other)")
    for v, n in verdict_counts.most_common():
        print(f"  {v:<20s} {n:>6d}  ({100*n/total:.1f}%)")
    print()

    print("## Classificatie op body-inhoud")
    print("  fill-info  = bevat een fill-prijs, order-id of executed-veld")
    print("  confirm    = pure bevestiging (res/success/ok/queued)")
    print("  error      = weigering of foutveld (uitgezonderd 'error':false)")
    print("  unknown    = leeg of onherkenbaar")
    for c, n in class_counts.most_common():
        print(f"  {c:<10s} {n:>6d}  ({100*n/total:.1f}%)")
    print()

    print(f"## Body-shapes (top 10, sorted by count)")
    for shape, n in shape_counts.most_common(10):
        print(f"  {n:>6d}  {shape}")
    print()

    print(f"## Voorbeelden (tot {args.samples} per shape)")
    for shape, n in shape_counts.most_common(10):
        print(f"\n### {shape}  ({n} rijen)")
        for verdict, body, acct in examples.get(shape, [])[: args.samples]:
            acct_tail = acct[-6:] if acct else "??????"
            print(f"  [{verdict:<12s}] acct=…{acct_tail}  body={body[:180]}")

    print()
    print("## Oordeel")
    fill = class_counts.get("fill-info", 0)
    if fill == 0:
        print("  → PMT-body draagt NOOIT een fill-prijs of order-id.")
        print("    De laag T2 (bevestiging) heeft geen broker-truth-veld in de body;")
        print("    'sent 200' is de HTTP-status van onze POST plus PMT's confirmatie.")
        print("    T3 (fill) MOET dus uit een andere bron komen (Fills-CSV / Rithmic).")
    else:
        pct = 100 * fill / total
        print(f"  → {fill} van {total} bodies ({pct:.1f}%) dragen fill-info-hints.")
        print("    Kijk in bovenstaande voorbeelden welke shape(s) dat zijn en welke")
        print("    velden precies — dat is het T2-oppervlak dat we kunnen bouwen.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
