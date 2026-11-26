# -*- coding: utf-8 -*-
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, KeepTogether, PageBreak)

NAVY  = colors.HexColor("#12263F")
NAVY2 = colors.HexColor("#1E3A5F")
SAND  = colors.HexColor("#F3EDE3")
GOLD  = colors.HexColor("#B8862B")
AZURE = colors.HexColor("#2C6E9B")
ROSE  = colors.HexColor("#9B3A46")
GREY  = colors.HexColor("#5C6672")
LINE  = colors.HexColor("#D8D2C6")

OUT = "/tmp/claude-0/-home-user-Tradingkit/f7df63b5-dbb1-5e06-9686-53e7edb951e9/scratchpad/MEX_Rolverdeling_vloot_2026-08-26.pdf"

ss = getSampleStyleSheet()
def S(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.3, leading=13.4, textColor=NAVY,
                alignment=TA_LEFT, spaceAfter=5)
    base.update(kw)
    return ParagraphStyle(name, **base)

Body   = S("Body")
Lead   = S("Lead", fontSize=10.6, leading=15.4, textColor=NAVY2, spaceAfter=8)
H1     = S("H1", fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=NAVY, spaceBefore=13, spaceAfter=7)
H2     = S("H2", fontName="Helvetica-Bold", fontSize=11.4, leading=14, textColor=GOLD, spaceBefore=11, spaceAfter=4)
H3     = S("H3", fontName="Helvetica-Bold", fontSize=9.6, leading=12.6, textColor=NAVY, spaceBefore=7, spaceAfter=2)
Small  = S("Small", fontSize=8.2, leading=11.4, textColor=GREY)
Cell   = S("Cell", fontSize=8.2, leading=10.8, spaceAfter=0)
CellB  = S("CellB", fontName="Helvetica-Bold", fontSize=8.2, leading=10.8, spaceAfter=0)
CellH  = S("CellH", fontName="Helvetica-Bold", fontSize=8.0, leading=10.4, textColor=colors.white, spaceAfter=0)
Bullet = S("Bullet", leftIndent=10, bulletIndent=1, spaceAfter=3)

def P(t, s=Body):  return Paragraph(t, s)
def bl(items, s=Bullet):
    return [Paragraph(t, s, bulletText="•") for t in items]

def callout(title, body, accent=GOLD, bg=SAND):
    t = Table([[Paragraph(f"<b>{title}</b>", S("cot", fontSize=9.2, leading=12.6, textColor=NAVY, spaceAfter=3))],
               [Paragraph(body, S("cob", fontSize=8.8, leading=12.4, textColor=NAVY2, spaceAfter=0))]],
              colWidths=[168*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),bg),
        ("LINEBEFORE",(0,0),(0,-1),2.2,accent),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,0),7),("BOTTOMPADDING",(0,-1),(-1,-1),7),
        ("TOPPADDING",(0,1),(-1,1),0),("BOTTOMPADDING",(0,0),(-1,0),1),
    ]))
    return t

def table(header, rows, widths, aligns=None):
    data=[[Paragraph(h, CellH) for h in header]]
    for r in rows:
        data.append([Paragraph(c, CellB if i==0 else Cell) for i,c in enumerate(r)])
    t=Table(data, colWidths=widths, repeatRows=1)
    st=[("BACKGROUND",(0,0),(-1,0),NAVY),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LINEBELOW",(0,0),(-1,-1),0.4,LINE),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#FAF8F4")])]
    t.setStyle(TableStyle(st))
    return t

