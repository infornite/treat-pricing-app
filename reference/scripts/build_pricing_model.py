#!/usr/bin/env python3
"""
Treat Plumbing pricing model, full reproducible build.
=====================================================

Takes the three AroFlo CSV exports and rebuilds the entire pricing model
(reactive engine, quoted engine, per-type conditions, relining fit,
standard rate reference, quote conversion) into a single JSON file that
the HTML tool embeds.

USAGE
-----
    python3 build_pricing_model.py [INPUT_DIR] [OUTPUT_JSON]

Defaults: INPUT_DIR = current directory, OUTPUT_JSON = pricing_model.json

INPUT FILES EXPECTED in INPUT_DIR (names can be edited in CONFIG below):
    jobs_jan23_to_jun26.csv      completed jobs   (one row per job)
    invoices_jan23_to_jun26.csv  invoice lines    (one row per line item)
    quotes_jan23_to_jun26.csv    quotes           (multiple rows per quote)

Only numpy and pandas are required (no statsmodels).

METHOD, in brief (full notes in README.md):
  * Price is the invoiced total ("Task Invoices Total Ex"), treated as the
    value of the job. We do NOT compute hours x rate.
  * Reactive vs quoted are separated using an approved-quote fingerprint on
    the job number plus the "Quoted Works" invoice label.
  * Job types are keyword-classified from the work-performed narrative
    ("Invoice Description" for jobs, "Task Description" for quotes), after
    stripping HTML and cutting at the recommendation boundary so only work
    performed is classified.
  * Per reactive type, price drivers (conditions) are selected by a
    log-linear OLS fit and kept only when well supported and material.
  * Quote conversion counts pending as NOT won.
"""
import sys, re, json
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
IN_DIR  = sys.argv[1] if len(sys.argv) > 1 else "."
OUT     = sys.argv[2] if len(sys.argv) > 2 else "pricing_model.json"
F_JOBS  = "jobs_jan23_to_jun26.csv"
F_INV   = "invoices_jan23_to_jun26.csv"
F_QTS   = "quotes_jan23_to_jun26.csv"
WINDOW  = "Jan 2023 to Jun 2026"

CONF_HIGH, CONF_MED = 40, 15          # sample-size thresholds for the flag
COND_MIN_CAT_N      = 60              # need this many jobs to fit conditions
COND_MIN_GROUP_N    = 20             # each side of a flag must have this many
COND_MIN_T          = 1.6           # |t-stat| to keep a driver
COND_MIN_EFFECT     = 0.12          # |effect| (12%) to keep a driver
COND_MAX_SHOWN      = 4             # cap conditions shown per type

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")

def strip_html(t):
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    return re.sub(r"\s+", " ", t).strip()

BOUNDARY = ["further works", "further urgent works", "further recommended", "we recommend",
            "we advise", "we would recommend", "we will submit", "recommended works",
            "recommend the following", "will submit a quotation"]
def work_performed(t):
    """Strip HTML, then cut at the first recommendation-boundary phrase so we
    only classify the WORK PERFORMED, not recommended future works."""
    t = strip_html(t); low = t.lower(); cut = len(t)
    for b in BOUNDARY:
        i = low.find(b)
        if i != -1 and i < cut: cut = i
    return t[:cut].strip()

def has(t, *kw): return any(k in t for k in kw)

def classify_reactive(text):
    t = text.lower()
    if has(t, "electric eel", " eel"): return "Drain clear (electric eel)"
    if has(t, "jet blaster", "jet rod", "hydro jet", "jetter", "water jet"): return "Drain clear (jet/hydro)"
    if has(t, "backflow", "rpzd", "reduced pressure zone"): return "Backflow / TMV"
    if has(t, "hot water", "hwu", "h/w unit", "tempering", "tmv", "storage tank", "continuous flow"): return "Hot water / TMV"
    if has(t, "burst"): return "Burst pipe repair"
    if has(t, "tap", "mixer", "cistern", "toilet", "wc ", "basin", "flexi", "washer", "fixture", "shower head"): return "Tap / fixture repair"
    if has(t, "block", "choked", "overflow", "backing up", "clear the", "cleared"): return "Blockage clear (general)"
    if has(t, "leak"):
        if has(t, "no leak", "no water damage", "pressure test", "dye test", "investigate", "moisture", "flood dye", "no fault"): return "Leak investigation"
        return "Leak repair"
    if has(t, "investigate", "attend", "inspect", "assess"): return "Investigation / attendance"
    return "Other reactive"

