# Paste-klare startprompts — 06-10

_Eigenaar: Scrum Master. Eén blok per chat, bedoeld om letterlijk te plakken._
_Uitgebreide context staat in `docs/startprompts.md`; dit bestand is de korte versie._

🔴 **Aanleiding: gemeten op 06-10 is sinds 30-09 elke commit van de Scrum Master.**
Middleware App, Pine Dev en Backtest Setup staan 7 dagen stil, Web 18 dagen,
Analyses & Data 6 weken, MCP trader-dev heeft nooit iets op het bord gezet.
Het bord draagt intussen 20+ open items. Niet omdat er niets te doen is.

---

## 🟦 Middleware App

```
Start met `git pull origin claude/middleware-setup-guide-afhvtk`. Lees docs/SPRINT.md en
de bovenste drie items in docs/inbox.md.

Fase 2 is open: de config-API draait live en staat dicht (401 op /api/config,
401 op /api/config/audit, 405 op /api/config/validate, 401 op /api/secrets —
op 06-10 gemeten na uitrol van 6f7c22a).

Claim in deze volgorde, één item per keer, status wip + owner + losse commit:
1. D-119 — het fan-out-statusvenster (read-only). Dit gaat EERST. routed_*.jsonl
   draagt kind/account/transport/result al, en docs/runtime-snapshot.md wordt nu
   elk uur geschreven. Geen nieuwe telemetrie, geen wijziging aan het live pad.
2. D-83/D-84 — de settings-tab in middleware/app/viewer.py, tussen Playbook en
   Live (r. 702-716). Auth erft van _api_authorized(). HARDE EIS: proxy
   server-side naar localhost:5000 en voeg de Bearer daar toe — CORS blijft
   dicht, de token komt nooit in de browser. Dit scherm stuurt orders.
3. D-116 — behandel als veiligheidsitem. Drie dingen in één fix: doorvallen naar
   het platte bericht bij demping, de catch in RenderAndPostAsync een
   tekst-fallback geven, en de rate-limit vóór de tier-C-afslag halen.

Weet dit: de live bronboom is een APARTE repo (/root/mex-middleware-b, één
commit, geen remote). Wat je commit draait NIET automatisch. Zet in je
oplevering expliciet "staat in de repo, nog niet uitgerold" tot D-128 een vaste
uitrolstap heeft. Geen contracts-veld in de settings-tab (D-53/D-122: qty is van
Pine, de env is leeg en de drop-in is verwijderd).
```

---

## 🟨 Pine Dev

```
Start met `git pull origin claude/middleware-setup-guide-afhvtk`. Lees docs/SPRINT.md,
items D-124, D-125 en D-126.

Die drie raken ALLE DRIE dezelfde payout-poort. Doe ze in ÉÉN ronde met ÉÉN
OOS-reset — losse rondes betekent drie keer de klok op nul.

Volgorde:
1. D-126 — f_ladderCap(effPayoutNr) → f_firmLadder(firmPreset, effPayoutNr), en
   f_ladderCap eruit. f_firmLadder wordt al uit data/propfirms.json gegenereerd
   en heeft in 13/13 scripts NUL call-sites, waardoor een 250K legacy account nu
   blokkeert op $1.500 in plaats van $3.000. Doe dit eerst: zolang de ladder fout
   is weet je niet wanneer de poort hóórt te sluiten.
2. D-125 — pmtBlock moet ook consistencyOK eisen (of hangen op payoutReady). Nu
   kan een account zich klemzetten: cap bereikt dus geen entries, consistency
   niet gehaald dus geen payout, en consistency verbetert alleen door te handelen.
3. D-124 — useWaitForCap naar een input, DEFAULT true zodat gedrag niet wijzigt.

Bouw ook de poort die dit had voorkomen: breid tools/gen_pine_firms.py uit zodat
elke gegenereerde f_firm* minstens één call-site moet hebben, anders faalt de
generatie hard. Zelfde vorm als owner_dll_check.py.

Qty is beslist: Ferry beheert hem in Pine, de middleware-override is verwijderd
(D-53/D-122 dicht). Pine's qty IS de gehandelde qty, dus ownerDll = 4 × SL × qty
is correct gekalibreerd.
```

---

## 🟩 Backtest Setup