# ---------------------------------------------------------------- page frame
def deco(canv, doc):
    canv.saveState()
    w,h = A4
    canv.setFillColor(NAVY); canv.rect(0, h-13*mm, w, 13*mm, stroke=0, fill=1)
    canv.setFillColor(GOLD); canv.rect(0, h-13.9*mm, w, 0.9*mm, stroke=0, fill=1)
    canv.setFillColor(colors.white); canv.setFont("Helvetica-Bold", 8)
    canv.drawString(21*mm, h-8.6*mm, "MEX TRADERS  ·  Pips and Palm Trees")
    canv.setFont("Helvetica", 8); canv.setFillColor(colors.HexColor("#B9C4D2"))
    canv.drawRightString(w-21*mm, h-8.6*mm, "Rolverdeling van de vloot  ·  26-08-2026")
    canv.setStrokeColor(LINE); canv.setLineWidth(0.4)
    canv.line(21*mm, 14*mm, w-21*mm, 14*mm)
    canv.setFillColor(GREY); canv.setFont("Helvetica", 7.6)
    canv.drawString(21*mm, 10*mm, "Intern · Pine Dev · geen out-of-sample bewijs — zie slot")
    canv.drawRightString(w-21*mm, 10*mm, f"{doc.page}")
    canv.restoreState()

doc = BaseDocTemplate(OUT, pagesize=A4, title="MEX Traders - Rolverdeling van de vloot",
                      author="Pine Dev", subject="Welke strategie heeft doel en komt het beste tot zijn recht",
                      leftMargin=21*mm, rightMargin=21*mm, topMargin=20*mm, bottomMargin=18*mm)
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="n",
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=deco)])

W = doc.width
s=[]

# ============================================================ 1 · TITEL
s.append(Spacer(1,4*mm))
s.append(P("Welke strategie heeft doel", S("T", fontName="Helvetica-Bold", fontSize=25, leading=28, textColor=NAVY, spaceAfter=2)))
s.append(P("en waar komt hij het beste tot zijn recht", S("T2", fontName="Helvetica", fontSize=14.5, leading=18, textColor=GOLD, spaceAfter=10)))
s.append(P("Een rolverdeling over de dertien scripts van de vloot, geschreven op wat er op 26 augustus 2026 "
           "daadwerkelijk gemeten is — en op wat er nadrukkelijk <i>niet</i> gemeten is.", Lead))
s.append(Spacer(1,3*mm))

s.append(callout("Het korte antwoord",
    "Er is op dit moment <b>één engine met een cijfer waar iets op rust: EL MATADOR op MES</b> — $30,59 gebankte "
    "payout per bezette account-dag, eerste payout na 85 dagen, en als enige een gesloten pariteitspoort. "
    "Alle andere payout-cijfers zijn ofwel ongeldig onder een open harde poort, ofwel gemeten op een surrogaat-markt.<br/><br/>"
    "Maar de belangrijkste bevinding gaat niet over de rangorde. <b>Geen enkele engine fundeert een vers account op "
    "zijn bevroren volle contractgrootte.</b> Op één contract fundeert er wél elke engine. Dat verplaatst de vraag van "
    "&quot;welke strategie is de beste?&quot; naar &quot;welke strategie past bij welk account, op welke grootte, in welke fase?&quot; — "
    "en dat is een andere, nuttigere vraag.", GOLD))
s.append(Spacer(1,4*mm))

# ============================================================ 2 · MEETLAT
s.append(P("1 · Waarop we meten", H1))
s.append(P("Niet op profit factor, en niet op totale winst. De meetlat is <b>gebankte payout-dollars per bezette "
           "account-dag</b>, gemeten op de contractgrootte die het account daadwerkelijk overleeft.", Body))
s.append(P("Dat lijkt een detail maar het draait de conclusies om. Een prop-account is geen onbeperkt vat: het kost geld, "
           "het heeft een klok, en het kan breken. Twee engines met een identieke profit factor kunnen ver uiteenlopen "
           "zodra je meeneemt hoeveel dagen ze een account bezet houden voordat er geld uit komt, en hoe vaak ze het "
           "account onderweg opblazen. Account-mechanica kan de rangorde van twee statistisch gelijke engines omdraaien.", Body))
s.append(P("Alles hieronder is daarom uitgedrukt in $/account-dag en in doorlooptijd tot de eerste payout (P1).", Body))

# ============================================================ 3 · SIZING
s.append(P("2 · De muur die voor alle dertien geldt", H1))
s.append(P("Dit is de bevinding met de grootste praktische gevolgen, en de enige die op mechanisme-niveau is vastgesteld: "
           "hij reproduceert over álle engines en is onafhankelijk van welke rangorde er ook uit de meting komt.", Body))
