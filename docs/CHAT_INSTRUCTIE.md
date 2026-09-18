# Instructie voor alle MEX-chats — vastlegging loopt via de Scrum Master

_Vastgesteld 2026-08-19. Eigenaar: Scrum Master._

Plak het blok onderaan dit document als **openingsbericht** in elke code-chat
(Middleware App · Backtest Setup · Pine Dev · Website · Analyses & Data).

---

## Welke chat is welke rol?

De rollen hieronder (en overal in `SPRINT.md`, `inbox.md` en de startprompts) komen uit de
**eigenaarstabel**, niet uit de chattitels in Ferry's zijbalk. Die twee lopen uiteen, en dat
kostte 18-09 een vraag die niemand uit het repo kon beantwoorden. Vandaar deze tabel.

| Rol (in alle documenten) | Chattitel in de zijbalk | Map |
|---|---|---|
| **Middleware App** | **App Setup** ⚠️ *afgeleid, niet bevestigd* | `middleware/**` |
| **Backtest Setup** | Backtest Setup | `backtest/**` · `tools/**` · `validation/**` |
| **Pine Dev** | Pine Dev | `pine/**` · `tools/gen_pine_firms.py` |
| **Web** | Website Build Mex-traders.com | `web/**` |
| **Legacy (Discord Notify)** | Discord Notify · Legacy accounts setup en scripts ⚠️ *twee chats, rolverdeling onbevestigd* | notify-kanaal in de .NET-receiver |
| **Scrum Master** | Scrum Master serverwijzigingen | `docs/**` |

Chats zónder rol in dit project: *Analyses, data en chat-organisatie* (branch afgevoerd, D-43),
*LifeOS taken overzicht* (Chief of Staff, non-MEX — hoort de MEX-repo niet te hebben),
*MCP trader-dev SSE transport*.

⚠️ **De twee regels met een waarschuwing zijn mijn afleiding uit een schermafbeelding, geen
bevestigde koppeling.** Klopt er iets niet, zeg het — dan corrigeer ik deze tabel. Dat
`DECISIONS.md` op 19-08 onderscheid maakt tussen *"de Discord Notify-sessie"* en *"Legacy"*
suggereert dat het inderdaad twee aparte chats zijn.

---

## Waarom

Vijf chats die allemaal zelf in Notion schrijven leveren hetzelfde probleem op dat
we in de repo al hebben: meerdere waarheden, niemand die weet welke geldt. Daarom
is er één route naar Notion, en die loopt via de Scrum Master.

## De rolverdeling — drie plekken, drie soorten waarheid

| Wat | Waar de waarheid staat |
|---|---|
| Code, configuratie, contract-specs, firm-regels | **de repo** `ferhen1981/tradingkit` |
| Wat er LIVE draait | **de VPS zelf** (`systemctl cat <service>`) |
| Taken | **LifeOS → Tasks** — voorvoegsel `🛠️ MEX Dev ·` |
| Besluiten, documentatie, archief | **LifeOS → Notes** — `🛠️ MEX Dev — …` |

Documentatie kan nooit actueler zijn dan code, en code nooit actueler dan runtime.
Bij tegenspraak wint de laag erboven.

## Wat jij als code-chat doet

**Wel:**
- Code en tests schrijven binnen je eigen map.
- Je eigen technische documentatie in de repo bijhouden (handoffs, README's, specs).
- Alles wat een andere chat, een gedeelde bron of het live executiepad raakt melden —
  in `docs/inbox.md` of rechtstreeks in de Scrum Master-chat.

**Niet:**
- Zelf Notion-pagina's aanmaken of bijwerken. Ook niet "even snel een taak toevoegen".
- Buiten je eigen map muteren.
- Een getal kopiëren dat al in een centrale bron staat.

## Hoe je iets aanlevert

Zet het in `docs/inbox.md` in dit formaat. De Scrum Master verwerkt het naar de
Notion-backlog en haalt het daarna uit de inbox — de inbox is een wachtrij, geen
archief.

```
### <korte titel>
**<van> → <naar/eigenaar>** · <datum> · status: OPEN

Probleem:
Waarom cross-chat:
Betrokken bestanden:
Benodigde wijziging:
Live-impact:      NONE / LOW / MEDIUM / HIGH
Acceptatiecriteria:
```

Raakt het het live executiepad, voeg dan toe:

```
Service:
Runtime geverifieerd:   ja/nee + hoe
Huidig gedrag:
Nieuw gedrag:
Failure mode:
Rollback:
```

## Wat je terugkrijgt

De Scrum Master zet elk item in de Notion-backlog met prioriteit, eigenaar,
afhankelijkheden en acceptatiecriteria, en bewaakt dat het niet verdwijnt. Besluiten
komen in het Besluitregister zodat een keuze niet in een chat-scrollback blijft
hangen. Achterhaalde documentatie wordt in het Documentatieregister gemarkeerd en
gearchiveerd in plaats van stilzwijgend te blijven rondslingeren.

---

## ▼ Plak dit in elke code-chat

```text
VASTLEGGING — werkafspraak per 2026-08-19

Alle vastlegging in Notion loopt via de Scrum Master-chat. Maak of wijzig zelf
geen Notion-pagina's.

Drie plekken, drie soorten waarheid:
- repo   = code, configuratie, contract-specs, firm-regels
- VPS    = wat er daadwerkelijk draait (systemctl cat <service>)
- LifeOS = taken (Tasks), besluiten + documentatie + archief (Notes)

Wat je zelf doet:
- code + tests binnen je eigen map
- je eigen technische docs in de repo (handoff, README, spec)

Wat je meldt in docs/inbox.md (of in de Scrum Master-chat):
- alles buiten je eigen map
- alles wat een gedeelde bron raakt (data/propfirms.json, backtest/config.py
  CONTRACTS, middleware/app/playbook.py STRAT_ASSET, cash_ledger, fills_pairing)
- alles wat het live executiepad kan raken
- elk conflict met werk van een andere chat
- elke architectuurwijziging die tijdens het bouwen ontstaat

Formaat voor een inbox-item:
  ### <titel>
  **<van> → <eigenaar>** · <datum> · status: OPEN
  Probleem / Waarom cross-chat / Betrokken bestanden /
  Benodigde wijziging / Live-impact / Acceptatiecriteria

Raakt het live execution, dan ook: service, runtime geverifieerd (ja/nee + hoe),
huidig gedrag, nieuw gedrag, failure mode, rollback.

De Scrum Master verwerkt het naar Notion en bewaakt de afhankelijkheid. Vraag
het daar op als je wilt weten wat er open staat — niet in je eigen scrollback.
```
