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
  tekenpoort     een box.new/label.new onder een `[1]`-edge-detector. Met
                 calc_on_order_fills draait zo'n blok meer dan een keer per bar en
                 staat de tekening dubbel; de eerste handle raakt onbereikbaar.

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
    findings += check_input_defaults(path)
    findings += check_draw_guards(path)

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
    # Waar iets voor het EERST wordt gedeclareerd. `decl` hierboven is een verzameling over
    # het hele bestand, dus die ziet gebruik-voor-declaratie niet -- en precies dat gaf op
    # 03-11 CE10272 op `acctStarted`: de lint zei "ok" en TradingView weigerde het script.
    # Dit is de derde keer dat een poort een ORDENING of EIGENSCHAP mist terwijl hij op
    # aanwezigheid toetst. Pine leest een script van boven naar beneden, dus een naam die
    # lager wordt gedeclareerd dan hij wordt gelezen bestaat op dat punt niet.
    declline = {}
    def _note(name, n):
        if name and name not in BUILTIN:
            declline.setdefault(name, n)
    for n, l in enumerate(C, 1):
        # ⚠️ ALLEEN aan het begin van een statement. De verzameling hierboven staat ook
        # declaraties na "(" of "," toe voor tuple-destructuring, en dát matcht óók een
        # NAMED ARGUMENT: `size=size.tiny` las `size` als declaratie. Voor een verzameling
        # is over-verzamelen onschuldig (het onderdrukt alleen waarschuwingen), voor een
        # ORDENINGSTEST is het fataal -- de eerste versie van deze check meldde daardoor
        # 36 vals-positieven en nul goede bestanden.
        m = re.match(r'\s*(?:var\s+|varip\s+)?'
                     r'(?:(?:bool|int|float|string|color|line|label|box|table|array<[^>]*>|matrix<[^>]*>)(?:\[\])?\s+)?'
                     r'([A-Za-z_]\w*)\s*(?::=|=(?!=))', l)
        if m:
            _note(m.group(1), n)
        m = re.match(r'\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>', l)
        if m:
            _note(m.group(1), n)
            for a in m.group(2).split(','):
                a = a.strip().split()[-1] if a.strip() else ''
                if a: _note(re.sub(r'[^\w].*', '', a), n)
        m = re.match(r'\s*for\s+(?:\[([^\]]*)\]|([A-Za-z_]\w*))', l)
        if m:
            for a in (m.group(1) or m.group(2) or '').split(','):
                _note(a.strip(), n)
        m = re.match(r'\s*\[([A-Za-z_0-9,\s]+)\]\s*=', l)
        if m:
            for a in m.group(1).split(','): _note(a.strip(), n)

    early = {}
    for n, l in enumerate(C, 1):
        l2 = re.sub(r'\b[A-Za-z_]\w*\s*=(?!=)', '', l)
        l2 = re.sub(r'\.[A-Za-z_]\w*', '', l2)
        for m in re.finditer(r'(?<![\w.])([a-zA-Z_]\w*)', l2):
            w = m.group(1)
            if w.isupper() or w not in declline:
                continue
            if n < declline[w]:
                early.setdefault(w, (n, declline[w]))
    for w, (use, dec) in sorted(early.items(), key=lambda x: x[1][0]):
        findings.append(f"r{use}: {w} wordt gelezen maar pas op r{dec} gedeclareerd "
                        f"-- Pine leest van boven naar beneden, dit is CE10272")

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


