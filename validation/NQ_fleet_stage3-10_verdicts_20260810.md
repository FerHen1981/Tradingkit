# Stages 3-10 — verdicts (NQ-fleet, data t/m 2026-06-17, OOS = laatste 6 mnd, one-shot)

## S3 Engine-validatie — PASS
Geen look-ahead (limit vult pas de bar ná plaatsing; exits vanaf bar ná fill — engine-design),
kosten aan ($1.55 + 1 tick), IS-trades: Toro 4.782 / Dorado 5.541 (≥100), volledig preset-reproduceerbaar.

## S4 Bulk backtest — GATE-AS-WRITTEN: FAIL · pre-geregistreerd accountdoel: PASS
Contract-PF recente 12m: Toro 1.00 · Dorado/Patrón 0.99 → allen < 1.2 (gate zoals skill schrijft: FAIL).
Per regime-jaar (Toro): Y1 0.92 → Y2 0.99 → Y3 1.00 (edge-loos op contractniveau, wel verbetering richting nu).
Accountdoel (pre-geregistreerd, grondregel 5):
- TORO eval pass-rate: IS 32.5% · recente-12m 37.5% (gate ≥25% PASS) · OOS 36.4%
- DORADO banked/breach r12 $550 (gate ≥$500 PASS) · OOS $650 | PATRON r12 $650 PASS · OOS $650
Vervolg van de pipeline is dus expliciet op het accountdoel, niet op contract-PnL (vooraf zo geregistreerd).

## S5 Robuustheid — PASS (met MC-flag)
WFE (doelmetric OOS/IS): Toro 36.4/32.5 = 1.12 ≥ 0.5 ✓ · Dorado bpb 650/208 ✓.
Perturbaties (IS): basis 32.5%; gap 7-10→29.4 · gap 11-14→31.7 · stop 58→32.5 · stop 86→35.7 ·
confirm 0→31.0 · confirm 4→33.3 — alles binnen ±20% van basis ✓.
Delta-AAN-sensitiviteit: 27.0% (slechter) → delta UIT blijft juist.
MC (1000× bootstrap OOS-trades): p5 maxDD $98.5k CONTINU-lens — ondraaglijk zonder account-halts;
bevestigt: dit bestaat alleen als account-variance-play (risico per poging gecapt op DD $2.5k). FLAG.

## S6 Fleet-fit — PASS
Dagelijkse PnL-correlatie: Toro-NQ vs Minero-GC **-0.03** · vs León-ES **+0.04** (701/650 overlapdagen) — vrijwel nul.

## S7 Stress (OOS, 2-tick slip + dubbele commissie) — TORO PASS · DORADO/PATRON FAIL
TORO: pass-rate 36.4% → 36.4% (ongewijzigd) ✓.
DORADO/PATRON: banked 6.500→3.000 (-54%), bpb 650→188 (-71%), breaches 10→16 → zakt >50% = FAIL.
CONSEQUENTIE (pipeline-regel): NQ-PA-configs stoppen hier. NQ = alleen eval-voertuig; PA op NQ niet gevalideerd.

## S8 Risk management — PARTIAL (geflagd, zoals pre-geregistreerd)
Toro q5 × stop ≤72t → max ~$1.800 = 3.6% van 50k per trade (eval = bewuste variance-play; gate ≤1% strikt FAIL, geflagd).
PA-kant: MAE-guard + DLL + day-trail in script aanwezig ✓ (maar PA-NQ is op S7 al gestopt).

## S9 Live guardrails — PASS
Auto-stop: (1) account-DD = harde stop per poging; (2) rolling-PF: stop NQ-eval-inzet als 4-weekse live PF < 0.7;
(3) slippage-divergentie: stop-slippage mediaan > 3 ticks over 20 fills → pauze; (4) alert-pad live bewezen (Discord/PMT hele week).

## S10 Paper/live — INCONCLUSIVE (1 week < 4 weken) + reflectie
Live-week valt buiten het databestand (eindigt 17-06) → structurele vergelijking:
- Live Toro NQ 9-12: 10 trades, win 50%, PF 1.57, +$5.495 → boven backtest-verwachting (OOS win 26%, PF 1.04) = positieve variance, klein n; consistent met een 36%-pass-wereld (207 passeerde live ✓).
- Live Dorado/Patrón (n=8, +$341) ≈ backtest-verwachting (~breakeven vóór de stress-haircut).
Doorlopen tot ≥4 weken logging vóór promotie-besluiten.