def classify_quoted(text):
    t = text.lower()
    if has(t, "reline", "relining", "cipp", "cured in place", "pipe liner"): return "Pipe relining"
    if has(t, "excavat", "re-run", "rerun", "dig ", "replace the", "replace burst", "new pipe", "pipe replacement", "chase "): return "Excavation / pipe replacement"
    if has(t, "stormwater", "storm water", "pit", "ag line", "agline", "sub soil", "drainage system"): return "Stormwater works"
    if has(t, "pump"): return "Pump works"
    if has(t, "backflow", "rpzd", "tmv", "tempering"): return "Backflow / TMV"
    if has(t, "hot water", "hwu", "storage tank", "continuous flow"): return "Hot water"
    if has(t, "preventative", "maintenance", "clear out", "clear-out", "annual", "scheduled", "planned maintenance", "clean out"): return "Preventative maintenance / clear-out"
    if has(t, "tile", "render", "paint", "plaster", "waterproof", "repair wall", "gyprock", "ceiling repair", "make good", "building work", "remedial"): return "Remedial / building works"
    if has(t, "tap", "mixer", "cistern", "toilet", "basin", "fixture"): return "Tap / fixture"
    return "Other quoted"

def conf(n): return "high" if n >= CONF_HIGH else ("medium" if n >= CONF_MED else "low")

def ols_log(df, flags):
    """Log-linear OLS. Returns beta, t-stats, residuals."""
    y = np.log(df["total"].values)
    X = np.column_stack([np.ones(len(df))] + [df[f].astype(float).values for f in flags])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    sigma2 = (resid @ resid) / (n - k)
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
    return beta, beta / se, resid

# condition (driver) library: flag name -> detector(jobnumber, lowercased_text)
def multi_unit(t):
    nums = set(re.findall(r"unit\s*(\d+)", t))
    return len(nums) >= 2 or "multiple units" in t or "several units" in t

# CONDITION flags are job-nature characteristics that scale the core works
# price. They deliberately EXCLUDE things that are charged as named add-on
# line items (jet, camera, eel, leak detection), because those are added
# separately on top. After hours stays a condition because it carries a real
# works premium beyond the fixed $380 callout, and that callout is a separate
# add-on, so there is no double count once the add-on lines are stripped.
def make_flags(after_hours_set):
    return {
        "after_hours": lambda jn, t: (jn in after_hours_set) or has(t, "after hours", "after-hours", "out of hours"),
        "excavation":  lambda jn, t: has(t, "excavat", "jackhammer", "concrete", "dig ", "chase ", "cut out the", "core hole", "core drill"),
        "replace":     lambda jn, t: has(t, "replace", "renew", "supply and install", "install new", "installed a new", "new unit"),
        "multi_unit":  lambda jn, t: multi_unit(t),
        "access":      lambda jn, t: has(t, "roof", "riser", "ceiling cavity", "manhole", "confined space", "scaffold", "height safety", "crane", "harness", "elevated work"),
        "roots":       lambda jn, t: has(t, "tree root", "roots"),
    }
COND_LABELS = {
    "after_hours": ("After hours / emergency", "Out of hours attendance. This is the works premium only. The fixed callout fee is a separate add on."),
    "excavation":  ("Excavation or breaking concrete", "Digging, jackhammering, cutting out, chasing walls or core drilling."),
    "replace":     ("Replacing or installing a unit", "Supplying and fitting new gear rather than repairing what is there."),
    "multi_unit":  ("Multiple units affected", "Work spanning two or more units or tenancies."),
    "access":      ("Difficult access", "Roof, riser, ceiling cavity, confined space or height work."),
    "roots":       ("Tree roots", "Root intrusion in the line."),
}

# ----------------------------------------------------------------------
# load
# ----------------------------------------------------------------------
def load(name):
    df = pd.read_csv(f"{IN_DIR}/{name}", dtype=str, keep_default_na=False)
    df = df[[c for c in df.columns if not c.startswith("Unnamed")]]
    df["Jobnumber"] = df["Jobnumber"].str.strip()
    return df

jobs = load(F_JOBS)
inv  = load(F_INV)
qts  = load(F_QTS)

# ----------------------------------------------------------------------
# derive
# ----------------------------------------------------------------------
jobs["wp"]    = jobs["Invoice Description"].map(work_performed)
jobs["low"]   = jobs["wp"].str.lower()
jobs["total"] = num(jobs["Task Invoices Total Ex"])

# Named add-on line items, charged on top of the core works. We strip their
# value off each job so the BASE is the core works price only. The add-ons are
# then offered separately in the tool (the layer Peter adds by hand).
ADDON_NAMES = ["Emergency After Hours Callout", "Jet Blaster", "Drain Camera Survey",
               "Electric Eel", "Pipe Location Leak Detection"]
