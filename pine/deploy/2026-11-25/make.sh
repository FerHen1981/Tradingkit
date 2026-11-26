#!/usr/bin/env bash
# Bouwt de deploy-kopieën uit de basisscripts in pine/. Alleen input-defaults wijzigen; basis blijft bevroren.
set -euo pipefail
cd "$(dirname "$0")/../../.."
T=pine/MEX_EL_TORO_NQ_HF_INTRA_v1_0_0.pine; S=pine/MEX_EL_TESORO_MGC_CON_EOD_v1_0_0.pine; R=pine/MEX_EL_REY_MNQ_PROD_EOD_v1_0_0.pine
D=pine/deploy/2026-11-25
toro() { # $1=tp $2=preset $3=maxWinStreak $4=out
  sed -e 's/^contractSize       = input.float(7, "Fixed Qty"/contractSize       = input.float(4, "Fixed Qty"/' \
      -e 's/^gapMinSize   = input.float(4,  "Min FVG Size (units)"/gapMinSize   = input.float(19, "Min FVG Size (units)"/' \
      -e 's/^gapMaxSize   = input.float(12, "Max FVG Size (units)"/gapMaxSize   = input.float(27, "Max FVG Size (units)"/' \
      -e 's/^confirmBarsIn = input.int(2, "Confirmation window (bars)"/confirmBarsIn = input.int(4, "Confirmation window (bars)"/' \
      -e "s/^tpSize  = input.float(90, \"Take Profit (units, Fixed mode)\"/tpSize  = input.float($1, \"Take Profit (units, Fixed mode)\"/" \
      -e 's/^ddModel       = input.string("Intraday", "Drawdown Model"/ddModel       = input.string("EOD", "Drawdown Model"/' \
      -e 's/^enableDailyLossLimit = input.bool(true, "Owner DLL - enable"/enableDailyLossLimit = input.bool(false, "Owner DLL - enable"/' \
      -e 's/^useFirmPreset = input.bool(false, "Use firm preset/useFirmPreset = input.bool(true, "Use firm preset/' \
      -e "s/^firmPreset    = input.string(\"apex_50k_intraday_eval\", \"Firm program\"/firmPreset    = input.string(\"$2\", \"Firm program\"/" \
      -e "s/^maxWinStreak         = input.int(0, \"Max winsten op rij per dag (0 = uit)\"/maxWinStreak         = input.int($3, \"Max winsten op rij per dag (0 = uit)\"/" "$T" > "$D/$4"; }
toro 122 fundednext_50k_rapid_eval 0 EL_TORO_NQ_EVAL_4c_TP122_fundednext.pine
toro 122 topstep_50k_eval          1 EL_TORO_NQ_EVAL_4c_TP122_topstep.pine
toro 155 fundednext_50k_rapid_eval 0 EL_TORO_NQ_EVAL_4c_TP155_fundednext.pine
toro 155 topstep_50k_eval          1 EL_TORO_NQ_EVAL_4c_TP155_topstep.pine
tes() { # $1=qty $2=preset-or-LIVE $3=tp $4=out
  if [ "$2" = LIVE ]; then PRE='s/^$NOOP$//'; else PRE="s/^firmPreset    = input.string(\"apex_50k_legacy_pa\", \"Firm program\"/firmPreset    = input.string(\"$2\", \"Firm program\"/"; fi
  sed -e "s/^contractSize       = input.float(1, \"Fixed Qty\"/contractSize       = input.float($1, \"Fixed Qty\"/" -e "$PRE" \
      -e "s/^tpSize  = input.float(85, \"Take Profit (units, Fixed mode)\"/tpSize  = input.float($3, \"Take Profit (units, Fixed mode)\"/" "$S" > "$D/$4"; }
tes 2 fundednext_50k_rapid_pa 85 EL_TESORO_MGC_FUNDED_2c_fundednext.pine
tes 2 topstep_50k_xfa         85 EL_TESORO_MGC_FUNDED_2c_topstep.pine
tes 1 LIVE                    120 EL_TESORO_MGC_LIVE_1c_TP120.pine
live() { python3 - "$1" <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
for a,b in [('ddModel       = input.string("Intraday", "Drawdown Model"','ddModel       = input.string("EOD", "Drawdown Model"'),
            ('acctTrailDD   = input.float(2000, "Trailing Drawdown ($)"','acctTrailDD   = input.float(3000, "Trailing Drawdown ($)"'),
            ('acctDLL       = input.float(1000, "PA Daily Loss Limit ($)"','acctDLL       = input.float(3000, "PA Daily Loss Limit ($)"'),
            ('consistencyPct= input.float(50, "Consistency rule (%)"','consistencyPct= input.float(100, "Consistency rule (%)"'),
            ('useFirmPreset = input.bool(true, "Use firm preset','useFirmPreset = input.bool(false, "Use firm preset')]:
    assert s.count(a)==1, (p,a); s=s.replace(a,b)
open(p,'w').write(s)
PY
}
live "$D/EL_TESORO_MGC_LIVE_1c_TP120.pine"
sed -e 's/^contractSize       = input.float(6, "Fixed Qty"/contractSize       = input.float(2, "Fixed Qty"/' "$R" > "$D/EL_REY_MNQ_LIVE_2c.pine"; live "$D/EL_REY_MNQ_LIVE_2c.pine"
rm -f "$D/EL_TESORO_MGC_FUNDED_2c.pine"
echo "gebouwd: $(ls $D/*.pine | wc -l) bestanden"
