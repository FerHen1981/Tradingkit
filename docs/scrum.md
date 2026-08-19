# Scrum board — één plek voor wie-wat-doet

Chats kunnen elkaar niet bereiken. Er is geen live kanaal tussen sessies, dus dit
bestand is het enige coördinatiepunt: **lees het als eerste, werk het als laatste bij.**
Alles wat een sessie moet overleven staat hier of in een ander bestand — nooit in
chat-scrollback.

Verzoeken aan een andere eigenaar horen hier (of in `docs/inbox.md` voor losse
observaties). Doe nooit werk in andermans map.

## Rolverdeling

Zie de werkafspraken (§2 eigenaarschap, §3 single source of truth). ⚠️ Die tekst staat
op dit moment **alleen in chat-scrollback** en heeft nog geen bestand — dat is in strijd
met het uitgangspunt hierboven. Eerste actie: vastleggen, bij voorkeur als
`docs/werkafspraken.md`, en dan hiernaar verwijzen in plaats van kopiëren.

| Gebied | Eigenaar |
|---|---|
| `backtest/**` | Backtest Setup |
| `pine/**`, `tools/gen_pine_firms.py` | Pine Dev |
| `middleware/**` | Middleware App |
| `data/propfirms.json` | gedeeld — via de generator |

## Live vs niet-live (geverifieerd 2026-08-18)

| Service | Source |
|---|---|
| `mex-receiver` (TV → PMT/Discord, .NET) | `/root/mex-middleware-b` — repo-source **alleen** op `claude/legacy-accounts-scripts-analysis-ui0j6m` |
| `mex-viewer`, `mex-lab`, Notion-syncs | `middleware/app/viewer.py`, `backtest/lab/`, `middleware/app/` |

`middleware/app/main.py` + `router.py` + `brokers/` draaien **niet**. Patch daar niets in
de verwachting dat het executie raakt.

## Openstaande beslispunten

1. **Eén branch of één branch per chat?** De werkafspraken (§5) zeggen één branch:
   `claude/middleware-setup-guide-afhvtk`. `docs/chats.md` zegt *"One branch per chat —
   never push to another chat's branch."* Die twee kunnen niet allebei gelden.
2. **Rolnamen zijn dubbel.** Werkafspraken: Backtest Setup / Pine Dev / Middleware App.
   `docs/chats.md`: Analyses & Data / Middleware dev / Pine dev. Kies één set.
3. **Wie is de Scrum Master?** `docs/chats.md` legt het legen van de inbox bij Analyses &
   Data. Als dat zo blijft, beheert die chat ook dit bord.

## Schuld — niemand bouwt hier overheen

- [ ] **.NET receiver staat niet op HEAD.** De live code van `mex-receiver` bestaat alleen
      op `claude/legacy-accounts-scripts-analysis-ui0j6m`. Merge nodig.
- [ ] **`docs/inbox.md` en `docs/chats.md` bestaan alleen op**
      `claude/analyses-data-chat-org-3tii8j`. Op de single branch bestaan ze niet, dus de
      inbox-regel verwijst nu naar een onzichtbaar bestand.
- [ ] **Commissie per contract staat op drie waarden** (Pine 0.67 / 1.55, backtest 0.52 /
      1.75). Eén bron kiezen — kandidaat: `backtest/config.py CONTRACTS`.
- [ ] **Dode Python notify-laag.** `middleware/app/notify.py` + `notices.py` + `/notice`
      (branch `claude/discord-notify-hnydfa`) draaien niet; de kaarten komen van de
      .NET-receiver. Besluit: weghalen of bewust laten staan.

## Werk dat klaar is maar nog niet op de single branch staat

| Commit(s) | Branch | Wat |
|---|---|---|
| `970483c` `6986c4e` `8c414cb` | `legacy-accounts-...` | **Live.** BlockedGate (signal blocked 1× per stopreden per dag), CONFIG/AUTO FLAT/LIMIT EXPIRED naar tier B, parser-fixes in `render-signal.js`, deploy-recept in de receiver-README |
| `929985e` `863393a` | `discord-notify-hnydfa` | Pine v6.9.2 — `f_mwNotice` + CONFIG-`else if`-keten opgeknipt |
| `c0b2b8f` `e630814` `a9aeef1` `260063e` `1468bdb` | `discord-notify-hnydfa` | Python notify-laag (niet live, zie schuld) |

## Verzoeken aan eigenaren

| Datum | Aan | Verzoek | Status |
|---|---|---|---|
| 2026-08-18 | Pine Dev | 8 scripts opnieuw plakken in TradingView (v6.9.2) — nodig voor de CONFIG-kaart bij sessiestart, alleen met `useJournal` aan | open |
| 2026-08-18 | Middleware App | Legacy-branch mergen zodat de live .NET-receiver op HEAD staat | open |
| 2026-08-18 | Middleware App | Besluit over de dode Python notify-laag | open |
| 2026-08-18 | Backtest Setup | Commissie-waarden gelijktrekken naar één bron | open |