inv["unit"] = num(inv["Inv Line Unit Sell"])
inv["qty"]  = num(inv["Inv Quantity"]).fillna(1)
inv["line_amt"] = inv["unit"] * inv["qty"]
addon_per_job = inv[inv["Inv Item Description"].str.strip().isin(ADDON_NAMES)].groupby("Jobnumber")["line_amt"].sum()
jobs["addon_amt"] = jobs["Jobnumber"].map(addon_per_job).fillna(0)
jobs["base_total"] = (jobs["total"] - jobs["addon_amt"]).clip(lower=0)

after_hours_set = set(inv[inv["Inv Item Description"].str.strip() == "Emergency After Hours Callout"]["Jobnumber"])
FLAGS = make_flags(after_hours_set)

q = qts.drop_duplicates("Jobnumber").copy()
q["total"]  = num(q["Total Ex"])
q["status"] = q["Status"].str.strip()
q["wp"]     = q["Task Description"].map(work_performed)
approved_set = set(q.loc[q["status"] == "Approved", "Jobnumber"])

lump = inv.drop_duplicates("Jobnumber").set_index("Jobnumber")["Inv Description"].str.strip()
jobs["lump"]      = jobs["Jobnumber"].map(lump).fillna("")
jobs["quoted_fp"] = jobs["Jobnumber"].isin(approved_set) | jobs["lump"].str.lower().str.contains("quoted works")

react = jobs[~jobs["quoted_fp"] & (jobs["total"] > 0)].copy()
react["total"] = react["base_total"]            # price the CORE works; add-ons are separate
react = react[react["total"] > 0]
react["cat"] = react["wp"].map(classify_reactive)

# which named add-ons each job actually carried (for per-type defaults)
ADDON_DISPLAY = {"Emergency After Hours Callout": "Emergency after-hours callout",
                 "Jet Blaster": "Jet blaster", "Drain Camera Survey": "Drain camera survey (CCTV)",
                 "Electric Eel": "Electric eel", "Pipe Location Leak Detection": "Pipe location / leak detection"}
for raw, disp in ADDON_DISPLAY.items():
    s = set(inv[inv["Inv Item Description"].str.strip() == raw]["Jobnumber"])
    react["ad__" + disp] = react["Jobnumber"].isin(s)
for f, fn in FLAGS.items():
    react[f] = [fn(jn, t) for jn, t in zip(react["Jobnumber"], react["low"])]

qa = q[(q["status"] == "Approved") & (q["total"] > 0)].copy()
qa["cat"] = qa["wp"].map(classify_quoted)

# ----------------------------------------------------------------------
# reactive engine + per-type conditions
# ----------------------------------------------------------------------
reactive_out = []
for cat, g in react.groupby("cat"):
    med = float(g["total"].median())
    block = {"category": cat, "n": int(len(g)), "median": round(med), "confidence": conf(len(g)),
             "base": round(med), "band_lo": round(g["total"].quantile(.25) / med, 3),
             "band_hi": round(g["total"].quantile(.75) / med, 3), "conditions": []}
    if len(g) >= COND_MIN_CAT_N:
        cand = [f for f in FLAGS if g[f].sum() >= COND_MIN_GROUP_N and (~g[f]).sum() >= COND_MIN_GROUP_N]
        if cand:
            beta, tstat, _ = ols_log(g, cand)
            keep = []
            for i, f in enumerate(cand, start=1):
                pct = np.exp(beta[i]) - 1
                if abs(tstat[i]) >= COND_MIN_T and abs(pct) >= COND_MIN_EFFECT:
                    keep.append((f, abs(pct)))
            keep = [f for f, _ in sorted(keep, key=lambda x: -x[1])[:COND_MAX_SHOWN]]
            if keep:
                b2, _, r2 = ols_log(g, keep)
                block["base"]    = round(float(np.exp(b2[0])))
                block["band_lo"] = round(float(np.exp(np.quantile(r2, .25))), 3)
                block["band_hi"] = round(float(np.exp(np.quantile(r2, .75))), 3)
                block["conditions"] = [
                    {"key": f, "label": COND_LABELS[f][0], "help": COND_LABELS[f][1],
                     "factor": round(float(np.exp(b2[j])), 3), "pct": round((np.exp(b2[j]) - 1) * 100)}
                    for j, f in enumerate(keep, start=1)]
    reactive_out.append(block)
reactive_out.sort(key=lambda r: -r["n"])

# per-type add-on prevalence: default-tick those on >=50% of the type's jobs,
# and note as "common" those on >=20%
for block in reactive_out:
    g = react[react["cat"] == block["category"]]
    block["default_addons"] = [disp for disp in ADDON_DISPLAY.values() if g["ad__" + disp].mean() >= 0.50]
    block["common_addons"]  = [disp for disp in ADDON_DISPLAY.values() if 0.20 <= g["ad__" + disp].mean() < 0.50]

