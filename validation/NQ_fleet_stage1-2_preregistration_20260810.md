# Stage 1-2 — Pre-registratie NQ-fleet validatie (20260810)
VASTGELEGD VOORDAT ENIGE BACKTEST OP data/NQ_1m_last3y_slim.csv IS GEDRAAID.

## Data & windows (vast)
- Bestand: NQ_1m_last3y_slim.csv, 2023-06-18 .. 2026-06-17 (3y, 1m, echte delta-feed).
- IS: 2023-06-18 .. 2025-12-17 · **OOS (one-shot): 2025-12-17 .. 2026-06-17** (laatste 6 mnd).
- Regime-jaren: Y1 23/06-24/06 · Y2 24/06-25/06 · Y3 25/06-26/06.
- Kosten ALTIJD aan: $1.55/ct/zijde + 1 tick slippage (stress: $3.10 + 2 ticks).

## Kandidaten (bron: intern gevalideerde fleet-configs = setup-sheet 20260810; label (c)/intern, geen externe claims)
1. **TORO_EVAL** — El Toro, doel = Apex 50k eval pass (intraday, DD 2500/goal 3000).
   Regels: FVG 9-12t, confirm 2, delta UIT, VWAP-veto AAN, swing-stop (max 72t), TP fixed 122t,
   recovery-trail aan, q5, alle uren (flat 16:55-18:00), limit@50%.
   Falsifieerbare edge: 1 TP-winner ≈ goal; pass-rate > timeout/breach-mix van een muntworp-baseline.
2. **DORADO_PA** — El Dorado TUNED, doel = PA banked/breach (intraday).
   Regels: FVG 9-12, confirm 0, day-trail $300, BE 20/8, trail 48/24, MAE-guard, wait-for-cap, q2, delta UIT.
3. **PATRON_PA** — idem met EOD-drawdown (El Patrón + dt300).

## Pre-geregistreerde gates
- S3: geen look-ahead (limit vult pas bar ná plaatsing — engine-design), kosten aan, IS-trades >= 100, reproduceerbaar uit preset.
- S4 (gate zoals skill voorschrijft): recente-12m contract-PF >= 1.2 na kosten — WORDT GERAPPORTEERD ZOALS GESCHREVEN.
  Daarnaast per grondregel 5 het pre-geregistreerde accountdoel (Apex-lens):
  TORO: funnel pass-rate (step 5, horizon 20) recente 12m >= 25%; DORADO/PATRON: banked/breach >= $500 recente 12m.
- S5: WFE (OOS/IS op doelmetric) >= 0.5; ±20% perturbatie (gap-band, stop-cap, confirm, + delta-AAN-sensitiviteit) blijft binnen 30% van basis; MC p5 maxDD < DD-budget.
- S6: dagelijkse PnL-correlatie vs El Minero (GC) en El León (ES) < 0.7.
- S7: OOS met 2-tick slip + dubbele commissie: doelmetric zakt < 50% en geen totale ineenstorting.
- S8: risk per trade <= ~1.4% (q5 × ~$700 op 50k geflagd), DLL/day-trail in script aanwezig.
- S9: guardrails gedefinieerd + alert-pad live bewezen (Discord/PMT draaide).
- S10: >= 4 weken paper/live — we hebben 1 week => verwacht INCONCLUSIVE; reflectie live-week is structureel
  (data eindigt 17-06; live-week 24-07..08-08 valt buiten het bestand — geen zelfde-window vergelijking mogelijk).

## Anti-p-hacking
OOS wordt precies 1x aangeraakt (S4/S5/S7 rapporteren dezelfde ene OOS-run per config + de ene stress-run).
Perturbaties draaien ALLEEN op IS. Delta-AAN is een gelabelde sensitiviteit, geen primaire arm.
