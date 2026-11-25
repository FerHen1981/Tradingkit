# Deploy-set 25-11-2026 — scripts met de gemeten inputs

Kopieën van de v3.13.8-scripts uit `pine/` met alléén de defaults aangepast die uit de metingen van
24/25-11 volgen (`docs/PLAN-2026-11-25-accountstructuur.md`, `docs/DECISIONS.md`). De basisscripts in
`pine/` zijn niet gewijzigd; de bevroren sets blijven bevroren. Eigenaar van `pine/**` is Pine Dev; deze
map is door de SM aangemaakt op directe opdracht van Ferry (melding in `docs/inbox.md`).

| Bestand | Rol | Basis | Gewijzigde defaults | Gemeten |
|---|---|---|---|---|
| `EL_TORO_NQ_EVAL_4c_TP122_fundednext.pine` | eval FundedNext Rapid Pro, ook Lucid Pro | EL TORO NQ HF | qty 4 · FVG 19–27 · confirm 4 · TP 122 (SL 90, expiry 9, CVD 3 stonden al) · EOD · owner-DLL uit · preset `fundednext_50k_rapid_eval` | 57% pass, mediaan 1 dag (twee hits); TP 155 zou 62% geven maar is een nieuwe set |
| `EL_TORO_NQ_EVAL_4c_TP122_topstep.pine` | eval Topstep Combine | idem | idem + max 1 winst per dag · preset `topstep_50k_eval` | 52% pass, mediaan 3 dagen |
| `EL_TORO_NQ_EVAL_4c_TP155_fundednext.pine` / `_topstep.pine` | eval, één hit op 4 NQ | idem | als TP 122 maar TP 155 (= $3.088 per hit) | 62% (FundedNext) / 45% (Topstep); **nieuwe set, OOS-klok op nul** |
| `EL_TESORO_MGC_FUNDED_2c_fundednext.pine` | funded FundedNext (ook Lucid) | EL TESORO MGC | qty 2 · preset `fundednext_50k_rapid_pa`; verder de bevroren set (8–23, c4, e12, SL 100, TP 85, trail+cap 150/50/300, giveback-2 50 @ 04:00, 5 verliezen, owner-DLL 4 stops) | zie funded-metingen 25-11 |
| `EL_TESORO_MGC_FUNDED_2c_topstep.pine` | funded Topstep XFA | idem | qty 2 · preset `topstep_50k_xfa` (EOD 2.000, geen DLL, geen consistentie = standaardpad) | idem |
| `EL_REY_MNQ_LIVE_2c.pine` | Apex Live | EL REY MNQ | qty 2 · geen preset · EOD · trailing 3.000 · DLL 3.000 (= uit) · consistentie 100 (= uit) | 0% breach / 250 d, $2.390 per 250 d; pariteit El Rey nog open |
| `EL_TESORO_MGC_LIVE_1c_TP120.pine` | Apex Live, optie/meetaccount | EL TESORO MGC | qty 1 · TP 120 · geen preset · EOD · 3.000 · DLL uit · consistentie uit | 14% breach / 250 d, $700; TP 120 is een nieuwe set (nieuwe OOS-klok) |

## Op de chart nog zelf zetten (staat bewust niet in de bestanden)

- `0 · ACCOUNT — Identity` → PMT/Tradovate Account ID van het account.
- `10 · SIGNAL — Alerts` → route (PMT Tradovate of PMT Rithmic) en PMT Token.
- `1 · Timezone` → Valid from = startdatum; `8 · ACCOUNT — Guard` → Account start = activatiedatum.
- De preset-tabellen in álle scripts zijn 25-11 opnieuw gegenereerd uit de registry (`tools/gen_pine_firms.py`):
  FundedNext Rapid Pro/Direct en Topstep Combine/XFA staan erin.
- El Tesoro funded bij Lucid: preset `fundednext_50k_rapid_pa` laten staan (zelfde regels), zodra de
  Lucid-regels officieel zijn nagelezen.

## Regels die blijven gelden

- **Wis de Properties-tab vóór je een export deelt of uploadt** — de export schrijft het PMT-token en het
  account-ID in platte tekst weg.
- Elke wijziging aan een bevroren set (TP 155, TP 120) is een nieuwe onderzoeksronde en zet de OOS-klok op nul.
- Pine is indentation-sensitive: 4 spaties, geen tabs (gecontroleerd: 0 tabs in deze map).
- Herbouwen: `bash pine/deploy/2026-11-25/make.sh` (alleen input-defaults, basis blijft bevroren).
- `pine/tools/pine_lint.py`: El Toro ×4 en El Rey schoon. De drie El Tesoro-kopieën krijgen de melding
  "default delta-motor is ta.requestVolumeDelta" — dezelfde bewuste keuze als in het basisscript (besluit Ferry
  25-08), dat de lint op bestandsnaam vrijstelt; de kopie niet. Inhoudelijk gelijk aan de basis.
