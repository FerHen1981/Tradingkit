# Startprompts per chat — ronde 29-09e

_Eigenaar: Scrum Master. Watermerk: `HEAD`, 29-09._

## Stand

Fase 0 en 1 zijn af. **Fase 2 is de kritieke lijn** — D-82 (config-API) is het enige dat nog
tussen nu en Web staat. De registry dekt alle acht firma's, dus fase 5 is ook niet meer
geblokkeerd.

## Wat Ferry deze ronde besliste

**D-109 · de firm-DLL is informatie, geen rem.** *"Accounts moet handelen tot ze de
ingestelde target halen of door mij ingestelde DLL bereiken en als de harde DLL limit
bereikt wordt stopt ie vanzelf."*

**D-110 · zijn eigen DLL is een formule:**
```
owner_dll = min( sl_per_contract × dll_sl_multiple × qty ,  ruimte × max_fraction_of_room )
ruimte    = balans − liq_niveau
```
Geverifieerd op zeven punten uit het fleet-doc (SL 100, multiple 4). 🔴 Hij leest `balans`
uit **T3**, dus **Pine kan hem niet uitrekenen** — de volle rem hoort aan de
middlewarekant en kan niet vóór fase 4. Pine bouwt nu alleen de eerste term.

**D-111 · de eval-helft van de widget toont straks drie dingen:** passed en failed **in het
getoonde venster**, plus het **aantal actieve** evals. `passed_at` is afleidbaar uit de
fills — de **vorige handelsdag** vóór de eerste trade (Ferry's regel, feestdagen uit het
fleet-doc overgeslagen).

---

## 🟦 Middleware App (chat: **App Setup**) — D-82 eerst, dat houdt Web tegen

```
git pull origin claude/middleware-setup-guide-afhvtk

1. 🔴 D-82 AFMAKEN — dit is de kritieke lijn. Web (D-83/D-84) kan er niet omheen en
   staat al twee rondes stil. Auth als ontwerpeis, niet als bijzaak: dit endpoint stuurt
   orders. Elke schrijfactie door dezelfde validatie als D-80 en in het auditspoor van D-81.

2. 📱 D-111 — de eval-helft van de widget, en lever dit in TWEE stappen.

   STAP A, kan nu en is één regel: het aantal ACTIEVE evals uit
   eval_stats.raw_counts.running. Gebruik de RAW counts, niet counts_50k_eq — Ferry vraagt
   om een aantal, en de 50k-normalisatie bestaat voor de publieke site (D-74) waar
   accountgrootte misleidt. Op zijn telefoon is 5 accounts gewoon 5.

   STAP B, het venstertellertje. passed_at is AFLEIDBAAR en hoeft dus niet gegokt:
   de vorige HANDELSDAG vóór de eerste trade op het funded account, met de feestdagen uit
   het fleet-doc (26 nov, 25 dec, 1 jan, 18 jan, 15 feb) overgeslagen. Dat geeft voor de
   tien bestaande accounts: PA013 24-07 · PA018 03-08 · PA022 24-08 · PA023 04-09 ·
   PA024 11-09 · PA025 16-09 · PA026 17-09 · PA027+PA028 18-09 · PA029 23-09.

   🔴 DE FAILED-KANT IS NIET AFLEIDBAAR. Een breached eval wordt nooit funded, heeft dus
   geen eerste trade. Die telling begint bij nul en loopt vanaf nu. MAAK DAT ZICHTBAAR in
   de weergave — een failed-teller op 0 die eigenlijk "onbekend" betekent is dezelfde
   stille nul als de drawdown-fallback in D-68, de ledger-fallback in D-75 en de
   DLL-van-nul in D-108. Drie keer dezelfde fout in één maand; deze hoeft niet de vierde
   te worden.

3. 🔴 UIT D-110, EN DIT KOMT BIJ JULLIE TERECHT. De volledige owner-DLL kan alleen aan
   jullie kant, want hij heeft de BALANS nodig:
       owner_dll = min( 100 × 4 × qty , (balans − liq_niveau) × 1/3 )
   Pine bouwt nu alleen de eerste term. Neem de tweede mee in de planning van fase 4
   (D-92) — niet eerder, en bouw geen schatting van de ruimte. Parameters staan in
   schema-config.md §3c als owner_caps, gesleuteld op de program-sleutel uit de registry.

4. Loopt nog: D-74, D-69, en D-106 (log per POST welk endpoint gekozen werd — dat haalt
   de eerste onbekende weg bij het account dat 100% van het afwijkende verkeer draagt).
```

---

## 🟨 Pine Dev — D-110, en de volgorde is de opdracht