s.extend(bl([
  "Op de <b>bevroren volle contractgrootte breekt elke engine</b> een vers account.",
  "Op <b>één contract fundeert elke engine</b> wél.",
]))
s.append(Spacer(1,2*mm))
s.append(P("Er zijn twee muren, en de eerste die je raakt is niet degene waar meestal over gepraat wordt:", Body))
s.append(Spacer(1,1.5*mm))
s.append(table(
  ["Muur","Bedrag","Waarom hij bindt"],
  [["Trailing drawdown","$2.000","Op een vers account vergrendelt de buffer de floor pas op $2.100. Een verliesreeks van "
    "ongeveer $2.700 breekt het account <i>voordat</i> die vergrendeling er is. Dit is de muur die je als eerste raakt."],
   ["Daily loss limit","$1.000","EL MATADOR met zes MES-contracten en een stop van $150 per contract komt op één slechte "
    "dag uit op −$1.033. Eén dag, en het account is weg."]],
  [30*mm, 20*mm, W-50*mm]))
s.append(Spacer(1,3*mm))
s.append(callout("Waarom dit een ontwerpkeuze is en geen bug",
   "De Pine-bron kán contracten inschalen — <font face='Courier'>derisk</font> en <font face='Courier'>deriskPA</font> "
   "zitten er gewoon in. De <i>bevroren configuratie</i> gebruikt ze alleen niet. Er ligt dus een open ontwerpkeuze: "
   "start klein en schaal op naarmate de buffer groeit, of koppel de contractgrootte aan de accountfase. "
   "Zolang die keuze niet gemaakt is, is één contract de enige grootte waarop de cijfers hieronder betekenis hebben.", AZURE))

s.append(PageBreak())

# ============================================================ 4 · BEWIJSTOESTAND
s.append(P("3 · Bewijstoestand per engine", H1))
s.append(P("De sweep van 25 augustus (trap 0 t/m 9) is de meest recente volledige meting. Wat hij opleverde, en hoe hard "
           "elk cijfer is:", Body))
s.append(Spacer(1,2*mm))
s.append(table(
  ["Engine","Markt","$/account-dag","P1","Harde poort","Bruikbaarheid"],
  [["EL MATADOR","MES","$30,59","dag 85","dicht (data-pariteit)","Bruikbaar — met kostenvoorbehoud"],
   ["EL LEON","MYM","$17,48","dag 118","OPEN","<b>Ongeldig</b>, niet &quot;ongeveer goed&quot;"],
   ["EL REY","MNQ","$13,21","dag 161","OPEN","<b>Ongeldig</b>"],
   ["EL PATRON","MGC (GC-twin)","fundeert niet op 1 ct","—","n.v.t.","Afgevallen, onder MGC-voorbehoud"],
   ["EL TESORO","MGC (GC-twin)","fundeert niet op 1 ct","—","geen export","Onder MGC-voorbehoud"],
   ["EL BANDIDO","MYM","fundeert niet op 1 ct","—","OPEN","Niet live"]],
  [26*mm, 24*mm, 26*mm, 14*mm, 28*mm, W-118*mm]))
s.append(Spacer(1,3*mm))
s.append(callout("&quot;Ongeldig&quot; is niet mijn woord maar dat van de pijplijn",
   "Over onvervulde harde poorten zegt <font face='Courier'>state.py</font> zelf dat ze downstream-cijfers "
   "<i>&quot;invalid rather than merely early&quot;</i> maken. Behandel LEON's $17,48 en REY's $13,21 dus niet als "
   "indicatief-maar-ongeveer-goed. Als die poort dichtgaat kan het cijfer een andere kant op bewegen. Precies dit "
   "onderscheid kostte op 23 augustus de GC+ES-conclusie de kop.", ROSE, colors.HexColor("#F7EEEF")))
