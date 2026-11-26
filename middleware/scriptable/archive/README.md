# Scriptable widget archive

Widget-scripts die niet meer op Ferry's telefoon draaien, maar die we
bewust niet weggooien — bewijs wordt niet vernietigd (`validation/`-regel,
zelfde geest).

## `mex-fleet-widget.js`

**Vervangen door `middleware/scriptable/MEX_Today.js` op 28-09-2026, D-105.**

Dit script kende vier standen `all` · `funded` · `eval` · `week` met een
per-stack layout. Op 18-09 kreeg het onder D-76 een `Today`-rij per stack
en onder D-74 een eval-stand die de bedragen door 50k-genormaliseerde
tellers verving.

**Wat er misging:** Ferry draaide op zijn telefoon een ander script —
`MEX_Today.js` — met vier standen `today` · `yesterday` · `week` · `total`
en een eigen `Eval / Funded`-splitrij. Beide lazen `https://app.mex-traders.com/api/widget`
maar renderden anders. Zolang niemand had vastgesteld welk script waar
draaide, landden onze wijzigingen in het verkeerde bestand en bereikten
Ferry's toestel niet.

**Waarom bewaren:** de fixes in de commits die dit bestand raakten —
`D-76: Today per stack` (`c12d305`) en `D-74 middleware-helft: widget
eval-stand` (`1ed07a6`) — dragen redeneringen en tests die op de nieuwe
bron toepasbaar zijn. Bij twijfel over waarom een render-keuze staat zoals
hij staat, hoort de git-log van dit bestand nog steeds tot de bron.

Do NOT copy this file back to `middleware/scriptable/`. De actieve bron is
`middleware/scriptable/MEX_Today.js`.
