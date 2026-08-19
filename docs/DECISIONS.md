# DECISIONS.md — beslissingslogboek

> Eén regel per beslissing of vaststelling die buiten het eigen item reikt. Nieuwste
> bovenaan. Formaat: `datum · item · wat · waarom · raakt`. Eén zin, geen proza.
> Dit is waar sessies met elkaar praten — via het spoor, niet live.
>
> Uitgebreide onderbouwing hoort in het item op het bord of in de Notion-notitie
> *🛠️ MEX Dev — Besluitregister*; hier staat alleen de regel zelf.

---

- 2026-08-19 · D-32 · **Scrum Master mag zelf corrigeren** binnen eigen domein, bij aantoonbaar onjuiste documentatie en bij een aantoonbare, lokale breuk — nooit op het live executiepad, nooit andermans werk weggooien, nooit een open architectuurkeuze zelf maken · elke correctie krijgt een regel hier · raakt: alle chats
- 2026-08-19 · D-33 · **Toezicht is mutatie-gedreven, niet op een klok** · elke Scrum Master-sessie start met een diff tegen het watermerk onderaan `SPRINT.md` · raakt: alle chats
- 2026-08-19 · D-00 · **Één bord: `docs/SPRINT.md`** · drie coördinatiedocumenten waren onafhankelijk ontstaan (twee `docs/scrum.md` + de itemlijst in `inbox.md`) · raakt: alle chats
- 2026-08-19 · D-00 · **Claim-protocol ingevoerd** (status `wip` + owner + losse commit vóór het werk; conflict = signaal) · voorkomt dat twee chats dezelfde feature bouwen, zoals bij de notice-cards gebeurde · raakt: alle chats
- 2026-08-19 · D-00 · **Rolverdeling vastgezet**: Backtest Setup · Pine Dev · Middleware App · Web · Analyses & Data · Scrum Master · de namen uit `docs/chats.md` vervallen · raakt: eigenaarstabel
- 2026-08-19 · D-00 · **`docs/inbox.md` blijft de wachtrij, niet het register** · nieuwe meldingen komen daar binnen en worden door de Scrum Master op het bord gezet · raakt: alle chats
- 2026-08-19 · S-04 · **WEERLEGD: `playbook.py` en `firm_rules.py` bestaan wél** — op `claude/middleware-setup-guide-afhvtk`, met `STRAT_ASSET` op regel 34 · de conclusie 'bestaat op geen enkele branch' kwam voort uit kijken vanaf een niet-gemergede branch · raakt: S-05, D-13
- 2026-08-19 · D-03 · **VASTGESTELD: de Notion-database *MEX Reconciliation (live)* heeft 0 rijen** · de reconciliatielaag is gebouwd maar heeft nooit in productie geschreven · raakt: D-03, D-20
- 2026-08-19 · D-02 · **VASTGESTELD: `risk.py` wordt alleen door `main.py` en `router.py` geïmporteerd** en die draaien niet · de per-account risicolimieten handhaven niets · raakt: D-05
- 2026-08-19 · D-01 · **VASTGESTELD: `viewer.py:161` faalt open bij een lege `VIEWER_PASSWORD`** · de hele fleet-API is publiek zolang die variabele niet gezet is · raakt: mex-viewer
- 2026-08-19 · — · **RUNTIME GEVERIFIEERD op mex-mw-01**: `mex-receiver` (.NET) draait uit `/root/mex-middleware-b/src/Mex.Journal.Receiver`, `dryRun:false`, `armed:true`, `pmtConfigured:true`, `renderEnabled:true` · geleverd door de Discord Notify-chat · raakt: D-02, D-04, D-05, D-06
