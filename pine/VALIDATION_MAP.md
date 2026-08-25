# Validatie-map — welke export hoort bij welk script

> Eigenaar: Pine Dev. Hoort bij **D-42**. Bevroren parameters staan in
> `.claude/skills/strategy-validation-pipeline/references/frozen-engines.md`;
> dit bestand gaat over de *koppeling* tussen een script en het bewijs ervoor.

## De regel

**Een TradingView-export geldt alleen als bewijs voor een script als de export de
shorttitle van dát script draagt.** De shorttitle staat in de export-bestandsnaam en in
`Properties`. Draagt hij een andere naam, dan is de export bewijs voor een *ander*
script of voor niets — en mag hij niet als validatie van dit script geciteerd worden.

Reden: shorttitle is het enige identiteitsveld dat TradingView zelf in de export schrijft.
Bestandsnaam, chart-symbool en mapnaam zijn allemaal door de gebruiker te zetten en
overleven een fork niet.

## Waarom dit misging — één defect, drie verschijningen

Alle drie de defecten in `MEX_FLEET_PACKAGE_2026-08-23` komen uit dezelfde handeling:
**een script forken zonder het identiteitsblok te herschrijven.**

| Verschijning | Wat er staat | Wat het hoort te zijn |
|---|---|---|
| `MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0.pine` | regel 9 `EL MATADOR` / `MAT-MES-P` **én** regel 10 `EL CENTINELA` / `CEN-MES-P` | alleen `EL MATADOR` / `MAT-MES-P` |
| export op MES | `CEN-MES-P` | `MAT-MES-P` |
| export op MNQ1! | `TΞSORO_PI` | `REY-NQ-PI` |
| export op MYM1! | `TΞSORO_PE` | `LEO-MYM-P` |

De MATADOR-fork liet de oude kop *naast* de nieuwe staan; de twee andere scripts zijn van
TESORO geforkt en hielden diens shorttitle **volledig**. Vandaar dat een MNQ- en een
MYM-export allebei "TESORO" heten terwijl TESORO op MGC draait.

**Structurele fix, niet alleen opruimen:** de identiteit (merknaam, shorttitle, markt,
profiel) hoort op precies één plek in het bestand te staan, bovenaan, en `strategy()`
moet daaruit lezen. Zolang de naam op twee plekken kan staan, kan een fork ze uit elkaar
laten lopen zonder dat iets stukgaat.

## Koppeling per script

Status `bevestigd` = de export draagt de shorttitle van het script.
Status `afgeleid` = de koppeling volgt logisch uit markt + profiel, maar de export draagt
een andere naam; **niet als bewijs citeren tot de export opnieuw gedraaid is.**

| Script | Shorttitle | Markt | Export in het pakket | Status |
|---|---|---|---|---|
| `MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0` | `MAT-MES-P` | MES | export met `CEN-MES-P` | **afgeleid** — CENTINELA is de werknaam van dezelfde MES-engine; er is geen tweede MES-script. **Hersteld 24-08:** regel 10 droeg een tweede merkkop en is vervangen door de lineage-regel die de andere scripts ook dragen. Regels 46-47 noemen CENTINELA nog wél — dat zijn pariteits- en herkomstnotities, geen identiteitsclaim, en die blijven staan. |
| EL REY — Production Intraday | `REY-NQ-PI` | MNQ1! | export met `TΞSORO_PI` | **afgeleid** — `_PI` = Production Intraday, en MNQ Production Intraday bestaat maar één keer in de vloot |
| EL LEON — Production EOD | `LEO-MYM-P` | MYM1! | export met `TΞSORO_PE` | **afgeleid** — `_PE` = Production EOD, en MYM Production EOD bestaat maar één keer in de vloot |
| overige zes scripts | — | — | geen export in het pakket | **geen bewijs** |

## Wat er nodig is om `afgeleid` naar `bevestigd` te krijgen

Per script één keer opnieuw exporteren nadat het identiteitsblok is hersteld. Dat is
goedkoper dan het alternatief en het is de enige manier waarop de koppeling zichzelf
bewijst in plaats van dat een document hem beweert.

Zolang een regel `afgeleid` staat, mag het getal eronder wél gebruikt worden voor
richting en volgorde, **niet** als validatiebewijs in een rapport of in een
go/no-go-besluit over funded kapitaal.

