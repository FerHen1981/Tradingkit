# D-02 — dagelijkse risk-gate (trigger, buffer, DLL) per Apex-account-type

Concrete spec voor wie de risk-gate bouwt in `mex-receiver` (.NET, live path) én in
`El Tesoro v7.9.2` (Pine, backtest & signal-generation). Twee configuraties, elk
gebonden aan een Apex-account-type. Getest tegen 1 jaar MGC1! trade-data
(`T_SORO_COMEX_MINI_MGC1_20260819_e5951.xlsx`, 3.651 trades, 254 sessies).

## Kern-mechaniek

**Twee onafhankelijke drempels per handelsdag:**

1. **Daily Loss Limit (DLL)** — intra-trade hard geënforced.
   Als cum_session_pnl + MAE_current_trade ≤ -DLL → sluit positie, halt account voor sessie.
   Boekt exact -DLL (geen slip, want intra-tick enforcement).

2. **Trail** — alleen op trade-close cum.
   Als cum_session_pnl ≥ TRIGGER → activeer trail, exit_lvl = piek - BUFFER.
   Op elke volgende trade-close: update peak (alleen omhoog), exit_lvl = piek - BUFFER.
   Als cum ≤ exit_lvl na een trade-close → sluit positie, halt account voor sessie.

**Beide werken onafhankelijk:** DLL beschermt tegen catastrofe binnen één trade;
trail lockt behaalde winst zonder op intra-trade tick-noise te vuren.

**Reset:** cum_session_pnl wordt op $0 gezet bij CME-roll (18:00 ET).

**Venster:** entries alleen tussen 18:00-23:59 ET (Ma-Vr). Buiten dat venster geen
nieuwe entries; open positie draait door zoals normaal.

## Twee configuraties

### Config A — Apex 50K **Intraday** & Apex 50K **Legacy EOD** (default)

Deze past op ALLE Apex 50K account-typen. Overleeft trailing DD $2.500.

| Parameter | Waarde |
|---|---|
| Contract size | **q3** (of q4 als extra tolerantie gewenst) |
| Trigger (T) | **$10** |
| Buffer (B) | **$100** |
| DLL | **$150** |
| Venster (ET) | 18:00 – 23:59 |
| Enforcement | DLL intra-trade hard, trail op trade-close |

**Verwacht per 50K account per jaar (1 jaar data):**
- q3: **$12.810 payout** (alle 6 stappen, laatste = wait-for-cap)
- q4: **$16.606 payout** (alle 6 stappen, laatste = wait-for-cap)

### Config B — Apex 50K Legacy EOD **alleen** (agressief, hoger risico)

| Parameter | Waarde |
|---|---|
| Contract size | q6 |
| Trigger (T) | $50 |
| Buffer (B) | $25 |
| DLL | $500 |
| Venster (ET) | 18:00 – 23:59 |
| Enforcement | DLL intra-trade hard, trail op trade-close |

**Waarschuwing:** deze config blowt Apex 50K in de eerste 4-8 weken (drawdown-diepte
in de start-fase overschrijdt trailing $2.500). **Niet gebruiken op onvoldoende
buffered account.** Alleen relevant voor 100K+ accounts of Apex Legacy zonder
strakke trailing.

## Waarom deze getallen

Uit de trade-data (venster 18-23 ET, alle 5 werkdagen):

- **Mediaan intraday piek**: +$168 (q6). Trigger $10 op q3 = 30 gold-punten →
  wordt in 60% van sessies geraakt.
- **MAE-distributie per trade**: mediaan $123, 90e percentiel $609 (op q6). DLL
  $150 op q3 = q3-schaal MAE mediaan $62, DLL vangt alleen echte disaster-days.
- **Bimodale pullback na piek**: 59% van piek-sessies gaat direct naar close op piek;
  35% dumpt fully weg. Buffer $100 op close-cum is genoeg om directe post-piek
  drops te vangen zonder in het intra-trade noise-band te vallen.

## Fan-out-consequenties (voor `mex-receiver`)

De risk-gate zit **per account, per sessie**. Fan-out gebeurt NA de risk-gate:
- Als één Pine-alert vuurt, en 3 accounts staan op halt → order gaat naar de
  overige accounts, halt-accounts krijgen niets.
- Halt-status per account resetten bij CME-roll (18:00 ET).
- Halt-status is een sessie-eigenschap, GEEN persistente vlag.
- `middleware/app/risk.py` heeft al `_halted` als per-account per-day set — die
  logica moet naar `mex-receiver` overgeheveld want daar loopt de live path.

## Fan-out-consequenties (voor Pine)

El Tesoro v7.9.2 moet:
- Halt-status intern bijhouden per sessie, cum_pnl bij CME-roll resetten
- Alerts blokkeren als halt actief is (geen nieuwe entries)
- Bestaande open positie sluiten wanneer halt getriggerd wordt (DLL of trail)
- Backtest overlay: laat visueel zien welke dagen halt-status hadden en waarom
  (SL / trail / natural close)

## Toets tegen propfirm-engine

De Pine-strategy moet twee overlays ondersteunen:
1. **Native mode** (huidige gedrag) — normale entries/exits zonder risk-gate
2. **Apex-mode** — risk-gate actief, per account-variant:
   - `EOD`: trailing update op EOD balance (Legacy)
   - `Intraday`: trailing real-time op laagste intra-sessie punt
   - `Legacy_EOD_locked`: hetzelfde als EOD maar met lock op $50.100

Voor elke variant moet de backtest kunnen laten zien:
- Overleeft account het jaar?
- Hoeveel payouts (0-6) worden bereikt?
- Op welke datum blowt het account (indien van toepassing)?

## Wat te verifiëren voor live-uitrol

1. **CVD-context**: deze reeks is CVD-loos (raw MGC1! trade-export). De live-script
   draait met CVD. Getallen zijn ondergrens; live-behoud waarschijnlijk 50-70% van
   in-sample cijfers.
2. **OOS-check**: op split in 2 helften was OOS-behoud voor gel-filter-modellen
   maar 10-14%. Voor de HOOFDregel (T/B/DLL zonder cel-filter) is OOS-behoud
   naar schatting 50-70% (structurele uur-filter houdt stand, cel-selectie niet).
3. **Slip in enforcement**: `mex-receiver` moet daadwerkelijk intra-tick sluiten op
   DLL. Als dat niet lukt en het wordt trade-close enforcement, zakken de cijfers
   met factor 2-4×.
4. **Startperiode**: eerste 15-25 weken zijn typisch opbouw met payout pas ná
   week 30 (payout-eligibility na consistency + safety net + 8 trading days).

## Sanity check op de bestaande fleet

Huidige 6 funded accounts op MGC:
- 018, 013, 016, 015, 017, 021
- Alle op q6 met impliciet oude regel (geen DLL, geen trail)
- Balances tussen $50.053 en $55.303, buffers $751 tot $5.203 boven trailing

**Aanbeveling:** deze accounts overzetten naar Config A (q3, T=$10/B=$100/DLL=$150)
zodra `mex-receiver` de risk-gate ondersteunt. 013 (dichtstbij payout) eerst.

## Nog niet gedaan

- OOS-toets specifiek voor T/B/DLL regel zonder cel-filter
- Correlatie-effect: 6 accounts op zelfde MGC + zelfde regel = 6× dezelfde SL-halt
  op zware dagen. Fleet-model nodig voor P(≥k gelijktijdige halts).
- Live-CVD-effect kwantificeren (vereist een paar weken A/B: CVD-on vs CVD-off)
