#!/usr/bin/env python3
"""
Build the pricing model from the COMPREHENSION classification.

  python3 build_model_from_classification.py [OUT_JSON]

Inputs (in this folder):
  jobs_jan23_to_jun26.csv, invoices_jan23_to_jun26.csv, quotes_jan23_to_jun26.csv
  class_jobs.json    (job number -> {primary_system, primary_action, characteristics, ...})
  class_quotes.json  (quote number -> same shape)

Produces OUT_JSON (default pricing_model_v2.json) in the same shape the HTML tool
consumes, so you can paste it over the DATA block in treat-pricing-tool.html.

What is different from the keyword build:
  * Job TYPE is the classified primary_system, not a keyword guess.
  * "Diagnose/investigate only" becomes a characteristic, and it is the one
    that pulls price DOWN (these jobs are genuinely cheaper).
  * Characteristics are the richer set the model read from the narrative.
  * Base figures are RECENCY WEIGHTED so recent prices count more.
Runs on whatever is classified so far; rerun after finishing classification.
"""
import sys, re, json
import numpy as np, pandas as pd

OUT = sys.argv[1] if len(sys.argv) > 1 else "pricing_model_v2.json"
HALFLIFE_DAYS = 550            # recency weighting half life (~1.5 years)
TODAY = pd.Timestamp("2026-06-01")

def num(s): return pd.to_numeric(s.astype(str).str.replace(',','',regex=False).str.strip(), errors='coerce')
def strip_html(t):
    t=re.sub(r'<[^>]+>',' ',t); t=t.replace('&nbsp;',' ').replace('&amp;','&').replace('&#39;',"'")
    return re.sub(r'\s+',' ',t).strip()
BOUND=['further works','further urgent works','we recommend','we advise','we will submit','recommended works','will submit a quotation']
def wp(t):
    t=strip_html(t); low=t.lower(); cut=len(t)
    for b in BOUND:
        i=low.find(b)
        if i!=-1 and i<cut: cut=i
    return t[:cut].strip()

def wquantile(v, w, q):
    o=np.argsort(v); v=np.asarray(v)[o]; w=np.asarray(w)[o]
    cw=np.cumsum(w)-0.5*w; cw/=w.sum()
    return float(np.interp(q, cw, v))
def conf(n): return 'high' if n>=40 else ('medium' if n>=15 else 'low')

def ols_log(df, flags, wt):
    y=np.log(df['val'].values); W=np.sqrt(wt.values)
    X=np.column_stack([np.ones(len(df))]+[df[f].astype(float).values for f in flags])
    Xw=X*W[:,None]; yw=y*W
    beta,*_=np.linalg.lstsq(Xw,yw,rcond=None)
    resid=y-X@beta; n,k=X.shape
    s2=(resid@resid)/max(n-k,1); se=np.sqrt(np.diag(s2*np.linalg.inv(X.T@X)))
    return beta, beta/np.where(se==0,1e9,se), resid

# ---- load ----
jobs=pd.read_csv('jobs_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 15'])
inv =pd.read_csv('invoices_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 19'])
qts =pd.read_csv('quotes_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 15'])
for d in (jobs,inv,qts): d['Jobnumber']=d['Jobnumber'].str.strip()
cj=json.load(open('class_jobs.json')) if __import__('os').path.exists('class_jobs.json') else {}
cq=json.load(open('class_quotes.json')) if __import__('os').path.exists('class_quotes.json') else {}
print('classified: jobs=%d quotes=%d'%(len(cj),len(cq)))

# ---- add-on stripping (same as before) ----
ADDON_NAMES=["Emergency After Hours Callout","Jet Blaster","Drain Camera Survey","Electric Eel","Pipe Location Leak Detection"]
ADDON_DISP={"Emergency After Hours Callout":"Emergency after-hours callout","Jet Blaster":"Jet blaster",
            "Drain Camera Survey":"Drain camera survey (CCTV)","Electric Eel":"Electric eel","Pipe Location Leak Detection":"Pipe location / leak detection"}
inv['unit']=num(inv['Inv Line Unit Sell']); inv['qty']=num(inv['Inv Quantity']).fillna(1); inv['amt']=inv['unit']*inv['qty']
addon_job=inv[inv['Inv Item Description'].str.strip().isin(ADDON_NAMES)].groupby('Jobnumber')['amt'].sum()

