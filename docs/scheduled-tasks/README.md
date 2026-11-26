# Geplande taken (claude.ai › Scheduled tasks) — stand 06-11-2026

_Eigenaar: Scrum Master. **Sinds 06-11 vallen álle geplande taken onder beheer van de SM**
(besluit Ferry: "Ook die dagelijkse taken vallen onder je beheer"). De prompts zelf leven in de
taakinstellingen op claude.ai; dit bestand is het spoor: welke taken er zijn, wat ze doen, en
wat er wanneer is gewijzigd. Wijzigt een andere chat een taak, dan hoort dat hier te staan —
op 06-11 bleken twee taken (EOD Recap, Discord-autopost) en twee prompt-wijzigingen (Outlook,
Dagstart) van buiten deze chat te komen; die zijn nu opgenomen._

| Taak | Schema (America/Curacao) | Connectors | Schrijft naar | Status |
|---|---|---|---|---|
| PA · Dagstart | dagelijks 06:17 | Notion, Microsoft 365 | PA — Dagbrief **en** 🛠️ MEX — Dagstand; boekingsvoorstellen in de Approval Queue | aan |
| PA · Dagafsluiting | dagelijks 21:11 | Notion, Microsoft 365 | idem; boekt in WealthOS **alleen na akkoord** op een Approval-item | aan |
| Daily Outlook 07:00 | ma–vr 07:00 | Notion | Content Hub, Outlook-item van vandaag (tekst, zonder screenshots); draft | aan |
| MEX EOD Recap — dagelijkse draft | ma–vr 17:25 Chicago (= 18:25 Curaçao, net na de Apex-reset) | Notion, Microsoft 365 | Content Hub, Recap-item van vandaag; draft, Status blijft Script | aan (nieuw 06-11) |
| MEX Recap — auto-post naar Discord | ma–vr elk uur 18:40–23:40 Chicago | Notion | post het meest recente **gepubliceerde** Recap-item naar Discord, één keer (marker "✅ Discord geplaatst"); webhook uit een afgeschermde Notion-pagina | aan (nieuw 06-11) |
| Daily Recap 22:00 | dagelijks 22:00 | Notion | Content Hub, Recap-item | **uit sinds 06-11** — dubbel met de EOD Recap, later op de avond en ook in het weekend |
| Healthcare-budget naar $650 | eenmalig 01-12 09:00 | — | herinnering in deze chat | aan |

**Publicatiestroom Recap:** EOD Recap maakt de draft (Script) → Ferry zet Status op
**Gepubliceerd** → de autopost-taak post hem binnen het uur op Discord en zet de marker. De
Outlook kent nog geen autopost: Ferry kopieert de embed zelf.

**Tussentijdse berichten naar Discord** lopen via dezelfde stroom: de SM maakt een Content
Hub-item (Type Recap, Status Gepubliceerd, titel met "tussentijdse update", embed-JSON onder
de kop "Discord embed") en start de autopost-taak handmatig. De recap-taken negeren items
met "tussentijdse update" in de titel. Eerste keer: 06-11 (drie nieuwe funded accounts,
hedging-waarschuwing, mailbox gekoppeld).

## Wat er op 06-11 is gewijzigd

1. **Microsoft 365** hangt aan Dagstart en Dagafsluiting (Ferry, via de taakinstellingen; via
   de API kan dat niet). Eerste run met mail: Dagstart 06-11, correct — de twee Apex-hedging-
   mails stonden erin en zijn door de SM nagelezen.
2. **Commissie- en eval-regel gelijkgetrokken in beide recap-taken** (EOD Recap én de oude
   Daily Recap): alleen funded accounts in het vlootcijfer, evaluaties apart als "geen geld",
   en op Custom-Executor-rijen alleen het **verschil** met het Apex-tarief (MGC $0,15 per
   contract per kant; micro-index $0) omdat Gross PnL daar al netto is van $0,52 per kant.
   Beide trokken tot 06-11 het volle tarief af en telden evals mee — dezelfde dubbeltelling die
   op 05-11 uit de PA-taken is gehaald.
3. **Daily Recap 22:00 uitgezet** (niet verwijderd): dubbel met de EOD Recap van 17:25 CT, die
   direct na de Apex-reset draait, alleen op weekdagen, en de privacyregel (geen
   accountnummers of -aantallen in publieke output) al droeg. Terug aanzetten kan in één klik.
4. De **Discord-autopost** leest de webhook uit een afgeschermde Notion-pagina. Dat is een
   secret buiten `.env`; hij staat daarmee in het secrets-register thuis (D-11/D-150).

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
