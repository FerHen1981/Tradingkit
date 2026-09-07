# v7-proposal — draft, niets is aangesloten

Deze map is een **voorstel**. Er wordt niets van gelezen door de engine, de backtester
of de middleware. De acht scripts in `pine/` blijven ongewijzigd op v6.9.1.

| Bestand | Wat het zou vervangen |
|---|---|
| `data/instruments.json` | Markt- en instrumentfeiten: tick, pointvalue, sessie, kosten, roll-familie. Nu impliciet in 8 scripts + `backtest/config.py`. |
| `data/profiles.json` | De 8 `.pine`-bestanden. 3 assets x 2 houdingen (grind/push). Elke waarde is letterlijk uit de huidige scripts overgenomen. |

Visueel overzicht van het bijbehorende instellingenscherm staat in het artifact
"MEX MR·FVG Settings"; de architectuurnotitie staat in Notion onder
"MEX Pine v7 — Architectuurvoorstel".

## Openstaand voor deze draft
- `provenance.pf_h1` / `pf_h2` / `trades` per profiel moeten uit `backtest/funnel.py` komen.
- GC gebruikt R 2.5 op grind en 1.5 op push; ES gebruikt 1.5 op beide. Gevalideerd of drift?
- Kostenvelden voor FX/crypto (spread, swap, funding) zijn schattingen en moeten per broker geverifieerd.

## Correctie op een eerdere aanname
Break-even en trail bereiken de broker **wel**. Naast de `alert()`-aanroepen in `f_sendExec`
draagt elke `strategy.entry`/`strategy.exit` een `alert_message` (aan zodra de PMT-route aan
staat, zie `alertMsgAuto`), en die vuurt bij elke order-fill — dus ook wanneer de door BE of
trail verplaatste stop geraakt wordt. `comment_loss` tagt de fill met BE|/TRAIL|/RECOV|/SL|.

Wat wel klopt: de stop wordt scriptzijdig beheerd. De bracket die bij de entry naar Tradovate
ging blijft op de oorspronkelijke afstand staan; de BE-bescherming ontstaat doordat het script
sluit, niet doordat de broker-stop meebeweegt.

Eén asymmetrie die een blik waard is: bij de fill (regel 1330/1332) draagt de exit een
`alert_message`; de per-bar heruitgifte met de bijgestelde stop (regel 1439/1462) doet dat niet.
Te bevestigen in het TradingView-alertlog, niet vanuit de code.
