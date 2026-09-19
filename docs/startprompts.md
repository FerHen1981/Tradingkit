# Startprompts per chat — ronde 18-09-b · **na de D-53-oplevering**

_Eigenaar: Scrum Master. Watermerk: `1144057`, 18-09._

**Wat er sinds ronde 18-09-a is veranderd:**
- 🔴 **D-53 is gebouwd** (`72274d7`, Middleware App) en staat op `review`. Hij is **nog niet
  live** — dat is één handeling van Ferry. Zolang die niet gebeurd is draait de receiver nog
  op de oude code en gaan MATADOR-alerts nog steeds met 6 contracten de deur uit.
- ✅ **D-76 is dicht** (widget-Today per stack, gereviewd door Middleware App).
- ✅ **D-74 web-helft is dicht en gereviewd.** De middleware-helft loopt.
- De gate-volgorde in `docs/execution-flow.md` staat weer op **#7** voor de qty-override —
  Middleware App verplaatste de *code* naar precies die plek. CLO's oorspronkelijke tabel
  klopte; mijn correctie erop is teruggedraaid.

**D-66 blijft de sleutel** voor Pine Dev en Backtest Setup. Die houdt D-63 → D-54 → D-57
tegen en daarmee de hele vlootrangorde. Ronde 18-09-a beschrijft dat blok volledig; het is
ongewijzigd en staat hieronder alleen samengevat.

---

## 🟦 Middleware App (chat: **App Setup**) — vier items, alle vier vrij

```
git pull origin claude/middleware-setup-guide-afhvtk

Lees docs/SPRINT.md en de rondes van 18-09 in docs/inbox.md. D-53 is akkoord bevonden —
mooi werk, met name dat jullie de override uit eigen beweging ná de risicopoorten hebben
gezet. Dat was mijn D-70-bevinding en die is daarmee opgelost: reject-rijen in
routed_*.jsonl dragen nu de onaangeraakte Pine-body.

DOE NU, in deze volgorde:

1. 🔴 D-74 — JULLIE HELFT AFMAKEN. Dit is het enige item waar publicatie van eval-bedragen
   nog dagelijks doorloopt. Vier dingen:
   (a) `account_type` (eval/funded) per account in het datamodel;
   (b) PASSED/BREACHED-tellers, genormaliseerd naar 50k-equivalent (factor = grootte/50000);
   (c) `public_stats.write` roept `for_public_evals()` aan — Web heeft die functie én
       `assert_no_eval_metrics()` al opgeleverd en ik heb ze functioneel nagemeten
       (1×50k + 1×100k passed = 3,0; 300k breached = 6,0; geneste lekken worden gevangen);
   (d) 📱 DE WIDGET. `middleware/scriptable/mex-fleet-widget.js` rendert in de `eval`-stand
       vandaag `realized` en `buffer` IN DOLLARS. Dat is exact wat Ferry op 05-09 aanwees.
       Voor eval horen daar alleen genormaliseerde tellers te staan. En zet de labels erbij
       die execution-flow.md §3.1 voorschrijft: `50k-eq · N=<aantal>` voor eval,
       `✓ verified <datum>` / `⚠ unverified since <datum>` voor funded.
   Het label uit (d) is het belangrijkste deel van deze hele ronde — zie punt 2.

2. D-73 — sla PMT's antwoordbody op in de routed-regel. `sent 200` is de status van ONZE
   POST, niet PMT's oordeel over de order. routed_journal.py r. 23-27 noemt die rijen zelf
   "accepted orders", niet "fills". Rejected() leest die body al en gooit hem daarna weg.

3. D-69 — de Render-blueprint deployt `middleware/app/main.py`. Dat bestand bestaat niet
   meer (verwijderd in D-05). De blueprint is daarmee dood; of je repareert hem of je
   haalt hem weg, maar hij mag niet blijven staan alsof hij werkt.

4. D-07 en D-17 — niet langer geblokkeerd. D-07 hing aan D-08 (done). D-17 is de viewer-rol
   (units-only) uit web/handover/mex_units/ + public-stats.json periodiek publiceren; dat
   raakt D-74 direct, dus doe hem in dezelfde ronde als je kunt.

NIET AAN BEGINNEN:
- D-75 (actuals uit /root/exports). Ik wacht op één meting van Ferry: `ls /root/exports`.
  Liggen daar geen Cash_History-CSV's, dan is er niets om op te pakken en bouw je aan een
  bron die niet bestaat. Het LABEL uit D-74(d) is wél nu al zinvol en staat daarom daar.
- D-23 — staat op "to be refined" bij Ferry.
```

---

## 🟨 Pine Dev — D-64 kan nu, de rest hangt aan D-66

