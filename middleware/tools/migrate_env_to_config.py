#!/usr/bin/env python3
"""D-81 · Eenmalige migratie van gedeprecieerde env-vars naar `mex.json`.

Leest de env-vars die vandaag de gates voeden — `MEX_HALTED_ACCOUNTS`,
`MEX_ACCOUNT_ENTRY_CAPS`, `MEX_DEFAULT_ENTRY_CAP` — en produceert een
`accounts[]` + `defaults` blok dat de fase-1 provider consumeert (zie
`docs/schema-config.md` §3/§4). Merget met een bestaande file als je er
al één hebt.

Gebruik op de VPS (draait naast `mex-receiver`, muteert geen live pad):

    # 1) Preview naar stdout:
    python3 middleware/tools/migrate_env_to_config.py --from-systemd mex-receiver

    # 2) Schrijf een nieuwe file (of merge met bestaande):
    python3 middleware/tools/migrate_env_to_config.py \\
        --from-systemd mex-receiver \\
        --out /root/mex-config/mex.json \\
        --updated-by "d81-migration"

    # 3) Handmatig, zonder systemd (env-values op de opdrachtregel):
    python3 middleware/tools/migrate_env_to_config.py \\
        --halted PAAPEX...013,APEX...205 \\
        --caps "PAAPEX...013=8,PAAPEX...018=10" \\
        --default-cap 6 \\
        --out /root/mex-config/mex.json

Wat het NIET doet: `MEX_ACCOUNT_QTY` (blijft env — schema §7-vangnet),
kanalen/tokens/webhooks (die staan pas in D-82's kluis + `channels`-blok).
De env-vars zelf verdwijnen niet — dat is een aparte handmatige stap in
de systemd-unit, met de startwaarschuwing als reminder.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_kv_ints(spec: str) -> dict[str, int]:
    """`PA…013=8,PA…018=10` → {'PA…013': 8, 'PA…018': 10}. Onparsebare rijen
    worden overgeslagen met een stderr-melding; een gok publiceren is een
    grotere fout dan een teller die één rij mist."""
    out: dict[str, int] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        kv = part.split("=", 1)
        if len(kv) != 2:
            print(f"skip malformed kv {part!r}", file=sys.stderr)
            continue
        try:
            n = int(kv[1].strip())
        except ValueError:
            print(f"skip non-integer value {part!r}", file=sys.stderr)
            continue
        if n <= 0:
            print(f"skip non-positive value {part!r}", file=sys.stderr)
            continue
        out[kv[0].strip()] = n
    return out


def parse_list(spec: str) -> list[str]:
    return [x.strip() for x in (spec or "").split(",") if x.strip()]


def parse_default_cap(spec: str | None) -> int | None:
    if not spec:
        return None
    try:
        n = int(spec)
    except ValueError:
        return None
    return n if n > 0 else None


def read_systemd_env(unit: str) -> dict[str, str]:
    """`systemctl show -p Environment <unit>` → dict. Leeg als niet beschikbaar."""
    try:
        out = subprocess.check_output(
            ["systemctl", "show", "-p", "Environment", unit],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"systemctl unavailable ({exc}); use --halted/--caps/--default-cap in plaats.",
              file=sys.stderr)
        return {}
    # Formaat: Environment=KEY1=val1 KEY2="quoted val" …
    payload = out.split("=", 1)[1] if "=" in out else ""
    env: dict[str, str] = {}
    # Match KEY=VALUE waarbij VALUE gequoot kan zijn.
    for m in re.finditer(r'(\w+)=(?:"([^"]*)"|(\S+))', payload):
        env[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return env


def build(halted: list[str], caps: dict[str, int], default_cap: int | None,
          updated_by: str, existing: dict | None) -> dict:
    """Voeg de migratie samen met een bestaande file. Bestaande velden winnen
    op velden die de migratie ook zou zetten — zo overschrijft een handmatige
    settings-tab-wijziging deze migratie niet ongewild."""
    doc = existing or {}
    doc.setdefault("version", 0)
    doc["version"] = int(doc.get("version") or 0) + 1
    doc["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    doc["updated_by"] = updated_by

    # defaults.caps.entries_per_day
    defaults = doc.setdefault("defaults", {})
    caps_block = defaults.setdefault("caps", {})
    if default_cap is not None and "entries_per_day" not in caps_block:
        caps_block["entries_per_day"] = default_cap

    # accounts[]
    accounts = doc.setdefault("accounts", {})

    for acct in halted:
        row = accounts.setdefault(acct, {})
        # Alleen zetten als er nog geen status is — een handmatig actieve
        # override in de file moet niet stil worden teruggezet naar halted.
        row.setdefault("status", "halted")

    for acct, cap in caps.items():
        row = accounts.setdefault(acct, {})
        row.setdefault("status", "active")
        row_caps = row.setdefault("caps", {})
        row_caps.setdefault("entries_per_day", cap)

    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-systemd", metavar="UNIT",
                    help="lees env-vars uit `systemctl show -p Environment <UNIT>`")
    ap.add_argument("--halted", default=None,
                    help="expliciete waarde voor MEX_HALTED_ACCOUNTS (kommalijst)")
    ap.add_argument("--caps", default=None,
                    help="expliciete waarde voor MEX_ACCOUNT_ENTRY_CAPS (`acct=n,…`)")
    ap.add_argument("--default-cap", default=None,
                    help="expliciete waarde voor MEX_DEFAULT_ENTRY_CAP (integer)")
    ap.add_argument("--out", default="-",
                    help="pad naar mex.json (default `-` = stdout)")
    ap.add_argument("--updated-by", default="d81-migration",
                    help="tekst in `updated_by`-veld (default 'd81-migration')")
    args = ap.parse_args()

    env: dict[str, str] = {}
    if args.from_systemd:
        env = read_systemd_env(args.from_systemd)

    halted_spec = args.halted if args.halted is not None else env.get("MEX_HALTED_ACCOUNTS", "")
    caps_spec = args.caps if args.caps is not None else env.get("MEX_ACCOUNT_ENTRY_CAPS", "")
    default_spec = args.default_cap if args.default_cap is not None else env.get("MEX_DEFAULT_ENTRY_CAP", "")

    halted = parse_list(halted_spec)
    caps = parse_kv_ints(caps_spec)
    default_cap = parse_default_cap(default_spec)

    if not halted and not caps and default_cap is None:
        print("geen input — niets te migreren. (Zet --halted / --caps / --default-cap of --from-systemd.)",
              file=sys.stderr)
        return 2

    existing: dict | None = None
    if args.out != "-" and Path(args.out).exists():
        try:
            existing = json.loads(Path(args.out).read_text())
        except Exception as exc:
            print(f"kon bestaande {args.out} niet lezen: {exc}", file=sys.stderr)
            return 3

    doc = build(halted, caps, default_cap, args.updated_by, existing)
    text = json.dumps(doc, indent=2, sort_keys=False) + "\n"

    if args.out == "-":
        sys.stdout.write(text)
    else:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(out_path)   # atomair — zelfde patroon als public_stats.write

    # Korte samenvatting op stderr — telt in de melding, niet in de output.
    print(f"wrote v{doc['version']}: {len(halted)} halted, {len(caps)} caps, "
          f"defaultCap={default_cap} → {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
