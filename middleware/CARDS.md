# Trade-cards — event→kaart-matrix (spec voor render-signal.js)

Detectie: substring in `embeds[0].title` (de Pine-titels zijn stabiel).
Payload komt als JSON op stdin; output via $MEX_SIGNAL_OUT.

## Tier A — volledige kaart 800×420 (de momenten die tellen)
| Event | Detectie | Kleurdominant | Kern van de kaart |
|---|---|---|---|
| EXIT winst | "EXIT" + PnL `+` | azuur | PnL groot · reason-badge (TP/TRAIL/RECOV/BE-STOP) · entry→exit+ticks · MFE/MAE/hold · dag/week/gate-blok |
| EXIT verlies | "EXIT" + PnL `-` | rose | idem, PnL in rose |
| PASSED | "PASSED" | goud (celebration) | "EVAL PASSED" · eindsaldo · dagen/trades · volgende stap (PA) |
| FAILED | "FAILED" | rose | oorzaak (breach/DD) · schade · reset-advies |
| PAYOUT READY | "PAYOUT" | goud | cap · withdrawable · cyclus x/6 · qual/consistency |
| ACCOUNT HALT | "ACCOUNT HALT" | rose, randalarm | reden · DD-room op halt · sinds wanneer |

## Tier B — compacte strip 800×220 (context, geen hoofdmoment)
| Event | Detectie | Accent |
|---|---|---|
| LONG/SHORT LIMIT · MARKET (entry) | "LONG "/"SHORT " + LIMIT/MARKET | azuur/rose richting · SL/TP-regel |
| FILL | "FILL" | sand |
| RISK OFF (→BE) | "RISK OFF" | goud — "initial risk off the table" |
| TRAIL ACTIVE | "TRAIL" | goud |
| DAY HALT | "DAY HALT"/"Day-" | rose-dim · reden + hervat-tijd (18:00) |
| DERISK L1/L2 · PA DERISK | "DERISK" | goud-diep · nieuwe qty |
| PASS LOCK | "LOCK" | goud · afstand tot target |
| PA THRESHOLD | "THRESHOLD" | goud |
| REGIME → FAV/UNFAV | "REGIME" | azuur/rose pijl |

## Tier C — tekst-embed (geen kaart; ops/ruis — blijft fallback-pad)
CONFIG · ACCOUNT STARTED · LIMIT EXPIRED · SIGNAL BLOCKED · AUTO FLAT
Ratio: hoogfrequent of puur administratief; een kaart voegt niets toe en
Discord-rate-limit (30/min/webhook) wil je bewaren voor Tier A/B.

## Regels
1. Onbekende titel ⇒ generieke sand-kaart (nooit stil verloren).
2. Kleur volgt uitsluitend de brand-tokens (abyss/deep/surface/sand/goud/azuur/rose).
3. Eén webhook per kanaal-doel: trades (A/B) gescheiden van ops (C) aanbevolen.
4. Tier is data, geen code: `CARD_TIER_OVERRIDES` in .env kan events promoveren/degraderen.
