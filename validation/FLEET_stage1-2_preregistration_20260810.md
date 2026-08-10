# Stage 1-2 — Pre-registratie GC/ES/MGC/MES validatie (20260810)
VASTGELEGD VOOR DE RUNS. Aanvulling op de NQ-pipeline van vandaag.

## Data & windows
- GC: data/GC_norm.csv · ES: data/ES_norm.csv (beide 2023-08-02 .. 2026-07-31; delta-loos -> delta-arm niet testbaar).
- MGC/MES: zelfde prijsreeksen (micro volgt full), eigen contractspecs: MGC $10/pt ($1/tick), MES $5/pt ($1.25/tick),
  commissie micro $0.67/ct/zijde (gemeten, Tradovate-fills 08-08); GC $1.75, ES $1.55.
- IS: .. 2026-01-31 · "OOS": 2026-01-31 .. 2026-07-31 · regime-jaren Y1/Y2/Y3 vanaf 2023-08-02 · recente 12m vanaf 2025-07-31.

## !! OOS-BESMETTING (verplichte disclosure, skill-regel 2)
De GC- (9-18) en ES- (9-15/vwap-uit/conf2) configs zijn eerder deze sessie geselecteerd via split-half sweeps
over het VOLLEDIGE venster, inclusief de laatste 6 maanden. Het "OOS"-venster hieronder is daarmee GEEN maagdelijke
out-of-sample voor de signaalkeuze; het wordt gerapporteerd als **quasi-OOS [TAINTED]** en telt als in-sample-adjacant.
De enige schone OOS voor deze configs is toekomstige data (de lopende live-logging).
WEL vers: de micro-vraag (overleeft de edge de MGC/MES-commissiestructuur en micro-sizing) en de stress/qty-armen.

## Kandidaten (fleet-configs uit de setup-sheet; label intern)
| id | signaal | doel/overlay | qty |
|---|---|---|---|
| GC_EVAL  | Minero 9-18/conf0/vwap-aan/stop100/R1.5 | 50k intraday eval 2500/3000 | 1 |
| GC_FUNDED| Tesoro idem + R2.5/BE/trail/dt300/MAE/wfc | 250k intraday PA 6500, DLL1000 | 2 |
| ES_EVAL  | Leon 9-15/conf2/vwap-uit/stop100/R1.5 | 50k EOD eval 2500/3000 | 1 |
| ES_FUNDED| Rey idem + dt300/MAE/wfc | 250k intraday PA 6500, DLL1000 | 2 |
| MGC_EVAL | = Minero-signaal | 50k intraday eval | 10 |
| MGC_FUNDED| = Tesoro-signaal | 50k EOD PA 2500, DLL1000 | 8 |
| MES_EVAL | = Leon-signaal | 50k EOD eval | 10 |
| MES_FUNDED| = Rey-signaal | 50k EOD PA 2500, DLL1000 | 5 |

## Gates (idem NQ-pipeline)
S4 zoals geschreven: recente-12m contract-PF >= 1.2 (gerapporteerd) + accountdoel: eval pass-rate r12 >= 25%,
funded banked/breach r12 >= $500. S5: WFE >= 0.5 (doelmetric quasi-OOS/IS), perturbaties IS-only binnen ±30%
(GC: gap 6-15/12-21, stop 80/120, confirm 2 · ES: gap 6-12/12-18, stop 80/120, confirm 0 · micro's: qty ±).
S7: stress quasi-OOS 2-tick + 2x commissie, verval doelmetric < 50%. S6: dagcorrelaties GC-ES erbij.
S10: 1 live-week beschikbaar -> INCONCLUSIVE; MGC/MES hebben WEL echte live fills (03-08..08-08) als referentie.
