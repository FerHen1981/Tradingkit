import json
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak)

d=json.load(open("alerts_parsed.json"))
NAVY=colors.HexColor("#030F28"); DEEP=colors.HexColor("#0E2A5E")
GOLD=colors.HexColor("#E8B54F"); SAND=colors.HexColor("#F2EBDA")
AZUR=colors.HexColor("#5AA2FF"); ROSE=colors.HexColor("#E0796E")

ss=getSampleStyleSheet()
H1=ParagraphStyle("H1",parent=ss["Title"],fontSize=17,textColor=NAVY,spaceAfter=2,alignment=0)
H2=ParagraphStyle("H2",parent=ss["Heading2"],fontSize=11.5,textColor=NAVY,spaceBefore=9,spaceAfter=4)
P =ParagraphStyle("P", parent=ss["BodyText"],fontSize=8.6,leading=11.6)
SM=ParagraphStyle("SM",parent=ss["BodyText"],fontSize=7.4,leading=9.4,textColor=colors.HexColor("#444"))
CELL=ParagraphStyle("CELL",parent=ss["BodyText"],fontSize=6.9,leading=8.3)

doc=SimpleDocTemplate("MEX_alert_settings_vorige_week.pdf",pagesize=landscape(A4),
    leftMargin=11*mm,rightMargin=11*mm,topMargin=11*mm,bottomMargin=11*mm,
    title="MEX — alert-instellingen 3 t/m 10 augustus 2026")
S=[]

S.append(Paragraph("MEX — welke instellingen draaiden er afgelopen week?", H1))
S.append(Paragraph("Gereconstrueerd uit <b>TradingView_Alerts_Log_20260810</b> (1.611 regels, 12 juli – 10 augustus 2026). "
  "Controleblad voor het omzetten van de webhook-URL's naar de middleware-trechter.", P))
S.append(Spacer(1,4))

S.append(Paragraph("Hoe je dit leest — drie dingen die je moet weten vóór je iets aanpast", H2))
S.append(Paragraph(
 "<b>1. TradingView bevriest de inputs op het moment dat je de alert aanmaakt.</b> De waarden hieronder zijn dus wat de alert "
 "écht uitvoerde, niet wat er nu op je chart staat. Wijk je chart af, dan draaide de alert op de oude waarden — dat is precies "
 "waarom dit blad bestaat.", P))
S.append(Paragraph(
 "<b>2. De alert-naam toont wáárden, niet aan/uit.</b> Bewijs: ΞL LΞÓN op ES toont in de naam een CVD-streak van 4, terwijl de "
 "CONFIG-regel van hetzelfde account <font face='Courier'>streak=off</font> zegt. Het getal stond ingevuld, de filter stond uit. "
 "Voor aan/uit is alleen tabel B (CONFIG) bewijs.", P))
S.append(Paragraph(
 "<b>3. Tabel B is compleet en gelabeld, tabel A is een deelverzameling.</b> Een CONFIG-regel verschijnt alleen op de eerste live "
 "bar ná het aanmaken van een alert. Voor de MGC-alerts van ΞL TΞSORO zit er geen CONFIG in het venster — voor die accounts is "
 "tabel A het enige bewijs, en daar ontbreekt de aan/uit-status.", P))
S.append(Spacer(1,5))

S.append(Paragraph("Tabel A — alerts die actief waren tussen 3 en 10 augustus 2026", H2))
hdr=["Instrument","Account","Alert-ID","Actief","n","Qty","Entry","Exp","R","MM (dag)","Fase","FVG","cw","streak","Route","Soort"]
rowsA=[hdr]
for r in d["alerts"]:
    rowsA.append([r["ticker"].replace("CME_MINI:","").replace("COMEX_MINI:","").replace("COMEX:",""),
        r["acct"], r["alert_id"], f'{r["first"][5:]}–{r["last"][5:]}', str(r["n"]), r["qty"],
        "L50%" if "Limit" in r["entry"] else r["entry"], r["expiry"], r["R"],
        (r["mm"].replace("Day-trail (keep peak)","trail")+" "+r["mmNums"]).strip() or "—",
        r["phase"].replace("Research (none)","Research").replace("Apex ",""),
        f'{r["gapMin"]}-{r["gapMax"]}', r["confW"], r["streak"],
        r["route"].replace("Auto (this script)","Auto").replace("PMT Tradovate","PMT") or "n.b.",
        "Discord" if r["disc"] else "executie"]) 
