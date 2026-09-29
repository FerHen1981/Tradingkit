# Startprompts per chat — ronde 29-09d

_Eigenaar: Scrum Master. Watermerk: `HEAD`, 29-09._

## Stand

Fase 0 en 1 zijn af. Fase 2 loopt (D-82 config-API, D-85 secrets-store). De registry dekt
alle acht firma's. **13+ items dicht sinds de herijking.**

## Twee besluiten van Ferry die vandaag vielen

**D-109 — de firm-DLL is informatie, geen rem.** *"De eod accounts hebben een DLL van $1000
op zowel evals en pa maar ik houd daar geen rekening mee. Accounts moet handelen tot ze de
ingestelde target halen of door mij ingestelde DLL bereiken en als de harde DLL limit
bereikt wordt stopt ie vanzelf."* De registry blijft dus zoals hij is; die waarde voedt
alleen nog *"ruimte tot de DLL"* in D-96.

**D-110 — zijn eigen DLL is een formule**, geen tabel met getallen:

```
owner_dll = min( sl_per_contract × dll_sl_multiple × qty ,  ruimte × max_fraction_of_room )
ruimte    = balans − liq_niveau
```

Geverifieerd tegen **zeven** punten uit zijn fleet-doc met SL 100 en multiple 4 — qty 1 t/m
5 geeft $400/$800/$1.200/$1.600/$2.000, en de 250K en 300K vallen op dezelfde formule.
Staat in `docs/schema-config.md` §3c.

🔴 **Die formule beslecht een ontwerpvraag die openstond.** Hij leest `qty` uit Pine,
`liq_niveau` uit de registry en **`balans` uit T3** — dus **Pine kan hem niet uitrekenen**.
De volledige rem hoort aan de middlewarekant en kan niet vóór fase 4. Wat wél nu kan is de
eerste term, en dat is precies genoeg om de firm-rem veilig te verwijderen.

---

## 🟨 Pine Dev — D-110, eerste term. En let op de volgorde.

```
git pull origin claude/middleware-setup-guide-afhvtk

Ferry heeft besloten (D-109): de firm-DLL is informatie, geen rem. Accounts handelen tot
de target of tot ZIJN DLL; de harde firmalimiet stopt het vanzelf bij de broker.

WAT ER VANDAAG STAAT — er zijn DRIE daglimiet-remmen en de firmawaarde is de actieve:
  acctDLL  = input.float(1000, "PA Daily Loss Limit ($)")          r. 486
  acctDLL := pfDLL                                                  r. 1010  <- preset wint
  dllHit   = acctDLL > 0 and (isPA or (isEval and ddModel=="EOD"))
             and runningPnL <= -acctDLL                             r. 1760
  enableDailyLossLimit (default FALSE) + dailyLossLimit (700) -> lossHit
  useRiskGate (default FALSE) + rgDLL (150)

GEVRAAGD: dllHit remt niet meer op de firmawaarde, maar op Ferry's eigen waarde.

🔴 DE VOLGORDE IS BINDEND EN DIT IS HET HELE PUNT.
Haal je dllHit weg terwijl enableDailyLossLimit op FALSE staat — en dat is de default —
dan heeft dat account GEEN ENKELE Pine-rem meer en loopt het door tot de firmalimiet.
Die BREACHT een eval in plaats van hem te pauzeren. Dus:
  1. eerst Ferry's eigen rem aan, met de waarde uit de formule;
  2. aantoonbaar laten zien dat hij werkt;
  3. dan pas de firm-rem uit dllHit halen.
Nooit in één commit zonder dat stap 1 en 2 staan.

DE WAARDE DIE JE INVULT — alleen de eerste term, want die heeft alleen qty nodig:
  owner_dll = sl_per_contract (100) × dll_sl_multiple (4) × qty
Dat geeft $400 bij qty 1, $800 bij 2, $1.200 bij 3, $1.600 bij 4, $2.000 bij 5 — exact de
ladder uit Ferry's fleet-doc, op zeven punten nagerekend.

⛔ DE TWEEDE TERM NIET IN PINE BOUWEN. "nooit meer dan 1/3 van de ruimte" heeft de BALANS
nodig en die kent Pine niet. Die helft komt in de middleware, na fase 4 (D-92). Bouw er
geen benadering voor — een geschatte ruimte is erger dan geen ruimte, want hij ziet eruit
als de echte.

📌 acctDLL blijft in het script: D-96 heeft de firmawaarde nodig als WEERGAVE
("ruimte tot de DLL"). Alleen dllHit gebruikt hem niet meer.
📌 Dit raakt het live pad. Zelfde discipline als bij D-107: laat zien dat het alleen om de
rem gaat en niet om handelslogica.
```

