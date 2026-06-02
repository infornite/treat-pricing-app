#!/usr/bin/env python3
"""Comprehension-based classifier pilot. Reads job narratives, asks a Claude
model to read each and return structured fields, reports usage and cost, and
compares against the old keyword label. Usage: python3 classify_pilot.py N MODEL"""
import sys, os, re, json, time
import pandas as pd, numpy as np
from anthropic import Anthropic

N     = int(sys.argv[1]) if len(sys.argv) > 1 else 10
MODEL = sys.argv[2] if len(sys.argv) > 2 else "claude-haiku-4-5-20251001"
OUT   = sys.argv[3] if len(sys.argv) > 3 else "pilot.json"
BATCH = 10
PRICE = {"claude-haiku-4-5-20251001": (1.0, 5.0), "claude-sonnet-4-6": (3.0, 15.0)}

client = Anthropic(api_key=open("/home/claude/.ak").read().strip())

# ---- load + prep (same prep as the model build) ----
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
def has(t,*kw): return any(k in t for k in kw)
def keyword_label(text):
    t=text.lower()
    if has(t,'electric eel',' eel'): return 'Drain clear (electric eel)'
    if has(t,'jet blaster','jet rod','hydro jet','jetter'): return 'Drain clear (jet/hydro)'
    if has(t,'backflow','rpzd'): return 'Backflow / TMV'
    if has(t,'hot water','hwu','tmv','tempering'): return 'Hot water / TMV'
    if has(t,'burst'): return 'Burst pipe repair'
    if has(t,'tap','mixer','cistern','toilet','basin','fixture'): return 'Tap / fixture repair'
    if has(t,'block','choked','overflow','backing up','cleared'): return 'Blockage clear (general)'
    if has(t,'leak'): return 'Leak (investigation/repair)'
    if has(t,'investigate','attend','inspect'): return 'Investigation / attendance'
    return 'Other reactive'

jobs=pd.read_csv('jobs_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 15'])
inv =pd.read_csv('invoices_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 19'])
qts =pd.read_csv('quotes_jan23_to_jun26.csv',dtype=str,keep_default_na=False).drop(columns=['Unnamed: 15'])
for d in (jobs,inv,qts): d['Jobnumber']=d['Jobnumber'].str.strip()
jobs['wp']=jobs['Invoice Description'].map(wp); jobs['title']=jobs['Task'].map(title)
jobs['total']=num(jobs['Task Invoices Total Ex'])
q=qts.drop_duplicates('Jobnumber'); approved=set(q[q['Status'].str.strip()=='Approved']['Jobnumber'])
lump=inv.drop_duplicates('Jobnumber').set_index('Jobnumber')['Inv Description'].str.strip()
jobs['lump']=jobs['Jobnumber'].map(lump).fillna('')
react=jobs[~(jobs['Jobnumber'].isin(approved)|jobs['lump'].str.lower().str.contains('quoted works'))].copy()
react=react[(react['total']>0)&(react['wp'].str.len()>80)]
react['kw']=react['wp'].map(keyword_label)
np.random.seed(11)
samp=react.sample(min(N,len(react))).reset_index(drop=True)

SYS=("You classify plumbing job records for a Sydney strata-maintenance plumber. "
 "For each record you get a short title and the work-performed narrative. Classify by what was ACTUALLY DONE in the narrative, "
 "not by every term mentioned. If they only attended, inspected or diagnosed and recommended future works, the action is 'Diagnose/investigate only'. "
 "Return STRICT JSON only: an array, one object per record, same order and id. Each object: "
 '{"id":int,'
 '"primary_system":one of ["Drainage/sewer","Stormwater","Water supply/pipe","Hot water","Fixture/tapware","Backflow/TMV","Gas","Roof/waterproofing","Other"],'
 '"primary_action":one of ["Diagnose/investigate only","Repair","Replace/install","Clear blockage","Test/compliance","Make safe/temporary"],'
 '"characteristics":subset of ["after_hours","return_visit","building_shutdown","multi_unit","excavation","difficult_access","specialist_equipment","tree_roots","multiple_items","concealed_pipe","common_property","no_fault_found"],'
 '"key_driver":short phrase for the main thing pushing price up or down,'
 '"confidence":"high"|"medium"|"low"}. No prose, no markdown fences.')

def call(batch):
    recs=[{"id":int(r.id),"title":r.title[:60],"narrative":r.wp[:1400]} for r in batch.itertuples()]
    msg=client.messages.create(model=MODEL,max_tokens=2200,system=SYS,
        messages=[{"role":"user","content":json.dumps(recs)}])
    txt="".join(b.text for b in msg.content if b.type=="text").strip()
    txt=re.sub(r'^```(json)?|```$','',txt.strip(),flags=re.M).strip()
    return json.loads(txt), msg.usage.input_tokens, msg.usage.output_tokens

results={}; tin=tout=0
samp['id']=samp.index
for s in range(0,len(samp),BATCH):
    b=samp.iloc[s:s+BATCH]
    try:
        arr,i,o=call(b); tin+=i; tout+=o
        for rec in arr: results[int(rec['id'])]=rec
    except Exception as e:
        print('batch %d error: %s'%(s,str(e)[:200]))
    time.sleep(0.3)

pin,pout=PRICE.get(MODEL,(1.0,5.0))
cost=tin/1e6*pin+tout/1e6*pout
rows=[]
for _,r in samp.iterrows():
    res=results.get(int(r['id']),{})
    rows.append({'jobnumber':r['Jobnumber'],'title':r['title'],'total':float(r['total']),
                 'keyword_label':r['kw'],'llm_system':res.get('primary_system'),
                 'llm_action':res.get('primary_action'),'characteristics':res.get('characteristics',[]),
                 'key_driver':res.get('key_driver'),'confidence':res.get('confidence')})
json.dump({'model':MODEL,'n':len(rows),'input_tokens':tin,'output_tokens':tout,'cost_usd':round(cost,3),'rows':rows},
          open(OUT,'w'),indent=2)
print('MODEL %s | n=%d | in=%d out=%d tok | cost $%.3f'%(MODEL,len(rows),tin,tout,cost))
print('full-run projection for ~11000 records: $%.2f'%(cost/max(len(rows),1)*11000))
