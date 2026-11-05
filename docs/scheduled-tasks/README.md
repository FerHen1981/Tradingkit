# Geplande taken (claude.ai › Scheduled tasks) — stand 05-11-2026

_Eigenaar: Scrum Master. De prompts zelf leven in de taakinstellingen op claude.ai; dit bestand
is het spoor: welke taken er zijn, wat ze doen, en wat er op 05-11 is gewijzigd._

| Taak | Soort | Schema (America/Curacao) | Connectors | Schrijft naar |
|---|---|---|---|---|
| PA · Dagstart | Chat | dagelijks 06:17 | Notion (+ Microsoft 365 zodra verbonden) | PA — Dagbrief **en** 🛠️ MEX — Dagstand; boekingsvoorstellen in de Approval Queue |
| PA · Dagafsluiting | Chat | dagelijks 21:11 | idem | PA — Dagbrief **en** 🛠️ MEX — Dagstand; boekt in WealthOS **alleen na akkoord** op een Approval-item |
| Daily Outlook 07:00 | Chat | ma–vr 07:00 | Notion | Content Hub, Outlook-item van vandaag (tekst, zonder screenshots) |
| Daily Recap 22:00 | Chat | dagelijks 22:00 | Notion | Content Hub, Recap-item van vandaag (tekst, zonder screenshots) |

## Wat er op 05-11 is gewijzigd (besluit Ferry 04-11, optie B)

1. **PA · Dagstart / Dagafsluiting** schrijven het MEX-blok nu óók op `🛠️ MEX — Dagstand`
   (page `40eb61ea444d811891f0f09ab6d3f41d`), de enige bron voor de MEX-stand.
2. **Commissies** worden berekend in plaats van op $0 gelaten: per contract per kant MGC $0,52,
   MES/MNQ/MYM $0,37 (bron: `backtest/config.py`), met de vermelding "berekend, niet afgerekend"
   totdat de middleware het veld `Commissions` uit de Cash History vult (D-163).
3. **Boekingsvoorstellen** gaan als Approval-item (`🛠️ MEX — Boeking: …`) in 📥 Inbox; de
   avondtaak boekt uitsluitend na een akkoord van Ferry op zo'n item.
4. **Outlook en Recap** maken het Content Hub-item van vandaag zelf aan als de charts-crawler
   niets heeft klaargezet, op tekstdata van het web — zonder screenshots. Voorheen weigerden ze
   dan en kwam er niets.
5. De mailbox mag gelezen worden zodra de Microsoft 365-connector aan de taak hangt.

## Bevinding bij het nakijken (05-11)

Het Trade Journal (`collection://1ddb61ea-444d-8136-8cd1-000b89919d64`) wordt **wél**
automatisch gevuld (`Sync Status = Auto`, `Source = Custom Executor`, rijen tot vanavond), met
Gross PnL, slippage, MFE/MAE en account in Notes — maar `Commissions` staat overal op 0 en de
**Dagbalans** (`collection://353af0a8-…`) is leeg. De regel in `CLAUDE.md` dat "de
LifeOS-schrijfkant nooit automatisch gedraaid heeft" (D-20, gemeten 18-09) is dus achterhaald
voor het journaal en blijft gelden voor de Dagbalans en de commissies. D-163 is daarop
herijkt.

## Terugdraaien

De prompts van vóór 05-11 staan in `originals-2026-11-05.md`.