---

## 🟦 Middleware App (chat: **App Setup**) — de widget afleveren, en door op fase 2

```
git pull origin claude/middleware-setup-guide-afhvtk

1. 📱 DE WIDGET AFLEVEREN VOOR FERRY'S IPHONE.
   D-105 staat op done — ik heb de hele keten nagemeten, niet alleen het script:
   vier splitrijen, eval op aantallen uit eval_stats.counts_50k_eq (geen bedragen),
   laatste handelsdag uit yesterday.session_date, node --check schoon. En doorgemeten
   dat de API die velden ook echt vult: _build_eval_stats() r. 185 -> viewer.py:310/328.

   Wat ik NIET kan en jullie wel: ÉÉN VERIFICATIE TEGEN LIVE DATA vanaf de VPS.
   curl de echte /api/widget en controleer drie dingen:
     - eval_stats.counts_50k_eq bevat niet-nul waarden (anders toont de eval-rij "—"
       en ziet een kapotte keten eruit als een lege dag);
     - yesterday.session_date is gevuld en is de laatste dag MET trades;
     - stacks.funded.today en stacks.eval.today tellen op tot het top-level today.
   Meld de uitkomst; dan weet Ferry dat wat hij op zijn telefoon zet ook echt klopt.

2. D-82 afmaken — dat deblokkeert Web (D-83/D-84) en is nu de kritieke lijn.

3. 🔴 NIEUW UIT D-110, en dit komt bij jullie terecht: Ferry's eigen DLL is een formule
   en de volledige vorm KAN ALLEEN AAN JULLIE KANT.
       owner_dll = min( sl_per_contract × dll_sl_multiple × qty , ruimte × 1/3 )
       ruimte    = balans − liq_niveau
   qty komt uit Pine, liq_niveau uit de registry, BALANS UIT T3 (D-92). Pine bouwt nu
   alleen de eerste term. Neem de tweede mee in de planning van fase 4 — niet eerder, en
   bouw geen schatting van de ruimte. Parameters staan in schema-config.md §3c als
   owner_caps, gesleuteld op de program-sleutel uit de registry.

4. D-74 en D-69 lopen nog; D-106 (log per POST welk endpoint gekozen werd) blijft open.
```

---

## 🟩 Backtest Setup — spoor B afmaken

```
git pull origin claude/middleware-setup-guide-afhvtk

D-104, D-100 en D-68 staan op done. De registry dekt alle acht firma's en D-96 faalt niet
meer op een ontbrekende regel — dat was de blokkade voor fase 5.

Door op D-101 (interpreter voor de Pine-deelverzameling, hard weigeren op het onbekende)
en daarna D-102 (door de hele molen).

📌 Uit D-110: de owner-DLL-formule gebruikt `ruimte = balans − liq_niveau`. Als jullie
prop-firm-simulatie een eigen daglimiet modelleert, gebruik dan de FIRMAWAARDE uit de
registry en niet Ferry's eigen rem — die is een operationele keuze en hoort niet in de
simulatie. Dat is dezelfde scheiding als D-109.
```

---

## 🟪 Web — D-82 is het laatste dat voor jullie staat

Zodra de config-API er is zijn **D-83 en D-84** aan de beurt. Lees `docs/schema-config.md`
§2, §3 en §5 — en nu ook **§3c**, want `owner_caps` komt in hetzelfde scherm te staan naast
de firmaregels: *firmaregel $1.000 · jouw rem $400*. Dat naast elkaar tonen is de kern van
wat Ferry in D-109 vroeg.