def check_input_defaults(path):
    """De DEFAULT van een `input.*` moet een CONST zijn, en dat is een echte val.

    `input.time(timestamp("America/New_York", 2099, 1, 1, 0, 0, 0), ...)` ziet correct uit
    en compileert NIET: de meerargument-vorm van `timestamp` levert een `simple int` terwijl
    de default een `const int` moet zijn (CE10123, *"call timestamp (simple int) ... const
    int expected"*). Alleen de vorm met ÉÉN stringliteraal -- `timestamp("2099-01-01T00:00:00-05:00")`
    -- is const.

    Dit is drie keer langs groene poorten gekomen: op 08-10 in `validFrom`/`validUntil`, een
    tweede keer in dezelfde release, en op 03-11 opnieuw in de nieuwe `Account start`-input.
    De poorten die er toen al waren toetsten op letterlijke regels, dus ze zagen de
    EIGENSCHAP niet. Daarom staat de regel hier en niet als een verboden tekst.

    ⚠️ Niet elke aanroep als default is fout, en dat is bewust zo gelaten:
    `input.color(color.new(#2F80ED, 88), ...)` is geldig Pine, want `color.new` met
    literalen is const-foldbaar. Een poort die daarop afgaat staat onterecht rood, en
    daar went men aan -- precies hoe de gedeelde-blok-poort maanden niets meer zei.
    Daarom: `timestamp` alleen in de enkele-stringvorm, een korte lijst bekende
    const-foldbare aanroepen mag, en al het ONBEKENDE wordt gemeld. Zo blijft de melding
    iets betekenen en groeit de lijst alleen met iets wat iemand heeft nagekeken.
    """
    CONST_FOLDABLE = ("color.new", "color.rgb")
    raw = open(path).read().split("\n")
    findings = []
    for n, line in enumerate(raw, 1):
        if line.lstrip().startswith("//"):
            continue
        m = re.search(r"input\.[a-z_]+\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\(", line)
        if m is None:
            continue
        call = m.group(1)
        if call == "timestamp":
            # Alleen de vorm met precies EEN stringliteraal is const.
            if not re.search(r'input\.[a-z_]+\(\s*timestamp\(\s*"[^"]*"\s*\)', line):
                findings.append(f"r{n}: de default is de meerargument-vorm van timestamp() en "
                                f"dus een simple int, geen const -- gebruik "
                                f"timestamp(\"JJJJ-MM-DDThh:mm:ss\u00b1uu:mm\"). Dit geeft CE10123.")
        elif call not in CONST_FOLDABLE:
            findings.append(f"r{n}: de default van deze input is {call}(...). Dat is niet in de "
                            f"lijst const-foldbare aanroepen ({', '.join(CONST_FOLDABLE)}), dus "
                            f"controleer of hij compileert en zet hem er dan bij.")
    return findings

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


