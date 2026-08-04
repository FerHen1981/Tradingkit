# PineConnector (MT4/5) alert routing — integration guide

Adds a **PineConnector** destination to the MEX scripts so entries/exits fire the
PineConnector alert syntax, letting the MT4/5 EA execute on spot FX / CFD (e.g.
**FTMO**). This is the automation bridge for the non-futures leg.

You don't need to `import` the (unpublished) library — the ~12 lines below inline
exactly what these scripts need. Drop them in, wire the two hooks, done.

> Compile-note: this environment can't compile Pine. Paste any editor error back
> and I'll fix it. Recommended: bake this into the next version (v6.8.10/v6.8.15)
> **after** v6.8.9 is confirmed to compile, so untested changes don't stack.

## 1. Add the routing option

In the alert-destination input, add `"PineConnector"`:
```pine
alertDest = input.string("Off", "Alert destination",
     options=["Off","PMT Tradovate","Discord","Journal","PineConnector"], group=GROUP_EXEC, ...)
```

## 2. Add the PineConnector inputs + helpers (near the EXECUTION section)

```pine
usePC     = alertDest == "PineConnector"
pcLicense = input.string("", "PineConnector License ID", group=GROUP_EXEC)
pcSymbol  = input.string("", "PC broker symbol (blank = chart ticker)", group=GROUP_EXEC,
     tooltip="Your broker's exact symbol, e.g. EURUSD, GBPUSD.a, XAUUSD. Blank uses the chart ticker.")
pcRiskPct = input.float(0.5, "PC risk % of balance per trade", minval=0.01, group=GROUP_EXEC,
     tooltip="FTMO-style sizing: the EA computes lots so a stop-out loses this % of balance. Respects prop risk rules automatically.")
pcTrailPips = input.float(0, "PC trailing distance (pips, 0=off)", minval=0, group=GROUP_EXEC)

f_pcSym()  => pcSymbol == "" ? syminfo.ticker : pcSymbol
f_pcPx(float x) => str.tostring(x, format.mintick)
f_pcEntry(bool isLong, float slPx, float tpPx) =>
    string s = pcLicense + "," + (isLong ? "long" : "short") + "," + f_pcSym() +
         ",vol_pct_bal_loss=" + str.tostring(pcRiskPct) +
         ",sl_price=" + f_pcPx(slPx) + ",tp_price=" + f_pcPx(tpPx)
    pcTrailPips > 0 ? s + ",trailtrig=1,traildist=" + str.tostring(pcTrailPips) : s
f_pcSL(float slPx) => pcLicense + ",newsltplong," + f_pcSym() + ",sl_price=" + f_pcPx(slPx)  // (also newsltpshort)
f_pcClose() => pcLicense + ",closelongshort," + f_pcSym()
```

## 3. Wire the two hooks

**A. On fill** — where the script confirms a new position (`if newLong or newShort`
in the POSITION MANAGEMENT block). The bracket (SL+TP) rides with the entry, so
the EA manages the exit itself:
```pine
if usePC and (newLong or newShort)
    alert(f_pcEntry(newLong, curStop, curLimit), alert.freq_once_per_bar)
```

**B. On a forced exit** — the auto-flat / day-halt / account-halt `strategy.close_all`
spots (and the pending-cancel spot). Send a flat command so the EA closes too:
```pine
if usePC
    alert(f_pcClose(), alert.freq_once_per_bar)
```
Add that line next to each `strategy.close_all(...)` and to the limit-expiry
cancel block.

**C. (Optional) BE / trail stop moves** — where `curStop` ratchets in the
position-management block, mirror it to the EA:
```pine
if usePC and posRiskOff        // or when curStop changed
    alert((inLong ? "newsltplong" : "newsltpshort") ..., alert.freq_once_per_bar)
```
Simplest to skip C and let `pcTrailPips` handle trailing broker-side.

## 4. TradingView alert setup

Create ONE alert on the strategy with condition = "alert() function calls only",
message left empty (the script builds the payload), webhook URL =
`https://pineconnector.net/api/webhook` (or your PC endpoint). Set
`alertDest = "PineConnector"`, fill the License ID + broker symbol.

## 5. FTMO / prop notes

- **Sizing:** `vol_pct_bal_loss` sizes lots from the stop distance so a stop-out
  loses exactly `pcRiskPct` of balance — the right primitive for FTMO's daily/
  overall loss limits. (Use `vol_pct_eq_loss` to risk off equity incl. floating.)
- **SL/TP as price** avoids all pip/point ambiguity across brokers.
- **FTMO ≠ Apex.** The account overlay in these scripts models Apex trailing-DD /
  payout ladder — irrelevant on FTMO. For a true FTMO run set `Account Phase =
  Research (none)` (no Apex overlay) and let FTMO's own rules govern; a dedicated
  FTMO overlay (profit target / max daily / max overall) is a separate build.
- **Delta on FX:** auto tick-volume; per the CVD test, turn the Streak off (see
  `docs/forex_delta.md`).
