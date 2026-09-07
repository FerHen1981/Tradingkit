# GC/ES/MGC/MES — stage 3-10 verdicts (20260810)
OOS = 2026-01-31..2026-07-31, voor GC/ES-signaalkeuze **quasi-OOS [TAINTED]** (zie pre-registratie).
PA-runs met DLL $1000 (live-realiteit) + MAE + wait-for-cap + day-trail $300.

## S3 — PASS (alle 8): kosten aan (GC 1.75 / ES 1.55 / micro 0.67 gemeten), IS-trades ruim >100, preset-reproduceerbaar.

## S4 — gate-as-written: FAIL overal (r12 contract-PF 0.99-1.09 < 1.2) · accountdoel:
| config | doel r12 | gate ≥ | verdict |
|---|---|---|---|
| GC_EVAL 40.0/35.4/40.9% (IS/r12/OOS) | 35.4% | 25% | PASS |
| ES_EVAL 41.1/45.8/54.5% | 45.8% | 25% | PASS (sterkste) |
| MGC_EVAL 39.2/35.4/40.9% | 35.4% | 25% | PASS (micro-commissie doet evals niks) |
| MES_EVAL 41.1/45.8/50.0% | 45.8% | 25% | PASS |
| GC_FUNDED bpb r12 $3250 (6500/2) | ≥$500 | | PASS |
| ES_FUNDED banked $0 overal (br 9/3/2) | $0 | ≥$500 | **FAIL — stopt hier** |
| MGC_FUNDED bpb r12 $577, OOS $750 | ≥$500 | | PASS |
| MES_FUNDED bpb r12 $500, OOS $1000 | ≥$500 | | PASS (randje) |
Regime-trend contract-PF: GC 1.17→1.15→1.01 · ES 1.08→1.13→1.06 — edge dunt uit richting nu maar blijft ≥1.

## S5 — robuustheid: PASS evals
GC-perturbaties (IS, basis 40.0): 34.4-45.6 (stop80 zelfs beter) ✓ · ES (basis 41.1): 30.6-41.1 ✓ (gap 6-12 −26%, binnen ±30).
WFE (doel OOS/IS): GC 1.02 · ES 1.33 · MGC 1.04 · MES 1.22 — alle ≥0.5 ✓. MC p5 maxDD continu-lens $57-96k → FLAG (alleen met account-halts draaien).
Micro-qty (IS, funded): MGC q6/8/10 → bpb 559/~/667 (schaal helpt) · MES q3 $0 / q5 marge / q6 bpb 58 → MES-funded is marginaal.

## S6 — fleet-fit: PASS. Dag-PnL-correlatie GC↔ES 0.024 (656 d); eerder NQ↔GC −0.03, NQ↔ES 0.04. Drie ~onafhankelijke benen.

## S7 — stress (2-tick + 2× comm., quasi-OOS): evals PASS · **funded FAIL over de hele linie**
Evals: GC 40.9→40.9 · ES 54.5→50.0 · MGC 40.9→40.9 · MES 50.0→50.0 — vrijwel ongevoelig ✓.
Funded: GC 1500→0 · MGC 4500→1500 (bpb 750→136, −82%) · MES 3000→0 · (ES was al gestopt) → verval >50% = FAIL.

## S8 — PARTIAL: eval-risico per poging gecapt op DD (variance-play, geflagd); PA-limieten (MAE/DLL/day-trail) in script ✓.
## S9 — PASS: zelfde guardrails als NQ-run; alert-pad week live bewezen.
## S10 — INCONCLUSIVE (1/4 wk) mét cruciale observatie — **live-divergentie funded**:
De echte Tradovate-week (03-08..08-08) toont MGC-funded PF 1.65-3.07, +$16.1k over 5 accounts — ruim BOVEN het
gestresste backtest-beeld. Bewezen verklaring uit deze sessie: de conservative-fill engine onderschat het
day-trail/BE-harvest-profiel (veel scratch-exits die live goed uitpakken). Funded-status is daarmee:
**backtest-fragiel maar live-bewezen (1 week)** → voorwaardelijk door laten draaien onder de S9-guardrails,
wekelijkse live-vs-model-log beslist na 4 weken. ES_FUNDED (full, 250k-lens) is óók in de backtest $0 → niet starten.

## Eindoordeel
- **Gevalideerd (eval):** GC · ES · MGC · MES — pass-rates 35-55%, stress-ongevoelig, onderling ontkorreleerd.
  ES/MES = sterkste eval-been; micro-evals zijn een volwaardig goedkoop alternatief.
- **Funded:** alleen MGC (en GC-250k) halen het accountdoel; alle funded-configs zakken door de stress-gate →
  geen onvoorwaardelijke validatie. Live draaien mag alleen met guardrails + wekelijkse logging; ES-full-funded niet.
