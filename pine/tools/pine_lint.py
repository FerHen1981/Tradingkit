#!/usr/bin/env python3
"""Statische controle op Pine v6-bronnen, vóór het plakken in TradingView.

Ontstaan uit de fouten die deze vloot echt heeft gemaakt, niet uit een algemene
lint-wens. Elke check hier hoort bij een compileerfout die we al eens hebben gehad:

  haakjes        CE10016 "Extra closing parenthesis" - blijft over als je een input
                 weghaalt maar zijn ingesprongen `tooltip=`-vervolgregel laat staan.
  verweesd       dezelfde oorzaak, één stap eerder zichtbaar.
  dubbel         "variable already declared" - twee blokken met dezelfde naam, zoals
                 de dode PA-BBWP naast de werkende BBWP uit groep 9.
  ongedeclareerd CE10272 "Undeclared identifier" - een verwijzing die achterblijft
                 nadat de declaratie is verdwenen (barsSinceNotBull, skipMonEarly).
  defaults       input.string met een default die niet in options staat.
  tabs           Pine is inspringgevoelig en accepteert geen tabs.

Gebruik:  python3 pine/tools/pine_lint.py pine/**/*.pine
Exitcode 1 zodra één bestand een bevinding heeft.
"""
import sys, re, glob

BUILTIN = set('''
open high low close volume time time_close hl2 hlc3 ohlc4 hlcc4 bar_index last_bar_index last_bar_time
na nz fixnan true false and or not if else for while var varip switch to by in import as export type method
float int bool string color line label box table array matrix map polyline chart break continue
plot plotshape plotchar plotcandle plotbar plotarrow fill bgcolor barcolor hline alert alertcondition
math str ta request strategy syminfo timeframe barstate session dayofweek dayofmonth month year weekofyear
hour minute second timestamp input indicator library runtime ticker currency display size shape location
style format text xloc yloc extend order position adjustment barmerge lookahead scale timenow
dividends earnings splits linefill TradingView simple series const input_ na_
'''.split())


def code(s):
    """Regel zonder stringliteralen en zonder commentaar."""
    out = []; q = False; i = 0
    while i < len(s):
        c = s[i]
        if q:
            if c == '\\': i += 2; continue
            if c == '"': q = False
            i += 1; continue
        if c == '"': q = True; i += 1; continue
        if c == '/' and i + 1 < len(s) and s[i + 1] == '/': break
        out.append(c); i += 1
    return ''.join(out)