s.append(Spacer(1,2.5*mm))
s.append(P("Drie voorbehouden drukken op élk cijfer hierboven", H3))
s.extend(bl([
  "<b>Kosten.</b> Alle drie de validatie-exports draaiden commissie 0,51 terwijl de registry voor MNQ, MES en MYM "
  "0,37 draagt. 0,51 ligt verdacht dicht bij de goudwaarde 0,52 — vermoedelijk een goudcommissie op index-micro's. "
  "Ook MATADOR's pariteit is onder 0,51 behaald.",
  "<b>MGC.</b> PATRON, TESORO en BANDIDO zijn gemeten op de GC-twin omdat echte MGC-data ontbreekt. Dat voorbehoud "
  "geldt ook voor een <i>afwijzing</i>: PATRON is zwaar in twijfel, niet dood verklaard.",
  "<b>Validatie, geen out-of-sample.</b> Het meetvenster loopt vanaf 24-08-2023 en valt volledig binnen de periode "
  "waarop de configuraties gekozen zijn.",
]))

# ============================================================ 5 · ROLLEN
s.append(PageBreak())
s.append(P("4 · Wat elke engine is bedoeld te zijn", H1))
s.append(P("Een merknaam is in deze vloot een <i>vaste strategie-persoonlijkheid</i>, geen etiket. Hieronder per merk: "
           "waar hij voor bedoeld is, waar hij tot zijn recht komt, en waar hij dat juist niet doet.", Body))

def engine(name, tag, purpose, shines, careful, status, accent=GOLD):
    head = Table([[Paragraph(f"<b>{name}</b>", S("en", fontName="Helvetica-Bold", fontSize=11, leading=13.6, textColor=colors.white, spaceAfter=0)),
                   Paragraph(tag, S("et", fontSize=8.2, leading=13.6, textColor=colors.HexColor("#D9C9A6"), spaceAfter=0))]],
                 colWidths=[62*mm, W-62*mm])
    head.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),NAVY2),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("ALIGN",(1,0),(1,0),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    rows=[["Doel", purpose],["Komt tot zijn recht", shines],["Pas op", careful],["Status", status]]
    b=Table([[Paragraph(a, S("k", fontName="Helvetica-Bold", fontSize=8.2, leading=11, textColor=GOLD, spaceAfter=0)),
              Paragraph(v, Cell)] for a,v in rows], colWidths=[34*mm, W-34*mm])
    b.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LINEBELOW",(0,0),(-1,-2),0.35,LINE),
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#FBFAF7")),
        ("LINEBEFORE",(0,0),(0,-1),2.2,accent)]))
    return KeepTogether([Spacer(1,3.5*mm), head, b])

s.append(engine("EL MATADOR", "MES · Production CVD6 EOD · MAT-MES-P",
  "Het anker van de vloot. De enige engine die op dit moment een gemeten, gevalideerd payout-cijfer draagt.",
  "Op een volwassen EOD-account waar je de klok kunt uitzitten. $30,59 per account-dag en P1 op dag 85 is de snelste "
  "doorlooptijd die we hebben. Zijn brede FVG-venster (10–22 ticks) en 1,75R maken hem minder afhankelijk van precieze "
  "timing dan de scherpere engines.",
  "Zijn tick-economie is groot: een volle stop is ongeveer −$914, een volle TP +$1.569. Op zes contracten zit hij daarmee "
  "boven de daily loss limit met één slechte dag. Dit is exact de engine waarop de sizing-muur gemeten is.",
  "Enige gesloten poort. Pariteit is wel behaald onder de verkeerde commissie — hertoetsen zodra 0,37 staat.", GOLD))

s.append(engine("EL REY", "MNQ · Production EOD / Intraday · REY-MNQ-P / REY-NQ-PI",
  "De scherpste engine van de vloot: FVG 2–8 ticks, CVD-streak 8. Hij wacht lang en slaat smal toe.",
  "Op MNQ, waar de tickgrootte klein genoeg is om een gap van twee ticks betekenis te geven. Zijn 1,25R met een hoge "
  "win rate is een ander winstprofiel dan MATADOR: meer, kleinere winnaars.",
  "P1 op dag 161 is de langste doorlooptijd van de drie gemeten engines — hij houdt een account bijna een half jaar bezet "
  "voor de eerste uitbetaling. Op een account waar de klok kost, is dat een reëel nadeel.",
  "Payout-cijfer <b>ongeldig</b> onder een open harde poort. Wacht op her-export tegen de bron-configuratie.", AZURE))

