# Treat Plumbing pricing model

A permanent record and rebuild kit for the Treat Plumbing job pricing tool. If the working conversation is lost, everything needed to understand, defend, and recreate the model is in this folder.

## What is in this folder

| File | What it is |
|---|---|
| `treat-pricing-tool.html` | The interactive tool. Open in any browser. Self contained, the data is embedded inside it. |
| `build_pricing_model.py` | The full analysis as one reproducible script. Reads the three CSV exports, writes `pricing_model.json`. |
| `pricing_model.json` | The generated model data. This is the permanent record of every figure the tool shows. |
| `README.md` | This file. |

The CSV exports themselves are not included here. Re export them from AroFlo (see below) and drop them in this folder to rerun.

## How to rebuild from scratch

1. Put the three AroFlo CSV exports in this folder with these names:
   * `jobs_jan23_to_jun26.csv`
   * `invoices_jan23_to_jun26.csv`
   * `quotes_jan23_to_jun26.csv`
2. Run the script. It needs only Python with pandas and numpy.
   ```
   python3 build_pricing_model.py
   ```
3. That writes `pricing_model.json`. To refresh the tool, replace the object assigned to `const DATA =` near the bottom of `treat-pricing-tool.html` with the contents of `pricing_model.json`.

The script prints a short summary on success and is the single source of truth for the method. The thresholds it uses (sample sizes, how a driver is kept) sit in the CONFIG block at the top.

## The three source files (AroFlo)

All three come from AroFlo reports, covering January 2023 to June 2026.

* `jobs` is completed jobs, one row each. Key fields: `Jobnumber`, `Task Invoices Total Ex` (the price), `Invoice Description` (the work performed narrative), `Address Suburb`, `Status`.
* `invoices` is invoice line items, one row per line, roughly 1.36 lines per invoice. Carries the three description fields and the named line item rates (`Inv Item Description`, `Inv Line Unit Sell`). Joins to jobs on `Jobnumber` at about 99.6%.
* `quotes` is quotes, several rows per quote (the quote total is repeated on each line). Key fields: `Total Ex`, `Task Description`, `Status` (Approved, Rejected, Pending Approval, In Progress).

## How the model works

### The core idea
The price of a job is the invoiced total, treated as the value of the work. The model does not compute hours times a rate. The realised rate across jobs with logged hours runs near 380 to 420 dollars an hour, several times the nominal charge out, because the skill is in pricing the difficulty and urgency into one number. So the tool predicts that number from history.

There is no usable cost data. Material cost is blank or zero on about 82% of jobs, and the labour cost field equals the sell price about 82% of the time, so it mirrors the price rather than recording a true cost. The tool can price a job but cannot show margin. This is how the business records data, not a gap to patch.

### Two engines
Work splits into two populations that price differently and are not additive.
* **Reactive**, about 70%. Attend and fix, priced after the fact from the invoiced total.
* **Quoted works**, about 30%. Scoped and approved up front, priced on scope and quantity.

A completed job is flagged as a won quoted work when its job number is an approved quote, or when its invoice label is "Quoted Works". Everything else is reactive. This split lands at 69.9 / 30.1.

### The three layers (reactive)
The reactive price is built in three layers.
1. **Base works rate** by job type, the typical core works amount with the named add-on line items stripped out, so the base is the works only.
2. **Characteristics** that scale the base up or down.
3. **Standard add-ons** stacked on top, the fixed line item charges.

### Base (add-ons stripped)
For each job the named add-on line amounts (callout, jet, camera, eel, leak detection) are subtracted from the invoiced total, leaving the core works price. The base for a type is the median of that. This is what makes the three layers add up without double counting: add-ons are removed here and put back as layer three.

### Classification
Job types are assigned by keyword from the work performed narrative. First the HTML is stripped, then the text is cut at the first recommendation boundary phrase (for example "further works", "we recommend") so only work performed is classified, never recommended future works. This matters: skipping the cut once polluted the relining rate with clear out jobs. Classification is first pass and meant to be refined with the team.

### Characteristics (the per type drivers)
For each reactive type, candidate characteristics are detected from the narrative: after hours, excavation, replacement, multiple units, difficult access, tree roots. These deliberately exclude things charged as add-on line items (jet, camera, eel, leak detection), which belong in layer three. A log linear regression of the stripped base on these flags is fitted per type. A driver is kept only when both groups have at least 20 jobs, the t statistic is at least 1.6, and the effect is at least 12%. Kept drivers show as percentage uplifts; the estimate is the base multiplied by the ticked factors. The band is the residual spread after conditioning. Types with no supported driver show none.

After hours is the one driver that is both a characteristic and an add-on. The works premium sits in the characteristic, the fixed callout fee sits in the add-on, and because the callout was stripped from the base they do not overlap.

### Relining
Relining is the one quoted type with a length signal, so it has a calculator: price is roughly a fixed set up plus a per metre rate, fitted on approved relining quotes that stated a length. Length explains under half the variation, so it is indicative only, shown alongside the median band.

### Standard add-ons
The named line item rates (callout, jet, camera, eel, leak detection) are added on top as layer three. For each job type the tool pre ticks the add-ons that appeared on at least half of that type's jobs (for example jet and camera on jet drain work), so totals reconstruct sensibly while staying editable.

### Quote conversion
Conversion counts pending quotes as not won, since a quote left sitting is a job not landed. Approvals are recorded reliably. Rejections are not (only 156 are marked rejected while around 1900 sit pending), so pending mixes genuine losses with stalled quotes.

## Findings worth keeping (verified against the data)

These corrected or confirmed the original project brief.

* **Quotes and completed jobs do share numbers.** About 26% of completed jobs also appear in the quotes file, almost all as Approved. The earlier belief that there was zero overlap was an artefact of a narrow date slice. This means quote to job conversion is observable directly on the job number, no API needed for the won side.
* **The nominal 90 dollar an hour rate is not visible in the totals.** Realised rate is near 400 an hour. This confirms the value pricing idea at scale rather than on one example.
* **Add on rates confirmed:** after hours callout about 380, jet 300, camera 250, eel 180 to 200, pipe location varies around 550.
* **Conversion, honestly counted, is about 49% overall**, not the 90%-plus that counting only decided quotes implies.

## Headline numbers (window Jan 2023 to Jun 2026)

* 7,026 completed jobs, 4,005 distinct quotes, 1,950 approved.
* Reactive base works rates (add-ons stripped), typical job: tap and fixture 431, hot water 543, burst pipe 649, drain clear jet 789, electric eel 672, leak investigation 492. Characteristics and add-ons stack on top.
* Quoted medians: excavation and pipe replacement 3,840, relining 6,468, remedial 1,940, stormwater 1,580.
* Relining: about 4,850 set up plus 546 per metre.

These are reproduced exactly by `build_pricing_model.py`, so the JSON is always the authority over anything written here.

## Next steps, when ready

* Have the team correct the job type classification on a sample, since everything rests on the buckets being right.
* The AroFlo API would give the unified quote to job lifecycle and a live deployed tool. It needs credentials from the owner.
