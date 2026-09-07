# bck.mex-traders.com — Backtest Lab cockpit · handoff

> Plak dit als openingsbericht in een nieuwe chat om daar met bck verder te gaan.
> Deze doc is de volledige stand: wat het is, hoe het draait (technisch), wat af
> is en wat nog open staat. Repo: `ferhen1981/tradingkit`, branch
> **`claude/middleware-setup-guide-afhvtk`**.

## 1. Wat bck is
Een **self-service backtest-cockpit** in de browser — de plek waar we de *edge*
onderzoeken. Eén strategie-spec × dataset × timeframes wordt door **drie lenzen**
gehaald:
- **Classic / research** — de kale edge (expectancy, PF, win%).
- **Eval / funnel** — prop-firm eval-simulatie.
- **Funded / payouts** — payout-simulatie op een funded account.

Het is bewust géén copy-trader en géén live-executie — puur onderzoek + het
genereren en OOS-verifiëren van kandidaat-strategieën.

## 2. Hoe het draait (technisch)
- **Service:** `mex-lab.service` (systemd) → `python -m backtest.lab.lab_viewer`.
- **Poort:** `127.0.0.1:8090` (env `LAB_PORT`, default 8090).
- **Domein:** `bck.mex-traders.com` → Caddy reverse-proxy → `:8090` (auto-HTTPS).
- **Data-root:** env `LAB_DIR` — bevat `datasets/`, `results/<run_id>/`,
  `index.json` (runs-registry) en de candidate-store.
- **Owner-gate:** env `LAB_PASSWORD` (leeg = open), plus `LAB_SECRET`.
- **Auto-deploy:** `backtest/deploy/mex-lab-autopull.timer` + `autopull.sh` pullen
  de branch. **Let op:** Python laadt de HTML één keer in geheugen — na een pull
  moet je **`sudo systemctl restart mex-lab`** draaien om de nieuwe pagina te
  serveren. (Verwar de service niet met `mex-viewer` = de Fleet-cockpit op 8080.)
- **Verifiëren zonder browsercache:**
  `curl -s localhost:8090/ | grep -nE "Upload dataset|Strategy library"`.

### Modules (`backtest/lab/`)
| Bestand | Rol |
|---|---|
| `lab_viewer.py` | De HTTP-cockpit zelf: serveert de pagina + JSON-API (`/api/specs`, `/api/datasets`, `/api/candidates`, run-endpoints). |
| `paths.py` | Resolvet `LAB_DIR` en alle subpaden. |
| `datasets.py` | Dataset-catalogus (naam, symbool). |
| `catalog.py` | Data-room catalog. |
| `normalize.py` | Streaming-normalizer voor Quantower/ATAS CSV-exports → genormaliseerde bars. |
| `runs.py` | Runs-registry met herkenbare `run_id`. |
| `insights.py` | Rule-based insight-engine achter de **Journey**-walkthrough (lens-per-lens uitleg). |

### Strategie-engine (buiten `lab/`, maar dít is de edge)
- `backtest/engine` + `backtest/config` + `backtest/spec` — de eigenlijke
  bar-by-bar engine en de spec→config-brug.
- **Specs:** `backtest/specs/*.yaml` — **15 stuks**: `bb_revert`, `bos`, `choch`,
  `cvd_divergence`, `donchian`, `el_toro_pa`, `el_toro_true`, `ema_cross`,
  `liquidity_sweep`, `ma_pullback`, `macd_cross`, `momentum`, `order_block`,
  `rsi_reversion`, `silver_bullet`.
- **Pluggable entry-generators (Level B→C):** engine dispatcht per config naar
  `_entry_*` generators — EMA-cross, break-of-structure (BOS), de volledige
  directionele familie, plus de **confluence-laag** met de **ICT Silver Bullet**
  (primary FVG + vereiste *prior liquidity sweep* + *VWAP-bias* + kill-zones
  London/NY-AM/NY-PM).
- `describe_config(cfg)` in `spec.py` leest een config eerlijk uit naar family
  (`trend` / `momentum` / `reversal` / `confluence` / `mixed`) + gates/filters/exit.

## 3. De cockpit-UI (paneelvolgorde)
1. **Upload dataset** — raw CSV-export → normalized → cataloged. (Staat bovenaan;
   je hebt data nodig vóór een run.)
2. **Run a backtest** — spec × dataset × timeframes × lens → Run.
3. **Strategy library** — elke governed strategie als kaart: family-badge, entries,
   confluence-gates + kill-zones, filters, exit. Klik = laadt in de runner.
4. **Generate strategies** — sample → in-sample screen → OOS verify (de overfit-gate).
5. **Candidates** — leaderboard met IS PF / OOS PF / retain / OOS n / verdict.
6. **Journey** + runs-tabel + run-detail (indicatoren, settings, IS/OOS-datumvenster).

## 4. Stand van zaken (up & running)
- `mex-lab` draait live op de VPS (`mex-mw-01`) op `:8090`; `bck.mex-traders.com`
  is bereikbaar.
- `/api/specs` geeft alle **15 specs** terug, geclassificeerd
  (7 trend / 2 momentum / 5 reversal / 1 confluence), met de Silver-Bullet-gates
  zichtbaar.
- Laatste commits: `a3247fc` (Strategy Library + transparantie), `62c37f8`
  (Upload-paneel naar boven). Branch is gepusht.

## 5. Open taken / next
1. **De "4e variant" builder** — een UI om zelf registry-groepen aan te vinken →
   live `describe_config`-preview → als spec opslaan → runnen. De backend
   (`describe_config` + spec-validatie) ligt er al klaar voor.
2. **Per-run confluence in de run-detail** — `describe` zit nu alleen in de
   library; ook in de run-opslag zetten zodat elke historische run z'n gates toont.
3. **Edge-jacht via de interface** — Silver Bullet per kill-zone (bijv. NY-AM
   only) door de 3 lenzen halen; idem voor de nieuwe entry-families.

## 6. Werkafspraken
- Ontwikkelen/committen/pushen op **`claude/middleware-setup-guide-afhvtk`**.
- Pine is 4-spaties-indent, geen tabs (niet relevant voor bck, wel repo-breed).
- Nooit secrets committen (`.env`, `accounts.yaml`, `*.db` zijn git-ignored).
- Na een pull op de VPS: **`sudo systemctl restart mex-lab`** + hard-refresh
  (Ctrl+Shift+R) i.v.m. browsercache.
