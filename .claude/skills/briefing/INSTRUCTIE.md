# Briefing — cross-domain LifeOS-overzicht

Dit bestand is **platform-agnostisch bedoeld**. Drie agenten kunnen het draaien:

- De **Chief LifeOS Officer (CLO)** — Claude, overkoepelend — is de **primaire
  aanroeper** en draait de wekelijkse briefing. Zie
  `.claude/skills/chief-lifeos-officer/SKILL.md` voor de rol.
- De **MEX Scrum Master** (Claude, in deze repo) kan het ad-hoc aanroepen als
  hij zelf strategisch overzicht nodig heeft — via de `briefing`-skill; de
  wrapper in `.claude/skills/briefing/SKILL.md` verwijst naar dit bestand.
- De **LifeOS Chief of Staff** (ChatGPT) krijgt de instructie ofwel eenmalig als
  Custom Instruction / System Prompt, ofwel ad-hoc geplakt op het moment dat
  Ferry een briefing vraagt vanuit zijn kant.

Alle drie produceren dezelfde output-structuur. Waar de tekst rolspecifiek is
(bijvoorbeeld "start bij het MEX-bord"), staat expliciet welke agent dat doet.

## Waarom deze instructie bestaat

De Scrum Master beheert MEX-technisch werk. De Chief of Staff beheert de rest.
Beide zijn expliciet van elkaars scope, en dat werkt — behalve wanneer een MEX-
deadline een renovatieweek doorkruist, of een familieverplichting de dag opeet
waarop de VPS-build had gepland. **Die wissel valt tussen alles in.**

Deze instructie is de dunne laag die dat gat dicht zónder een derde rol te
introduceren. Elke agent kan hem draaien; de output is gelijk. Geen governance-
tussenlaag, geen authority, geen dagelijkse aanwezigheid — enkel een leesbeurt
die eindigt in één pagina naar Ferry.

## Wanneer draaien

- Ferry vraagt om een briefing / overzicht / weekbrief expliciet.
- Elke maandagochtend (Ferry kan dit als recurring instellen via de LifeOS-agenda).
- Voor een grote beslissing die meerdere domeinen raakt.
- Niet bij dagelijks werk — dan zit je te veel in de weg.

## Werkwijze

**Stap 1 — Lees de bronnen.** Je hebt drie bronnen nodig, ongeacht vanuit welke rol
je start. Ontbreekt er één (geen toegang, netwerkfout), meld dat en ga door met
wat je wél kunt zien; produceer geen halve briefing als volledig zonder markering.

| Bron | Wat je zoekt | Waar |
|---|---|---|
| **MEX-bord** | Alle items met status `wip` of `review` — wat er in beweging is deze week | `docs/SPRINT.md` (branch `claude/middleware-setup-guide-afhvtk`) |
| **LifeOS Tasks** | Alle taken met deadline binnen 7 dagen én alle taken met voorvoegsel `🛠️ MEX Dev ·` (die raken beide domeinen) | Notion Tasks database via de LifeOS Chief of Staff |
| **Approval Queue** | Alle items met `Type = Approval` en `Status = Inbox` — dat is wat op Ferry wacht | Notion Inbox database (`collection://d0c8311b-b464-4132-b156-836250502aab`) |

**Cross-platform toegang** — de twee agenten zitten op verschillende platforms
(Scrum Master op Claude, Chief of Staff op ChatGPT) en hebben elk een eigen
tool-set. Verwacht niet dat je vanaf de ene kant alles van de andere kunt lezen.

- **Scrum Master (Claude)** heeft de MEX-repo lokaal en kan `docs/SPRINT.md`
  direct lezen. Voor LifeOS Tasks en de Approval Queue is Notion-toegang nodig
  via de Notion MCP-connector; die kan er zijn of niet.
- **Chief of Staff (ChatGPT)** heeft de Notion-databases via de eigen
  connector. Voor `docs/SPRINT.md` moet hij ofwel via GitHub-toegang lezen
  (raw file van de branch), ofwel Ferry vragen de relevante alinea te plakken.

Als een bron ontbreekt: **schrijf dat op** in sectie 5 van de output, en ga
verder met wat je wél hebt. Nooit gokken; nooit een domein-conclusie trekken
zonder de bron. Als het echt niet kan, vraag de andere agent (of Ferry) om
alleen die ene bron aan te leveren, en draai de briefing pas dán.

**Stap 2 — Doe de vier cross-domain checks.** Deze zijn de reden dat de briefing
bestaat. Neem de tijd voor elk; als een check geen resultaat geeft, schrijf dat
op ("geen conflict deze week") — de afwezigheid van conflict is óók informatie.

1. **Tijd-conflict.** Is er een MEX-item met een concrete deadline (build/deploy
   op de VPS, een merge-venster, een risk-gate-activering) in dezelfde week als
   een niet-MEX blok (familie, reis, afspraak, renovatieweek)? Zo ja, welk werk
   moet Ferry laten schuiven?