```
Start met `git pull origin claude/middleware-setup-guide-afhvtk`. Lees docs/SPRINT.md,
items D-113, D-101 en D-102.

Claim D-113 of ga verder met D-101; één item per keer, status wip + owner.

D-113 — backtest/engine.py remt nog alleen op cfg.acct_dll, terwijl Pine sinds
D-110 remt op min(4 × SL × qty, firm_dll). Dat is een pariteitsverschil op
dagniveau. De vorm is bekend: acct_dll = 4 × SL × qty reproduceert de eigen rem
exact. Wat mist is de min met de firmawaarde, plus dat de rem op lossBasisEff
meet in plaats van op de ruwe running-P&L. De ⅓-ruimteterm hoort er NIET in.

D-101 — increment 3b (statements) en 4 (evaluator) staan nog open. D-102 kan pas
starten als de evaluator een draaibare backtest uit een .pine produceert.

Nieuw signaal uit D-126 dat jullie aangaat: de payout-ladder in de registry is
PER PROGRAMMA verschillend (250K legacy → [3000,3000,3000], Blue Guardian →
[2500,3000]). Neemt fleet.py of de funded-sim een vaste ladder aan, dan klopt die
voor niet-Apex-50K niet. Meld of dat zo is.
```

---

## 🟪 Web

```
Start met `git pull origin claude/middleware-setup-guide-afhvtk`. Lees docs/SPRINT.md.

D-83 en D-84 zijn NIET meer van jullie: D-120 besliste dat de settings-tab in de
bestaande cockpit komt (middleware/app/viewer.py), dus die items zijn naar
Middleware App gegaan. Er komt geen app-shell in web/**.

Wat er voor jullie ligt:
1. D-34 — publieke claims, staat op review. Maak dat af.
2. resultaten.astro + public-stats.json volgen zodra het eval-format er is (D-74).

Harde randvoorwaarde bij alles wat publiek wordt: er is GEEN geldige
vlootrangorde en de OOS-klok staat op nul. Geen enkele publieke claim mag
suggereren dat deze vloot out-of-sample bewezen is.

Signaal uit de infra-meting van 06-10: mex-public-stats.timer staat INACTIVE op
de VPS, dus public-stats.json wordt niet geschreven. Neem dat mee in je planning.
```

---

## 🟧 Analyses & Data

```
Start met `git pull origin claude/middleware-setup-guide-afhvtk`. Lees docs/SPRINT.md
item D-112 en docs/fleet-report-spec.md. Jullie voorvoegsel voor eigen besluiten is A-.

1. D-112 — klopt docs/fleet-report-spec.md met hoe jullie het fleet-startschema
   opstellen? Dat document is sinds 28-09 de acceptatietest voor D-96 en D-97, dus
   een afwijking daar wordt straks een afgekeurde fase.

2. Nieuwe vraag, en hij raakt jullie cijfers direct: welke van jullie berekeningen
   nemen een VASTE contractgrootte aan? De PMT-export van 05-10 laat qty 1, 2, 5 en
   één op 35 zien, en tussen 18-09 en 06-10 draaide er een middleware-override die
   39 accounts op 1 zette (nu verwijderd). Elke doorlooptijd- of
   payout-per-dag-berekening die één qty aanneemt, klopt over die periode niet.
   Geef aan wat dat raakt en wat je nodig hebt om het te corrigeren.
```

---

## 🟥 MCP trader-dev

```
Start met `git pull origin claude/middleware-setup-guide-afhvtk`. Lees
docs/CHAT_INSTRUCTIE.md en docs/SPRINT.md.

Deze rol stond in de instructie maar had NUL items op het bord en NUL regels in
docs/inbox.md. Dat is dezelfde fout als bij Analyses & Data: wie geen map bezit,
valt uit de eigenaarstabel en dus uit de ronde. Vanaf nu sta je vast in de ronde,
met voorvoegsel M- voor je eigen besluitregister.

Eerste opdracht: zet je OPENSTAANDE VRAGEN in docs/inbox.md, met per vraag wat je
nodig hebt en van wie. In de chat bereiken ze niemand. Zodra ze daar staan pak ik
ze in de volgende ronde op en krijgen ze een M- of D-nummer.

Relevant voor jou: D-58 staat nog open — de default branch van de repo wijst naar
claude/mcp-trader-dev-sse-ibl64y, een dode branch die 186 commits achterloopt.
```