```
git pull origin claude/middleware-setup-guide-afhvtk

DOE NU:

1. D-64 — MEX_EL_DORADO.pine compileert niet, en de GENERATOR is de bron. Handmatig
   herstellen in de .pine is dus fout werk: het wordt bij de volgende generatie overschreven.
   Fix tools/gen_pine_firms.py (dat bestand blijft bij jullie, ook al staat tools/** op
   Backtest Setup) en genereer opnieuw.

2. D-66 — samen met Backtest Setup. DE PARITEITSVRAAG: draait de vloot op een andere
   CVD-motor dan de backtester meet? 9 van de 9 scripts gebruiken ta.requestVolumeDelta(),
   terwijl "canonical CVD" in de pijplijn een deterministische OHLCV-polariteitsproxy is.
   Dit is een MEETVRAAG, geen fix. Stel eerst vast óf ze verschillen en hoeveel.

NIET AAN BEGINNEN:
- D-63 (bron-wint-conflict) — wacht op D-66. Als de motoren verschillen verandert de vraag.
- D-57 (derisk in de bevroren configs) — wacht op D-54, die op D-66 wacht.
- D-44 staat op review bij mij; de fix zelf ligt bij Ferry in het PMT-dashboard.
```

---

## 🟩 Backtest Setup — D-68 kan nu, de rest hangt aan D-66

```
git pull origin claude/middleware-setup-guide-afhvtk

DOE NU:

1. D-68 — de vloot-pijplijn leest de accountregels NIET uit de registry maar codeert ze
   hard. backtest/pipeline/fleet.py:84 zet acct_trail_dd=2000.0 en acct_dll=1000.0 in de
   code, en higher.py:237 valt stil terug op 2500 als dat veld leeg is. Die stille fallback
   is het echte gevaar: een verkeerde drawdown levert een plausibel ogend maar onjuist
   cijfer. Lees ze uit data/propfirms.json en laat het HARD falen als een regel ontbreekt.

2. D-66 — samen met Pine Dev, zie hun blok. Jullie kant is de meetkant: wat meet de
   backtester precies als "CVD", en is dat hetzelfde als wat TradingView teruggeeft?

NIET AAN BEGINNEN:
- D-54 (rangorde afmaken) — hangt aan D-66. Alleen MATADOR heeft nu een geldig cijfer;
  LEON en REY staan achter een open harde poort en zijn daarmee ONGELDIG, niet "indicatief".
- D-15 / D-16 / D-25 / D-38 / D-39 — onderzoeksitems, niet deze ronde.
- D-50 en D-27 staan geblokkeerd.
```

---

## 🟪 Web (chat: **Website Build Mex-traders.com**) — deze ronde niets nieuws

Jullie helft van D-74 is opgeleverd, nagemeten en akkoord (`36f0425`), en D-34 is dicht.
De render in `resultaten.astro` kan pas zodra Middleware App het payload-format levert
(punt 1c hierboven). **Begin daar niet op vooruit** — dan bouw je tegen een format dat nog
kan schuiven. Ik meld het in `docs/inbox.md` zodra het er is.

---

## 🧑‍✈️ Ferry — vier handelingen, in deze volgorde

**1. 🔴 D-53 uitrollen.** Dit is de enige die vandaag iets aan de executie verandert.

```bash
cd /root/mex-middleware-b
dotnet build src/Mex.Journal.Receiver -c Release
# zet in de EnvironmentFile: MEX_ACCOUNT_QTY=<account>=1,<account>=1,...
systemctl restart mex-receiver
```
Controleer daarna bij de eerste alert dat de doorgestuurde body `"quantity":"1"` draagt.

**2. 📱 `ls -la /root/exports/*Cash_History*.csv`** — bepaalt of D-75 een taak is of een
lege huls. Plak de uitvoer, ook als het niets oplevert; "niets" is hier ook een antwoord.

**3. 📱 Widget op de telefoon bekijken** — past de vierde rij op een small widget, of kapt
hij af? Kapt hij af, dan haal ik de `Accounts`-rij eruit; die staat ook op het dashboard.

**4. D-72 — de routekeuze.** Web heeft statisch bewezen dat PMT nooit een bracket-exit
echoot: `f_sendExec` wordt aan de sluitkant alleen aangeroepen voor vijf administratieve
closes. Poort #12 zou daarmee bijna elke echte trade als `unconfirmed` markeren — dat is
fail-blind, niet fail-closed. Er liggen drie routes (a/b/c) in D-72 op het bord.

Daarna, wanneer het uitkomt: D-44 (PMT-dashboard: Auto BreakEven = YES, risicotype ≠ `Price`),
D-47 (twee resterende alerts), D-11 (drie secrets roteren), D-31 (snapshot-timer),
D-58 (default branch), D-03 (reconciliatie-timer).