---

# EL TORO — de vier eval-scripts (24-08)

`EL_TORO_NQ_ES_GC_FINAL_FRONTIER.csv` staat als `pine/validation/EL_TORO_FINAL_FRONTIER.csv`.
De vier scripts staan in `pine/`; de v6.9.5-TORO is naar `pine/history/` verplaatst.

## Koppeling script ↔ frontier-rij

| Script | Shorttitle | Frontier-rij | Status |
|---|---|---|---|
| `MEX_EL_TORO_NQ_HF_INTRA_v1_0_0` | `TOR-NQ-HF` | `FI · NQ · Intraday · FAST` — 7 NQ · FVG4-12 · CVD3 · VWAP · SL90 · TP90 · exp9 | **afgeleid** — alle zeven parameters komen exact overeen, maar het script compileerde niet (zie inbox 22), dus deze cijfers komen niet uit dit bestand |
| `MEX_EL_TORO_ES_FAST_INTRA_v1_0_0` | `TOR-ES-FI` | `FI · ES · Intraday · FAST` — 6 ES · FVG2-8 · CVD OFF · VWAP OFF · SL90 · TP44 · exp18 | **afgeleid** — parameters komen overeen; Pine-pariteit niet aangetoond (inbox 22) |
| `MEX_EL_TORO_GC_SNIPER_EOD_v1_0_0` | `TOR-GC-SN` | `SE · GC · EOD · SNIPER` — 5 GC · FVG10-14 · CVD6 · VWAP · SL90 · TP64 · exp12 | **afgeleid** — parameters komen overeen; Pine-pariteit niet aangetoond (inbox 22) |
| `MEX_EL_TORO_NQ_SNIPER_INTRA_v1_0_0` | `TOR-NQ-SN` | **geen rij** — 7 NQ · FVG4-8 · CVD7 · SL100 · TP90 · exp6 komt in de hele CSV niet voor | **geen bewijs** |
| *ontbreekt* | — | `FAST-EOD · GC · EOD · FAST` — 6 GC · FVG2-10 · CVD0/1 · VWAP OFF · SL120 · TP54 · exp9 | **geen script** |

Twee dingen om niet over te lezen:

1. **Het beste config uit de hele frontier heeft geen script.** De GC FAST-EOD-rij scoort
   `pass_opportunity_index_per_year` **1710** — hoger dan elke andere rij, en zeventien keer
   de GC SNIPER (50,3) die wél een script kreeg. Er is 4.011 kansen per jaar tegen 100.
2. **`TOR-NQ-SN` draagt geen enkel bewijs.** Geen rij in de frontier heeft CVD7, SL100 of
   expiry 6. Zolang dat zo is, is dit script een voorstel en geen gevalideerde config.

De vier `2D`/`3D`-rijen (ES en GC, staged/MULTI) hebben ook geen script; die lijken buiten
deze levering te vallen.

## Herstelde naamdefecten

Twee van de vier shorttitles braken het schema BRAND-MARKT-PROFIEL:

| Was | Is | Waarom |
|---|---|---|
| `TES-FI` | `TOR-ES-FI` | `TES-` is het TESORO-voorvoegsel (`TES-MGC-C`). Een TORO-script dat zich als TESORO aandient is exact het defect uit de vorige ronde — een derde geval van dezelfde fork-fout. |
| `TGC-SE` | `TOR-GC-SN` | droeg helemaal geen merk, alleen markt + profiel. |

`TOR-NQ-HF` en `TOR-NQ-SN` waren al goed. Alle vier blijven ≤ 10 tekens.

## De one-shot-economie klopt, en is opzet

Alle vier zijn zo gesized dat **één winnende trade de eval haalt en één verliezende trade
hem breekt**. Dat is geen fout maar het gebruikspatroon van EL TORO.

| Script | TP netto | Doel | Marge | Volle stop | Trailing DD |
|---|---|---|---|---|---|
| `TOR-NQ-HF` | 90t × $5 × 7 = $3.150 − $22 = **$3.128** | $3.000 | +$128 | $3.150 | $2.500 → breach |
| `TOR-NQ-SN` | 90t × $5 × 7 = $3.150 − $22 = **$3.128** | $3.000 | +$128 | $3.500 | breach |
| `TOR-ES-FI` | 44t × $12,50 × 6 = $3.300 − $19 = **$3.281** | $3.000 | +$281 | $6.750 | breach |
| `TOR-GC-SN` | 64t × $10 × 5 = $3.200 − $16 = **$3.185** | $3.000 | +$185 | $4.500 | breach |