s.append(engine("EL LEON", "MYM · Production EOD + twee recovery-profielen · LEO-MYM-P / LEO-YM-CE / LEO-YM-CI",
  "De goedkoopste engine per fout. Op MYM is een tick één indexpunt à $0,50 — een numeriek grote stop van 480 is in "
  "dollars klein.",
  "Precies daar waar het misgaat: op een account dat hersteld moet worden. De twee Q2-varianten op twee contracten zijn "
  "geen afgezwakte versie van de productie-engine maar zijn eigenlijke rol. Ze veranderen de exposure, niet de signalen.",
  "Rapporteer bij MYM altijd ticks én dollars. Een stop van 480 klinkt roekeloos en is het niet — maar iemand die alleen "
  "het getal ziet, trekt de verkeerde conclusie.",
  "Payout-cijfer <b>ongeldig</b> onder een open harde poort. Zelfde her-exportroute als EL REY.", AZURE))

s.append(engine("EL TESORO", "MGC · Conservative EOD · TES-MGC-C",
  "Het diversificatie-anker. MGC is de enige niet-aandelenbucket in de hele vloot.",
  "Als tegenwicht naast de index-engines, en alleen daar. Zijn strategische waarde zit niet in zijn eigen rendement maar "
  "in het feit dat hij op een andere motor loopt dan MNQ, MES en MYM. 2,25R op een Liquidity-Core-regime met zondag uit — "
  "hij handelt weinig en selectief.",
  "Fundeert in de meting niet op één contract. En die meting is op de GC-twin gedaan, dus je weet niet of dat aan de "
  "engine ligt of aan de surrogaat-markt.",
  "Onder MGC-voorbehoud. Geen export, harde poort dicht noch open — hij is nooit getoetst.", GOLD))

s.append(engine("EL PATRON", "MGC · Aggressive EOD · PAT-MGC-A",
  "De agressieve goud-variant: acht contracten, dezelfde 2,25R, kortere stop van 120 ticks.",
  "Uitsluitend op volwassen EOD-accounts met een gevulde buffer. Draai geen constante acht MGC op een intraday-PA met "
  "een bewegende trail — dat is de combinatie waar zijn drawdown van ongeveer $9.343 een account kost.",
  "In de sweep viel hij op drie punten om: geen edge (−$2,76 per trade, PF 0,96), de edge zat in één handelsrichting, en "
  "zonder uur-en-dag-masker verdampte hij helemaal. Dat laatste is cherry-picking en dat telt niet.",
  "Zwaar in twijfel — maar de afwijzing staat óók op de GC-twin, dus hij is niet definitief dood.", ROSE))

s.append(engine("EL BANDIDO", "MYM · HF / Harvest EOD · BAN-MYM-H",
  "De hoogfrequente oogst-engine: FVG 4–8, CVD3, 1,5R, harde dagcap van $1.000. Ongeveer 2.070 trades in het onderzoek.",
  "In theorie op een account waar je snel dagen wil afvinken. Zijn hele ontwerp draait om volume: PF ongeveer 1,17 is "
  "dun, maar bij dat aantal trades kan dun genoeg zijn.",
  "Hoge breach- en churn-cijfers. Bij deze trade-frequentie is een dunne PF een fragiele PF: kleine kostenverschuivingen "
  "of slippage tikken hier veel harder door dan bij een engine met honderd trades.",
  "<b>Niet live zetten.</b> De Pine-pariteitspoort staat open. Tel hem niet mee als draaiende engine.", ROSE))

