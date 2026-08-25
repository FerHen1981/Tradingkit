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

## Tier B — ook als kaart (per dag/sessie eenmalig, dus geen rate-limit-risico)
| Event | Detectie | Accent |
|---|---|---|
| CONFIG | "CONFIG" | dim — instellingen bij sessie-start, `k=v`-rijen |
| AUTO FLAT | "AUTO FLAT" | dim — sessievenster dicht, prijs waarop is platgemaakt |
| LIMIT EXPIRED | "LIMIT EXPIRED" | dim — richting + limietprijs die nooit geraakt werd |
| ACCOUNT STARTED | "ACCOUNT STARTED" | goud — account, fase en de eerste order |

## Tier C — tekst-embed (geen kaart)
Leeg sinds 25-08: elk Pine-event dat een kaart kan dragen, krijgt er een. De
Discord-rate-limit (30/min/webhook) wordt nu bewaakt door de rate-limit in
`PostRate` in plaats van door events op tekst te laten staan.

## SIGNAL BLOCKED — gepoort, niet getierd
Staat een account op halt, dan wordt élk geldig setup-signaal geblokkeerd: hetzelfde
bericht komt bar na bar terug. Daarom beslist `BlockedGate` in de receiver, niet de
tier-tabel:

- Blokkade die de **handelsdag of het account beëindigt** (`Day halt: …`, `Account: …`,
  breach, eval passed) ⇒ **één kaart**, per symbool per categorie (`day` / `account`)
  per handelsdag (kalenderdatum New York, dezelfde grens als de dagteller in de scripts).
- Elke **routineblokkade** (time gate, flat window, stop invalid, qty < 1, MAE/DD guard)
  en elke herhaling ⇒ **niets naar Discord**; het journaal houdt ze wél
  (`blocked-notice suppressed`).
- `MEX_CARD_TIER_OVERRIDES="SIGNAL BLOCKED=B"` zet de poort uit en laat álles door.

## Regels
1. Onbekende titel ⇒ generieke sand-kaart (nooit stil verloren).
2. Kleur volgt uitsluitend de brand-tokens (abyss/deep/surface/sand/goud/azuur/rose).
3. Eén webhook per kanaal-doel: trades (A/B) gescheiden van ops (C) aanbevolen.
4. Tier is data, geen code: `CARD_TIER_OVERRIDES` in .env kan events promoveren/degraderen.
5. Gedempt is niet verloren: wat Discord niet haalt, staat in `routed_*.jsonl`.