```
git pull origin claude/middleware-setup-guide-afhvtk

D-110 staat klaar. De inhoud is één regel; de VOLGORDE is waar het om gaat.

WAT ER VANDAAG STAAT — drie daglimiet-remmen, en de firmawaarde is de actieve:
  acctDLL  = input.float(1000, "PA Daily Loss Limit ($)")          r. 486
  acctDLL := pfDLL                                                  r. 1010  <- preset wint
  dllHit   = acctDLL > 0 and (isPA or (isEval and ddModel=="EOD"))
             and runningPnL <= -acctDLL                             r. 1760
  enableDailyLossLimit (default FALSE) + dailyLossLimit (700) -> lossHit
  useRiskGate (default FALSE) + rgDLL (150)

GEVRAAGD (Ferry, D-109): dllHit remt niet meer op de firmawaarde maar op Ferry's eigen
waarde. De firmalimiet stopt het account vanzelf bij de broker.

🔴 BINDENDE VOLGORDE — haal je dllHit weg terwijl enableDailyLossLimit op FALSE staat, en
dat is de default, dan heeft dat account GEEN ENKELE Pine-rem meer en loopt het door tot de
firmalimiet. Die BREACHT een eval in plaats van hem te pauzeren.
  1. eerst Ferry's eigen rem aan, met de waarde uit de formule;
  2. aantoonbaar laten zien dat hij werkt;
  3. dan pas de firmwaarde uit dllHit halen.
Niet in één commit zonder dat stap 1 en 2 staan.

DE WAARDE — alleen de eerste term, want die heeft alleen qty nodig:
  owner_dll = 100 × 4 × qty  ->  $400 / $800 / $1.200 / $1.600 / $2.000 bij qty 1 t/m 5
Exact de ladder uit Ferry's fleet-doc, op zeven punten nagerekend.

⛔ DE TWEEDE TERM NIET IN PINE. "nooit meer dan 1/3 van de ruimte" heeft de BALANS nodig en
Pine kent die niet. Die komt in de middleware na fase 4. Bouw er geen benadering voor: een
geschatte ruimte is erger dan geen ruimte, want hij ziet eruit als de echte.

📌 acctDLL blijft in het script — D-96 heeft de firmawaarde nodig als WEERGAVE. Alleen
dllHit gebruikt hem niet meer.
📌 Zelfde discipline als bij D-107: laat zien dat het om de rem gaat en niet om
handelslogica. Dat bewijs heeft D-86 straks nodig voor het OOS-klokbesluit.

DAARNA: D-85 loopt bij jullie samen met Middleware App (geheimen uit de chart-inputs).
D-86 blijft wachten tot fase 2 rond is.
```

---

## 🟩 Backtest Setup — spoor B afmaken

```
git pull origin claude/middleware-setup-guide-afhvtk

D-104, D-100 en D-68 zijn dicht. De registry dekt alle acht firma's en D-96 faalt niet meer
op een ontbrekende regel — dat was de blokkade voor fase 5.

D-101 afmaken (de interpreter voor de Pine-deelverzameling die HARD weigert op het
onbekende), daarna D-102: door de hele molen — walk-forward, Monte Carlo, stress,
prop-firm-simulatie op het resultaat van de interpreter in plaats van op een
herimplementatie.

📌 Uit D-109/D-110, en dit raakt jullie simulatie direct: er zijn nu TWEE daglimieten en ze
horen niet op één hoop. De FIRMAWAARDE staat in de registry en is wat de prop firm
handhaaft — die hoort in de simulatie. Ferry's EIGEN rem (owner_caps, schema-config.md §3c)
is een operationele keuze en hoort er NIET in. Simuleer je zijn rem mee, dan meet je zijn
gedrag in plaats van de firmaregels, en dan is het cijfer niet meer vergelijkbaar tussen
programma's. Dat is dezelfde scheiding als D-109.
```

---

## 🟪 Web — nog één item, en dan zijn jullie aan de beurt

**D-82 is het laatste dat voor jullie staat** en het loopt nu bij Middleware App. Zodra de
config-API er is beginnen D-83 en D-84.

Lees `docs/schema-config.md` §2, §3, §5 — en nu ook **§3c**, want `owner_caps` komt in
hetzelfde scherm te staan **naast** de firmaregels: *firmaregel $1.000 · jouw rem $400*.
Dat naast elkaar tonen is de kern van wat Ferry in D-109 vroeg: hij wil kunnen zien wat de
firma oplegt én wat hij zichzelf oplegt, zonder ze te verwarren.

⚠️ En het punt dat bepaalt wat "af" betekent: **met dit scherm wordt de webapp onderdeel van
het live executiepad.** Vandaag toont een fout daar een verkeerd getal; straks stuurt hij
een order naar het verkeerde account.