s.append(engine("EL TORO", "ES / GC / NQ · vier evaluatie-scripts · TOR-*",
  "Evaluatie-accounts halen. Dat is een ander doel dan payout maximaliseren, en daarom heeft deze familie een eigen "
  "parametrisering: vaste TP in units in plaats van R-multiple, een confirmatievenster van twee bars, zondag uit.",
  "Op een verse eval waar je de $3.000 target wil raken zonder de trailing drawdown te breken. De vaste TP is hier het punt: "
  "een eval beloont een voorspelbare afstand, niet een optimale.",
  "Het is een eval-familie en geen funded-familie. De payout-machinerie — consistency, payout-ladder, MAE-guard — zit er "
  "bewust niet in. Zet ze niet op een PA.",
  "Trailing drawdown staat nu op $2.000 conform Apex 4.0. Op een legacy-eval moet dat handmatig terug naar $2.500.", AZURE))

s.append(engine("EL PRINCIPE en EL MINERO", "research en gereserveerd",
  "EL PRINCIPE is een gebalanceerde MNQ-variant in onderzoek. EL MINERO is een gereserveerde naam voor een toekomstige "
  "HF- of commodity-engine.",
  "Nergens — ze draaien niet.",
  "Ze bestaan in de naamgevingsarchitectuur zodat er later geen merknaam hergebruikt hoeft te worden. Dat is de enige "
  "functie die ze nu hebben.",
  "Niet live, geen script in de vloot van dertien.", GREY))

# ============================================================ 6 · PORTEFEUILLE
s.append(PageBreak())
s.append(P("5 · Van rangorde naar accounttoewijzing", H1))
s.append(P("De verleiding is om de tabel uit hoofdstuk 3 te lezen als een ranglijst en de accounts van boven naar beneden "
           "te vullen. Dat is precies de fout die hier al eens gemaakt is. <b>Rangorde is niet hetzelfde als "
           "accounttoewijzing</b>, om drie redenen.", Body))
s.append(Spacer(1,1.5*mm))
s.append(P("Correlatie: er is maar één niet-index-bucket", H3))
s.append(P("MNQ, MES en MYM zijn alle drie Amerikaanse aandelenindex-exposure. Ze kunnen bij een risk-on- of "
           "risk-off-schok hard meebewegen, ook als hun signaaltiming verschilt. MGC is de enige uitzondering, en dat is "
           "meteen de strategische waarde van EL TESORO — los van wat zijn eigen rendement doet.", Body))
s.append(P("<b>Claim geen decorrelatie voordat je hem gemeten hebt.</b> Twintig tot dertig actieve dagen gerealiseerde "
           "dagelijkse P&amp;L-correlatie is het minimum. Blijft de paarsgewijze dagcorrelatie tussen MES, MNQ en MYM "
           "structureel boven 0,70, dan is de index-bucket te groot en moet er een andere niet-index-markt bij.", Body))
s.append(Spacer(1,1.5*mm))
s.append(P("Accountfase bepaalt de engine, niet andersom", H3))
s.append(P("Een verse eval, een jong PA met een lege buffer en een volwassen PA met een vergrendelde floor zijn drie "
           "verschillende risico-omgevingen. EL TORO hoort in de eerste. De recovery-profielen van EL LEON horen in de "
           "tweede. EL PATRON hoort uitsluitend in de derde — en dat staat er niet voor niets bij.", Body))
s.append(Spacer(1,1.5*mm))
s.append(P("Doorlooptijd is een kost", H3))
s.append(P("P1 na 85 dagen versus P1 na 161 dagen is bijna een verdubbeling van de tijd dat een betaald account bezet is "
           "voordat er geld uit komt. Bij gelijke $/dag wint de engine met de kortere doorlooptijd, omdat je het account "
           "eerder kunt herinzetten. Dit is de reden dat de meetlat op account-dagen staat en niet op profit factor.", Body))

# ============================================================ 7 · WAT ER MOET GEBEUREN
s.append(P("6 · Wat er moet gebeuren om dit oordeel hard te maken", H1))
s.append(P("De rolverdeling hierboven is bruikbaar als werkindeling. Ze is nog geen bewijs. Dit is wat er tussen zit, in "
           "de volgorde waarin het moet:", Body))
