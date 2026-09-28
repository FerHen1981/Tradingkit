# Startprompts per chat — ronde 29-09b · **fase 0 dicht, fase 1 bijna**

_Eigenaar: Scrum Master. Watermerk: `2d24877`, 29-09._

## Stand

- ✅ **Fase 0 is af.** D-77 en D-78 staan allebei op `done`.
- ✅ **D-79 en D-80 zijn gereviewd en gesloten.** Fase 1 rest alleen **D-81**.
- ➡️ Daarna **D-82** (config-API), en dan is **Web** aan de beurt met de settings-tab.

## Twee dingen uit de reviews die iedereen aangaan

**Uit D-77:** ik heb een voorstel van Middleware App niet overgenomen, en de reden is
leerzaam. Zij zagen twaalf PMT-velden die in hun steekproef altijd `0` waren en wilden die
als format-constanten behandelen. **Zes ervan worden in Pine berekend** uit `useTrail` en
`useBreakEven`; ze stonden op dat account simpelweg uit. Hard op 0 zetten zou betekenen dat
trailing of break-even aanzetten in Pine stilzwijgend bij de middleware blijft hangen —
**exact de faalmodus van D-44**, dat net dicht is. Het event draagt ze nu in een
`risk`-object. *Les: "altijd 0 in de steekproef" is geen bewijs dat iets constant is;
kijk waar de waarde vandaan komt.*

**Uit D-79:** ik had bijna een bevinding opgeschreven die er geen was. Ik hield de
terugval-op-leeg bij een verdwenen configbestand voor fail-open — maar alle drie de
consumptiepunten vallen terug op de env-map, en hun commentaar zei dat ook. *Les voor
mijzelf: lees het commentaar voor je een bevinding schrijft.*

---

## 🟦 Middleware App (chat: **App Setup**) — fase 1 afmaken, dan de API

```
git pull origin claude/middleware-setup-guide-afhvtk

D-77 en D-78 staan op done, D-79 en D-80 heb ik gereviewd en gesloten. Sterk werk: dat de
file wint maar env het vangnet blijft, op alle drie de consumptiepunten, is precies de
juiste keuze — daarmee kan hot-reload draaien zonder dat 39 accounts in één klap mee moeten.

1. 🔴 D-81 AFMAKEN, met twee punten uit mijn D-80-review erbij:

   (a) EEN VERDWENEN CONFIGBESTAND IS STILLER DAN EEN KAPOT BESTAND. De missing-tak
       schrijft alleen naar Console.Error en roept FailAndMaybeAlarm niet aan, terwijl
       parse- en validatiefouten dat wél doen. Een bestand dat weg is, is minstens zo
       ernstig — en de oorzaken (verkeerd pad na een deploy, mount weg, halve atomic
       replace) zijn precies die je 's nachts treffen. Laat die tak ook alarmeren.

   (b) 🔴 VOLGORDE-RISICO, en dit is het belangrijkste van deze ronde.
       "Terugval op leeg" is vandaag veilig OMDAT env nog gevuld is. Haalt jullie
       migratie die env-waarden weg, dan betekent leeg ineens GEEN REGELS: geen halted
       accounts, geen entry-caps, geen qty-override. Verander die tak naar
       last-good-behouden VOORDAT de env-kant leegloopt, niet erna.

2. D-82 — de config-API. Lezen, valideren, schrijven, met authenticatie als ontwerpeis
   en niet als bijzaak: dit endpoint stuurt orders. Elke schrijfactie door dezelfde
   validatie als D-80 en in het auditspoor van D-81. Ferry bedient hem alleen zelf, maar
   bouw het zo dat een tweede gebruiker later geen herbouw vraagt.
   ⚠️ Dit deblokkeert Web (D-83/D-84), dus het is nu de kritieke lijn.

3. D-105, D-53 en D-74 lopen nog bij jullie; D-69 is klein opruimwerk.

D-77 IS DICHT maar lees §3c van docs/schema-event.md voordat je aan D-87 begint — daar
staat wat er van jullie review is overgenomen en wat niet, met de reden erbij. Het event
heeft nu een `risk`-object en `text.color`, en CardTier.For(title) wordt For(kind, action).

D-106 ligt deels bij jullie: log per POST welk endpoint gekozen werd.
```

---

## 🟩 Backtest Setup — D-104 afmaken, dan door op spoor B

