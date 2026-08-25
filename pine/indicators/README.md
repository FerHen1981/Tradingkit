# Companion indicators

Zes losse indicatoren die tonen waar de strategie op filtert. Zelfde huisstijl: MPL-header,
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

## De strategie is de bron

Deze scripts **spiegelen** de berekening uit `pine/v1_0_0/`, ze definiëren hem niet. Lopen ze
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

Elke indicator sluit af met **Side allowed** — LONG, SHORT, BOTH of —. Dat is precies de
bijdrage van dat filter aan `sigLongOK` / `sigShortOK` in de strategie. Staan ze alle zes op
LONG, dan houdt geen enkel filter een long tegen.
