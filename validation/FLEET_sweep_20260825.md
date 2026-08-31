# Vloot-sweep trap 0→9 — spoor (2026-08-25)

> **Wat dit is.** Het append-only bewijsspoor van de eerste volledige vloot-sweep
> (D-55). De sweep zelf draaide 24–25 augustus (commit `0bc13a7`); de rauwe
> `pipeline_state.json` staat in de **lab-map en dus niet in git**, en de conclusies
> stonden alleen in `docs/DECISIONS.md` en `CLAUDE.md`. Dit bestand legt vast **wat
> er gemeten is**, zodat het navolgbaar blijft als de cijfers herzien worden (D-54).
>
> **Dit is een transcriptie, geen herdraai.** De micro-datasets (~1,05M bars/markt)
> staan op Ferry's machine, niet in de checkout. Bronnen: sweep-commit `0bc13a7`
> (mechanisme + poortsemantiek) · `DECISIONS.md` 25-08 (de per-engine cijfers,
> regels "EERSTE VOLLEDIGE VLOOT-SWEEP", "PATRON valt af", "SYSTEEMBEVINDING …DLL")
> · `CLAUDE.md` vloot-tabel. Wijkt een herdraai hiervan af, dan is de herdraai leidend
> en krijgt dit bestand een intrekkingsnotitie eronder — niet herschreven.

## Meetvenster & status van de cijfers
- **Venster:** `--since 2023-08-24` — één gemeenschappelijk 3-jaars venster over alle
  engines (eerlijke vergelijking + geen OOM op de 2-core box). Vóór die uitlijning
  liep het 4,29M-bar GC-twin-bestand uit het geheugen (PATRON/TESORO gaven "FOUT").
- **⚠️ D-18: dit venster is VALIDATIE, geen out-of-sample.** De `v1_0_0`-configs zijn
  bevroren op **23-08-2026**; echte OOS loopt forward vanaf die datum. Op de sweepdatum
  is dat **twee dagen**. Elk cijfer hieronder valt volledig binnen het validatievenster —
  claim er geen OOS-bewijs uit.
- **⚠️ Maar 3 van de 9 engines hebben een export**, en trap 1 (harde pariteitspoort)
  meet tegen een export: MATADOR/MES, LEON_PROD/MYM, REY_INTRA/MNQ. De overige zes
  kunnen trap 0 en 2 draaien maar hun harde poort blijft dicht.

## Doel van de meting
Niet PF, maar **gebankte payout-$ per bezette account-dag**, gemeten op de
contractgrootte die daadwerkelijk overleeft. Zie de systeembevinding: de bevroren
volle grootte overleeft nergens, dus alle payout-cijfers staan op **1 contract**.

## SYSTEEMBEVINDING (trap 7/8) — staat los van de rangorde, mechanisme-niveau
Geverifieerd, reproduceert over álle engines, en **onafhankelijk van welke rangorde
dan ook** (→ D-53). Research-mode aan/uit gaf identieke funded-uitkomst, dus geen
dubbeltelling.

- **De bevroren volle contractgrootte is niet fresh-account-funderbaar.** Op volle
  grootte breekt élke engine op trap 7/8; op 1 contract fundeert élke engine.
- **Twee bindende muren, en de trailing-DD raak je als eerste:**
  1. **$2.000 trailing drawdown** van een vers account — een verliesreeks van ~$2.700
     breekt hem vóórdat de buffer de floor vergrendelt.
  2. **$1.000 PA daily-loss-limit** — MATADOR met 6 MES-contracten (stop $150/ct):
     één slechte dag = `daily loss $−1.033 exceeded DLL $1.000`.
- De `.pine`-bron schaalt contracten in (`derisk`/`deriskPA`); de **bevroren config
  doet dat niet**. Dit is een openstaande ontwerpkeuze (start-klein-en-schaal-op, of
  qty per accountfase), geen backtest-bug. → D-53 (sizing in de fan-out, route B),
  D-57 (route A, later).

