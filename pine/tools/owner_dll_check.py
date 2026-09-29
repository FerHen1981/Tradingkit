#!/usr/bin/env python3
"""D-110 stap 1 -- controleert de EIGEN dagrem in de dertien v1_0_0-scripts.

Twee dingen, en het tweede is de poort naar stap 2:

1. LEEST de defaults uit de .pine-bron zelf (niet overgetypt) en rekent de formule na:
       owner_dll = stop-per-contract x stops-per-dag x qty
   plus een gedragstoets op de haltvoorwaarde `lossBasis <= -dailyLossLimitEff`.

2. VERGELIJKT de eigen rem met de firm-rem (`acctDLL`, uit het firm-preset als
   useFirmPreset aan staat). Stap 2 van D-110 -- `dllHit` eruit -- mag PER SCRIPT pas
   als de eigen rem daar de strengste is. Is hij dat niet, dan zou het weghalen van de
   firm-rem de bescherming juist LOSSER maken, en dat is precies de volgorde die D-110
   verbiedt.

Exit 0 = alle scripts gelezen en de gedragstoets slaagt. Exit 1 = een leesfout of een
toets die faalt. Een script waar stap 2 nog niet mag is GEEN fout -- dat is de uitslag.
"""
from __future__ import annotations
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PINE = sorted((ROOT / "pine").glob("MEX_EL_*_v1_0_0.pine"))


def _default(src: str, name: str, kind: str) -> float | bool | str | None:
    """Pakt de default van `name = input.<kind>(<default>, ...)` of van een constante."""
    m = re.search(rf"^{re.escape(name)}\s*=\s*input\.{kind}\(\s*([^,]+),", src, re.M)
    if m is None:
        m = re.search(rf"^{re.escape(name)}\s*=\s*([^\s#/]+)\s*$", src, re.M)
    if m is None:
        return None
    raw = m.group(1).strip().strip('"')
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return float(raw)
    except ValueError:
        return raw


def firm_dll(preset: str) -> float | None:
    """De daglimiet van een programma, uit de registry -- dezelfde bron als de generator."""
    data = json.loads((ROOT / "data" / "propfirms.json").read_text())
    progs = data.get("programs", data)
    if isinstance(progs, dict):
        progs = list(progs.values())
    for p in progs:
        if p.get("key") == preset:
            mdl = p.get("targets_limits", {}).get("max_daily_loss")
            return float(mdl["value"]) if mdl else 0.0
    return None


def halts(loss_basis: float, limit: float, enabled: bool) -> bool:
    """De haltvoorwaarde uit r. `lossHit`, één op één."""
    return enabled and loss_basis <= -limit


def main() -> int:
    rows, bad = [], []
    for path in PINE:
        src = path.read_text(encoding="utf-8")
        name = path.name.replace("_v1_0_0.pine", "")
        qty = _default(src, "contractSize", "float")
        sl = _default(src, "ownerDllSlUSD", "float")
        stops = _default(src, "ownerDllStops", "float")
        override = _default(src, "dailyLossLimit", "float")
        on = _default(src, "enableDailyLossLimit", "bool")
        use_fp = _default(src, "useFirmPreset", "bool")
        preset = _default(src, "firmPreset", "string")
        acct = _default(src, "acctDLL", "float")
        trail = _default(src, "acctTrailDD", "float") or 0.0
        if None in (qty, sl, stops, override, on, preset):
            bad.append(f"{name}: default niet te lezen")
            continue

        owner = sl * stops * max(qty, 1.0)
        eff = override if override > 0 else owner
        firm = firm_dll(preset) if use_fp else acct
        if firm is None:
            bad.append(f"{name}: preset {preset} niet in de registry")
            continue

        # Gedragstoets: net binnen de limiet houdt de dag open, net erover sluit hem.
        if halts(-eff + 0.01, eff, on) or not halts(-eff, eff, on):
            bad.append(f"{name}: haltvoorwaarde vuurt niet op {-eff:.0f}")

        # De firm-rem geldt alleen op PA of op een EOD-eval (dllHit-voorwaarde), en
        # 0 betekent sinds D-108 GEEN limiet.
        firm_active = firm > 0
        step2_ok = (not firm_active) or eff <= firm
        rows.append((name, qty, owner, override, eff, preset, firm, step2_ok, trail))

    w = max(len(r[0]) for r in rows) if rows else 10
    print(f"{'script':<{w}} {'qty':>4} {'eigen rem':>10} {'firm-rem':>9}  stap 2")
    print("-" * (w + 40))
    for name, qty, owner, override, eff, preset, firm, ok, trail in rows:
        note = "MAG" if ok else "NOG NIET -- eigen rem is losser"
        fm = f"${firm:,.0f}" if firm > 0 else "geen"
        extra = f"  (override ${override:,.0f})" if override > 0 else ""
        dd = "  ⚠️ > trailing DD" if trail > 0 and eff > trail else ""
        print(f"{name:<{w}} {qty:>4.0f} {'$'+format(eff, ',.0f'):>10} {fm:>9}  {note}{extra}{dd}")

    blocked = [r[0] for r in rows if not r[7]]
    over_dd = [r[0] for r in rows if r[8] > 0 and r[4] > r[8]]
    print()
    print(f"{len(rows)} scripts gelezen · gedragstoets: {'GESLAAGD' if not bad else 'GEFAALD'}")
    if blocked:
        print(f"⛔ stap 2 (dllHit eruit) mag NOG NIET op {len(blocked)} van de {len(rows)}:")
        for b in blocked:
            print(f"   - {b}")
        print("   Daar is 4 x SL x qty GROTER dan de firmalimiet, dus de firm-rem is nog")
        print("   de strengste. Verlaag qty naar wat er echt gehandeld wordt, of zet een")
        print("   override, en draai dit opnieuw.")
    if over_dd:
        print()
        print(f"⚠️ Bij {len(over_dd)} van de {len(rows)} is de eigen rem GROTER dan de trailing")
        print("   drawdown van het account: één dag op die limiet breekt het account. Dat is")
        print("   geen fout in de formule maar in de qty -- de bevroren contractgrootte is de")
        print("   backtestgrootte, niet wat er live gehandeld wordt (zie D-53).")
    for b in bad:
        print("FOUT:", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