tA=Table(rowsA, repeatRows=1, colWidths=[16*mm,32*mm,20*mm,18*mm,9*mm,9*mm,12*mm,9*mm,10*mm,22*mm,15*mm,13*mm,8*mm,11*mm,15*mm,16*mm])
st=[("BACKGROUND",(0,0),(-1,0),NAVY),("TEXTCOLOR",(0,0),(-1,0),SAND),
    ("FONTSIZE",(0,0),(-1,-1),6.8),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
    ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#BBBBBB")),
    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),1.6),("BOTTOMPADDING",(0,0),(-1,-1),1.6)]
for i,r in enumerate(d["alerts"],start=1):
    if r["disc"]: st.append(("BACKGROUND",(0,i),(-1,i),colors.HexColor("#EFF4FC")))
    if r["acct"]=="PAAPEX2700250000018": st.append(("TEXTCOLOR",(5,i),(5,i),ROSE))
tA.setStyle(TableStyle(st)); S.append(tA)
S.append(Spacer(1,3))
S.append(Paragraph("Blauwe regels = losse Discord-alert naast de executie-alert (het oude twee-alerts-model). "
  "<b>Rood</b> = de qty-8 op account …018 die naast de qty-6 van …013 op dezelfde MGC-chart draait. "
  "‘n.b.’ = de route staat niet in de inputlijst van die scriptversie en is niet uit de log af te leiden.", SM))

S.append(PageBreak())
S.append(Paragraph("Tabel B — volledige CONFIG-snapshots (gelabeld, bewijs)", H2))
S.append(Paragraph("Elke kolom is één CONFIG-bericht dat het script zelf verstuurde op zijn eerste live bar. "
  "Dit is de enige bron die óók aan/uit-status bevat.", P))
S.append(Spacer(1,3))

u={}
for c in d["config"]: u.setdefault(c["cfg"],[]).append(c)
items=[]
for cfg,c in u.items():
    kv=dict(p.split("=",1) for p in cfg.split(";") if "=" in p)
    items.append((max(x["time"] for x in c), c[0]["ticker"], kv))
items.sort(reverse=True)
KEYS=['ver','acct','qty','entry','expiry','fvg','confW','stop','pivK','buf','maxStop','tp','R','goalTp',
      'guard','BEeff','trailEff','tpEff','vwapVeto','cvd','streak','bias','sweep','monFilter','DLL',
      'phase','mae','derisk','deriskPA','tz']
LBL={'ver':'scriptversie','acct':'journal-account','qty':'contracten','entry':'entry-modus','expiry':'expiry (bars)',
     'fvg':'FVG-band','confW':'confirm-venster','stop':'stop-modus','pivK':'pivot K','buf':'swing-buffer',
     'maxStop':'max stop','tp':'TP-modus','R':'R-multiple','goalTp':'goal-TP','guard':'DD-guard',
     'BEeff':'break-even','trailEff':'trail','tpEff':'TP effectief','vwapVeto':'VWAP-veto','cvd':'CVD-filter',
     'streak':'CVD-streak','bias':'bias-filter','sweep':'sweep-filter','monFilter':'maandag-filter',
     'DLL':'daglimiet','phase':'fase','mae':'MAE-guard','derisk':'derisk','deriskPA':'derisk PA','tz':'tijdzone'}

