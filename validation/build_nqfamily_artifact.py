#!/usr/bin/env python3
"""Bouwt het verdict-rapport uit de twee resultaatbestanden.

Gates komen uit de pre-registratie en worden hier alleen toegepast, niet
bijgesteld. Waar data ontbreekt is de uitkomst ONBESLIST — nooit stilzwijgend
een PASS of een FAIL.
"""
from __future__ import annotations
import html, json, pathlib

BASE = json.load(open("validation/NQFAMILY_results_20260811.json"))
FIX = json.load(open("validation/NQFAMILY_results_cvdfix_20260811.json"))

STRATS = ["EL_PATRON", "EL_DORADO", "EL_MATADOR"]
NAMES = {"EL_PATRON": "ΞL PΛTRON", "EL_DORADO": "ΞL DORΛDO", "EL_MATADOR": "ΞL MΛTΛDOR"}
KIND = {"EL_PATRON": "PA · banked per breach", "EL_DORADO": "PA · banked per breach",
        "EL_MATADOR": "Eval · pass-rate"}
SLOTS = ["NQ", "MNQ", "ES", "GC", "YM"]
TAINT = {"NQ": "verbruikt", "MNQ": "verbruikt", "ES": "vers", "GC": "vers", "YM": "vers"}


def cell(s, slot):
    """Beste beschikbare meting: de cvd-fix wint van de nul-delta-run."""
    k = f"{s}|{slot}"
    if k in FIX:
        d = dict(FIX[k]); d["source"] = "cvd"; return d
    d = dict(BASE.get(k, {})); d["source"] = "norm"; return d


def val(d, key):
    o = d.get(key)
    return o.get("value") if isinstance(o, dict) else None


def gates(s, slot):
    """Loopt de gates in volgorde en stopt bij de eerste die niet haalt."""
    d = cell(s, slot)
    if not d:
        return [], "geen data"
    zero_delta = d["source"] == "norm" and slot in ("ES", "GC", "YM") \
        and s in ("EL_PATRON", "EL_DORADO")
    res = []

    if zero_delta:
        res.append(("S3", "onbeslist", "CVD-filter aan, maar de reeks heeft geen volume-delta"))
        return res, "S3"

    n_is = d.get("is_research", {}).get("trades", 0)
    res.append(("S3", "pass" if n_is >= 100 else "fail",
                f"{n_is:,} IS-trades, kosten aan".replace(",", ".")))
    if n_is < 100:
        return res, "S3"

    pf = d.get("recent12m", {}).get("pf", 0)
    ok4 = pf >= 1.2
    res.append(("S4", "pass" if ok4 else "fail", f"PF recente 12m = {pf}  (gate ≥ 1,20)"))
    if not ok4:
        return res, "S4"

    o_is, o_oos = val(d, "obj_is"), val(d, "obj_oos")
    wfe = (o_oos / o_is) if (o_is and o_oos is not None) else None
    res.append(("S5", "pass" if (wfe or 0) >= .5 else "fail",
                f"WFE = {wfe:.2f}" if wfe is not None else "niet te berekenen"))
    if (wfe or 0) < .5:
        return res, "S5"
    return res, "S7"


def stress_pct(s, slot):
    d = cell(s, slot)
    o, st = val(d, "obj_oos"), val(d, "stress_oos")
    if o in (None, 0) or st is None:
        return None
    return 100 * (st - o) / o


ST = {"pass": "ok", "fail": "no", "onbeslist": "un"}
LABEL = {"pass": "PASS", "fail": "FAIL", "onbeslist": "ONBESLIST"}

rows = []
for s in STRATS:
    for slot in SLOTS:
        d = cell(s, slot)
        g, stopped = gates(s, slot)
        rows.append(dict(strat=s, slot=slot, d=d, gates=g, stopped=stopped,
                         stress=stress_pct(s, slot)))


def esc(x):
    return html.escape(str(x))


