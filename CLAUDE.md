# Treat Plumbing pricing tool, project brief

This file is the standing context for the project. It carries what is TRUE about the business and the data, and the decisions made so far. It does not tell you to reuse any particular code. The `reference/` folder is a prior attempt to learn from or discard, not a foundation to inherit. Build the working pipeline fresh in `src/` and check it against `reference/` where useful.

## Goal

Build a job pricing tool for Treat Plumbing, a Sydney eastern suburbs strata maintenance plumber. The owner prices almost every job himself and is the bottleneck. The tool should let other staff price a job the way the business actually prices, learned from invoiced history, so it must replicate the pricing, not run a textbook cost calculation.

## Ground truth about the data (verified, carry these forward)

These were checked against the data and several corrected an earlier brief. They are findings, not opinions.

* Price is a single judged number. On most invoices the price is one manually typed "Labour and Materials" line, not hours times a rate. The realised rate runs around 400 dollars an hour against a nominal 90, so the skill is value pricing. Predict the invoiced total, do not compute hours times rate.
* No margin data. Material cost is blank or zero on about 82 percent of jobs and the labour cost field mirrors the sell price, so there is no cost base. The tool prices a job, it cannot show margin. This is how the business records data, not a gap to fix.
* Two populations, not additive. Reactive work (about 70 percent) is attend and fix, priced after the fact. Quoted works (about 30 percent) are scoped and approved up front and priced on scope and quantity.
* Quotes and jobs are one record type on a shared number sequence. A won quote keeps its number and reappears as a completed job, so about 26 percent of jobs also appear in the quotes file as Approved. Quote to job conversion is therefore observable on the job number, no API needed for the won side.
* Win and loss. Quote statuses are maintained (Approved, Rejected, Pending Approval, In Progress). Count pending as not won, which puts realistic conversion near 49 percent. Only about 156 quotes are marked rejected while around 1,900 sit pending, so pending hides genuine losses, treat the win rate as a ceiling.
* Prices have risen. Reactive medians are up about 15 percent from 2023 to the last year, more for some types (burst and jetting over 20 percent), flat for others (tap and fixture). Weight recent data more.
* Diagnosis is not repair. About 30 percent of reactive jobs only attend and diagnose, leaving the fix as later works, and they are genuinely cheaper. Reading the narrative separates these from real repairs, keyword matching cannot, and this is the single biggest classification gain.

## Standard add on rates (fixed line items, charged on top)

Emergency after hours callout 380, jet blaster 300, drain camera survey 250, electric eel about 180 to 200, pipe location or leak detection around 550. These already sit inside the invoiced total, so if the model strips them out to form a base, they are added back as a separate layer, never double counted.

## Current model design (direction, not locked)

Three layers, which the owner signed off:
1. Base works rate by job type, the typical core works amount with the named add on line items stripped out.
2. Characteristics that move the base up or down (after hours, excavation, difficult access, multiple units, replacement, reinstatement, large scope, and diagnosis only as the one downward lever).
3. Standard add ons stacked on top, with the ones usual for a job type pre selected.

Quoted works get characteristics too, weighted toward scope (reinstatement, large scope, quantity such as metres or units). Relining has its own length based estimate, roughly a fixed set up plus a per metre rate. Base figures should be recency weighted.

## The classifier (the part to rebuild well)

The weak point in the prior attempt was a keyword classifier that picked the first matching word, when about 93 percent of narratives match several job types. The better approach, started but not finished, is a comprehension pass: a model reads each narrative and returns structured fields, the primary system, what was actually done (diagnose, repair, replace, clear, test), and a list of characteristics. Classify by what the job WAS and what was DONE, not by every term mentioned.

Expensive asset to keep: `data/classified/class_jobs.json` and `class_quotes.json` hold 1,845 jobs and 45 quotes already classified this way. Regenerating them costs API money and time, so keep them and only classify the remainder. The schema and the run script are in `reference/`.

Highest value validation step: have the owner check a sample of the structured classification and correct it, since everything rests on the buckets being right.

## Data files

In `data/raw/`:
* `jobs_jan23_to_jun26.csv`, completed jobs, one row each. Price is `Task Invoices Total Ex`. Work narrative is `Invoice Description`. Short job descriptor is in the `Task` title after the last " - ".
* `invoices_jan23_to_jun26.csv`, invoice line items. Joins to jobs on `Jobnumber` at about 99.6 percent. Named add on rates live in `Inv Item Description` and `Inv Line Unit Sell`.
* `quotes_jan23_to_jun26.csv`, quotes, several rows per quote with the total repeated. Scope text is `Task Description`, status is `Status`.

Join key is `Jobnumber`. Window is January 2023 to June 2026.

## Working preferences

* British English spelling throughout.
* Never use dashes of any kind, no em dashes or en dashes. Use commas, full stops, or separate sentences.
* Write in properly structured paragraphs, distinct ideas as separate sentences, related sentences grouped.
* Default to Markdown, not Word documents, unless asked.

## Environment and commands (macOS)

The classification calls the Anthropic API and bills against an API key, separate from the Claude plan. Set the key as an environment variable in the shell, never paste it into a chat, and put a low spend cap on it in the Console first.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install anthropic pandas numpy
export ANTHROPIC_API_KEY=sk-ant-...   # your own key, kept local
```

API model strings: `claude-haiku-4-5-20251001` for the cheaper classification pass, `claude-sonnet-4-6` for the richer read on quotes.

## How to work in this project

Use normal desktop chat for design and decisions. Use Claude Code for running scripts, editing files, and previewing the tool (the app previews HTML). When rebuilding, prefer to re derive the logic in `src/` so it is understood and owned, treating `reference/` as one prior voice to check against rather than the answer.