def check(path):
    raw = open(path).read().split('\n')
    C = [code(l) for l in raw]
    findings = []

    bal = 0; neg = []
    for n, l in enumerate(C, 1):
        bal += l.count('(') - l.count(')') + l.count('[') - l.count(']')
        if bal < 0: neg.append(n); bal = 0
    if neg: findings.append(f"haakjes negatief op regel {neg}")
    if bal: findings.append(f"haakjes sluiten niet: eindsaldo {bal}")

    orph = []
    for n in range(1, len(raw)):
        if not re.match(r'^\s+(tooltip|options|display|inline|group|minval|maxval|step|title)\s*=', raw[n]):
            continue
        prev = C[n - 1]
        if prev.rstrip().endswith(','): continue
        if prev.count('(') == prev.count(')'): orph.append(n + 1)
    if orph: findings.append(f"verweesde vervolgregels op {orph}")

    seen = {}; dup = []
    for n, l in enumerate(raw, 1):
        m = re.match(r'^(?:var\s+)?(?:(?:bool|int|float|string|color|line|label|box|table)\s+)?([A-Za-z_]\w*)\s*=[^=]', l)
        if not m: continue
        nm = m.group(1)
        if nm in seen: dup.append((nm, seen[nm], n))
        else: seen[nm] = n
    if dup: findings.append(f"dubbele declaraties {dup}")

    for n, l in enumerate(raw, 1):
        if 'input.string(' not in l: continue
        blkt = l; k = n
        while 'options=' not in blkt and k < len(raw) and raw[k].startswith('     '):
            blkt += raw[k]; k += 1
        d = re.search(r'input\.string\(\s*"([^"]*)"', blkt)
        o = re.search(r'options=\[([^\]]*)\]', blkt)
        if d and o:
            opts = [x.strip().strip('"') for x in o.group(1).split(',')]
            if d.group(1) not in opts:
                findings.append(f"r{n}: input.string default {d.group(1)!r} staat niet in options")

    findings += check_plot_titles(path)

    tabs = [n for n, l in enumerate(raw, 1) if '\t' in l]
    if tabs: findings.append(f"tabs op {tabs}")

    decl = set(BUILTIN)
    for l in C:
        for m in re.finditer(r'(?:^\s*|[,\[(]\s*)(?:var\s+|varip\s+)?'
                             r'(?:(?:bool|int|float|string|color|line|label|box|table|array<[^>]*>|matrix<[^>]*>)(?:\[\])?\s+)?'
                             r'([A-Za-z_]\w*)\s*(?::=|=(?!=))', l):
            decl.add(m.group(1))
        m = re.match(r'\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>', l)
        if m:
            decl.add(m.group(1))
            for a in m.group(2).split(','):
                a = a.strip().split()[-1] if a.strip() else ''
                if a: decl.add(re.sub(r'[^\w].*', '', a))
        m = re.match(r'\s*for\s+(?:\[([^\]]*)\]|([A-Za-z_]\w*))', l)
        if m:
            for a in (m.group(1) or m.group(2) or '').split(','):
                if a.strip(): decl.add(a.strip())
        m = re.search(r'\[([A-Za-z_0-9,\s]+)\]\s*=', l)
        if m:
            for a in m.group(1).split(','): decl.add(a.strip())
    undecl = {}
    for n, l in enumerate(C, 1):
        l2 = re.sub(r'\b[A-Za-z_]\w*\s*=(?!=)', '', l)
        l2 = re.sub(r'\.[A-Za-z_]\w*', '', l2)
        for m in re.finditer(r'(?<![\w.])([a-zA-Z_]\w*)', l2):
            w = m.group(1)
            if w in decl or w.isupper(): continue
            undecl.setdefault(w, n)
    if undecl:
        findings.append("ongedeclareerd: " + ", ".join(f"{k} (r{v})" for k, v in sorted(undecl.items(), key=lambda x: x[1])))

    return findings


# Blokken die in de hele vloot letterlijk gelijk horen te zijn. Zodra er twee versies
# van bestaan is dat stille drift in het live executiepad -- precies de klasse fout die
# D-44 zichtbaar maakte (breakeven_offset ontbrak, in alle scripts tegelijk, jarenlang).
# Deze check is het goedkope deel van D-51: de duplicatie blijft, maar hij kan niet meer
# ongemerkt uiteenlopen.
SHARED_BLOCKS = {
    "f_pmtJSON": ("f_pmtJSON(", "multiple_accounts"),
    "middleware-alert": ('    if useMiddleware', '}", alert.freq_once_per_bar)'),
}


# CE10123: de titel van plot/plotshape/fill/bgcolor moet een CONST string zijn. Een titel
# als "EMA " + str.tostring(emaLen) is simple, niet const, en dat compileert niet -- maar je
# ziet het pas in TradingView. De titel is het tweede positionele argument, of title=.
_PLOTF = ("plot", "plotshape", "plotchar", "plotcandle", "plotbar", "plotarrow", "fill", "bgcolor", "barcolor", "hline")


def check_plot_titles(path):
    src = open(path).read()
    findings = []
    for m in re.finditer(r'(?<![\w.])(' + "|".join(_PLOTF) + r')\(', src):
        i = m.end() - 1
        depth = 0; q = False; k = i; args = []; cur = ""
        while k < len(src):
            c = src[k]
            if q:
                cur += c
                if c == '\\':
                    cur += src[k + 1]; k += 2; continue
                if c == '"': q = False
                k += 1; continue
            if c == '"':
                q = True; cur += c; k += 1; continue
            if c in '([':
                depth += 1
                if depth == 1:
                    k += 1; continue
            elif c in ')]':
                depth -= 1
                if depth == 0:
                    args.append(cur); break
            if c == ',' and depth == 1:
                args.append(cur); cur = ""; k += 1; continue
            cur += c
            k += 1
        title = None
        for a in args:
            if a.strip().startswith("title="):
                title = a.split("=", 1)[1]
        if title is None and m.group(1) in ("plot", "plotshape", "plotchar") and len(args) > 1:
            title = args[1]
        if title is None:
            continue
        t = title.strip()
        if not t.startswith('"'):
            continue                      # een variabele kan best const zijn; niet te zien
        if "+" in re.sub(r'"[^"]*"', "", t):
            ln = src[:m.start()].count("\n") + 1
            findings.append(f"r{ln}: {m.group(1)}() titel is samengesteld - moet een const string zijn (CE10123)")
    return findings


