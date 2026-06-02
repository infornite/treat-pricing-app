#!/usr/bin/env python3
"""
Production comprehension classifier with checkpointing.

  python3 classify_run.py jobs   claude-haiku-4-5-20251001  class_jobs.json   [LIMIT]
  python3 classify_run.py quotes claude-sonnet-4-6          class_quotes.json [LIMIT]

Reads each narrative, returns structured fields, writes a checkpoint keyed by
job number after every batch so a stopped run resumes where it left off.
"""
import sys, os, re, json, time
import pandas as pd, numpy as np
from anthropic import Anthropic

SRC   = sys.argv[1]                       # 'jobs' or 'quotes'
MODEL = sys.argv[2]
OUT   = sys.argv[3]
LIMIT = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9
BATCH = 15
PRICE = {"claude-haiku-4-5-20251001": (1.0, 5.0), "claude-sonnet-4-6": (3.0, 15.0)}
client = Anthropic(api_key=open("/home/claude/.ak").read().strip())

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
def title(t):
    p=re.split(r'\s-\s',t); return (p[-1] if len(p)>1 else t).strip()

# ---- assemble the records to classify ----
inv=pd.read_csv('invoices_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 19'])
inv['Jobnumber']=inv['Jobnumber'].str.strip()
if SRC=='jobs':
    jobs=pd.read_csv('jobs_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 15'])
    qts =pd.read_csv('quotes_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 15'])
    for d in (jobs,qts): d['Jobnumber']=d['Jobnumber'].str.strip()
    jobs['wp']=jobs['Invoice Description'].map(wp); jobs['title']=jobs['Task'].map(title)
    approved=set(qts.drop_duplicates('Jobnumber').query('Status.str.strip()=="Approved"',engine='python')['Jobnumber'])
    lump=inv.drop_duplicates('Jobnumber').set_index('Jobnumber')['Inv Description'].str.strip()
    jobs['lump']=jobs['Jobnumber'].map(lump).fillna('')
    df=jobs[~(jobs['Jobnumber'].isin(approved)|jobs['lump'].str.lower().str.contains('quoted works'))].copy()
    df=df[df['wp'].str.len()>40]
    df['text']=df['wp']; df['ttl']=df['title']
    KIND='completed job, work-performed narrative'
else:
    qts=pd.read_csv('quotes_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 15'])
    qts['Jobnumber']=qts['Jobnumber'].str.strip()
    df=qts.drop_duplicates('Jobnumber').copy()
    df['text']=df['Task Description'].map(wp); df['ttl']=df['Quote'].map(strip_html).str[:60]
    df=df[df['text'].str.len()>40]
    KIND='quoted works, proposed scope'

df=df[['Jobnumber','text','ttl']].reset_index(drop=True)

SYS=("You classify plumbing records for a Sydney strata-maintenance plumber. Each record is a "+KIND+". "
 "Classify by the SUBSTANCE of the work, not by every term mentioned. For completed jobs, if they only attended, "
 "inspected or diagnosed and left the fix as later works, action is 'Diagnose/investigate only'. "
 "Return STRICT JSON: an array, one object per record, same order and id. Each object: "
 '{"id":int,'
 '"primary_system":one of ["Drainage/sewer","Stormwater","Water supply/pipe","Hot water","Fixture/tapware","Backflow/TMV","Gas","Roof/waterproofing","Other"],'
 '"primary_action":one of ["Diagnose/investigate only","Repair","Replace/install","Clear blockage","Test/compliance","Make safe/temporary","Reline","Excavate/replace pipe","Remedial/building works","Preventative maintenance"],'
 '"characteristics":subset of ["after_hours","return_visit_or_staged","building_shutdown","multi_unit","excavation","difficult_access","specialist_equipment","tree_roots","multiple_items","concealed_or_in_slab","common_property","no_fault_found","reinstatement","structural_building_works","large_scope"],'
 '"quantity":{"metres":number-or-null,"units":number-or-null,"fixtures":number-or-null},'
 '"key_driver":short phrase for the main thing pushing price up or down,'
 '"confidence":"high"|"medium"|"low"}. '
 "reinstatement means tiling/rendering/painting/waterproofing/make-good. large_scope means an extensive multi-stage job. "
 "Fill quantity only when a number is clearly stated, else null. No prose, no markdown fences.")

# ---- checkpoint load ----
done={}
if os.path.exists(OUT):
    try: done=json.load(open(OUT))
    except: done={}
todo=df[~df['Jobnumber'].isin(done.keys())]
todo=todo.head(LIMIT)
print('source=%s model=%s | total=%d already=%d todo=%d'%(SRC,MODEL,len(df),len(done),len(todo)))

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
LOCK=threading.Lock()
WORKERS=6

def call(batch):
    recs=[{"id":i,"title":r.ttl[:60],"text":r.text[:1400]} for i,r in enumerate(batch.itertuples())]
    last=None
    for attempt in range(3):
        try:
            m=client.messages.create(model=MODEL,max_tokens=5000,system=SYS,
                messages=[{"role":"user","content":json.dumps(recs)}])
            txt="".join(b.text for b in m.content if b.type=="text").strip()
            txt=re.sub(r'^```(json)?|```$','',txt,flags=re.M).strip()
            return json.loads(txt), m.usage.input_tokens, m.usage.output_tokens
        except Exception as e:
            last=e; time.sleep(2*(attempt+1))
    raise last

batches=[todo.iloc[s:s+BATCH] for s in range(0,len(todo),BATCH)]
tin=tout=0; t0=time.time(); ndone=0

def work(b):
    arr,i,o=call(b)
    out={}
    for k,rec in enumerate(arr):
        idx=int(rec.get('id',k))
        jn=b.iloc[idx]['Jobnumber'] if idx<len(b) else b.iloc[k]['Jobnumber']
        rec.pop('id',None); out[jn]=rec
    return out,i,o

with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs={ex.submit(work,b):bi for bi,b in enumerate(batches)}
    for n,f in enumerate(as_completed(futs)):
        try:
            out,i,o=f.result()
            with LOCK:
                tin+=i; tout+=o; done.update(out); ndone+=len(out)
                tmp=OUT+'.tmp'; json.dump(done,open(tmp,'w')); os.replace(tmp,OUT)
        except Exception as e:
            print('  batch error: %s'%str(e)[:160])
        if n % 10==0:
            print('  ...%d/%d batches, %d records, %.0fs'%(n+1,len(batches),ndone,time.time()-t0))

pin,pout=PRICE.get(MODEL,(1.0,5.0))
print('RUN DONE %s | classified now=%d total=%d | tok in=%d out=%d | this-run cost $%.3f | %.0fs'%(
    SRC,ndone,len(done),tin,tout,tin/1e6*pin+tout/1e6*pout,time.time()-t0))
