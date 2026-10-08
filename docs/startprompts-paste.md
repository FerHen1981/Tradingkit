# Paste-klare startprompts — 08-10

_Eigenaar: Scrum Master. Eén blok per chat, letterlijk plakken. Kort gehouden: elke chat
krijgt één release van maximaal een dag, met een acceptatietest. Besluit Ferry 08-10:
kleine releases boven fase-brokken._

---

## 🟦 Middleware App

```
git pull origin claude/middleware-setup-guide-afhvtk
Lees in docs/inbox.md de drie bovenste berichten van 08-10.

RELEASE 3a — het playbook toont de invoer van de fleet-berekening, en de hardgecodeerde
doctrine gaat eruit. Eén dag. Volledige spec staat in de inbox onder "het playbook krijgt
de logica van het fleet-doc".

Acceptatie: de Playbook-tab toont per account ruimte / gelockt-of-vers / beste dag sinds
laatste payout / eerstvolgende cap / kwalificatiedagen / consistency-ruimte. En er staat
nergens meer een markt- of strategieregel die niet uit een bestand komt.

Claim met status wip + owner in docs/SPRINT.md, losse commit.
NIET: iets uit fase 3+ (dat staat in ARCHIVE.md), en geen nieuwe D-nummers.
```

---

## 🟩 Backtest Setup

```
git pull origin claude/middleware-setup-guide-afhvtk
Lees in docs/inbox.md het bericht van 08-10 over het playbook.

RELEASE 3b — de scoring van tailor.py als job die een bestand wegschrijft dat de cockpit
leest. Per accountprofiel 24 sets, score = haal-40d − 0,5 × breach-40d.

Acceptatie: draai op 013, 018 en 022 en reproduceer A-84 in docs/state.md.
Verwacht verschil omdat de cap sinds 08-10 vast $2.000 is en vanaf payout 6 vervalt —
benoem dat verschil, verzwijg het niet.

Daarna pas D-130 (ladder_cap hardgecodeerd Apex-50K + stille fallback in funded.py).
```

---

## 🟨 Pine Dev

```
git pull origin claude/middleware-setup-guide-afhvtk
Lees D-148 in docs/SPRINT.md.

RELEASE 2 — f_ladderCap() klopt niet met Apex. Er is GEEN oplopende ladder: vast maximum
per payout ($50k = $2.000) en vanaf de ZESDE payout geen maximum. data/propfirms.json is
al bijgewerkt en verified.

Acceptatie: een account voorbij vijf payouts krijgt geen pmtBlock meer; payout #1 blokkeert
op $2.000 in plaats van $1.500.

Daarna D-139: accountPhase kent drie opties en charts zenden "Research" uit. Maak van een
onbekende fase "alles dicht" in plaats van "alles open".
OOS-klok gaat op nul — akkoord, dat is hier de prijs waard.
```

---

## 🟪 Web

```
git pull origin claude/middleware-setup-guide-afhvtk

Twee kleine: (1) D-129 regel 3 — de poort bijt alleen bij sample:true; er moet een regel
bij die bij sample:false bijt, met Ferry's besluit: een AANTAL mag evals meenemen, een
BEDRAG nooit. (2) D-132 — verwijder web/handover/mex_units/; canoniek is
middleware/app/mex_units/. Verhuis README.md en tests/test_roles.py mee.
```

---

## 🟧 Analyses & Data

```
git pull origin claude/middleware-setup-guide-afhvtk
Jullie werk staat sinds 07-10 op de werkbranch (PR #3). A-80 t/m A-90 zijn gelezen.

Eén ding: draai tools/validate_dataset.py op één pilot-export. Ferry bevestigde dat de
feed Rithmic via NinjaTrader is; die run drukt de echte CVD-grens af, en die grens is het
onderzoeksvenster.

Werkafspraak gewijzigd: push gerust op je eigen branch, maar meld elke oplevering in
docs/inbox.md op de werkbranch. Anders bestaat hij voor niemand.
```

---

## 🟥 MCP trader-dev

```
git pull origin claude/middleware-setup-guide-afhvtk
Je rol is bevestigd: drijvende meet-/reviewrol, register M-, geen eigen map.

Verifieer ná oplevering: release 2 (de cap in Pine én Python — zelfde fout op twee
plekken, dus controleer of ze hetzelfde doen) en release 3a/3b (komt er nog een getal in
het playbook voor dat niet uit een bestand komt?).

Melden in docs/inbox.md. Niet muteren buiten je eigen scope.
```