def check_shared(paths):
    """Meld elk gedeeld blok dat niet in alle bestanden dezelfde checksum heeft."""
    import hashlib
    findings = []
    for label, (start, end) in SHARED_BLOCKS.items():
        buckets = {}
        for p in paths:
            s = open(p).read()
            try:
                a = s.index(start)
                b = s.index("\n", s.index(end, a))
            except ValueError:
                buckets.setdefault("ONTBREEKT", []).append(p)
                continue
            buckets.setdefault(hashlib.md5(s[a:b].encode()).hexdigest()[:10], []).append(p)
        if len(buckets) > 1:
            findings.append(f"{label}: {len(buckets)} varianten -> " + " | ".join(
                f"{h} ({len(v)}x: {', '.join(x.split('/')[-1] for x in sorted(v)[:3])}"
                + (", ..." if len(v) > 3 else "") + ")" for h, v in sorted(buckets.items())))
        else:
            h = next(iter(buckets))
            print(f"gedeeld {label:18} {h}  identiek in {len(paths)} bestanden")
    return findings


# D-09 legt vast dat de canonieke CVD de deterministische OHLCV-polariteitsproxy is en
# NIET ta.requestVolumeDelta. Grep op de functienaam meet dat NIET: die naam staat ook in
# de commentaarregel die de regel uitlegt, en in de niet-default tak van de dubbele motor.
# Wat telt is wat `bullDirOk` op de DEFAULT-stand voedt. Deze check meet dat.
#
# PATRON en TESORO staan bewust op de TV-motor (besluit Ferry 25-08, optie C): dat is wat
# ze altijd draaiden, en omzetten is een onderzoeksronde. Ze staan hier als uitzondering
# zodat de afwijking zichtbaar blijft in plaats van te verdwijnen.
NON_CANONICAL_BY_DESIGN = {"MEX_EL_PATRON_MGC_AGG_EOD_v1_0_0.pine",
                           "MEX_EL_TESORO_MGC_CON_EOD_v1_0_0.pine"}


def effective_delta_engine(src: str) -> str:
    """Welke motor voedt bullDirOk als je niets aan de inputs verandert?"""
    if "bullDirOk" not in src and "cvdEngine" not in src:
        return "n/a"          # dit bestand heeft geen delta-motor
    m = re.search(r'cvdEngine\s*=\s*input\.string\("([^"]+)"', src)
    if m is None:
        # Geen dropdown: er is maar een tak. Kijk welke.
        return "proxy" if re.search(r'^bool bullDirOk = proxyDir', src, re.M) else "tv-delta"
    return "proxy" if m.group(1).startswith("Research") else "tv-delta"


def check_delta_engines(paths):
    findings = []
    for p in paths:
        eng = effective_delta_engine(open(p).read())
        name = p.split("/")[-1]
        if eng in ("proxy", "n/a"):
            continue
        if name in NON_CANONICAL_BY_DESIGN:
            print(f"delta   {name:44} tv-delta (bewust, besluit Ferry 25-08)")
        else:
            findings.append(f"{name}: default delta-motor is ta.requestVolumeDelta, "
                            f"niet de canonieke OHLCV-proxy (D-09)")
    return findings


def main(argv):
    paths = []
    for a in argv or ['pine/**/*.pine']:
        paths += sorted(glob.glob(a, recursive=True))
    if not paths:
        print("geen bestanden"); return 1
    bad = 0
    shared = check_shared(paths) if len(paths) > 1 else []
    shared += check_delta_engines(paths)
    for f in shared:
        bad += 1
        print(f"FOUT  gedeeld blok\n        {f}")
    for p in paths:
        f = check(p)
        if f:
            bad += 1
            print(f"FOUT  {p}")
            for x in f: print(f"        {x}")
        else:
            print(f"ok    {p}")
    print(f"\n{len(paths)} bestanden, {bad} met bevindingen")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
