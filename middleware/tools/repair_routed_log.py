"""Herstel valse GEWEIGERDs in `routed_*.jsonl` (25-08 bug in Rejected()).

Achtergrond: tot commit `be6ab06` matchte `Rejected()` in de .NET-receiver op de
substring `"error"`. Een geslaagd PMT-antwoord luidt echter
`{"res":"Successfully send","error":false}` — het VELD `error` bestaat altijd,
met false erin. Het label werd daarmee ten onrechte `GEWEIGERD 200 door
doelserver` in plaats van `sent 200 (poging 1)`.

Gevolg voor het dashboard: `routed_journal.pair_events_with_report()` accepteert
alleen fills met een bijhorende PMT-regel die met `sent 200` begint (D-46b's
executiepoort). Elke valse GEWEIGERD houdt de bijbehorende FILL uit de LIVE-tab.

Deze tool herschrijft alleen die regels waarvan de body onmiskenbaar succes
signaleert. Blijft af van álle andere GEWEIGERDs (die waren echt) en van álle
sent-regels (die zijn al goed).

Kernregel: **een regel wordt hersteld dan en slechts dan als de bestaande
`result` met `GEWEIGERD` begint EN het response-fragment binnen die regel
`error:false` (en géén `error:true` of `success:false`) draagt**. Zo weigert de
tool zichzelf bij elke andere fout die iemand ooit vergat in te delen.

DRY-RUN default. `--apply` schrijft daadwerkelijk terug, met een `.bak` naast
het bestand als vangnet.

    python3 middleware/tools/repair_routed_log.py /root/intent-store/routed_20260825.jsonl
    python3 middleware/tools/repair_routed_log.py /root/intent-store/routed_20260825.jsonl --apply
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


# Whitelist: patronen die eenduidig succes betekenen.  Alleen wanneer minstens
# één van deze in de result-string staat én geen enkele fout-marker,
# beschouwen we de regel als een valse weigering.
_SUCCESS_TRUE = re.compile(r'"error"\s*:\s*false', re.I)
_SUCCESS_TXT = re.compile(r'successfully\s+send', re.I)

# Blacklist: als een van deze in de result staat, is het gewoon een échte
# weigering en blijft hij staan.
_ERROR_TRUE = re.compile(r'"error"\s*:\s*true|"error"\s*:\s*"[^"]+"', re.I)
_STATUS_FALSE = re.compile(r'"(success|status)"\s*:\s*false', re.I)
_TEXTUAL_ERROR = re.compile(
    r"not found in pool|cannot place|invalid ip|unauthorized|forbidden|"
    r"not allowed|rejected|access is denied",
    re.I,
)


@dataclass
class Report:
    scanned: int = 0
    rewritten: int = 0
    real_geweigerd: int = 0
    already_sent: int = 0
    non_pmt: int = 0
    unparseable: int = 0
    examples: list[str] | None = None

    def __post_init__(self) -> None:
        if self.examples is None:
            self.examples = []

    def line(self) -> str:
        return (
            f"scanned={self.scanned}  rewritten={self.rewritten}  "
            f"real_GEWEIGERD_kept={self.real_geweigerd}  already_sent={self.already_sent}  "
            f"non_pmt={self.non_pmt}  unparseable={self.unparseable}"
        )


def _is_false_weigering(result: str) -> bool:
    """True zodra de result-string zowel een succes-marker draagt als geen enkele
    fout-marker.  Dan is de GEWEIGERD-label onterecht."""
    if not _SUCCESS_TRUE.search(result) and not _SUCCESS_TXT.search(result):
        return False
    if _ERROR_TRUE.search(result):
        return False
    if _STATUS_FALSE.search(result):
        return False
    if _TEXTUAL_ERROR.search(result):
        return False
    return True


def _rewrite_result(old: str) -> str:
    """Vervang alleen het `GEWEIGERD 200 door doelserver:` prefix door
    `sent 200 (poging 1) ·`. De body blijft woordelijk staan zodat het spoor
    bewaard blijft."""
    # veelvoorkomende vorm: 'GEWEIGERD 200 door doelserver: {"res":...}'
    prefix = re.compile(r"^\s*GEWEIGERD\s+(\d+)\s+door\s+doelserver\s*:\s*", re.I)
    m = prefix.match(old)
    if m:
        body = old[m.end():].strip()
        return f"sent {m.group(1)} (poging 1) · {body}"
    # zeldzamer: GEWEIGERD zonder de standaardvorm. Behouden zoals hij is, maar
    # vervang de prefix zodat de executiepoort hem toch als sent leest.
    return re.sub(r"^\s*GEWEIGERD\b", "sent 200 (poging 1) · [repaired]", old, count=1)


def repair_line(line: str) -> tuple[str, str]:
    """Return (new_line, decision).  decision is een korte reden voor de report."""
    line = line.rstrip("\n")
    if not line.strip():
        return line + "\n", "blank"
    try:
        obj = json.loads(line)
    except ValueError:
        return line + "\n", "unparseable"
    if obj.get("kind") != "pmt":
        return line + "\n", "non_pmt"
    result = obj.get("result") or ""
    if not result.lstrip().upper().startswith("GEWEIGERD"):
        # al goed (sent 200 of iets anders zonder GEWEIGERD-prefix)
        return line + "\n", "already_sent" if "sent" in result.lower() else "other"
    if not _is_false_weigering(result):
        return line + "\n", "real_GEWEIGERD"
    obj["result"] = _rewrite_result(result)
    return json.dumps(obj, ensure_ascii=False) + "\n", "rewritten"


def repair_file(path: Path, apply: bool) -> Report:
    rep = Report()
    lines_out: list[str] = []
    with path.open(encoding="utf-8") as f:
        for raw in f:
            rep.scanned += 1
            new_line, decision = repair_line(raw)
            lines_out.append(new_line)
            if decision == "rewritten":
                rep.rewritten += 1
                if len(rep.examples) < 3:
                    rep.examples.append(new_line.strip()[:200])
            elif decision == "real_GEWEIGERD":
                rep.real_geweigerd += 1
            elif decision == "already_sent":
                rep.already_sent += 1
            elif decision == "non_pmt":
                rep.non_pmt += 1
            elif decision == "unparseable":
                rep.unparseable += 1

    if apply and rep.rewritten > 0:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(path, backup)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("".join(lines_out), encoding="utf-8")
        tmp.replace(path)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", help="een of meer routed_*.jsonl bestanden")
    ap.add_argument("--apply", action="store_true", help="schrijf de wijzigingen weg (default: dry-run)")
    args = ap.parse_args()

    total_rewritten = 0
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            print(f"! niet gevonden: {path}", file=sys.stderr)
            continue
        rep = repair_file(path, apply=args.apply)
        total_rewritten += rep.rewritten
        marker = "APPLY" if args.apply else "dry-run"
        print(f"[{marker}] {path}")
        print(f"        {rep.line()}")
        for ex in rep.examples:
            print(f"        e.g. {ex}")

    if not args.apply:
        print(f"\nDRY-RUN — {total_rewritten} regel(s) zouden worden hersteld.")
        print("Voeg --apply toe om echt te schrijven (backup landt in .bak).")
    else:
        print(f"\nAPPLIED — {total_rewritten} regel(s) hersteld. Herstart mex-viewer om de LIVE-tab te vernieuwen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