Elke TP klaart het doel met $128–$281 over; elke volle stop breekt het account. Dat de
ES-stop $6.750 diep is terwijl de DD $2.500 bedraagt, kost niets extra — op een eval is
gebroken gebroken en je betaalt het verschil niet. Herstel dat dus niet "voor de veiligheid";
het zou alleen de kans op de pass verlagen.

## Twee open punten op deze vier

1. **De GC-commissie staat op $1,55 per contract, de registry zegt $1,75 voor GC**
   (`backtest/config.py`; MGC is $0,52). Op de pass/fail-rekensom scheelt het $2 en dus
   niets, maar het is een tweede bron naast de registry — dezelfde soort als D-08. **Niet
   stilzwijgend wijzigen:** de frontier is op $1,55 gedraaid, dus het script veranderen laat
   het van zijn eigen validatie afwijken. Eerst een besluit, dan één keer opnieuw meten.
2. **De D-08-commissiewacht ontbreekt.** Geen van de vier draagt `SPEC_COMMISSION_SET` of
   `f_contractSpec` — de controle die in TESORO juist deze fout zou vangen. Dat is de reden
   dat punt 1 stil kon blijven.


---

# 25-08 · D-42 uitgevoerd, en wat dat voor de koppeling betekent

## De acht v6.9.5-scripts staan niet meer in `pine/`

Verplaatst naar `pine/history/`, niet verwijderd — git houdt ze sowieso, maar ze moeten
leesbaar blijven zolang oude exports ernaar verwijzen:

| Gearchiveerd | Opvolger |
|---|---|
| `MEX_EL_TESORO.v7.10.0.bak` | `MEX_EL_TESORO_MGC_CON_EOD_v1_0_0` |
| `MEX_EL_REY.v6.9.5.pine` | `MEX_EL_REY_MNQ_PROD_EOD_v1_0_0` + `..._INTRA_v1_0_0` |
| `MEX_EL_PATRON.v6.9.5.pine` | `MEX_EL_PATRON_MGC_AGG_EOD_v1_0_0` |
| `MEX_EL_MATADOR.v6.9.5.pine` | `MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0` |
| `MEX_EL_LEON.v6.9.5.pine` | de drie LEON-scripts |
| `MEX_EL_DORADO.v6.9.5.pine` | **geen** — DORADO staat niet in de vloottabel |
| `MEX_EL_MINERO.v6.9.5.pine` | **geen** — gereserveerd merk, geen engine |

⚠️ **De TESORO-back-up heet `.v7.10.0`, niet `.v7.9.5`.** Het besluit beschreef v7.9.5
(3 MGC, FVG 9–15, SL 100t, 1,55R); de werkboom droeg v7.10.0 met **6 MGC, FVG 9–15,
maxStop 130, SL 100, 1,55R, CVD4**. De naam volgt wat er stond, niet wat het besluit
aannam — anders archiveer je een bestand onder een versienummer dat het niet is.

## 🔴 Elke export in het pakket is ouder dan het script waar hij bij hoort

De vloot staat op **v2.3.0**; alle exports komen van de v1.0.x-lijn. Voor de parameters
maakt dat niets uit — de pariteitstest van Backtest Setup draait groen tegen de huidige
bestanden en de presets zijn regel voor regel geverifieerd. De toevoegingen (zes
signaalfilters, risk-gate, regimevensters) staan allemaal default UIT.

**Eén uitzondering, en die is echt:** `skipMonEarly` is 25-08 verwijderd uit **EL PATRON,
EL TESORO en de vier EL TORO's**, waar hij op `true` stond. In die zes handelt maandag
00:00–02:00 ET nu mee. **De bestaande exports van die zes beschrijven het script niet meer**
en mogen niet als validatie van v2.3.0 geciteerd worden. De overige zeven zijn ongemoeid:
daar stond de schakelaar al uit, dus was het verwijderen gedragsneutraal.
