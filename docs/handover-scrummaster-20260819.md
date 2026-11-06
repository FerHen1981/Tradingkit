# Overdracht aan de Scrum Master — chat "legacy-accounts / middleware receiver"

Datum 19 augustus 2026 · branch `claude/legacy-accounts-scripts-analysis-ui0j6m`
Deze chat bezit de **source van het live executiepad** (`mex-receiver`). Die staat op
geen enkele andere branch.

Velden: **eigenaar** (volgens de werkafspraken van 19-8) · **status** · **live?** (raakt
het executiepad) · **blokkeert** · **bron van waarheid**.

---

## A · Beslissingen die alleen de Scrum Master kan nemen

Dit zijn geen taken maar tegenstrijdigheden. Zolang ze open staan kiest elke chat zijn
eigen waarheid, en dat is precies hoe er tegenstrijdige instellingen live komen.

| # | Conflict | Waarom het nu pijn doet |
|---|---|---|
| A1 | **Twee coördinatieschema's.** `docs/chats.md` (branch `analyses-data-chat-org-3tii8j`) zegt *branch per chat, nooit op andermans branch pushen*. De werkafspraken van 19-8 zeggen *één branch voor alles*. | Sluiten elkaar uit. Ik kon vandaag niet bepalen waar mijn werk hoort zonder het aan FH te vragen. |
| A2 | **Twee sets eigenaarsnamen.** "Analyses & Data / Middleware dev / Pine dev" tegenover "Backtest Setup / Middleware App / Pine Dev", met andere mappen. | Regel 2 ("alleen de eigenaar muteert") is niet toepasbaar zolang niet vaststaat wie wie is. |
| A3 | **`origin/main` bevat alleen `Initial commit` (29 juli).** Zeven branches leven los naast elkaar. | Elke afspraak over "de repo is de single source of truth" is nu fictie. Dit blokkeert A4 en veel van B. |
| A4 | **Drie `docs/inbox.md`** op drie branches (incl. de mijne van vandaag). | Een melding in de ene inbox is onzichtbaar voor de andere chats. Coördinatie via git werkt pas ná de merge. |
| A5 | **Commissie per contract staat op vier waarden**: Pine 0,67 / 1,55 · backtest 0,52 / 1,75. | Raakt élk backtestgetal én de kostenaanname in het live pad. Zolang dit open is zijn resultaten tussen chats niet vergelijkbaar. |
| A6 | **Regel 4 uit `chats.md`: "CVD wordt nooit uitgezet."** In mijn validatie van 11-8 draaide El Matador met `use_cvd_filter=False` als vastgelegde aanname (er is geen CONFIG-bewijs van zijn live stand). | Volgens die regel had de analyse moeten stoppen. Ik wil de gepubliceerde Matador-uitslag hierop laten herwegen in plaats van hem zelf glad te strijken. |

**Advies over het bord zelf:** zet het in Notion, niet in git — zolang A3 open is kunnen de
chats elkaars bestanden niet lezen. Eén uitzondering vastleggen: **live-executie-incidenten
gaan direct, melden mag achteraf.** Het PMT-incident van vandaag had via een bord een halve
dag gekost.

---

## B · Openstaande items uit deze chat

### Live executiepad — hoogste prioriteit

| # | Item | Eigenaar | Status | Live? | Blokkeert |
|---|---|---|---|---|---|
| B1 | `167.233.215.60` in de PMT IP-pool zetten | FH | open | ja | **alle orders**; PMT weigert nu alles wat de trechter doorstuurt |
| B2 | Receiver bouwen + herstarten met commit `97c50cd` (IPv4-binding + weigering zichtbaar) | Middleware | **niet gecompileerd** — geen .NET SDK in de sessie; build op de VPS is de poort | ja | B3 |
| B3 | Terugkijken hoeveel orders sinds de omzetting geweigerd zijn | FH | open | ja | — kan alleen via PMT's alertgeschiedenis; de oude logging schreef weigeringen weg als `sent 200` |
| B4 | `result` in `routed_*.jsonl` kan nu `GEWEIGERD …` zijn en `sent 200` kan een achtervoegsel hebben | Middleware → **lezers** | gemeld | ja | `mex-journal-sync`, `mex-routed-journal`, dashboard: match op **prefix**, niet op de hele string |
| B5 | Middleware-secret roteren (stond in een gedeeld alerts-log) | FH | open sinds 11-8 | ja | doe het in dezelfde ronde als een URL-wissel |
| B6 | Alert van account …018 (MGC q8) wijst nog rechtstreeks naar Discord i.p.v. de trechter | Pine Dev / FH | open | ja | die orders lopen buiten de trechter om |
| B7 | `→ Middleware (fan-out)` uitvinken in *9 · EXECUTION* | Pine Dev | open | ja | levert de ruismelding "Captain Hook · MEX Signaal" |