def cfg_table(sel, title):
    S.append(Paragraph(title, ParagraphStyle("h3",parent=H2,fontSize=10)))
    head=["instelling"]+[f'{kv["acct"]}\n{tk.split(":")[-1]}\n{t[:10]}' for t,tk,kv in sel]
    rows=[[Paragraph(f'<b>{h}</b>',CELL) for h in head]]
    for k in KEYS:
        if k in ("acct",): continue
        rows.append([Paragraph(f'<b>{LBL.get(k,k)}</b>',CELL)]+
                    [Paragraph(kv.get(k,"—"),CELL) for _,_,kv in sel])
    w=[30*mm]+[(240*mm-30*mm)/len(sel)]*len(sel)
    t=Table(rows, repeatRows=1, colWidths=w)
    stt=[("BACKGROUND",(0,0),(-1,0),NAVY),("TEXTCOLOR",(0,0),(-1,0),SAND),
         ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#BBBBBB")),("VALIGN",(0,0),(-1,-1),"TOP"),
         ("TOPPADDING",(0,0),(-1,-1),1.3),("BOTTOMPADDING",(0,0),(-1,-1),1.3),
         ("BACKGROUND",(0,1),(0,-1),colors.HexColor("#F2F5FA"))]
    for i in range(1,len(rows)):
        if i%2==0: stt.append(("BACKGROUND",(1,i),(-1,i),colors.HexColor("#FAFAFA")))
    t.setStyle(TableStyle(stt)); S.append(t); S.append(Spacer(1,6))

cfg_table([i for i in items if i[0]>="2026-08"], "B1 · augustus — de snapshots die het dichtst bij vorige week liggen")
S.append(PageBreak())
cfg_table([i for i in items if i[0]<"2026-08"], "B2 · juli — historie (NQ-vloot, inmiddels geparkeerd)")

S.append(PageBreak())
S.append(Paragraph("Wat hieruit volgt — controleer dit vóór je de URL's omzet", H2))
for n,txt in enumerate([
 "<b>Elf accounts draaiden met twee alerts naast elkaar</b> (blauw in tabel A): één voor executie, één voor Discord. Dat was nodig vóór de trechter. Zet je de executie-alert om naar <font face='Courier'>https://mw.mex-traders.com/signal/&lt;secret&gt;</font> en vink je in het script de routes Discord + PMT + Journal aan, dan is de losse DISC-alert overbodig en kun je hem verwijderen. Doe dat pas nadat je de kaart in Discord hebt zien verschijnen — anders ben je je meldingen kwijt.",
 "<b>MGC draait op vier accounts met verschillende sizes: …013 q6, …016 q8, …018 q8, …019 q7, …020 q10.</b> Allemaal op dezelfde chart en hetzelfde signaal. Dat verklaart waarom je in Discord twee berichten met verschillende qty ziet bij één setup. Controleer of die spreiding bewust is; de fleet-matrix pint MGC op q3/q5.",
 "<b>De GC-alert op APEX…205 (q2, day-trail 700/800, fase Research) wijkt af van alle andere.</b> Dat is de full-GC-alert van 10 augustus — hetzelfde account dat op AutoLiq ging. Full GC vraagt ±$39k margin per contract; op een 50k-account past dat niet. Zet deze uit of om naar MGC vóór je hem op de trechter aansluit.",
 "<b>ΞL MINΞRO draaide op vier GC-accounts met identieke instellingen</b> (q3, R1.55, FVG 9-18, confW 0): …203, …208, …211 plus de MIDDLEWARE TEST-alert. Die laatste (q5, R1.5, 'MIDDLEWARE TEST' als account-ID) is een testalert — controleer of die nog moet draaien.",
 "<b>Voor de MGC-alerts van ΞL TΞSORO ontbreekt de CONFIG-regel.</b> Wil je de aan/uit-status van VWAP-veto, CVD-filter, MAE-guard en derisk hard hebben, maak die alerts dan opnieuw aan met 'Send CONFIG message on first live bar' aan — dan schrijft het script zijn volledige configuratie zelf weg en heb je dit blad de volgende keer niet nodig.",
], start=1):
    S.append(Paragraph(f"{n}. {txt}", P)); S.append(Spacer(1,3))

S.append(Spacer(1,6))
S.append(Paragraph("Bron: TradingView_Alerts_Log_20260810_5250e.csv · 1.611 alertregels · 63 unieke alerts, waarvan 25 actief in het venster 3–10 aug · "
  "16 CONFIG-berichten (11 uniek). Gegenereerd 11 augustus 2026. Systeemplan, geen advies · mex-traders.com", SM))

doc.build(S)
print("ok")