def check_draw_guards(path):
    """Een tekening mag niet onder een edge-detector hangen die op de VORIGE BAR meet.

    Dit is de poort op de fout die drie reparatierondes overleefde (D-161, D-162 en de
    patch van 04-11, alle drie op de tekeningen van EL TESORO). Niemand keek naar HOE
    VAAK het blok draaide.

    `calc_on_order_fills=true` laat het script binnen dezelfde bar OPNIEUW lopen zodra
    een order vult. `x[1]` is de stand van de VORIGE BAR, dus een conditie als
    `strategy.closedtrades > nz(strategy.closedtrades[1], 0)` blijft waar bij elke
    volgende uitvoering van diezelfde bar -- ook die op barclose. Een `box.new()` of
    `label.new()` daaronder wordt dan twee keer uitgevoerd: de tekst staat dubbel over
    zichzelf, en bij een aanmaak raak je de EERSTE handle kwijt -- die wordt nooit meer
    gegroeid, nooit hertekend, nooit opgeruimd en komt niet in de tekenhistorie. Dat is
    een lek buiten de drawing-begroting van 500, en het is onzichtbaar voor een
    zelfcontrole die naar de overgebleven handle kijkt.

    De twee vormen die WEL goed zijn, en beide staan in deze vloot:
      · `barstate.isconfirmed` in de conditie -- precies een uitvoering per bar
        (zo doen de tijdvenster-boxen, de FVG-boxen en de event-labels het);
      · een teller-latch in een `var` in plaats van `[1]` (`lastClosedSeen`,
        `dexClosedSeen`, `tdSeen`, `drawMadeNo`, `drawShutSeen`).

    De check kijkt per tekening omhoog naar het dichtstbijzijnde `if` op kolom 0 en
    beoordeelt die conditie. Een geneste `if` eronder erft de poort, dus de buitenste is
    de juiste om te lezen; en een tekening die buiten elk `if` staat draait per definitie
    elke uitvoering en is dus niet door een edge-detector gepoort.

    EEN INDIRECTIE DIEP, en dat is geen extraatje: in de echte fout stond `[1]` NIET in de
    conditie. Er stond `if drawTradeShut`, en de `[1]` zat in de definitie van die vlag
    honderden regels eerder. Een poort die alleen de conditie leest had de fout die hij
    moet pakken niet gepakt -- dat is hier eerst gebeurd en daarna gerepareerd. Dus worden
    de vlagdefinities op kolom 0 eerst ingelezen, en geldt een conditie die zo'n vlag
    noemt als een edge-detector op de vorige bar.
    """
    # `pine/history/**` doet niet mee, om dezelfde reden als bij check_shared: dat is
    # bevroren historie die per definitie achterloopt. De v6.9.5-familie heeft deze fout
    # OOK -- het exit-labelblok hing daar op `flatNow and nz(posSize[1]) != 0` -- en dat is
    # het bewijs dat de klasse zo oud is als de vloot. Maar die bestanden worden niet meer
    # gewijzigd, dus zouden ze deze poort permanent rood houden, en dan leest niemand hem.
    if "/history/" in str(path).replace("\\", "/"):
        return []
    lines = open(path).read().split("\n")

    # Eerste doorloop: welke vlaggen op kolom 0 zijn zelf een edge-detector op de vorige
    # bar? `bool x = ... [1] ...` en de vorm zonder type. Een `var`-declaratie is per
    # definitie geen edge-detector en doet niet mee.
    edge = {}
    for n, raw in enumerate(lines, 1):
        if raw[:1] in (" ", "\t") or raw.lstrip().startswith("//") or raw.startswith("var"):
            continue
        m = re.match(r'(?:bool\s+)?([a-zA-Z_]\w*)\s*=\s*(.+)$', code(raw))
        if m and "[1]" in m.group(2):
            edge[m.group(1)] = n

    def edge_src(cond):
        """De regel waar deze conditie zijn vorige-bar-meting vandaan haalt, of None."""
        if "[1]" in cond:
            return "deze conditie"
        for w in re.findall(r'(?<![\w.])([a-zA-Z_]\w*)', cond):
            if w in edge:
                return f"`{w}` (r{edge[w]})"
        return None

    findings = []
    guard = None          # (regelnummer, conditie) van het laatste `if` op kolom 0
    for n, raw in enumerate(lines, 1):
        if raw.lstrip().startswith("//") or not raw.strip():
            continue
        if raw[:1] not in (" ", "\t"):
            m = re.match(r'if\s+(.*)$', raw)
            guard = (n, m.group(1)) if m else None
            if not m:
                continue
        if guard is None:
            continue
        gn, cond = guard
        if "barstate.isconfirmed" in cond:
            continue
        src = edge_src(code(cond))
        if src is None:
            continue
        for fn in ("box.new", "label.new", "line.new", "polyline.new", "table.new"):
            if fn + "(" in code(raw):
                findings.append(
                    f"r{n}: {fn}() hangt op de `if` van r{gn}, en die meet op de VORIGE BAR "
                    f"via {src}. Met calc_on_order_fills draait dat blok meer dan een keer "
                    f"per bar, dus staat de tekening dubbel en raakt de eerste handle "
                    f"onbereikbaar -- gebruik een teller-latch in een `var`, of zet "
                    f"`barstate.isconfirmed` in de conditie")
                break
    return findings


def check_shared(paths):
    """Meld elk gedeeld blok dat niet in alle bestanden dezelfde checksum heeft.

    Alleen de LEVENDE STRATEGIEËN doen mee. Twee uitsluitingen, beide met een reden:
    `pine/history/**` is bevroren historie en moet per definitie achterlopen -- meerekenen
    betekent dat elke correctie op de vloot hier een nieuwe variant oplevert. En een
    indicator heeft geen executieblok, dus "ONTBREEKT" is daar geen bevinding maar de
    normale toestand. Die twee hielden deze poort permanent rood, en een poort die altijd
    rood staat leest niemand meer. Hij gaat erover of de dertien strategieën ONDERLING
    gelijk zijn -- en dat is precies wat hij moet bewaken.
    """
    import hashlib
    paths = [p for p in paths if "/history/" not in p.replace("\\", "/")
             and "strategy(" in open(p).read()]
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
        # Geen dropdown. Dan is er een constante, of maar een tak: kijk welke.
        c = re.search(r'string cvdEngine\s*=\s*"([^"]+)"', src)
        if c is not None:
            return "proxy" if c.group(1).startswith("Research") else "tv-delta"
        return "proxy" if re.search(r'bullDirOk\s*:?=\s*proxyDir', src) else "tv-delta"
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
