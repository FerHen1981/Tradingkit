# Planning dinsdag 11 augustus — recap-dag

Alles hieronder ligt klaar; je hoeft niets meer te bedenken, alleen uit te voeren.
Tijden in ET. Commando's met `PS>` draai je in **PowerShell op je eigen machine**,
commando's met `$` in een **SSH-sessie op mex-mw-01**. Meng die twee niet — dat ging
de vorige keer mis.

Eenmalig, voor je begint:

    PS> cd <map met de repo>\deploy
    PS> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    PS> . .\mex-ops.ps1
    PS> $env:MEX_HOST = "root@<ip van mex-mw-01>"

---

## 07:30 ET — de crawler-tijd rechtzetten (10 min)

**Eerst kijken, dan pas wijzigen.** Ik weet niet met welk commando de crawler wordt
aangeroepen — dat staat in jouw crontab, niet in de repo. Dus:

    PS> Get-MexCron

Kopieer wat je ziet. In `deploy/charts-crawler.cron` staat mijn voorstel met twee
tijden: **08:00 ET voor de outlook** (90 minuten vóór de open, overnight compleet en
pre-market op gang) en **17:05 ET voor de recap** (ná de auto-flat van 16:55 en ná het
begin van de CME-onderbreking om 17:00). Pas het `node charts.js`-gedeelte aan naar
wat jouw huidige crontab laat zien, en installeer dan:

    $ crontab -l > /tmp/cron.bak                      # altijd eerst een kopie
    $ crontab -e                                       # CRON_TZ-regel + de twee tijden
    $ crontab -l                                       # controleren dat CRON_TZ er staat

De `CRON_TZ=America/New_York`-regel is geen franje: zonder die regel draait cron op UTC
en verschuift elke opname een uur zodra de zomertijd eindigt.

Werkt `CRON_TZ` niet op deze distributie (de regel verdwijnt uit `crontab -l`), gebruik
dan het systemd-alternatief onderaan het cron-bestand.

## 08:15 ET — controleren dat de outlook-charts kloppen

    PS> Get-MexCharts

Vijf bestanden van ±380 kB in `Downloads\mex-charts\<datum>`. Kijk of het beeld nu de
volle breedte gebruikt: **geen alerts-paneel, geen cookie-banner, geen tekenbalk over de
chart.** De aangepaste opname die je gisteravond stuurde was op dat punt precies goed —
dat is de norm.

Ontbreekt er een chart, dan zegt `tools/fetch_outlook_charts.sh` op de server precies wat
er mis is (404 = crawler nog niet gedraaid, HTML in plaats van PNG = allowlist).

## 09:00 ET — de eerste chart omzetten

Eén chart, niet meer. Ik zou **MGC …013** nemen: de meeste events, dus de snelste
terugkoppeling. Volgorde uit het controleblad van gisteren:

1. In *9 · EXECUTION*: PMT Tradovate **aan**, Discord **aan**, Journal **aan**, Middleware/fan-out **uit**.
2. **Nieuwe** alert aanmaken met `https://mw.mex-traders.com/signal/<secret>`.
   Niet de bestaande bewerken — de inputs blijven dan bevroren op de oude waarden.
3. De oude executie-alert én de losse `DISC …`-alert van diezelfde chart verwijderen.
4. Meekijken:

       PS> Watch-MexRouted

Je wilt per event twee regels zien: `card queued (tier B)` en daarna `card sent 200`.
Pas als je de kaart in Discord ziet: volgende chart.

**Niet vergeten:** de qty-8-alert op account …018 draait nog rechtstreeks naar Discord.
Die is niet fout — het is een tweede account — maar hij hoort ook door de trechter.

## Tijdens de sessie — waar je op let

- `Get-MexHealth` moet `renderEnabled: true`, `dryRun: false`, `armed: true` geven.
- Gaat er iets mis: de kill-switch blokkeert entries maar **nooit exits**:

      $ curl -s -X POST "localhost:5000/killswitch?token=<token>&armed=false"

- Blijft een kaart uit maar staat het bericht wel in de audit, kijk dan naar de
  `discord-card`-regel: daar staat de reden (`card failed (…)`), en het tekstbericht is
  dan alsnog verstuurd.

## 17:05 ET — recap

De recap-charts staan er na de nieuwe cron-regel vanzelf. De cijfers hoef je niet uit
Discord te plukken; die haalt dit uit de audit:

    $ python3 /root/tools/recap_data.py /root/intent-store/routed_$(date -u +%Y%m%d).jsonl

Dat geeft: aantal events per soort, afgesloten trades, netto, winrate, profit factor,
uitsplitsing per account, guards (day-halt, derisk, blocked) en een tijdlijn in ET.
Met `--json` erachter krijg je het machineleesbaar.

**Let op de datumgrens:** de audit staat op UTC-datum. Na 20:00 ET zit de dag van
vandaag al in het bestand van morgen. Voor een recap om 17:05 ET klopt `date -u` nog.

Het script staat in de repo (`tools/recap_data.py`); zet het op de server met:

    $ mkdir -p /root/tools && curl -fsSL -o /root/tools/recap_data.py \
        https://raw.githubusercontent.com/FerHen1981/Tradingkit/claude/legacy-accounts-scripts-analysis-ui0j6m/tools/recap_data.py

## Waar de recap over gaat

Met de cijfers uit dat script plus de vijf recap-charts is de recap te schrijven volgens
het format in Notion. De vraag die hij beantwoordt is niet "wat deed de markt" maar
**"deed het systeem wat het hoorde te doen"**: kwamen de entries op de gate, hebben de
guards gedaan wat ze moesten, en klopt de live-uitkomst met de backtest-verwachting.
Dat laatste is tegelijk stage-10-materiaal voor de validatiepipeline — week 2 van 4.

## Als er tijd over is

- Middleware-secret roteren (stond in een gedeeld alerts-log) en in dezelfde ronde alle
  omgezette alert-URL's bijwerken.
- `mw.mex-traders.com` op de allowlist van de omgeving waar de outlook-routine draait.
  Zonder die wijziging blijft de geplande run stranden, hoe goed de methode ook is.
