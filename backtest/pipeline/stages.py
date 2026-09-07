"""The twelve gated stages of the MEX research pipeline (v7).

This is the spine. Every piece of lab work belongs to exactly one stage, and a
market/engine advances only when the stage's gate is demonstrably met. The gate
texts are copied from the authoritative methodology
(`.claude/skills/strategy-validation-pipeline/references/pipeline-v7-authoritative.md`)
so the UI never paraphrases the protocol into something softer.

Enforcement is deliberately ADVISORY for now (Ferry, 2026-08-20): every stage can
be run at any time, but the status of the ones before it is always shown, so a
result produced out of order is visibly out of order rather than silently
accepted.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    n: int
    key: str
    title: str
    gate: str
    hard: bool = False        # a hard gate invalidates everything downstream
    note: str = ""


STAGES: tuple[Stage, ...] = (
    Stage(0, "data_audit", "Data-audit",
          "Dekking, tijdzone, OHLC-continuïteit, volume/Delta-dekking, ticksize, point value, "
          "commissie en roll-artefacten vastgesteld; genormaliseerde dataset + kwaliteitsrapport bestaan."),
    Stage(1, "parity", "Pine-pariteitsengine",
          "Python/.NET vs Pine op één vaste baseline: bijna gelijk aantal trades én materieel "
          "vergelijkbare WR/PF.", hard=True,
          note="Harde poort — parameteroptimalisatie is ONGELDIG zolang pariteit onopgelost is."),
    Stage(2, "structural_edge", "Structurele edge, from scratch",
          "Positieve intrinsieke edge ná kosten op 1 contract. Nog géén PA-sizing of dagcaps. "
          "Seed niet met het optimum van een andere markt."),
    Stage(3, "regimes", "Regime-diagnostiek",
          "Elk regime IN/OUT/ALL gerapporteerd; een regime wordt alleen filter als het effect "
          "robuust én economisch verklaarbaar is."),
    Stage(4, "plateau", "Robuustheid / plateau",
          "Breed plateau i.p.v. scherp maximum; houdt stand per jaar/kwartaal en in rollende "
          "vensters; LONG en SHORT apart gecontroleerd."),
    Stage(5, "sizing", "Contractgrootte & pro-rata risico",
          "Volledige stop in dollars ligt onder de geldende DLL vóór slippage/commissie; grootte "
          "verandert doorvoer en risico, niet de intrinsieke PF."),
    Stage(6, "daily_mgmt", "Dagelijkse P&L-sturing",
          "Dagcap/giveback/activatie beoordeeld op payout-economie, niet op cosmetische "
          "equity-gladheid."),
    Stage(7, "pa_lifecycle", "PA-lifecycle-modellen",
          "Apex 50K EOD én Intraday gedraaid; Intraday modelleert ongerealiseerde MFE die de "
          "trailing HWM optrekt (of is expliciet als conservatief gelabeld)."),
    Stage(8, "time_for_money", "Time-for-money",
          "Gebankte payout-$ per bezette account-dag gerapporteerd, met payout #1-conversie, "
          "P2–P6, dagen tot P1, breach-cijfers en DLL-hits."),
    Stage(9, "prod_vs_harvest", "Production vs Harvest",
          "Twee kandidaten behouden; geen van beide leunt op uur/dag-cherrypicking."),
    Stage(10, "tv_validation", "TradingView-validatie",
          "Properties-audit gedaan; trades, timing, exit-redenen, P&L, MFE/MAE, LONG/SHORT en PF "
          "komen overeen met de simulator.", hard=True,
          note="Harde deployment-poort. Faalt hij? Onderzoek de eerste afwijkende trades — "
               "NIET opnieuw optimaliseren."),
    Stage(11, "portfolio", "Portefeuille-diversificatie",
          "Dagelijkse P&L-correlatie en overlap in verlies-/breachdagen gemeten over minstens "
          "20–30 actieve dagen. Claim geen decorrelatie daarvoor."),
)

BY_KEY = {s.key: s for s in STAGES}
BY_N = {s.n: s for s in STAGES}

# The non-negotiable ground rules, shown next to the plan so they are not folded
# away into a document nobody opens.
GROUND_RULES = (
    "Pariteit vóór optimalisatie — parameterzoeken is ongeldig zonder trap 1.",
    "Geen same-bar fill leakage; zonder tick-replay geldt: pessimistisch, geen exit op de fill-bar.",
    "18:00 ET is de handelsdaggrens, niet middernacht.",
    "Canonieke CVD = deterministische OHLCV-polariteitsproxy, niet de native Delta-kolom.",
    "Kosten altijd aan; slippage 1 tick basis, 2–3 in stress.",
    "Geen willekeurige uur/dag-filters; regimes alleen economisch vooraf gedefinieerd.",
    "Pre-registreer vóór je data aanraakt.",
    "One-shot OOS — het venster is opgebrand na één gebruik.",
    "Research-invalidatie: een materiële pariteitsfout laat alle rankings eronder vervallen.",
    "TradingView bewaart oude inputs — controleer het Properties-tabblad.",
    "Elke trap levert een artefact.",
    "Geen verzonnen bronnen.",
)
