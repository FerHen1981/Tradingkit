# Bevroren gevalideerde engines — stand 23 augustus 2026

Bron: `MEX_FLEET_PACKAGE_2026-08-23`, na MES CVD6 Pine-pariteit.
Deze parameters zijn **bevroren**. Een wijziging is een nieuwe onderzoeksronde vanaf
trap 1 van de pijplijn, geen tweak. Optimaliseer ze niet stilzwijgend.

De getallen hieronder zijn **reproduceerbare onderzoekscheckpoints op de huidige
datasets**, geen permanente marktwaarheden. Ze moeten opnieuw gevalideerd worden zodra
dataset, feemodel, prop-regels, uitvoeringsaannames of implementatie wijzigen.

## Naamgevingsarchitectuur

Merknaam = vaste strategie-persoonlijkheid. Titel en bestandsnaam coderen zichtbaar
MARKT + CON/AGG/PROD/HF + EOD/INTRA. Shorttitle ≤ 10 tekens.

| Merk | Markt | Profiel | Shorttitle | Status |
|---|---|---|---|---|
| EL TESORO | MGC | Conservative EOD | `TES-MGC-C` | gevalideerd |
| EL PATRON | MGC | Aggressive EOD | `PAT-MGC-A` | gevalideerd |
| EL REY | MNQ | Production EOD | `REY-MNQ-P` | gevalideerd |
| EL REY | MNQ | Production Intraday | `REY-NQ-PI` | profiel |
| EL MATADOR | MES | Production CVD6 EOD | `MAT-MES-P` | Pine-gevalideerd |
| EL LEON | MYM | Production EOD | `LEO-MYM-P` | gevalideerd |
| EL LEON | MYM | Recovery Intraday | `LEO-YM-CI` | profiel |
| EL LEON | MYM | Recovery EOD | `LEO-YM-CE` | profiel |
| EL BANDIDO | MYM | HF / Harvest EOD | `BAN-MYM-H` | **Pine-pariteit open** |
| EL PRINCIPE | MNQ | Balanced | — | research, niet live |
| EL MINERO | — | — | — | gereserveerd, toekomstige HF/commodity |
| EL TORO | — | — | — | **uitsluitend evaluatie-accounts** |

Een *operating profile* (INTRA/recovery/de-risked) verandert accountmodel en omvang,
**niet** de signaalarchitectuur. Een *naming-only release* verandert alleen de naam.

## Parameters

### EL REY — MNQ Production CVD8
6 MNQ default · FVG 2–8 ticks · OHLCV-proxy CVD8 · SL 200t · 1,25R · expiry 6 ·
BE/trail OFF · alle sessies behalve force-flat.
Pine: 140 trades, +$27.436, PF 1,884, WR 60,71%, LONG PF 1,637, SHORT PF 2,397,
max intrabar DD ≈ $4.907.
4 MNQ is een de-risked accountstatus-profiel — verandert exposure, niet de signalen.

### EL MATADOR — MES Production CVD6
6 MES · FVG 10–22t · OHLCV-proxy, Delta ON, streak ON, CVD6 · SL 120t · 1,75R ·
expiry 6 · BE/trail OFF · daily OFF · alle sessies · EOD-preset ·
$0,51/zijde commissie · 1 tick slippage.
Pine: 121 trades, +$32.994,48, PF 1,816, WR 52,07%, gem. winnaar $1.165,19,
gem. verliezer −$696,77, LONG PF 1,860, SHORT PF 1,785, max intrabar DD ≈ $5.784,60.
Tick-economie: volledige stop ≈ −$913,62; volledige TP +$1.568,88.

### EL TESORO — MGC Conservative
7 MGC · FVG 11–16 · CVD6 · SL 140t · 2,25R · Liquidity Core · BE/trail OFF.
Pine: ≈94 trades, +$16.286, PF 1,665, WR ≈72,3%, max intrabar DD ≈ $5.054.
Rol: primaire goud-diversificatieanker.

### EL PATRON — MGC Aggressive EOD
8 MGC · FVG 11–16 · CVD5 · SL 140t · 2,25R.
Pine: ≈150 trades, +$19.024, PF 1,372, WR ≈68,7%, max intrabar DD ≈ $9.343.
Standaard alleen op volwassen EOD-accounts. **Draai geen constante 8 MGC op een
Intraday PA met bewegende trail.**

### EL LEON — MYM Production CVD6
3 MYM default · FVG 12–20t · proxy CVD6 · SL 480t · 1,25R · expiry 24 ·
BE/trail OFF · daily OFF.
Pine: 186 trades, +$11.913,84, PF 1,437, WR 55,38%, LONG PF 1,987, SHORT PF 1,116,
max intrabar DD ≈ $5.299.
2 MYM is het recovery-profiel; bruto volledige stop ≈ $480 vóór kosten.
MYM-ticksemantiek: ticksize = 1 indexpunt, tickwaarde $0,50 per MYM. Een numeriek grote
stop is in dollars klein — rapporteer altijd beide.

### EL BANDIDO — MYM HF / Harvest CVD3
5 MYM · FVG 4–8t · proxy CVD3 · SL 160t · 1,5R · expiry 18 · BE/trail OFF ·
harde dagcap $1.000 · EOD.
Research: ≈2.070 trades na cap, PF ≈1,17, snelle P1, hoge breach/churn.
**Status: Pine-pariteit vereist vóór live inzet. Tel hem niet mee als draaiende engine.**

## Standalone rangorde

1. EL REY — MNQ Production
2. EL MATADOR — MES Production
3. EL TESORO — MGC Conservative
4. EL LEON — MYM Production
5. EL PATRON — MGC Aggressive
6. EL BANDIDO — MYM HF/Harvest (specialist, Pine-poort open)
7. EL PRINCIPE — MNQ Balanced, alleen research

Rangorde is **niet** hetzelfde als accounttoewijzing.

## Correlatie-waarschuwing

MGC is de enige niet-aandelenbucket. MNQ, MES en MYM zijn alle drie
Amerikaanse aandelenindex-exposure en kunnen bij risk-on/risk-off schokken sterk
meebewegen, ook als hun signaaltiming verschilt.

Claim geen statistische decorrelatie vóór de dagelijkse gerealiseerde P&L-correlatie
over minstens 20–30 actieve dagen gemeten is. Blijft de paarsgewijze dagcorrelatie
tussen MES/MNQ/MYM structureel boven 0,70, verklein dan de index-bucket of zoek een
andere niet-index-markt.

## Bekende defecten in het pakket van 23-08

Vastgesteld door de Scrum Master bij ontvangst; nog niet hersteld in de bron.

1. `MEX_EL_MATADOR_MES_PROD_EOD_v1_0_0.pine` draagt **twee** merkkoppen: regel 9 noemt
   EL MATADOR / `MAT-MES-P`, regel 10 noemt EL CENTINELA / `CEN-MES-P`.
2. Geen van de drie validatie-exports draagt de naam van het script dat het valideert:
   `CEN-MES-P_…MES1!` (→ EL MATADOR), `TΞSORO_PI_…MNQ1!` (→ vermoedelijk `REY-NQ-PI`),
   `TΞSORO_PE_…MYM1!` (→ vermoedelijk `LEO-MYM-P`). Pre-rename exports.
   **Bevestig de koppeling voor je een export als bewijs voor een script gebruikt.**