### Data en validatie

| # | Item | Eigenaar | Status | Live? | Bron |
|---|---|---|---|---|---|
| B8 | **`Delta` is identiek nul** in `ES_norm.csv`, `GC_norm.csv`, `YM_norm.csv` | Backtest Setup | vastgesteld 11-8 | nee | elke run met CVD-filter op die bestanden geeft 0 trades — geen marktuitslag maar een datakwestie |
| B9 | Voor GC en YM bestaan `*_cvd.csv` mét echte delta; **voor ES niet** | Backtest Setup | open | nee | ES-cellen blijven onbeslist tot er delta-data is |
| B10 | Validatie Patrón/Matador/Dorado: **0 van 15 door S4** (hoogste PF r12m = 1,04) | Backtest Setup | afgerond, gepubliceerd | nee | `validation/NQFAMILY_stage3-7_verdicts_20260811.md` · rapport: https://claude.ai/code/artifact/5901bfd1-3ce5-4bef-9268-73cb4706963d |
| B11 | **Besluit nodig:** past de S4-gate (PF ≥ 1,20) bij scripts die via de Apex-trechter renderen, of halen ze de lat niet? | Scrum Master | open | nee | zolang dit niet vastligt schuift de lat elke run |
| B12 | Stage-10 live-logging, week 2 van 4 | Backtest Setup | loopt | nee | wekelijkse live-vs-backtest-vergelijking |

### Accounts

| # | Item | Eigenaar | Status | Live? |
|---|---|---|---|---|
| B13 | Vier accounts in auto-liq op 10-08: …211, …016, …019, …020. **…019 (−$13,12) en …020 (−$0,42) staan onder de trailing-vloer.** | FH | status bij Apex onbekend | ja — bepaalt of je 8 of 10 actieve accounts hebt |
| B14 | MGC-sizes draaien q6–q10, de fleet-matrix pint q3/q5. De uitval was op grootte geordend (q10 en q7 eruit, q8 in liq, q6 overeind). | Scrum Master / FH | open | ja |

### Ops en outlook

| # | Item | Eigenaar | Status | Live? |
|---|---|---|---|---|
| B15 | Charts-crawler draait **02:45 ET**, gedocumenteerd als 08:00 ET | FH | open | nee — maar maakt de outlook onbruikbaar (7 uur vóór de open) |
| B16 | `mw.mex-traders.com` niet op de allowlist van de omgeving waar de outlook-routine draait | FH | open | nee — blokkeert de geplande run volledig |
| B17 | Outlook-methode rechtgezet: downloaden-en-lezen i.p.v. WebFetch | deze chat | **klaar** | nee — `tools/fetch_outlook_charts.sh` + format-note in Notion |

---

## C · Wat deze chat heeft opgeleverd (context, geen actie)

- `.NET`-receiver met trechter, kaart-rendering, kill-switch, dedupe en audit — `middleware/dotnet-receiver/`
- Renderer die de Pine-payload zelf leest — `middleware/renderer/render-signal.js`
- Reconstructie van alle alert-instellingen van 3–10 aug uit de alerts-log — `tools/parse_alerts_log.py` + PDF
- Validatiepipeline over 3 scripts × 5 slots — `validation/run_nqfamily_*.py`
- Recap-cijfers uit de audit-log — `tools/recap_data.py`
- Ops-hulpmiddelen — `deploy/mex-ops.ps1`, `deploy/charts-crawler.cron`, `deploy/morgen-11-aug.md`