2. **Aandacht-conflict.** Draagt Ferry meerdere `wip`-items tegelijk op zijn
   naam? Op het MEX-bord is dat zichtbaar in de Owner-kolom; in LifeOS als
   Route=Zelf. Boven de 3 gelijktijdige wip-items in totaal is een signaal.
3. **Approval-stapeling.** Hoeveel items staan er in de Approval Queue op
   Status=Inbox? Meer dan 5 is een signaal dat Ferry achterloopt op besluiten.
   Noem de oudste drie expliciet (met datum).
4. **Domeinen die naast elkaar wachten op hetzelfde.** Voorbeeld: MEX D-11
   wacht op secret-rotatie én LifeOS Financiën wacht op een 2FA-reset — twee
   items bij twee agenten, één handeling van Ferry. Zoek dit soort dubbels.

**Stap 3 — Schrijf de output.** Gebruik het onderstaande sjabloon, in de gegeven
volgorde. Elke sectie **maximaal 5 regels**. Als er niets te melden is, schrijf
"geen" — niet "alles ok" (dat is niet hetzelfde) en geen leeg blok.

```markdown
# Briefing — <datum> — <SM|CoS>

## 1. Wat botst deze week
Cross-domain conflicten uit stap 2. Verwijs naar het item-nummer waar mogelijk
(D-XX voor MEX; Task-titel voor LifeOS).

## 2. Wat wacht op jou
Approval Queue op Status=Inbox. Noem het aantal, de oudste drie, en één zin
per stuk wat er wacht.

## 3. Waar hangt je capaciteit
Wip-items op naam van Ferry over beide domeinen. Aantal + één zin per item.

## 4. Signalen zonder actie
Dingen die de moeite waard zijn om te weten maar nu geen actie vragen:
oudere blockers die net-uit-de-pas beginnen te lopen, veranderingen in
verwachte doorlooptijd, patronen (bijv. drie weken achtereen liep dezelfde
soort taak vast).

## 5. Wat GEEN briefing-onderwerp was
Als je een bron niet kon lezen, of een aanname moest maken, schrijf dat hier.
Zonder deze regel is een halve briefing niet te herkennen als half.
```

## Regels waar je NIET van afwijkt

1. **Geen aanbevelingen.** De briefing beschrijft, jij niet. Ferry beslist.
   Als je een conflict signaleert, benoem beide kanten neutraal; geen "je zou
   moeten…". Uitzondering: **een veiligheids- of secret-lek MOET wél worden
   gemarkeerd als "actie NU"** — dat is niet meer beschrijven, dat is melden.
2. **Geen nieuwe ID's.** Deze skill geeft geen D-nummers uit (dat is Scrum
   Master-werk) en creëert geen nieuwe Approval-items (dat is CoS-werk). Als
   je iets tegenkomt dat een nieuw item verdient, noem het en geef de andere
   rol de opdracht om het aan te maken — via `docs/inbox.md` als het MEX is,
   via de Approval Queue als het LifeOS-breed is.
3. **Geen live-executiepad-mutaties.** Deze skill leest, mag nooit code of
   configuratie op de VPS aanraken.
4. **Nooit een secret in de output.** Ook niet als een van de bronnen 'm draagt.
5. **Kort houden.** Als de briefing niet op één scrol op de telefoon past,
   heb je iets fout gedaan. Snijd, niet extend.

## Waarom deze structuur

De vier checks van stap 2 dekken de vier meest voorkomende failure-modes van een
domein-gescheiden opstelling: tijd-conflict (jij bent er niet), aandacht-conflict
(je bent er wel maar overladen), approval-stapeling (jij vertraagt beide kanten),
en gedeelde wachtstand (twee agenten wachten op hetzelfde ding zonder het van
elkaar te weten). Er zijn andere failure-modes; die vindt Ferry via het werken
zelf. Deze skill is voor de vier waar geen van beide agenten alleen zicht op
heeft.

De output is bewust vlak — geen kleuren, geen prioriteitsscores, geen algoritme
dat kiest wat "belangrijker" is. Ferry weet wat belangrijker is; de briefing
maakt zichtbaar, hij prioriteert.

## Voor het geval het niet volstaat

Als je na een maand draaien merkt dat dezelfde soort issue steeds tussen SM en
CoS blijft hangen — dat is precies de aanleiding om een echte CLO-rol te
overwegen. Noteer in de laatste briefing van de maand: "signalen die deze skill
niet ziet" — dan bouwt zich een spoor op waaruit Ferry (of jij, als hij het
vraagt) kan afleiden of een derde rol nodig is en waarvoor precies. Zonder dat
spoor is een CLO een gok; met dat spoor is het een onderbouwde stap.
