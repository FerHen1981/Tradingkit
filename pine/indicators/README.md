# Companion indicators

Zeven losse indicatoren die tonen waar de strategie op filtert. Zelfde huisstijl: MPL-header,
Pine v6, genummerde inputgroepen, themabewust palet (Auto/Dark/Light) en één tabel per script.
**Defaults volgen EL REY MNQ PROD EOD.**

| Script | Pane | EL REY-default |
|---|---|---|
| `MPT_CVD.pine` | eigen | Research OHLCV proxy, streak 8 |
| `MPT_BBWP.pine` | eigen | SMA, len 20, lookback 255, band 0–100 |
| `MPT_MFI.pine` | eigen | HMA 60 |
| `MPT_VOLUME_PROFILE.pine` | overlay | Daily, 30 bins, VA 70%, intrabar 1m |
| `MPT_DISCOUNT_PREMIUM.pine` | overlay | 60 bars, mid 50% |
| `MPT_EMA.pine` | overlay | EMA 200 op close |
| `MPT_TIME_GATE.pine` | overlay | alle uren/dagen aan behalve za/zo, regime "All sessions", force flat 16:55–18:00 |

## De strategie is de bron

Deze scripts **spiegelen** de berekening uit `pine/`, ze definiëren hem niet. Lopen ze
ooit uiteen, dan heeft de strategie gelijk en moet het indicatorbestand bij.

Dat is bewust een kopie en geen Pine-library. Een library moet je eerst publiceren op
TradingView voordat iets hem kan importeren, en bij elke wijziging opnieuw — en de strategie
zou hem dan ook moeten importeren, wat een hercompile van de hele vloot betekent. Zolang de
indicatoren leesgereedschap zijn en de strategie de waarheid, wegen die kosten niet op.
**Wijzig je een formule, doe het dan in de strategie en trek hem daarna hierheen door.**

## Tabellen botsen als je ze stapelt

Pine tekent elke tabel op zijn eigen `position`. Twee tabellen in dezelfde hoek liggen dus
**over elkaar heen** — daar is geen offset of z-volgorde voor. Elk script heeft daarom een
positie-input, standaard rechtsonder. Laad je meerdere overlay-indicatoren tegelijk (VP, D/P,
EMA staan alle drie op de prijs-pane), geef ze dan elk een eigen hoek.

De drie pane-indicatoren (CVD, BBWP, MFI) hebben er geen last van: die zitten in hun eigen pane.

## Wat elke tabel onderaan toont

Elke signaalindicator sluit af met **Side allowed** — LONG, SHORT, BOTH of —. Dat is precies
de bijdrage van dat filter aan `sigLongOK` / `sigShortOK` in de strategie. Staan ze alle zes op
LONG, dan houdt geen enkel filter een long tegen.

`MPT_TIME_GATE` werkt anders, want tijd is geen richting: die sluit af met **Blocked by** en
**Time gate OPEN/CLOSED**. De gates worden in dezelfde volgorde getoetst als in de strategie —
weekdag → uur → market regime → force flat → risk-gate-venster — en het veld noemt de EERSTE
die dicht staat. Zo weet je niet alleen dát er niet gehandeld wordt maar ook waardoor.

## MPT Suite — de zes context-modules in één script

`MPT_SUITE.pine` bundelt wat je normaal als losse indicatoren zou laden. Elke module heeft
zijn eigen schakelaar in groep 0 en rekent alleen als hij aanstaat.

| module | wat je krijgt |
|---|---|
| **1 Moving average** | type-dropdown (EMA/SMA/HMA/WMA/VWMA/RMA/DEMA/TEMA) + lengte + bron, plus een tweede MA voor context |
| **2 VWAP** | los van de dropdown, met drie los instelbare σ-banden en optionele arcering |
| **3 Time gate** | de negen regimevensters van de vloot, achtergrondkleur groen bij open en grijs in het force-flat-venster |
| **4 Discount/Premium** | positie in de recente range, met de helften gearceerd |
| **5 FVG** | detectie van de vloot (of "Confirmed close" als alternatief), mitigatie op Touched of Closed through, tick- én relatief threshold-filter, boxen lopen door tot ze mitigeren, stippellijnen op de openstaande randen |
| **6 Levels** | vorige dag/week/maand H-L (+ mid) en de high/low sinds het actieve venster openging |
| **7 Sessions** | per venster een box van high naar low, met de naam erbij en optioneel de midpoint; houdt de laatste N sessies vast |

De tabel staat standaard **middle right** en toont per actieve module zijn huidige waarde.
Zet hem op een andere hoek zodra je twee MPT-indicatoren tegelijk laadt: Pine tekent elke
tabel op zijn eigen positie en er is geen offset, dus twee tabellen in dezelfde hoek
overlappen elkaar.

**De strategie is leidend.** De venstertijden en de FVG-formule zijn letterlijk overgenomen
uit de `v1_0_0`-vloot. Wijkt er ooit iets af, dan is dit script fout en niet de strategie.

De losse `MPT_EMA`, `MPT_TIME_GATE` en `MPT_DISCOUNT_PREMIUM` blijven bestaan voor wie er
maar één wil laden; de suite vervangt ze functioneel.

