"""D-119 · Fan-out statusvenster — read-only lezing van wat de fan-out doet.

De tweeling van de settings-tab (D-83/D-84): die laat zien wat is ingesteld,
dit laat zien wat is gebeurd. Beide draaien dezelfde kritiek-regel die
D-125/D-126/D-127 (ingetrokken verklaringen) hard maakte: zonder meet-oppervlak
op het live pad raden we onzichtbaar fout.

Bronnen die vandaag al bestaan — dit module **leest** ze alleen en voegt geen
nieuwe telemetrie toe:

- `routed_*.jsonl` in `ROUTED_DIR` (default `/root/intent-store`). Draagt per
  bericht `ts`, `kind`, `account`, `transport` en `result`. Resultaat-strings
  die we classificeren:
    * `sent …` / `card sent …`                     → verstuurd
    * `card queued …`                              → verstuurd (achter-de-render)
    * `card rate-limited …` / `blocked-notice …`    → gedempt
    * `GEWEIGERD …` / `error …` / `card exception` → mislukt
    * `card failed …`                              → mislukt
    * `blocked: kill-switch`                       → gedempt (opzet)
    * `dry_run -> …`                               → verstuurd (droge run)

- `docs/runtime-snapshot.md` (D-31) — gegenereerd door `mex-runtime-snapshot.timer`.
  We lezen hem via het `SNAPSHOT_PATH`-env (default `/root/mex-journal/docs/
  runtime-snapshot.md`) en parsen de key/value-rijen in de eerste tabel. Zonder
  file: `null` op elk veld, geen fout — snapshot kan verouderd of weg zijn en
  dat is zélf informatie, niet een reden om 500 te gooien.

De classifier is **expliciet** gemaakt (geen regex-maze) zodat een nieuwe
result-vorm hier opduikt als "overig" en niet stilzwijgend als verstuurd telt.
Dat is dezelfde discipline die D-116 vraagt: een pad dat stilvalt moet
zichtbaar oplopen.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# -- windows -------------------------------------------------------------------

#: Vensters die het statusvenster toont. Keys zijn API-safe strings; waarden
#: zijn de duur in seconden. "all" telt zonder tijdfilter — nuttig als de
#: file-set smal is (één dag).
WINDOWS: dict[str, int | None] = {
    "last_hour": 3_600,
    "last_24h": 86_400,
    "last_7d": 7 * 86_400,
    "all": None,
}


# -- classification -----------------------------------------------------------

# Vorm: wat gaan we tellen. Een bericht valt in precies één bucket.
_SENT_PREFIXES = (
    "sent ",            # ForwardAsync success
    "card sent ",       # CardRender success
    "card queued",      # ingediend bij renderer; voor dit venster = verstuurd
    "dry_run ->",       # droge run; expliciet geen fout
)
_SUPPRESSED_SUBSTR = (
    "rate-limited",     # PostRate dempte
    "blocked-notice",   # BlockedGate dempte
    "blocked: kill",    # kill-switch dempte (gewenst gedrag)
    "suppressed",       # expliciete demping
    "card exception",   # render-fout zonder tekst-fallback (D-116 gat)
)
_FAILED_PREFIXES = (
    "GEWEIGERD",
    "error ",
    "card failed",
)


def classify(result: str) -> str:
    """`sent` / `suppressed` / `failed` / `other`. Case-sensitive op prefix,
    case-insensitive op substring — dezelfde conventies als de bronstrings."""
    r = result or ""
    low = r.lower()
    for sub in _SUPPRESSED_SUBSTR:
        if sub in low:
            return "suppressed"
    if r.startswith(_FAILED_PREFIXES):
        return "failed"
    for pfx in _SENT_PREFIXES:
        if r.startswith(pfx):
            return "sent"
    return "other"


# -- transport grouping -------------------------------------------------------


def transport_of(row: dict) -> str:
    """Een enkele label-sleutel voor "op welk kanaal is dit vertrokken".
    `transport` kwam in D-106 op PMT-rijen; voor de rest leiden we hem af van
    `kind` zodat de teller per kanaal werkt zonder het log te hoeven
    reorganiseren."""
    t = row.get("transport")
    if isinstance(t, str) and t:
        return t
    kind = row.get("kind") or "unknown"
    if kind == "pmt":
        return "pmt_unknown"      # pre-D-106 PMT-rij zonder transport-veld
    return kind                   # discord · discord-card · pineconnector · journal · unknown


# -- aggregation --------------------------------------------------------------


def _parse_ts(s: str) -> float | None:
    """ISO-string → epoch seconds. Faalt zacht."""
    if not s:
        return None
    try:
        # `.jsonl`-rijen dragen `o`-formaat: `2026-10-06T12:34:56.1234567Z`.
        # fromisoformat accepteert `Z` niet; vervang hem door `+00:00`.
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _iter_rows(paths: Iterable[str]) -> Iterable[dict]:
    for path in sorted(paths):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        # Half-geschreven regels (file nog in beweging) worden
                        # overgeslagen — hetzelfde gedrag als `analyze_pmt_bodies.py`.
                        continue
        except OSError:
            continue


def aggregate_window(rows: list[dict], window_s: int | None, now_ts: float) -> dict:
    """Tel per kanaal + totalen, hou de laatste foutcode vast, en de laatste
    activiteit per account."""
    cutoff = (now_ts - window_s) if window_s is not None else None

    per_transport: dict[str, dict] = defaultdict(
        lambda: {"sent": 0, "suppressed": 0, "failed": 0, "other": 0, "last_error": None}
    )
    totals = {"sent": 0, "suppressed": 0, "failed": 0, "other": 0}
    # Per account: laatste activiteit. "Account" is wat de receiver schreef —
    # een lege string voor berichten zonder account (bv. kill-switch van buiten).
    per_account: dict[str, dict] = {}

    for row in rows:
        ts = _parse_ts(row.get("ts", ""))
        if cutoff is not None and (ts is None or ts < cutoff):
            continue
        bucket = classify(row.get("result", ""))
        tr = transport_of(row)
        per_transport[tr][bucket] += 1
        totals[bucket] += 1
        if bucket == "failed":
            # Laatste foutstring — kort gehouden, want hij komt in het scherm.
            per_transport[tr]["last_error"] = (row.get("result") or "")[:160]
        acct = row.get("account") or ""
        if acct:
            prev = per_account.get(acct)
            if prev is None or (ts and ts > prev.get("ts", 0)):
                per_account[acct] = {
                    "ts": ts or 0,
                    "transport": tr,
                    "kind": row.get("kind") or "",
                    "last_result": (row.get("result") or "")[:160],
                    "last_bucket": bucket,
                }

    # account-dict → stabiele lijst, meest-recent eerst, cap op 50
    accounts_list = sorted(
        (
            {
                "account": a,
                "last_ts": (dt.datetime.fromtimestamp(v["ts"], tz=dt.timezone.utc)
                            .isoformat().replace("+00:00", "Z")) if v.get("ts") else None,
                "transport": v.get("transport"),
                "kind": v.get("kind"),
                "last_bucket": v.get("last_bucket"),
                "last_result": v.get("last_result"),
            }
            for a, v in per_account.items()
        ),
        key=lambda r: r["last_ts"] or "",
        reverse=True,
    )[:50]

    return {
        "totals": totals,
        "transports": dict(per_transport),
        "accounts": accounts_list,
    }


def _recent_files(routed_dir: str, days: int = 7) -> list[str]:
    """Alleen de laatste N files meenemen — grotere history is niet relevant
    voor het statusvenster, en elke extra file is extra I/O."""
    pattern = os.path.join(routed_dir, "routed_*.jsonl")
    files = sorted(glob.glob(pattern))
    return files[-days:] if days > 0 else files


# -- runtime snapshot --------------------------------------------------------


# De key-labels zoals de snapshot-script ze zet (zie
# `middleware/deploy/mex-runtime-snapshot.sh`). Hier gemapt naar API-safe keys.
_SNAPSHOT_FIELDS = {
    "service": "service",
    "gestart": "service_started",
    "bron": "src_path",
    "bron md5": "src_md5",
    "bron regels": "src_lines",
    "bron gewijzigd": "src_mtime",
    "binary": "binary_mtime",
    "binary bytes": "binary_bytes",
    "dotnet": "dotnet_version",
}


def _strip_md(cell: str) -> str:
    """`` `foo` `` → `foo`. Behoudt verder spaces."""
    return (cell or "").strip().strip("`").strip()


def read_runtime_snapshot(path: str) -> dict:
    """Parse de eerste `|key|value|`-tabel uit `docs/runtime-snapshot.md`.
    Alles verder — unit-definitie, env-namen, andere units — slaan we over;
    dat is voor een menselijke lezer en past niet in dit API-oppervlak.
    Zonder file: alle velden `null`, plus `file_present: false`."""
    out: dict = {"file_present": False, "path": path, "generated_at": None,
                 "binary_older_than_src": None}
    for k in _SNAPSHOT_FIELDS.values():
        out[k] = None
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    out["file_present"] = True

    # `**Gemaakt:** YYYY-MM-DD HH:MM:SS UTC`
    m = re.search(r"\*\*Gemaakt:\*\*\s+([\d\- :UTC]+)", text)
    if m:
        out["generated_at"] = m.group(1).strip()

    # `**Binary ouder dan de bron?** nee` of `⚠️ JA — …`
    m = re.search(r"\*\*Binary ouder dan de bron\?\*\*\s+(.+?)(?:\n|$)", text)
    if m:
        v = m.group(1).strip().lower()
        if v.startswith("nee"):
            out["binary_older_than_src"] = False
        elif "ja" in v:
            out["binary_older_than_src"] = True

    # Eerste tabel: regels van de vorm `| key | value |`.
    for line in text.splitlines():
        if not line.startswith("|") or line.strip().startswith("|---"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        key, value = parts[0].strip().lower(), parts[1].strip()
        api_key = _SNAPSHOT_FIELDS.get(key)
        if api_key is None:
            continue
        v = _strip_md(value)
        if v in ("—", ""):
            v = None
        # Integers waar het logisch is.
        if api_key in ("src_lines", "binary_bytes") and v is not None:
            try:
                out[api_key] = int(v)
                continue
            except ValueError:
                pass
        out[api_key] = v

    return out


# -- public API -----------------------------------------------------------------


def build(routed_dir: str | None = None, snapshot_path: str | None = None,
          days: int = 7) -> dict:
    """Bouw het statusvenster. Alles komt uit bestanden die al geschreven worden."""
    routed_dir = routed_dir or os.environ.get("ROUTED_DIR") \
        or os.environ.get("INTENT_DIR", "/root/intent-store")
    snapshot_path = snapshot_path or os.environ.get("SNAPSHOT_PATH") \
        or "/root/mex-journal/docs/runtime-snapshot.md"

    files = _recent_files(routed_dir, days=days)
    rows = list(_iter_rows(files))
    now_ts = time.time()

    windows_out = {name: aggregate_window(rows, secs, now_ts) for name, secs in WINDOWS.items()}

    return {
        "generated_at": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
                        .isoformat().replace("+00:00", "Z"),
        "routed_dir": routed_dir,
        "files_scanned": len(files),
        "rows_scanned": len(rows),
        "windows": windows_out,
        "runtime": read_runtime_snapshot(snapshot_path),
    }