s.append(Spacer(1,2*mm))
s.append(table(
  ["#","Wat","Waarom het eerst moet"],
  [["1","Commissie gelijktrekken naar 0,37 en LEON en REY her-exporteren tegen de bron-configuratie",
        "Trap 1 meet tegen een export. Zolang de export een andere configuratie en een verkeerde kostenaanname draagt, "
        "kan die poort niet dichtgaan — en zonder die poort is elk cijfer erachter ongeldig."],
   ["2","De CVD-motorvraag beantwoorden",
        "Als de scripts een andere delta-motor draaien dan de backtester meet, meet de sweep een ander entry-filter dan "
        "er live draait. Dat raakt élk cijfer, ook de $30,59. Er is tegenbewijs — MATADOR haalde pariteit — dus er is "
        "iets dat nog niet begrepen is. Beantwoord dit vóór je her-exporteert, anders meet je tegen een meetlat die zelf niet klopt."],
   ["3","MATADOR hertoetsen op de gecorrigeerde commissie",
        "Kosten verschuiven profit factor direct. $30,59 is nu het enige cijfer waar iets op gebouwd wordt; dat moet je "
        "niet op een verkeerde kostenaanname laten staan."],
   ["4","De sizing-ontwerpkeuze maken",
        "Start-klein-en-schaal-op, of contractgrootte per accountfase. Zolang dit open staat, is één contract de enige "
        "grootte waarop de cijfers betekenis hebben — en op één contract funderen drie van de zes engines helemaal niet."],
   ["5","Echte MGC-data halen",
        "Zonder MGC-data blijft élk oordeel over EL TESORO en EL PATRON onder voorbehoud staan, inclusief het negatieve."],
   ["6","EL BANDIDO's pariteitspoort dichtzetten",
        "Tot dat gebeurt telt hij niet mee als draaiende engine, hoe aantrekkelijk zijn trade-frequentie ook is."]],
  [10*mm, 58*mm, W-68*mm]))

# ============================================================ 8 · GRENZEN
s.append(Spacer(1,4*mm))
_h7 = P("7 · Wat je op basis van dit document niet mag claimen", H1)
_c7 = callout("Drie grenzen, expliciet",
  "<b>1 · Dit is geen out-of-sample bewijs.</b> Out-of-sample loopt vooruit vanaf het moment dat een configuratie "
  "bevroren wordt. Acht scripts staan bevroren sinds 23-08-2026, vijf sinds 25-08. Dat zijn dágen, geen jaren. Alle "
  "cijfers in dit document vallen binnen het validatievenster. Claim nergens — niet op de site, niet in een rapport, "
  "niet tegenover een prop firm — dat deze vloot out-of-sample bewezen is.<br/><br/>"
  "<b>2 · Er is geen geldige rangorde.</b> De verse meting geeft MATADOR boven LEON boven REY, maar twee van die drie "
  "cijfers staan onder een open harde poort. De oude volgorde uit een eerdere ronde is ingetrokken. Er staat op dit "
  "moment geen rangorde, en dit document maakt er geen.<br/><br/>"
  "<b>3 · Er is geen aangetoonde decorrelatie.</b> Drie van de vier markten zijn dezelfde exposure. Tot er twintig à "
  "dertig actieve dagen gerealiseerde P&amp;L-correlatie ligt, is spreiding een aanname en geen eigenschap.",
  ROSE, colors.HexColor("#F7EEEF"))
s.append(KeepTogether([_h7, _c7]))
s.append(Spacer(1,4*mm))
s.append(P("Herkomst van de cijfers", H2))
s.append(P("Vloot-sweep trap 0 t/m 9 van 24–25 augustus 2026, meetvenster vanaf 24-08-2023, vastgelegd in "
           "<font face='Courier'>validation/FLEET_sweep_20260825.md</font>. Bevroren parameters uit "
           "<font face='Courier'>frozen-engines.md</font>; alle dertien scripts zijn daartegen gecontroleerd en komen "
           "overeen. Prop-firm-regels uit <font face='Courier'>data/propfirms.json</font>. Scriptversie v3.2.0, "
           "26 augustus 2026.", Small))

doc.build(s)
print("PDF:", OUT)