jobs['total']=num(jobs['Task Invoices Total Ex'])
jobs['addon']=jobs['Jobnumber'].map(addon_job).fillna(0)
jobs['base_total']=(jobs['total']-jobs['addon']).clip(lower=0)
jobs['date']=pd.to_datetime(jobs['Completed Date'].str.strip(),errors='coerce',dayfirst=True)
jobs['w']=0.5**(((TODAY-jobs['date']).dt.days.clip(lower=0))/HALFLIFE_DAYS)

CHAR=["after_hours","return_visit_or_staged","building_shutdown","multi_unit","excavation","difficult_access",
      "specialist_equipment","tree_roots","multiple_items","concealed_or_in_slab","reinstatement","structural_building_works","large_scope"]
CHAR_LABEL={"after_hours":"After hours / emergency","return_visit_or_staged":"Return or staged visits","building_shutdown":"Building shutdown",
 "multi_unit":"Multiple units","excavation":"Excavation / breaking concrete","difficult_access":"Difficult access",
 "specialist_equipment":"Specialist equipment","tree_roots":"Tree roots","multiple_items":"Multiple items in one visit",
 "concealed_or_in_slab":"Concealed / in slab","reinstatement":"Reinstatement (tile/render/paint/waterproof)",
 "structural_building_works":"Structural / building works","large_scope":"Large scope","diagnose_only":"Diagnosis only (no repair done)"}

def attach(df, cls):
    df=df.copy()
    df['cls']=df['Jobnumber'].map(cls)
    df=df[df['cls'].notna()]
    df['system']=df['cls'].map(lambda c:c.get('primary_system') or 'Other')
    df['action']=df['cls'].map(lambda c:c.get('primary_action') or '')
    df['diagnose_only']=df['action'].eq('Diagnose/investigate only')
    for ch in CHAR:
        df[ch]=df['cls'].map(lambda c: ch in (c.get('characteristics') or []))
    return df

# ---- reactive engine ----
qapp=set(qts.drop_duplicates('Jobnumber').query('Status.str.strip()=="Approved"',engine='python')['Jobnumber'])
lump=inv.drop_duplicates('Jobnumber').set_index('Jobnumber')['Inv Description'].str.strip()
jobs['lump']=jobs['Jobnumber'].map(lump).fillna('')
react=jobs[~(jobs['Jobnumber'].isin(qapp)|jobs['lump'].str.lower().str.contains('quoted works'))]
react=react[react['total']>0]
react=attach(react,cj)
react['val']=react['base_total']
for raw,disp in ADDON_DISP.items():
    s=set(inv[inv['Inv Item Description'].str.strip()==raw]['Jobnumber']); react['ad__'+disp]=react['Jobnumber'].isin(s)

FLAGS_R=CHAR+['diagnose_only']
def build_engine(df, flags, weighted=True):
    out=[]
    for cat,g in df.groupby('system'):
        g=g[g['val']>0]
        if len(g)<8: continue
        w=g['w'] if weighted else pd.Series(1.0,index=g.index)
        med=wquantile(g['val'],w,.5)
        blk={'category':cat,'n':int(len(g)),'median':round(med),'confidence':conf(len(g)),
             'base':round(med),'band_lo':round(wquantile(g['val'],w,.25)/med,3),'band_hi':round(wquantile(g['val'],w,.75)/med,3),
             'conditions':[],'default_addons':[],'common_addons':[]}
        cand=[f for f in flags if g[f].sum()>=15 and (~g[f]).sum()>=15]
        if len(g)>=50 and cand:
            beta,t,_=ols_log(g,cand,w)
            keep=[]
            for i,f in enumerate(cand,1):
                pct=np.exp(beta[i])-1
                if abs(t[i])>=1.6 and abs(pct)>=0.12: keep.append((f,abs(pct)))
            keep=[f for f,_ in sorted(keep,key=lambda x:-x[1])[:6]]
            if keep:
                b2,_,r2=ols_log(g,keep,w)
                blk['base']=round(float(np.exp(b2[0])))
                blk['band_lo']=round(float(np.exp(np.quantile(r2,.25))),3); blk['band_hi']=round(float(np.exp(np.quantile(r2,.75))),3)
                blk['conditions']=[{'key':f,'label':CHAR_LABEL.get(f,f),'factor':round(float(np.exp(b2[j])),3),'pct':round((np.exp(b2[j])-1)*100)} for j,f in enumerate(keep,1)]
        if 'ad__'+list(ADDON_DISP.values())[0] in g.columns:
            blk['default_addons']=[d for d in ADDON_DISP.values() if g['ad__'+d].mean()>=0.5]
        out.append(blk)
    return sorted(out,key=lambda r:-r['n'])