```
git pull origin claude/middleware-setup-guide-afhvtk

D-68 en D-100 staan op review bij mij, D-101 loopt. Mooi dat de lexer meteen hard weigert
op het onbekende — dat is precies waar het om ging.

1. 🔴 D-104 AFMAKEN. Het staat op review maar de zeven 50K-programma's van de nieuwe
   firma's zijn de kern en die blokkeren twee dingen: D-78 is pas voor alle acht firma's
   geldig als elk `program` naar een bestaande registry-sleutel resolvet, en D-96 faalt
   per ontwerp hard op een ontbrekende regel.
   Ferry's regel: "de programma's die het dichtst bij de Apex-regels liggen" —
   Blue Guardian Standard, Top One Elite (consistency 40%), TradeDay EOD trailing.
   Leg die motivering per record vast in meta.

   🔴 En controleer apex_50k_legacy_pa: die draagt max_daily_loss $1.000 terwijl het
   fleet-doc voor legacy "geen DLL" zegt. De FIRMA legt er geen op (registry = null),
   FERRY legt zichzelf er één op in Tradovate (hoort in D-78 accounts[].caps). Staat zijn
   cap als firm-regel, dan bewaakt D-96 een limiet die Apex niet kent. Melden, niet stil
   rechtzetten — verified:true-record.

2. D-101 afmaken en door naar D-102 (door de hele molen).

Push de pine-kant van de generator NIET zelf; dat is D-108 bij Pine Dev.
```

---

## 🟨 Pine Dev — D-107 is het zwaarst en het raakt echte orders

```
git pull origin claude/middleware-setup-guide-afhvtk

Je D-77-review was scherp en heeft het schema echt beter gemaakt — v3 staat er, met §3b
(jullie punten) en §3c (die van Middleware App). D-108 zag ik langskomen, dank.

1. 🔴 D-107 — jouw terzijde, en het is het belangrijkste open live-item.
   (a) Vier sluitingspaden — auto-flat (2262), venster-grace (2282), dag-halt (2297),
       account-halt (2324) — roepen elk strategy.close_all() aan, alleen bewaakt door
       if posSize != 0 en zonder onderlinge uitsluiting. Twee kunnen op dezelfde bar vuren.
   (b) Vijf van de zes close-aanroepen sturen t_qty mee, de qty van de ENTRY, in plaats
       van math.abs(strategy.position_size). Alleen de cap-lock doet het laatste. Normaal
       valt dat samen; na een gederiskte of gecapte fill niet — dan sluit je te veel
       (doordraaien naar de andere kant) of te weinig (restpositie blijft staan).
   Het schema schrijft inmiddels voor dat een sluitende `fill` de WERKELIJKE positie
   draagt, dus (b) moet hoe dan ook. Mag samen met D-86 in één ronde, dan test je één keer.

2. D-85 samen met Middleware App zodra D-82 er is: de geheimen (pmtToken, pcLicense,
   accountID) uit de chart-inputs halen. Begin daar nog niet aan — eerst de store.

VOORUITBLIK D-86, nu het schema vaststaat: het event krijgt een `risk`-object met de zes
trail/breakeven-velden die jullie berekenen, `text.color` erbij, `kind` gesplitst in
`order` en `fill`, `id` met een volgnummer, en `action` met "cancel". Route B blijft:
jullie schrijven de kaarttekst, de middleware kiest de bestemming.
```

---

## 🟪 Web — nog één item en dan zijn jullie aan de beurt

Fase 1 rest alleen **D-81**. Daarna bouwt Middleware App **D-82**, de config-API — en dat
is precies wat D-83 en D-84 nodig hebben. Reken op de eerstvolgende ronde.

**Lees nu alvast `docs/schema-config.md`:**
- **§2** niveau 1 — per prop-firm-programma: kanaal, token, URL, Discord-webhook
- **§3** niveau 2 — per account: harde caps, publiceren, status, webhook
- **§5** — 🔴 **tokens worden verwijzingen, geen waarden.** Het scherm toont
  `apex_pmt · ✓ gezet · gewijzigd 12-09` en een veld om te vervangen, nooit de waarde zelf
- **§6** — `caps` is bewust een tweede plek naast Tradovate en moet expliciet gelabeld
  worden als *"wat de middleware bewaakt"*

⚠️ En het punt dat bepaalt wat "af" betekent: **met dit scherm wordt de webapp onderdeel
van het live executiepad.** Vandaag toont een fout daar een verkeerd getal; straks stuurt
hij een order naar het verkeerde account.