# ----------------------------------------------------------------------
# quoted engine
# ----------------------------------------------------------------------
quoted_out = []
for cat, g in qa.groupby("cat"):
    quoted_out.append({"category": cat, "n": int(len(g)), "median": round(float(g["total"].median())),
                       "p25": round(float(g["total"].quantile(.25))), "p75": round(float(g["total"].quantile(.75))),
                       "confidence": conf(len(g))})
quoted_out.sort(key=lambda r: -r["n"])

# ----------------------------------------------------------------------
# relining fit (price ~ setup + per_metre * metres)
# ----------------------------------------------------------------------
def metres(text):
    t = text.lower(); vals = []
    for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*(?:lineal\s*)?(?:lin\.?\s*)?(?:l\.?m\.?|lm|lineal met|metre|meter)", t):
        try:
            v = float(m.group(1))
            if 0.5 <= v <= 120: vals.append(v)
        except: pass
    return max(vals) if vals else np.nan
rel = qa[qa["cat"] == "Pipe relining"].copy()
rel["m"] = rel["wp"].map(metres)
f = rel.dropna(subset=["m"]); f = f[(f["total"] > 0) & (f["m"] > 0)]
slope, intercept = np.polyfit(f["m"], f["total"], 1)
pred = intercept + slope * f["m"]
r2 = 1 - ((f["total"] - pred) ** 2).sum() / ((f["total"] - f["total"].mean()) ** 2).sum()
reline_model = {"setup": round(float(intercept)), "per_metre": round(float(slope)),
                "n": int(len(f)), "r2": round(float(r2), 2)}

# ----------------------------------------------------------------------
# standard rate reference (fixed line-item rates)
# ----------------------------------------------------------------------
inv["unit"] = num(inv["Inv Line Unit Sell"])
addons = []
for name, label in [("Emergency After Hours Callout", "Emergency after-hours callout"),
                    ("Jet Blaster", "Jet blaster"), ("Drain Camera Survey", "Drain camera survey (CCTV)"),
                    ("Electric Eel", "Electric eel"), ("Pipe Location Leak Detection", "Pipe location / leak detection")]:
    s = inv[inv["Inv Item Description"].str.strip() == name]["unit"].dropna()
    if len(s):
        addons.append({"name": label, "typical": round(float(s.median())), "n": int(s.size)})

# ----------------------------------------------------------------------
# quote conversion (PENDING COUNTS AS NOT WON)
# ----------------------------------------------------------------------
qall = q.copy(); qall["cat"] = qall["wp"].map(classify_quoted)
winloss = []
for cat, s in qall.groupby("cat"):
    ap = int((s["status"] == "Approved").sum())
    rj = int((s["status"] == "Rejected").sum())
    pe = int(s["status"].isin(["Pending Approval", "In Progress"]).sum())
    tot = ap + rj + pe
    winloss.append({"category": cat, "approved": ap, "rejected": rj, "pending": pe,
                    "win_rate": round(ap / tot * 100, 1) if tot else None})
winloss.sort(key=lambda r: -(r["approved"] + r["rejected"] + r["pending"]))
overall_win = round((q["status"] == "Approved").sum() / len(q) * 100, 1)

# ----------------------------------------------------------------------
# assemble + write
# ----------------------------------------------------------------------
result = {
    "window": WINDOW,
    "counts": {"completed_jobs": int(len(jobs)),
               "reactive_jobs": int((~jobs["quoted_fp"]).sum()),
               "won_quoted_jobs": int(jobs["quoted_fp"].sum()),
               "distinct_quotes": int(len(q)),
               "approved_quotes": int(len(approved_set))},
    "split_pct": {"reactive": round((~jobs["quoted_fp"]).mean() * 100, 1),
                  "quoted":   round(jobs["quoted_fp"].mean() * 100, 1)},
    "reactive": reactive_out,
    "quoted": quoted_out,
    "reline_model": reline_model,
    "addons": addons,
    "winloss": winloss,
    "status_counts": {k: int(v) for k, v in q["status"].value_counts().items() if k.strip()},
    "overall_winrate": overall_win,
}
with open(OUT, "w") as fp:
    json.dump(result, fp, indent=2)

print(f"Wrote {OUT}")
print(f"  jobs {result['counts']['completed_jobs']}, quotes {result['counts']['distinct_quotes']}")
print(f"  split reactive {result['split_pct']['reactive']}% / quoted {result['split_pct']['quoted']}%")
print(f"  reactive types {len(reactive_out)}, quoted types {len(quoted_out)}")
print(f"  relining {reline_model}")
print(f"  overall win rate (pending=lost) {overall_win}%")
