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
| `MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0` | `MAT-MES-P` | MES | export met `CEN-MES-P` | **afgeleid** — CENTINELA is de werknaam van dezelfde MES-engine; er is geen tweede MES-script |
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