### Poortsemantiek trap 7/8 (sinds `0bc13a7`)
| verdict | betekenis |
|---|---|
| `passed` | volle bevroren grootte overleeft een vers account |
| `inconclusive` | 1 contract is funderbaar, maar de bevroren grootte breacht → vraagt om scaling |
| `failed` | zelfs 1 contract fundeert niet |

Trap 8 rapporteert de payout-$/account-dag op de grootte die **overleeft** — anders is
het cijfer een luchtspiegeling.

## Per-engine uitkomst (payout-$/account-dag op 1 contract)
| Engine | Markt | $/account-dag | P1 | Pariteitspoort (trap 1) | Bruikbaarheid |
|---|---|---|---|---|---|
| **MATADOR** | MES | **$30,59** | dag 85 | ✅ `data_parity` (dicht) | ✅ enige bruikbare — zie kostenvoorbehoud |
| LEON | MYM | $17,48 | dag 118 | ⛔ open (D-63 config-mismatch) | ⛔ **ONGELDIG**, niet "indicatief" |
| REY | MNQ | $13,21 | dag 161 | ⛔ open (D-63 config-mismatch) | ⛔ **ONGELDIG** |
| PATRON | MGC (GC-twin) | fundeert niet op 1 ct | — | n.v.t. | ⚠️ afgevallen — GC-twin-voorbehoud |
| TESORO | MGC (GC-twin) | fundeert niet op 1 ct | — | geen export | ⚠️ GC-twin-voorbehoud |
| BANDIDO | MYM | fundeert niet op 1 ct | — | pariteit open (D-61 compile-defect) | ⚠️ niet live |

### Rangorde — en waarom hij (nog) niet geldt
De verse meting geeft **MATADOR › LEON › REY**. Dat wijkt af van de oude CLAUDE.md-orde
(REY › MATADOR › TESORO › LEON), die al onder de research-invalidatieregel (grondregel 9)
viel. **Maar deze rangorde is óók niet bruikbaar:** alleen MATADOR heeft een gesloten
harde poort. LEON's $17,48 en REY's $13,21 staan onder een **open** harde poort, en
`backtest/pipeline/state.py` noemt onvervulde harde poorten precies de poorten die
downstream-cijfers *"invalid rather than merely early"* maken. Behandel $17,48 en $13,21
dus **niet** als "ongeveer goed" (→ D-54). **Rangorde ≠ accounttoewijzing.**

### PATRON — expliciet afgevallen (onder MGC-voorbehoud)
- trap 2: **GEEN EDGE** — −$2,76/trade, PF 0,96.
- trap 4: één handelsrichting draagt de edge.
- trap 9: **CHERRY-PICK** — zonder uur/dag-masker verdampt de edge.
- ⚠️ Gemeten op de **GC-twin**; echte MGC-data ontbreekt. Ook deze *afwijzing* staat
  daarmee onder voorbehoud (→ D-56). PATRON is zwaar in twijfel, niet definitief dood.

## Voorbehouden die op élk cijfer hierboven drukken
1. **Kosten (D-63/D-07).** Alle drie de validatie-exports draaiden commissie **0,51**
   terwijl de registry voor MNQ/MES/MYM **0,37** draagt (0,51 ligt tegen MGC's 0,52 —
   vermoedelijk een goudwaarde op index-micros, patroon van D-08). Kosten verschuiven PF
   direct. **Ook MATADOR's `data_parity` is behaald onder 0,51** → hertoetsen zodra de
   commissie op 0,37 staat; $30,59/dag is het enige cijfer waar iets op rust.
2. **MGC-voorbehoud (D-56).** PATRON/TESORO/BANDIDO zijn op de GC-twin gemeten.
3. **Validatie, geen OOS (D-18).** Zie meetvenster.

## Herkomst
Sweep-commit `0bc13a7` (24-08 23:42 UTC, "vloot-sweep tot trap 9") · `DECISIONS.md`
25-08 · `CLAUDE.md` vloot-tabel · getrieerd in D-52 → D-53/54/55/56.