reactive_out=build_engine(react,FLAGS_R)

# ---- quoted engine ----
q=qts.drop_duplicates('Jobnumber').copy(); q['total']=num(q['Total Ex']); q['status']=q['Status'].str.strip()
q['date']=pd.to_datetime(q['Created Date'].str.strip(),errors='coerce',dayfirst=True)
q['w']=0.5**(((TODAY-q['date']).dt.days.clip(lower=0))/HALFLIFE_DAYS)
qa=attach(q[(q['status']=='Approved')&(q['total']>0)],cq)
qa['val']=qa['total']; qa['diagnose_only']=False
FLAGS_Q=CHAR
quoted_out=build_engine(qa,FLAGS_Q)

# ---- relining metre model from classified quantity ----
reline_model=None
relrows=[]
for jn,c in cq.items():
    if (c.get('primary_action')=='Reline') or (c.get('primary_system')=='Drainage/sewer' and 'reline' in (c.get('key_driver','').lower())):
        m=(c.get('quantity') or {}).get('metres')
        relrows.append((jn,m))
relm=pd.DataFrame(relrows,columns=['Jobnumber','m']).dropna()
if len(relm)>=10:
    relm=relm.merge(q[['Jobnumber','total']],on='Jobnumber')
    relm=relm[(relm['m']>0)&(relm['total']>0)]
    if len(relm)>=10:
        b,a=np.polyfit(relm['m'],relm['total'],1); pred=a+b*relm['m']
        r2=1-((relm['total']-pred)**2).sum()/((relm['total']-relm['total'].mean())**2).sum()
        reline_model={'setup':round(float(a)),'per_metre':round(float(b)),'n':int(len(relm)),'r2':round(float(r2),2)}

# ---- add-on reference rates ----
addons=[]
for raw,disp in ADDON_DISP.items():
    s=inv[inv['Inv Item Description'].str.strip()==raw]['unit'].dropna()
    if len(s): addons.append({'name':disp,'typical':round(float(s.median())),'n':int(s.size)})

# ---- win/loss (pending = not won), independent of classification ----
winloss=[]
qall=q.copy()
qall['sys']=qall['Jobnumber'].map(lambda jn:(cq.get(jn) or {}).get('primary_system') or 'Unclassified')
for cat,s in qall.groupby('sys'):
    ap=int((s['status']=='Approved').sum()); rj=int((s['status']=='Rejected').sum())
    pe=int(s['status'].isin(['Pending Approval','In Progress']).sum()); tot=ap+rj+pe
    winloss.append({'category':cat,'approved':ap,'rejected':rj,'pending':pe,'win_rate':round(ap/tot*100,1) if tot else None})
winloss.sort(key=lambda r:-(r['approved']+r['rejected']+r['pending']))
overall_win=round((q['status']=='Approved').sum()/len(q)*100,1)

result={'window':'Jan 2023 to Jun 2026 (recency weighted, half life %d days)'%HALFLIFE_DAYS,
 'classified_counts':{'jobs':len(cj),'quotes':len(cq)},
 'reactive':reactive_out,'quoted':quoted_out,'reline_model':reline_model,'addons':addons,
 'winloss':winloss,'status_counts':{k:int(v) for k,v in q['status'].value_counts().items() if k.strip()},
 'overall_winrate':overall_win,
 'note':'Built from comprehension classification. Job type = primary_system. diagnose_only is the downward lever. Base figures recency weighted.'}
json.dump(result,open(OUT,'w'),indent=2)
print('Wrote',OUT)
print('reactive systems:',[ (c['category'],c['base'],len(c['conditions'])) for c in reactive_out])
print('quoted systems:',[ (c['category'],c['base']) for c in quoted_out])
print('reline:',reline_model,'| overall win (pending=lost):',overall_win)
