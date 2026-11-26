import csv, collections, json, re

L="/root/.claude/uploads/f5ac87aa-ab67-5ac4-bd43-6e52a3cadcc8/16ab65c3-TradingView_Alerts_Log_20260810_5250e.csv"
rows=list(csv.DictReader(open(L, encoding="utf-8-sig")))

def toks(name):
    """Splits de inputlijst tussen de buitenste haakjes, met respect voor
    geneste haakjes ('Day-trail (keep peak)' is één token)."""
    i=name.find("("); j=name.rfind(")")
    if i<0 or j<0: return name, []
    head=name[:i].strip(); body=name[i+1:j]
    out=[]; cur=""; depth=0
    for ch in body:
        if ch=="(": depth+=1
        elif ch==")": depth-=1
        if ch=="," and depth==0: out.append(cur.strip()); cur=""
        else: cur+=ch
    out.append(cur.strip())
    return head, out

PHASES={"Apex PA","Apex Eval","Research (none)"}
ROUTES={"Auto (this script)","Discord","PMT Tradovate","PineConnector","Middleware"}

def parse(name):
    head,t=toks(name)
    d={"script":head,"acct":t[0] if t else "","qty":t[1] if len(t)>1 else "",
       "entry":t[2] if len(t)>2 else "","expiry":t[3] if len(t)>3 else "",
       "R":t[4] if len(t)>4 else "","raw":t}
    d["mm"]      = next((x for x in t if x.startswith(("Day-trail","Custom","Fixed"))), "")
    d["phase"]   = next((x for x in t if x in PHASES), "")
    d["preset"]  = next((x for x in t if x.startswith("apex_")), "")
    d["route"]   = next((x for x in t if x in ROUTES), "")
    d["label"]   = next((x for x in t if ("·" in x) and not x.startswith("apex_")), "")
    # streak, gapMin, gapMax, confW: het blok "<s>, 9, <max>, <cw>"
    d["streak"]=d["gapMin"]=d["gapMax"]=d["confW"]=""
    for i in range(1,len(t)-2):
        if t[i]=="9" and t[i+1].isdigit() and 10<=int(t[i+1])<=20 and t[i+2].isdigit() and int(t[i+2])<=6:
            d["streak"],d["gapMin"],d["gapMax"],d["confW"]=t[i-1],t[i],t[i+1],t[i+2]; break
    # day-trail / day-cap bedragen staan direct achter de MM-mode
    if d["mm"] and d["mm"] in t:
        k=t.index(d["mm"])
        nums=[x for x in t[k+1:k+3] if x.replace(".","",1).isdigit()]
        d["mmNums"]="/".join(nums)
    else: d["mmNums"]=""
    return d

a=collections.defaultdict(list)
for r in rows: a[(r["Alert ID"],r["Ticker"],r["Name"])].append(r["Time"])
week=[(k,v) for k,v in a.items() if max(v)>="2026-08-03"]

recs=[]
for (aid,tk,nm),t in week:
    d=parse(nm.replace(": alert() function calls only",""))
    d.update(alert_id=aid, ticker=tk.split(",")[0], n=len(t), first=min(t)[:10], last=max(t)[:10],
             disc=nm.startswith("DISC"))
    recs.append(d)
recs.sort(key=lambda r:(r["ticker"], r["acct"], r["disc"]))

cfg=[]
for r in rows:
    m=re.search(r"ver=[^\"\\\\]*", r["Description"])
    if "CONFIG" in r["Description"] and m:
        h,_=toks(r["Name"]); cfg.append({"time":r["Time"][:16].replace("T"," "),"ticker":r["Ticker"].split(",")[0],
                                          "script":h,"cfg":m.group(0)})
cfg.sort(key=lambda c:c["time"], reverse=True)
json.dump({"alerts":recs,"config":cfg}, open("alerts_parsed.json","w"), indent=1, ensure_ascii=False)
print("alerts:",len(recs)," config:",len(cfg))
for r in recs:
    print(f'{r["ticker"]:<20} {r["acct"]:<22} q{r["qty"]:<3} R{r["R"]:<5} fvg{r["gapMin"]}-{r["gapMax"]} cw{r["confW"]} st{r["streak"]} | {r["mm"]} {r["mmNums"]} | {r["phase"]:<16}| {r["route"] or "-":<18}| {"DISC" if r["disc"] else "exec"} n={r["n"]}')
