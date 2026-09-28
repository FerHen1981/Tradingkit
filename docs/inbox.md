# Inbox — cross-chat verzoeken (Analyses & Data-branch)

> Het levende bord en de volledige inbox staan op de Scrum-Master-branch
> (`docs/SPRINT.md`, `docs/DECISIONS.md`, `docs/inbox.md`). Deze chat pusht alleen naar
> `claude/analyses-data-*`; wat hier staat is de melding vanuit deze chat, door de Scrum
> Master over te nemen.

Formaat per item: **van → aan** · datum · status.

---

## OPEN

### 🟩 Analyses & Data → SM · 28-09 · **A-voorvoegsel doorgevoerd** · status: done (commit `5aa97bc`)

- `docs/state.md`: alle eigen besluiten dragen nu `A-` (A-43, A-75, A-76, A-77); nummers
  ongewijzigd, interne verwijzingen kloppen. Nummeringsregel staat bovenaan het register.
- Fleet-doc: de bouwscript-tekst verwijst vanaf de volgende versie (`v2`) naar A-76/A-77 en
  toont de projectiebasis naast jullie meting op het volle venster ($187 per contract-dag
  op 1–14 sep versus $27,59 op 01→25 sep). Het afgeleverde doc van 28-09 blijft zoals het is.
- CLAUDE.md is jullie bestand; niet aangeraakt.

**Drie A-besluiten die buiten deze chat reiken — graag een D-nummer op het bord, dan
verwijst het A-item ernaar:**

1. **A-76 · guard-zone en DLL-regel.** Day-trail 250 / 100 / 500 per contract × qty,
   bevestigd op drie samples (30, 65 en 257 dagen); DLL = 4 × SL per contract maar nooit
   meer dan ⅓ van de ruimte tot liquidatie; qty-plafond = consistency op het
   aanvraagmoment (`qty ≤ 0,3 × winst_bij_aanvraag ÷ 500`), ruimte-eis 3 DLL-dagen;
   afschalen direct na payout of DLL-dag. Dit is de doctrine die `fleet-report-spec.md` §6
   beschrijft en die D-97 toetst. Raakt: D-96, D-97, `data/propfirms.json` (SL-multiple,
   consistency-percentage per programma).
2. **A-77 · eval-floor volgt open winst** (Apex-ticket #1777923, account 243: unrealized
   peak $51.667,25 → floor $49.167,25). Op 5 NQ is het hele budget 100 ticks swing vanaf
   de beste open stand; MFE ≥ 10t gevolgd door een volle SL is een breach. De Pine-engine
   in phase Apex Eval modelleert dit correct (Intraday-model). Voorstel, nog niet live:
   Enable Trailing On, activation 40t / buffer 40t op eval-charts; test via El Toro-export
   met trailing aan. Raakt: Pine dev (TOR-NQ-HF), D-77 event-schema (`halt`-type met
   reden), registry (trailing incl. open P&L als eigenschap per programma).
3. **A-76 · TP blijft 85t** (100t/1R op hetzelfde venster 6% slechter, winrate −4 punt;
   jaarvalidatie staat op 85t). Raakt: Pine dev, D-104 (registry draagt geen TP; hoort in
   de strategie-config, niet in de firm-registry).

Bron voor alles: `docs/state.md` A-76/A-77 en de exports `d8ac1`, `2dc43`, `01b87`,
`6ea8e`, `89aa5` (uploads, niet in repo).
