# Vlootmatrix 25-11-2026 — schermen, scripts, assets, firma-ID's

Eén alert per scherm; de middleware verdeelt het signaal over de accounts die aan dat scherm hangen
(control plane, geen copy-trader). Een scherm = één script met vaste inputs op één asset. Accounts met
dezelfde firma-regels en hetzelfde script delen een scherm.

## ID-schema

`<FIRMA>-<PROGRAMMA>-<nr>` — firma: AX Apex · FN FundedNext · TS Topstep · LU Lucid. Programma: EV eval,
RP Rapid Pro funded, DI Direct, CB Combine, XF XFA, LV live. Voorbeeld: `FN-RP-03` = derde funded
FundedNext Rapid Pro-account; `AX-LV-17` = Apex Live-account 17. De broker-account-ID (PAAPEX…, Tradovate-nr)
blijft de titel in de Accounts-DB; de vloot-ID komt in `Account Name`.

## Schermen (TradingView, 1-minuut, zoals de vloot nu draait)

| Scherm | Asset | Script (`pine/deploy/2026-11-25/`) | Voedt de accounts | Aantal |
|---|---|---|---|---|
| S1 | NQ1! | `EL_TORO_NQ_EVAL_4c_TP122_fundednext.pine` | FN-EV-01…05 (en later LU-EV-01…05) | 5 (+5) |
| S2 | NQ1! | `EL_TORO_NQ_EVAL_4c_TP122_topstep.pine` | TS-CB-01…05 | 5 |
| S3 | MGC1! | `EL_TESORO_MGC_FUNDED_2c_fundednext.pine` | FN-RP-01…05 (en later LU-…) | 5 (+5) |
| S4 | MGC1! | `EL_TESORO_MGC_FUNDED_2c_topstep.pine` | TS-XF-01…05 | 5 |
| S5 | MNQ1! | `EL_REY_MNQ_LIVE_2c.pine` | AX-LV-01…25 | 25 |
| S6 | MGC1! | `EL_TESORO_MGC_LIVE_1c_TP120.pine` | AX-LV-26…50 | 25 |

**Zes schermen, drie assets (NQ, MGC, MNQ).** Kies je TP 155 voor de evals, dan vervangen de
`_TP155_`-bestanden S1 en S2 (zelfde schermen). Wil je Apex Live alleen op El Rey, dan vervalt S6 en
voedt S5 alle 50.

## Per firma

| Firma | Eval-ID's | Scherm | Funded-ID's | Scherm | Limiet | Teller |
|---|---|---|---|---|---|---|
| FundedNext | FN-EV-01…15 (max $750K allocatie) | S1 | FN-RP-01…05 | S3 | 5 funded actief, 10 nieuw/maand | 15 rewards per profiel |
| Topstep | TS-CB-01…n (onbeperkt) | S2 | TS-XF-01…05 | S4 | 5 XFA | discretie, niet te weigeren |
| Lucid | LU-EV-01…05 | S1 | LU-FU-01…05 | S3 | 10 totaal, 5 funded | Payout 5 |
| Apex Live | — | — | AX-LV-01…50 | S5 / S6 | 50 | eigen aanvraag; regels nog te bevestigen |

## Wat per account in de middleware staat

firma · programma · vloot-ID · broker-account-ID · scherm · qty (eval 4, funded 2, live 2 of 1) ·
route (PMT Tradovate / PMT Rithmic) · startdatum · teller-stand (rewards/payouts) · opnamebeleid (buffer
$1.000 ja/nee). De payout-radar in de Dagstart-taak leest deze velden.

## Voorbehouden

- Accounts op één scherm delen de accountlaag van het script (saldo, DLL, consistentie in Pine). De
  per-account bewaking zit in de middleware (risk gate) en in de Accounts-DB, niet in het scherm.
- Apex Live: platform, datafeed en bot-toestemming nog niet bevestigd; S5/S6 pas inrichten als dat er is.
- Lucid: regels van de site zelf nog na te lezen vóór LU-ID's worden uitgegeven.
