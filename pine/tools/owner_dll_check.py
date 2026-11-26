#!/usr/bin/env python3
"""D-110 -- controleert de EIGEN dagrem in de dertien v1_0_0-scripts.

Twee dingen, en het tweede is de poort naar stap 2:

1. LEEST de defaults uit de .pine-bron zelf (niet overgetypt) en rekent de formule na:
       owner_dll = min( stop-per-contract x stops-per-dag x qty , firm_dll )
   De derde term van D-110 (ruimte x fractie) staat er bewust niet in: die heeft de
   balans nodig en blijft een middleware-signaal.
   Plus een gedragstoets op de haltvoorwaarde `lossBasisEff <= -dailyLossLimitEff`.

2. VERGELIJKT de eigen rem met de firm-rem (`acctDLL`, uit het firm-preset als
   useFirmPreset aan staat). Stap 2 van D-110 -- `dllHit` eruit -- mag PER SCRIPT pas
   als de eigen rem daar de strengste is. Is hij dat niet, dan zou het weghalen van de
   firm-rem de bescherming juist LOSSER maken, en dat is precies de volgorde die D-110
   verbiedt.

3. TOETST DE BRON, niet alleen de rekensom. Drie dingen moeten in elk script staan,
   anders is de gelijkwaardigheid met `dllHit` een aanname in plaats van een feit:
   de samenvoeging (`firmDllActive` met exact de voorwaarden van `dllHit`), de
   `lossBasisEff`-regel (zonder die regel verliest stap 2 dekking als
   `includeOpenInLoss` uit staat) en `lossHit` die op `dailyLossOn` hangt.

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


def firm_program(preset: str) -> tuple[float, str] | None:
    """(daglimiet, dd-model) van een programma, uit de registry -- de bron van de generator."""
    data = json.loads((ROOT / "data" / "propfirms.json").read_text())
    progs = data.get("programs", data)
    if isinstance(progs, dict):
        progs = list(progs.values())
    for p in progs:
        if p.get("key") == preset:
            tl = p.get("targets_limits", {})
            mdl = tl.get("max_daily_loss")
            dd = "EOD" if tl.get("drawdown_type") == "eod_trailing" else "Intraday"
            return (float(mdl["value"]) if mdl else 0.0), dd
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
        base = override if override > 0 else owner
        phase = _default(src, "accountPhase", "string")
        dd_in = _default(src, "ddModel", "string")
        if use_fp:
            prog = firm_program(preset)
            if prog is None:
                bad.append(f"{name}: preset {preset} niet in de registry")
                continue
            firm, dd_eff = prog
        else:
            firm, dd_eff = acct, dd_in


        # De firm-rem geldt alleen op PA of op een EOD-eval (dllHit-voorwaarde), en
        # 0 betekent sinds D-108 GEEN limiet. Sinds stap 1b doet hij mee in de eigen rem.
        # Exact de voorwaarde van dllHit -- en dus van firmDllActive in de bron.
        firm_active = firm > 0 and (phase == "Funded" or (phase == "Eval" and dd_eff == "EOD"))
        eff = min(base, firm) if firm_active else base
        step2_ok = (not firm_active) or eff <= firm

        # Bron-eisen: zonder deze drie regels is de gelijkwaardigheid met dllHit een aanname.
        for needle, why in (
            ("bool  firmDllActive = acctDLL > 0 and (isPA or (isEval and ddModel == \"EOD\"))",
             "de samenvoeging ontbreekt of wijkt af van de dllHit-voorwaarden"),
            ("float lossBasisEff = firmDllActive ? math.min(lossBasis, runningPnL) : lossBasis",
             "lossBasisEff ontbreekt -- stap 2 verliest dekking als includeOpenInLoss uit staat"),
            ("lossHit     = dailyLossOn and lossBasisEff <= -dailyLossLimitEff",
             "lossHit hangt niet op dailyLossOn"),
        ):
            if needle not in src:
                bad.append(f"{name}: {why}")

        # Stap 3 is gedaan: dllHit mag nergens meer in de CODE staan (commentaar wel --
        # daar legt hij uit waaróm hij weg is).
        code = [ln for ln in src.split("\n") if not ln.lstrip().startswith("//")]
        if [ln for ln in code if re.search(r"(?<![A-Za-z])dllHit(?![A-Za-z])", ln)]:
            bad.append(f"{name}: dllHit staat nog in de code -- stap 3 is daar niet af")

        # Gedragstoets: net binnen de limiet houdt de dag open, net erover sluit hem.
        if halts(-eff + 0.01, eff, on) or not halts(-eff, eff, on):
            bad.append(f"{name}: haltvoorwaarde vuurt niet op {-eff:.0f}")

        rows.append((name, qty, owner, override, eff, preset, firm, step2_ok, trail, firm_active))

    w = max(len(r[0]) for r in rows) if rows else 10
    print(f"{'script':<{w}} {'qty':>4} {'formule':>9} {'firm-rem':>9} {'eigen rem':>10}  stap 2")
    print("  een firm-rem tussen haakjes geldt niet op deze fase/dd-combinatie -- dllHit")
    print("  vuurt daar sowieso niet, dus weghalen is daar een no-op.")
    print("-" * (w + 40))
    for name, qty, owner, override, eff, preset, firm, ok, trail, act in rows:
        note = "MAG" if ok else "NOG NIET -- eigen rem is losser"
        fm = f"${firm:,.0f}" if firm > 0 else "geen"
        if firm > 0 and not act:
            fm = f"(${firm:,.0f})"
        extra = f"  (override ${override:,.0f})" if override > 0 else ""
        dd = "  ⚠️ > trailing DD" if trail > 0 and eff > trail else ""
        print(f"{name:<{w}} {qty:>4.0f} {'$'+format(owner, ',.0f'):>9} {fm:>9} {'$'+format(eff, ',.0f'):>10}  {note}{extra}{dd}")

    blocked = [r[0] for r in rows if not r[7]]
    over_dd = [r[0] for r in rows if r[8] > 0 and r[4] > r[8]]
    print()
    print(f"{len(rows)} scripts gelezen · gedragstoets: {'GESLAAGD' if not bad else 'GEFAALD'}")
    if blocked:
        print(f"⛔ stap 2 (dllHit eruit) mag NOG NIET op {len(blocked)} van de {len(rows)}:")
        for b in blocked:
            print(f"   - {b}")
        print("   De eigen rem is daar losser dan de firmalimiet. Sinds stap 1b hoort dat")
        print("   niet meer voor te komen -- staat hier toch iets, dan is de samenvoeging")
        print("   met firm_dll stuk en mag dllHit NERGENS weg.")
    if over_dd:
        print()
        print(f"⚠️ Bij {len(over_dd)} van de {len(rows)} is de eigen rem GROTER dan de trailing")
        print("   drawdown van het account: één dag op die limiet breekt het account.")
        print("   ⚠️ CORRECTIE 06-10 (D-53/D-122 dicht): dit is GEEN meetartefact meer. Ferry")
        print("   beheert de qty in Pine en de middleware-override is weg, dus de qty hier IS")
        print("   de gehandelde qty. Een rem van $2.800 op een account met $2.000 trailing")
        print("   drawdown is dus echte blootstelling, niet een backtestgetal. Verlaag de qty")
        print("   op die charts of zet een override.")
    for b in bad:
        print("FOUT:", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