# ---------------------------------------------------------------- matrix ----
matrix = []
for s in STRATS:
    tds = []
    for slot in SLOTS:
        r = next(x for x in rows if x["strat"] == s and x["slot"] == slot)
        last = r["gates"][-1] if r["gates"] else ("—", "onbeslist", "geen data")
        state = ST[last[1]]
        d = r["d"]
        obj = val(d, "obj_oos")
        pf = d.get("recent12m", {}).get("pf")
        detail = f"PF {pf}" if pf else "—"
        tds.append(f'''<td class="cell {state}">
          <div class="gate">{esc(last[0])}</div>
          <div class="state">{esc(LABEL[last[1]])}</div>
          <div class="det">{esc(detail)}</div></td>''')
    matrix.append(f'<tr><th scope="row"><span class="sname">{esc(NAMES[s])}</span>'
                  f'<span class="skind">{esc(KIND[s])}</span></th>{"".join(tds)}</tr>')

# ------------------------------------------------------------ detailtabel ----
det = []
for r in rows:
    d = r["d"]
    # Onbesliste cellen (geen volume-delta) tonen streepjes: nullen zouden lezen
    # als "getest en niets gevonden", en dat is precies niet wat er gebeurd is.
    if r["stopped"] == "S3" and r["gates"] and r["gates"][0][1] == "onbeslist":
        det.append(f'''<tr class="undec">
          <td>{esc(NAMES[r["strat"]])}</td><td class="mono">{esc(r["slot"])}</td>
          <td class="mono t-vers">vers</td>
          <td class="mono num" colspan="8">geen volume-delta in de reeks — niet te beoordelen</td>
        </tr>''')
        continue
    isr, oosr = d.get("is_research", {}), d.get("oos_research", {})
    ys = d.get("years", {})
    stress = r["stress"]
    det.append(f'''<tr>
      <td>{esc(NAMES[r["strat"]])}</td><td class="mono">{esc(r["slot"])}</td>
      <td class="mono t-{TAINT[r["slot"]]}">{esc(TAINT[r["slot"]])}</td>
      <td class="mono num">{isr.get("trades", 0):,}</td>
      <td class="mono num">{isr.get("pf", 0)}</td>
      <td class="mono num">{"·".join(str(ys.get(y, {}).get("pf", "—")) for y in ("Y1", "Y2", "Y3"))}</td>
      <td class="mono num">{d.get("recent12m", {}).get("pf", "—")}</td>
      <td class="mono num">{oosr.get("trades", 0):,}</td>
      <td class="mono num">{val(d, "obj_is") if val(d, "obj_is") is not None else "—"}</td>
      <td class="mono num">{val(d, "obj_oos") if val(d, "obj_oos") is not None else "—"}</td>
      <td class="mono num {'neg' if (stress or 0) < -50 else ''}">{f"{stress:+.0f}%" if stress is not None else "—"}</td>
    </tr>'''.replace(",", "."))

# ------------------------------------------------------------ perturbatie ----
pert = BASE.get("pert_YM_IS", {})
prows = []
for s in STRATS:
    base_v = (pert.get(f"{s}|basis") or {}).get("value")
    cells = []
    for v in ("gap_-20%", "gap_+20%", "stop_-20%", "stop_+20%", "cvd_flip"):
        x = (pert.get(f"{s}|{v}") or {}).get("value")
        if x is None or base_v in (None, 0):
            cells.append('<td class="mono num">—</td>')
        else:
            dp = 100 * (x - base_v) / base_v
            cls = "neg" if dp < -30 else ""
            cells.append(f'<td class="mono num {cls}">{x} <span class="dp">{dp:+.0f}%</span></td>')
    prows.append(f'<tr><td>{esc(NAMES[s])}</td>'
                 f'<td class="mono num">{base_v if base_v is not None else "—"}</td>'
                 f'{"".join(cells)}</tr>')

TPL = pathlib.Path("validation/artifact_template.html").read_text(encoding="utf-8")
out = (TPL.replace("<!--MATRIX-->", "\n".join(matrix))
          .replace("<!--DETAIL-->", "\n".join(det))
          .replace("<!--PERT-->", "\n".join(prows)))
pathlib.Path("validation/nqfamily_verdict.html").write_text(out, encoding="utf-8")
print("geschreven: validation/nqfamily_verdict.html")
